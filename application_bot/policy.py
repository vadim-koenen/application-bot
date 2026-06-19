from __future__ import annotations

import os
import json
from typing import Any

from application_bot.compliance import prohibited_requested, review_triggers
from application_bot.models import Job, PolicyResult, SubmissionDecision


def evaluate_submission_policy(
    source: str,
    *,
    flags: list[str] | set[str] | None = None,
    capabilities: list[str] | set[str] | None = None,
    live_apply_enabled: bool = False,
    recipient: str | None = None,
    adapter_allows_submission: bool = False,
    credentials_present: bool = False,
    required_questions_known: bool = False,
) -> PolicyResult:
    flags = set(flags or [])
    capabilities = set(capabilities or [])

    prohibited = prohibited_requested(capabilities)
    if prohibited:
        return PolicyResult(
            SubmissionDecision.BLOCKED,
            [f"Prohibited automation capability requested: {name}" for name in prohibited],
            True,
        )

    review = review_triggers(flags)
    if review:
        return PolicyResult(
            SubmissionDecision.REVIEW_REQUIRED,
            [f"Human review trigger present: {name}" for name in review],
            True,
        )

    if source == "linkedin_review_queue":
        return PolicyResult(
            SubmissionDecision.REVIEW_REQUIRED,
            ["LinkedIn opportunities are review-queue only; no scraping or click automation."],
            True,
        )
    if source in {"indeed_connector", "zip_connector"}:
        return PolicyResult(
            SubmissionDecision.BLOCKED,
            [f"Direct {source.replace('_connector', '')} automation is not permitted."],
            True,
        )
    if source == "email_to_apply":
        smtp_present = all(
            os.getenv(name)
            for name in (
                "SMTP_HOST",
                "SMTP_PORT",
                "SMTP_USERNAME",
                "SMTP_PASSWORD",
                "FROM_EMAIL",
            )
        )
        if live_apply_enabled and recipient and smtp_present:
            return PolicyResult(
                SubmissionDecision.AUTO_SUBMIT_EMAIL,
                ["Explicit live flag, recipient, and SMTP configuration are present."],
                False,
            )
        return PolicyResult(
            SubmissionDecision.AUTO_PACKET_ONLY,
            ["Email application remains dry-run until live flag and email config are present."],
            False,
        )
    if source in {"greenhouse", "lever", "ashby"}:
        if (
            adapter_allows_submission
            and credentials_present
            and required_questions_known
            and live_apply_enabled
        ):
            return PolicyResult(
                SubmissionDecision.AUTO_SUBMIT_ALLOWED,
                ["Adapter explicitly allows submission and all safety preconditions are met."],
                False,
            )
        return PolicyResult(
            SubmissionDecision.AUTO_PACKET_ONLY,
            ["Public ATS adapters are discovery and packet generation only by default."],
            False,
        )
    if source == "manual_json":
        return PolicyResult(
            SubmissionDecision.AUTO_PACKET_ONLY,
            ["Manually imported opportunities generate packets but are not auto-submitted."],
            False,
        )
    return PolicyResult(
        SubmissionDecision.REVIEW_REQUIRED,
        ["Unknown or ambiguous source defaults to human review."],
        True,
    )


def job_compliance_flags(job: Job) -> list[str]:
    corpus = " ".join(
        (
            job.description,
            job.requirements,
            job.responsibilities,
            job.raw_payload_json,
        )
    ).lower()
    flags: list[str] = []
    if "captcha" in corpus:
        flags.append("captcha")
    if "login required" in corpus or "create an account" in corpus:
        flags.append("login_required")
    if "legal attestation" in corpus:
        flags.append("unknown_legal_attestation")
    if "unknown required question" in corpus:
        flags.append("unknown_required_question")
    if "ambiguous consent" in corpus:
        flags.append("ambiguous_consent")
    return flags


def job_recipient(job: Job) -> str | None:
    if job.apply_url.lower().startswith("mailto:"):
        return job.apply_url.split(":", 1)[1].split("?", 1)[0].strip() or None
    try:
        raw_payload = json.loads(job.raw_payload_json or "{}")
    except json.JSONDecodeError:
        return None
    recipient = (
        raw_payload.get("recipient")
        or raw_payload.get("apply_email")
        or raw_payload.get("email")
    )
    return str(recipient).strip() if recipient else None


def evaluate_job_submission_policy(
    job: Job,
    config: dict[str, Any],
) -> PolicyResult:
    return evaluate_submission_policy(
        job.source,
        flags=job_compliance_flags(job),
        live_apply_enabled=bool(config.get("live_apply_enabled")),
        recipient=job_recipient(job),
    )
