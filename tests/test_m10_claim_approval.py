from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil

from application_bot.answers import build_answer_draft
from application_bot.claims import (
    approved_claim_count,
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
from application_bot.models import Job, PacketStatus
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


def set_claim_pending(config: dict, claim_id: str) -> None:
    update_claim_status(
        config["claim_evidence"],
        claim_id,
        "PENDING_USER_APPROVAL",
        source="test_fixture",
        note="Test fixture intentionally keeps this claim pending.",
    )


def test_claim_evidence_inventory_loads_and_counts():
    evidence = load_claim_evidence("config/claim_evidence.yaml")
    result = list_claims(evidence)
    assert approved_claim_count(result["counts"]) == 16
    assert result["counts"]["APPROVED_FROM_RESUME"] >= 1
    assert result["counts"]["APPROVED_FROM_WEBSITE"] >= 1
    assert result["counts"]["PENDING_USER_APPROVAL"] >= 1
    assert result["counts"]["DO_NOT_USE"] >= 1
    assert all("allowed_contexts" in claim for claim in result["claims"])


def test_resume_and_website_approval_statuses_are_counted(tmp_path):
    config = temp_config(tmp_path)
    import_claim_approvals(
        config["claim_evidence"],
        "config/approved_claims_vadim_context.yaml",
    )
    counts = claim_counts(load_claim_evidence(config["claim_evidence"]))
    assert counts["APPROVED_FROM_RESUME"] >= 1
    assert counts["APPROVED_FROM_WEBSITE"] >= 1
    assert approved_claim_count(counts) == 16


def test_approved_claim_is_used_and_pending_claim_is_not(tmp_path):
    config = temp_config(tmp_path)
    set_claim_pending(config, "years_of_experience")
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
    assert "Revenue Systems Architect" in packet.tailored_summary
    assert (
        "Principal Consultant, Revenue Systems Architecture & AI-Enabled GTM"
        in packet.tailored_summary
    )
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
    set_claim_pending(config, "years_of_experience")
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
    set_claim_pending(config, "years_of_experience")
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
        approval_match_patterns=[],
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


def test_date_backed_tenure_only_clears_compatible_requirement(tmp_path):
    config = temp_config(tmp_path)
    approval_file = tmp_path / "tenure-approvals.yaml"
    approval_file.write_text(
        """
approvals:
  - claim_id: years_of_experience
    claim_text: 4+ years of date-backed marketing automation experience.
    approval_status: APPROVED_FROM_USER_CONTEXT
    source: user_resume_context
    note: Limited to four years in marketing automation contexts.
    approval_match_patterns:
      - '\\b[1-4]\\+?\\s+years?\\b.{0,80}\\bmarketing automation\\b'
      - '\\b(?:Salesforce|SFDC).{0,40}(?:CRM|integration|sync)\\b.{0,80}\\b[1-4]\\+?\\s+years?\\b'
""".lstrip(),
        encoding="utf-8",
    )
    import_claim_approvals(config["claim_evidence"], approval_file)
    evidence = load_claim_evidence(config["claim_evidence"])
    inventory = load_claim_inventory(config["resume_claim_inventory"])

    compatible = approval_job()
    compatible.requirements = "4+ years of marketing automation experience."
    compatible_score = score_job(compatible, config)
    compatible.score = compatible_score.score
    compatible.verdict = str(compatible_score.verdict)
    compatible.score_details_json = json.dumps(
        {"dimensions": compatible_score.dimensions}
    )
    compatible_assessment = assess_packet(
        compatible,
        config,
        evaluate_job_submission_policy(compatible, config),
        inventory,
        evidence,
    )
    assert compatible_assessment.status == PacketStatus.PACKET_READY

    incompatible = approval_job()
    incompatible.requirements = "10+ years of marketing automation experience."
    incompatible_score = score_job(incompatible, config)
    incompatible.score = incompatible_score.score
    incompatible.verdict = str(incompatible_score.verdict)
    incompatible.score_details_json = json.dumps(
        {"dimensions": incompatible_score.dimensions}
    )
    incompatible_assessment = assess_packet(
        incompatible,
        config,
        evaluate_job_submission_policy(incompatible, config),
        inventory,
        evidence,
    )
    assert incompatible_assessment.status == PacketStatus.REVIEW_PACKET_CLAIM_GAPS
    assert incompatible_assessment.claim_gaps == ["years_of_experience"]

    unrelated = approval_job()
    unrelated.description = "Uses Salesforce for sales activity."
    unrelated.requirements = "4+ years of quota-carrying SaaS sales experience."
    unrelated_score = score_job(unrelated, config)
    unrelated.score = unrelated_score.score
    unrelated.verdict = str(unrelated_score.verdict)
    unrelated.score_details_json = json.dumps(
        {"dimensions": unrelated_score.dimensions}
    )
    unrelated_assessment = assess_packet(
        unrelated,
        config,
        evaluate_job_submission_policy(unrelated, config),
        inventory,
        evidence,
    )
    assert "years_of_experience" in unrelated_assessment.claim_gaps


def test_full_resume_tenure_clears_systems_requirement_not_unsupported_scope(
    tmp_path,
):
    config = temp_config(tmp_path)
    import_claim_approvals(
        config["claim_evidence"],
        "config/approved_claims_vadim_context.yaml",
    )
    evidence = load_claim_evidence(config["claim_evidence"])
    inventory = load_claim_inventory(config["resume_claim_inventory"])

    systems_job = approval_job()
    systems_job.requirements = (
        "10+ years of experience in marketing operations and revenue systems."
    )
    systems_score = score_job(systems_job, config)
    systems_job.score = systems_score.score
    systems_job.verdict = str(systems_score.verdict)
    systems_job.score_details_json = json.dumps(
        {"dimensions": systems_score.dimensions}
    )
    systems_assessment = assess_packet(
        systems_job,
        config,
        evaluate_job_submission_policy(systems_job, config),
        inventory,
        evidence,
    )
    assert systems_assessment.status == PacketStatus.PACKET_READY

    unsupported_job = approval_job()
    unsupported_job.requirements = (
        "15+ years leading paid media and managing managers."
    )
    unsupported_score = score_job(unsupported_job, config)
    unsupported_job.score = unsupported_score.score
    unsupported_job.verdict = str(unsupported_score.verdict)
    unsupported_job.score_details_json = json.dumps(
        {"dimensions": unsupported_score.dimensions}
    )
    unsupported_assessment = assess_packet(
        unsupported_job,
        config,
        evaluate_job_submission_policy(unsupported_job, config),
        inventory,
        evidence,
    )
    assert unsupported_assessment.status == PacketStatus.REVIEW_PACKET_CLAIM_GAPS
    assert unsupported_assessment.claim_gaps == [
        "leadership_team_size",
    ]


def test_approved_tenure_makes_fifteen_year_requirement_soft_not_claimed(
    tmp_path,
):
    config = temp_config(tmp_path)
    config["years_requirement_scoring"] = {
        "approved_years": 14,
        "moderate_threshold": 15,
        "moderate_penalty": -6,
        "high_threshold": 18,
        "high_penalty": -15,
    }
    config["packet_soft_requirement_claims"] = ["years_of_experience"]
    import_claim_approvals(
        config["claim_evidence"],
        "config/approved_claims_vadim_context.yaml",
    )
    evidence = load_claim_evidence(config["claim_evidence"])
    inventory = load_claim_inventory(config["resume_claim_inventory"])
    job = approval_job()
    job.requirements = (
        "15+ years of revenue systems and marketing operations experience."
    )
    result = score_job(job, config)
    job.score = result.score
    job.verdict = str(result.verdict)
    job.score_details_json = json.dumps(
        {
            "dimensions": result.dimensions,
            "reasons": result.reasons,
            "risk_flags": result.risk_flags,
        }
    )
    assessment = assess_packet(
        job,
        config,
        evaluate_job_submission_policy(job, config),
        inventory,
        evidence,
    )
    packet = generate_packet(
        job,
        config,
        evaluate_job_submission_policy(job, config),
        inventory=inventory,
        evidence=evidence,
        assessment=assessment,
    )
    generated = " ".join(
        (packet.tailored_summary, packet.cover_email, packet.cover_letter)
    )
    assert assessment.status == PacketStatus.PACKET_READY
    assert assessment.claim_gaps == []
    assert "SOFT_REQUIREMENT_MISMATCH" in assessment.reason_codes
    assert "15+ years" not in generated


def test_pending_tenure_still_blocks_fifteen_year_requirement(tmp_path):
    config = temp_config(tmp_path)
    config["packet_soft_requirement_claims"] = ["years_of_experience"]
    set_claim_pending(config, "years_of_experience")
    evidence = load_claim_evidence(config["claim_evidence"])
    inventory = load_claim_inventory(config["resume_claim_inventory"])
    job = approval_job()
    job.requirements = "15+ years of marketing operations experience."
    result = score_job(job, config)
    job.score = result.score
    job.verdict = str(result.verdict)
    job.score_details_json = json.dumps({"dimensions": result.dimensions})
    assessment = assess_packet(
        job,
        config,
        evaluate_job_submission_policy(job, config),
        inventory,
        evidence,
    )
    assert assessment.status == PacketStatus.REVIEW_PACKET_CLAIM_GAPS
    assert assessment.claim_gaps == ["years_of_experience"]


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
