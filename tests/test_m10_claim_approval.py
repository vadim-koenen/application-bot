from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil

from application_bot.answers import build_answer_draft
from application_bot.claims import (
    claim_counts,
    claim_gap_rows,
    export_approval_pack,
    import_claim_approvals,
    list_claims,
    update_claim_status,
)
from application_bot.config import (
    DEFAULT_CONFIG,
    load_answer_bank,
    load_claim_evidence,
    load_claim_inventory,
)
from application_bot.database import Database
from application_bot.models import Job
from application_bot.packets import assess_packet, generate_packet
from application_bot.pipeline import refresh_packets
from application_bot.policy import evaluate_job_submission_policy
from application_bot.reporting import write_daily_report
from application_bot.review import export_review_csv, export_review_html
from application_bot.scoring import score_job


def temp_config(tmp_path: Path) -> dict:
    evidence = tmp_path / "claim_evidence.yaml"
    inventory = tmp_path / "resume_claim_inventory.yaml"
    answer_bank = tmp_path / "application_answer_bank.yaml"
    shutil.copy("config/claim_evidence.yaml", evidence)
    shutil.copy("config/resume_claim_inventory.yaml", inventory)
    shutil.copy("config/application_answer_bank.yaml", answer_bank)
    config = deepcopy(DEFAULT_CONFIG)
    config["claim_evidence"] = str(evidence)
    config["resume_claim_inventory"] = str(inventory)
    config["application_answer_bank"] = str(answer_bank)
    return config


def approval_job() -> Job:
    return Job(
        external_id="approval-job",
        source="greenhouse",
        source_url="https://example.com/job",
        apply_url="https://example.com/apply",
        company="Evidence AI",
        title="Senior Director, Growth Marketing",
        department="Marketing",
        location="Remote - United States",
        remote_type="remote",
        salary_min=190000,
        salary_max=230000,
        description=(
            "Lead growth marketing, demand generation, lifecycle marketing, "
            "campaign operations, and performance measurement."
        ),
        requirements="10+ years of experience in marketing operations.",
        responsibilities="Build the function and align the leadership team.",
    )


def prepare_database(tmp_path: Path, config: dict) -> tuple[Database, int]:
    database = Database(tmp_path / "crm.sqlite")
    database.initialize()
    job = approval_job()
    job_id, _ = database.upsert_job(job)
    database.save_score(job_id, score_job(job, config))
    return database, job_id


def test_claim_evidence_inventory_loads_and_counts():
    evidence = load_claim_evidence("config/claim_evidence.yaml")
    result = list_claims(evidence)
    assert result["counts"]["APPROVED_FROM_USER_CONTEXT"] >= 8
    assert result["counts"]["PENDING_USER_APPROVAL"] >= 1
    assert result["counts"]["DO_NOT_USE"] >= 1
    assert all("allowed_contexts" in claim for claim in result["claims"])


def test_approved_claim_is_used_and_pending_claim_is_not(tmp_path):
    config = temp_config(tmp_path)
    job = approval_job()
    score = score_job(job, config)
    job.score = score.score
    job.verdict = str(score.verdict)
    job.score_details_json = json.dumps({"dimensions": score.dimensions})
    evidence = load_claim_evidence(config["claim_evidence"])
    inventory = load_claim_inventory(config["resume_claim_inventory"])
    policy = evaluate_job_submission_policy(job, config)
    assessment = assess_packet(job, config, policy, inventory, evidence)
    packet = generate_packet(
        job,
        config,
        policy,
        inventory=inventory,
        evidence=evidence,
        answer_bank=load_answer_bank(config["application_answer_bank"]),
        assessment=assessment,
    )
    assert "Principal Consultant | Revenue Systems Architecture & AI-Enabled GTM" in packet.tailored_summary
    assert "Exact years of experience are pending" not in packet.tailored_summary
    assert "years_of_experience" in packet.pending_claims_not_used
    assert packet.safe_substitutions


def test_rejected_and_do_not_use_claims_are_never_answered(tmp_path):
    config = temp_config(tmp_path)
    update_claim_status(
        config["claim_evidence"],
        "years_of_experience",
        "REJECTED",
        source="user_rejection",
        note="Do not use this claim.",
    )
    evidence = load_claim_evidence(config["claim_evidence"])
    answers = build_answer_draft(
        load_answer_bank(config["application_answer_bank"]),
        evidence,
    )
    assert answers["Work authorization"].startswith("PENDING_USER_APPROVAL")
    assert answers["Sponsorship"].startswith("PENDING_USER_APPROVAL")
    assert answers["Background check"].startswith("REVIEW_REQUIRED")


def test_rejected_positioning_is_withheld_from_packet_text(tmp_path):
    config = temp_config(tmp_path)
    update_claim_status(
        config["claim_evidence"],
        "current_positioning",
        "REJECTED",
        source="user_rejection",
        note="Do not use this positioning.",
    )
    job = approval_job()
    score = score_job(job, config)
    job.score = score.score
    job.verdict = str(score.verdict)
    job.score_details_json = json.dumps({"dimensions": score.dimensions})
    evidence = load_claim_evidence(config["claim_evidence"])
    inventory = load_claim_inventory(config["resume_claim_inventory"])
    policy = evaluate_job_submission_policy(job, config)
    packet = generate_packet(
        job,
        config,
        policy,
        inventory=inventory,
        evidence=evidence,
        answer_bank=load_answer_bank(config["application_answer_bank"]),
    )
    assert (
        "Principal Consultant | Revenue Systems Architecture & AI-Enabled GTM"
        not in packet.tailored_summary
    )
    assert "Koenen Revenue Systems" in packet.tailored_summary


