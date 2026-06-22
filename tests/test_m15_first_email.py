"""M15: first email-to-apply manual-review lane.

These tests exercise the real config (claim evidence + answer bank) and the
shipped review-only seed so the finish-line behaviour is regression-protected:

* the seed reaches PACKET_READY with no claim gaps,
* a dry-run email preview is generated without any send,
* the report surfaces EMAIL_READY_MANUAL_REVIEW / EMAIL_PREVIEWS_GENERATED,
* the two user-confirmed binary answers (work authorization, sponsorship) are
  usable as answers but never leak proactively into the packet body, and
* compensation and legal-sensitive answers stay locked to manual review.
"""

from __future__ import annotations

from pathlib import Path

from application_bot.adapters.manual_json import ManualJsonAdapter
from application_bot.config import (
    load_answer_bank,
    load_claim_evidence,
    load_claim_inventory,
    load_config,
)
from application_bot.database import Database
from application_bot.email_service import (
    queue_email_applications,
    send_email_applications,
)
from application_bot.packets import (
    assess_packet,
    generate_packet,
    packet_to_dict,
)
from application_bot.policy import evaluate_job_submission_policy
from application_bot.scoring import score_job


SEED_PATH = Path("examples/email_to_apply_seed.json")


def _prepare(tmp_path: Path):
    config = load_config()
    database = Database(tmp_path / "crm.sqlite")
    database.initialize()

    jobs = ManualJsonAdapter().discover_jobs(input_path=str(SEED_PATH))
    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "email_to_apply"

    job_id, _ = database.upsert_job(job)
    database.save_score(job_id, score_job(job, config))
    saved = database.get_job(job_id)
    assert saved is not None

    inventory = load_claim_inventory(config["resume_claim_inventory"])
    evidence = load_claim_evidence(config["claim_evidence"])
    answer_bank = load_answer_bank(config["application_answer_bank"])
    policy = evaluate_job_submission_policy(saved, config)
    assessment = assess_packet(saved, config, policy, inventory, evidence)
    packet = generate_packet(
        saved,
        config,
        policy,
        inventory=inventory,
        evidence=evidence,
        answer_bank=answer_bank,
        assessment=assessment,
    )
    database.save_packet_assessment(
        job_id,
        packet_status=str(assessment.status),
        claim_gaps=assessment.claim_gaps,
        reason_codes=assessment.reason_codes,
        recommended_next_action=assessment.recommended_next_action,
        submission_policy=str(policy.decision),
    )
    database.save_packet(
        job_id,
        str(tmp_path / "packet.md"),
        packet_to_dict(packet),
    )
    return database, config, assessment, packet


def test_seed_reaches_packet_ready_without_claim_gaps(tmp_path):
    _, _, assessment, _ = _prepare(tmp_path)
    assert str(assessment.status) == "PACKET_READY"
    assert assessment.claim_gaps == []


def test_email_ready_lane_generates_preview_without_sending(tmp_path):
    database, config, _, _ = _prepare(tmp_path)
    queue_result = queue_email_applications(database, config)
    assert queue_result["queued"] == 1
    assert queue_result["live_email_send_enabled"] is False

    result = send_email_applications(
        database,
        config,
        output_root=tmp_path / "exports",
        live=False,
    )
    assert result["mode"] == "DRY_RUN"
    assert result["email_previews_generated"] == 1
    assert result["applications_submitted"] == 0
    preview = Path(result["preview_paths"][0])
    assert preview.exists()

    report = database.report()
    assert report["email_ready_manual_review"] == 1
    assert report["email_previews_generated"] == 1
    assert report["application_count"] == 0


def test_confirmed_binary_answers_present_but_not_proactively_disclosed(tmp_path):
    _, _, _, packet = _prepare(tmp_path)
    answers = packet.suggested_answers
    assert answers["Work authorization"] == "Authorized to work in the United States."
    assert answers["Sponsorship"] == "Does not require visa sponsorship."

    # Compensation and legal-sensitive answers stay locked to manual review.
    assert answers["Compensation expectations"].startswith("REVIEW_REQUIRED")
    assert answers["Legal-sensitive questions"].startswith("REVIEW_REQUIRED")

    # The packet body (proactive outreach) must NOT volunteer work authorization,
    # sponsorship, compensation, or legal-sensitive details.
    body = " ".join(
        [packet.cover_email, packet.cover_letter, packet.tailored_summary]
    ).lower()
    for forbidden in (
        "authorized to work",
        "sponsorship",
        "visa",
        "compensation",
        "salary",
    ):
        assert forbidden not in body


def test_live_send_remains_blocked_under_default_config(tmp_path):
    database, config, _, _ = _prepare(tmp_path)
    queue_email_applications(database, config)
    result = send_email_applications(
        database,
        config,
        output_root=tmp_path / "exports",
        live=True,
        approval_phrase="I APPROVE ONE EMAIL SEND FOR Example SaaS Co Director",
    )
    assert result["mode"] == "LIVE_BLOCKED"
    assert result["applications_submitted"] == 0
