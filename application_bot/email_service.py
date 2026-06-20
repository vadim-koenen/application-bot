from __future__ import annotations

from datetime import date
from email.message import EmailMessage
from email.policy import default
import json
import os
from pathlib import Path
from typing import Any

from application_bot.adapters.email_to_apply import EmailToApplyAdapter
from application_bot.database import Database
from application_bot.models import EmailQueueStatus, SubmissionDecision
from application_bot.packets import slugify
from application_bot.policy import (
    evaluate_job_submission_policy,
    job_compliance_flags,
    job_recipient,
)


def _subject_and_body(packet: dict[str, Any], title: str) -> tuple[str, str]:
    cover_email = str(packet.get("cover_email") or "")
    lines = cover_email.splitlines()
    subject = f"{title} — Vadim Koenen"
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0].split(":", 1)[1].strip() or subject
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines.pop(0)
    return subject, "\n".join(lines).strip()


def queue_email_applications(
    database: Database,
    config: dict[str, Any],
) -> dict[str, Any]:
    queued = 0
    existing = 0
    skipped: list[dict[str, Any]] = []
    for job in database.list_jobs(scored_only=True):
        if job.source != "email_to_apply":
            continue
        recipient = job_recipient(job)
        packet = database.latest_packet(int(job.id))
        if not recipient:
            skipped.append({"job_id": job.id, "reason": "missing_recipient"})
            continue
        if packet is None:
            skipped.append({"job_id": job.id, "reason": "missing_packet"})
            continue
        packet_payload = json.loads(packet["packet_json"] or "{}")
        if packet_payload.get("packet_status") != "PACKET_READY":
            skipped.append(
                {
                    "job_id": job.id,
                    "reason": "packet_not_ready",
                    "packet_status": packet_payload.get("packet_status"),
                }
            )
            continue
        _, created = database.queue_email(
            int(job.id),
            int(packet["id"]),
            recipient,
            job_compliance_flags(job),
        )
        queued += int(created)
        existing += int(not created)
    return {
        "queued": queued,
        "already_queued": existing,
        "skipped": skipped,
        "live_apply_enabled": bool(config.get("live_apply_enabled")),
        "live_email_send_enabled": bool(config.get("live_email_send_enabled")),
    }


def render_email_preview(
    item: Any,
    output_root: str | Path,
    from_email: str | None = None,
) -> Path:
    packet = json.loads(item.packet_json or "{}")
    subject, body = _subject_and_body(packet, item.title)
    message = EmailMessage(policy=default)
    message["From"] = from_email or "dry-run@application-bot.local"
    message["To"] = item.recipient
    message["Subject"] = subject
    message["X-Application-Bot-Mode"] = "DRY_RUN"
    message["X-Application-Bot-Job-ID"] = str(item.job_id)
    message.set_content(body)

    folder = Path(output_root) / "email_previews" / date.today().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (
        f"{slugify(item.company)}_{slugify(item.title)}_{item.id}.eml"
    )
    path.write_bytes(message.as_bytes())
    return path


def send_email_applications(
    database: Database,
    config: dict[str, Any],
    *,
    output_root: str | Path,
    live: bool = False,
    approval_phrase: str = "",
    adapter: EmailToApplyAdapter | None = None,
) -> dict[str, Any]:
    items = database.list_email_queue(
        statuses={
            str(EmailQueueStatus.QUEUED),
            str(EmailQueueStatus.PREVIEW_GENERATED),
            str(EmailQueueStatus.BLOCKED),
            str(EmailQueueStatus.ERROR),
        }
    )
    previews: list[str] = []
    sent = 0
    blocked: list[dict[str, Any]] = []

    if not live:
        for item in items:
            path = render_email_preview(
                item,
                output_root,
                from_email=os.getenv("FROM_EMAIL"),
            )
            database.mark_email_preview(item.id, str(path))
            previews.append(str(path))
        return {
            "mode": "DRY_RUN",
            "email_previews_generated": len(previews),
            "preview_paths": previews,
            "applications_submitted": 0,
            "blocked": blocked,
        }

    global_reasons: list[str] = []
    if not bool(config.get("live_apply_enabled")):
        global_reasons.append("LIVE_APPLY_ENABLED is false")
    if not bool(config.get("live_email_send_enabled")):
        global_reasons.append("LIVE_EMAIL_SEND_ENABLED is false")
    configured_phrase = str(config.get("email_send_approval_phrase") or "")
    if not configured_phrase or approval_phrase != configured_phrase:
        global_reasons.append("approval phrase is missing or does not match")

    if global_reasons:
        return {
            "mode": "LIVE_BLOCKED",
            "email_previews_generated": 0,
            "applications_submitted": 0,
            "blocked": [{"scope": "global", "reasons": global_reasons}],
        }

    sender = adapter or EmailToApplyAdapter()
    for item in items:
        job = database.get_job(item.job_id)
        flags = json.loads(item.compliance_flags_json or "[]")
        if job is None or flags:
            reason = "missing job" if job is None else f"compliance flags: {', '.join(flags)}"
            database.mark_email_blocked(item.id, reason)
            blocked.append({"queue_id": item.id, "reason": reason})
            continue
        policy = evaluate_job_submission_policy(job, config)
        if policy.decision != SubmissionDecision.AUTO_SUBMIT_EMAIL:
            reason = f"submission policy is {policy.decision}"
            database.mark_email_blocked(item.id, reason)
            blocked.append({"queue_id": item.id, "reason": reason})
            continue
        packet = json.loads(item.packet_json or "{}")
        subject, body = _subject_and_body(packet, item.title)
        result = sender.send(
            recipient=item.recipient,
            subject=subject,
            body=body,
            live_apply_enabled=True,
            live_email_send_enabled=True,
            approval_phrase=approval_phrase,
            configured_approval_phrase=configured_phrase,
        )
        if result.get("sent"):
            database.mark_email_sent(item.id)
            sent += 1
        else:
            reason = str(result.get("reason") or "email adapter declined send")
            database.mark_email_blocked(item.id, reason)
            blocked.append({"queue_id": item.id, "reason": reason})

    return {
        "mode": "LIVE",
        "email_previews_generated": 0,
        "applications_submitted": sent,
        "blocked": blocked,
    }