def test_claim_gaps_and_approval_pack_export(tmp_path):
    config = temp_config(tmp_path)
    database, _ = prepare_database(tmp_path, config)
    refresh_packets(database=database, output_root=tmp_path / "packets", config=config)
    evidence = load_claim_evidence(config["claim_evidence"])
    gaps = claim_gap_rows(database, evidence)
    assert gaps[0]["claim_id"] == "years_of_experience"
    assert gaps[0]["suggested_safe_rewrite"]
    exported = export_approval_pack(
        database, evidence, tmp_path / "approval-pack"
    )
    assert exported["claim_gaps_found"] == 1
    assert Path(exported["markdown_path"]).exists()
    assert Path(exported["json_path"]).exists()


def test_explicit_approval_converts_packet_to_ready(tmp_path):
    config = temp_config(tmp_path)
    database, _ = prepare_database(tmp_path, config)
    before = refresh_packets(
        database=database, output_root=tmp_path / "before", config=config
    )
    assert before["packet_statuses"]["REVIEW_PACKET_CLAIM_GAPS"] == 1
    update_claim_status(
        config["claim_evidence"],
        "years_of_experience",
        "APPROVED_FROM_USER_CONTEXT",
        source="user_resume_review",
        note="Vadim explicitly confirmed the role's tenure requirement is supported.",
    )
    after = refresh_packets(
        database=database, output_root=tmp_path / "after", config=config
    )
    assert after["packet_statuses"]["PACKET_READY"] == 1
    assert any("/ready/" in path for path in after["packet_paths"])


def test_import_approvals_updates_local_inventory(tmp_path):
    config = temp_config(tmp_path)
    approval_file = tmp_path / "approvals.yaml"
    approval_file.write_text(
        """
approvals:
  - claim_id: years_of_experience
    claim_text: 10+ years of relevant experience.
    approval_status: APPROVED_FROM_USER_CONTEXT
    source: user_resume_review
    note: Explicit evidence review completed.
""".lstrip(),
        encoding="utf-8",
    )
    result = import_claim_approvals(config["claim_evidence"], approval_file)
    assert result["updated"] == 1
    evidence = load_claim_evidence(config["claim_evidence"])
    claim = next(
        claim for claim in evidence["claims"] if claim["claim_id"] == "years_of_experience"
    )
    assert claim["approval_status"] == "APPROVED_FROM_USER_CONTEXT"
    assert claim["claim_text"] == "10+ years of relevant experience."
    assert "packet_text" in claim["allowed_contexts"]


def test_approved_claim_scope_does_not_clear_unrelated_requirement(tmp_path):
    config = temp_config(tmp_path)
    approval_file = tmp_path / "approvals.yaml"
    approval_file.write_text(
        """
approvals:
  - claim_id: named_tool_proficiency
    claim_text: Proficient with Marketo and Salesforce.
    approval_status: APPROVED_FROM_USER_CONTEXT
    source: user_evidence
    note: Only Marketo and Salesforce are approved.
    approval_match_patterns:
      - '\\bMarketo\\b'
      - '\\bSalesforce\\b'
""".lstrip(),
        encoding="utf-8",
    )
    import_claim_approvals(config["claim_evidence"], approval_file)
    evidence = load_claim_evidence(config["claim_evidence"])
    inventory = load_claim_inventory(config["resume_claim_inventory"])
    job = approval_job()
    job.requirements = "Deep expertise in enterprise activation metrics."
    score = score_job(job, config)
    job.score = score.score
    job.verdict = str(score.verdict)
    job.score_details_json = json.dumps({"dimensions": score.dimensions})
    assessment = assess_packet(
        job,
        config,
        evaluate_job_submission_policy(job, config),
        inventory,
        evidence,
    )
    assert "named_tool_proficiency" in assessment.claim_gaps


def test_answer_bank_loads_with_sensitive_review_rules():
    bank = load_answer_bank("config/application_answer_bank.yaml")
    assert bank["answers"]["website"]["status"] == "APPROVED"
    assert bank["answers"]["work_authorization"]["status"] == "PENDING_USER_APPROVAL"
    assert bank["answers"]["sponsorship"]["status"] == "PENDING_USER_APPROVAL"
    assert bank["answers"]["legal_sensitive"]["status"] == "REVIEW_REQUIRED"
    assert bank["answers"]["unknown_required_question"]["status"] == "REVIEW_REQUIRED"


def test_refresh_review_html_csv_and_daily_readiness(tmp_path):
    config = temp_config(tmp_path)
    database, _ = prepare_database(tmp_path, config)
    refreshed = refresh_packets(
        database=database, output_root=tmp_path / "packets", config=config
    )
    assert refreshed["applications_submitted"] == 0
    html = export_review_html(database, tmp_path / "review")
    csv_result = export_review_csv(database, tmp_path / "review.csv")
    assert Path(html["html_path"]).exists()
    html_text = Path(html["html_path"]).read_text(encoding="utf-8")
    assert "Application Bot Review Queue" in html_text
    assert "All statuses" in html_text
    assert Path(csv_result["csv_path"]).exists()
    readiness = claim_counts(load_claim_evidence(config["claim_evidence"]))
    report = write_daily_report(
        database,
        tmp_path / "daily",
        claim_readiness=readiness,
    )
    assert report["claim_readiness"]["PENDING_USER_APPROVAL"] >= 1
    assert Path(report["markdown_path"]).exists()
