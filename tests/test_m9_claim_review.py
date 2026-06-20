from __future__ import annotations

from copy import deepcopy
import csv
import json
from pathlib import Path

import yaml

from application_bot.claims import packet_claim_violations
from application_bot.config import (
    DEFAULT_CONFIG,
    load_claim_inventory,
    load_company_registry,
)
from application_bot.database import Database
from application_bot.models import Job, PacketStatus
from application_bot.packets import assess_packet, generate_packet
from application_bot.pipeline import run_dry_pipeline
from application_bot.policy import evaluate_job_submission_policy
from application_bot.review import (
    export_review_csv,
    export_review_queue,
    source_report,
)
from application_bot.scoring import score_job


FIXTURE = Path(__file__).parent / "fixtures" / "realistic_jobs.json"
CLAIMS = Path("config/resume_claim_inventory.yaml")


def fixture_jobs() -> list[Job]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [Job(**row) for row in payload["jobs"]]


class StaticAdapter:
    def __init__(self, jobs: list[Job]):
        self.jobs = jobs

    def discover_jobs(self, **kwargs):
        return self.jobs


def write_registry(tmp_path: Path) -> Path:
    path = tmp_path / "registry.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "companies": [
                    {
                        "company": "Fixture Companies",
                        "ats": "greenhouse",
                        "board_token": "fixture",
                        "enabled": True,
                        "target_relevance": ["growth marketing", "GTM systems"],
                        "notes": "Offline fixture",
                        "source_url": "https://example.com/public-jobs",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def run_fixture_pipeline(tmp_path: Path, config: dict | None = None):
    return run_dry_pipeline(
        database_path=tmp_path / "crm.sqlite",
        registry_path=write_registry(tmp_path),
        output_root=tmp_path / "exports",
        config=config or deepcopy(DEFAULT_CONFIG),
        limit=50,
        adapters={"greenhouse": StaticAdapter(fixture_jobs())},
    )


def test_claim_inventory_loads_required_safe_content():
    inventory = load_claim_inventory(CLAIMS)
    assert inventory["identity"]["name"] == "Vadim Koenen"
    assert inventory["current_business_identity"]["primary"] == "Koenen Revenue Systems"
    assert inventory["approved_metrics"] == []
    assert "GTM systems architecture" in inventory["approved_positioning_themes"]


def test_packet_uses_only_approved_claims(tmp_path):
    job = fixture_jobs()[0]
    result = score_job(job, DEFAULT_CONFIG)
    job.score = result.score
    job.verdict = str(result.verdict)
    job.score_details_json = json.dumps(
        {"dimensions": result.dimensions, "reasons": result.reasons}
    )
    inventory = load_claim_inventory(CLAIMS)
    policy = evaluate_job_submission_policy(job, DEFAULT_CONFIG)
    packet = generate_packet(job, DEFAULT_CONFIG, policy, inventory=inventory)
    assert "Koenen Revenue Systems (KRS)" in packet.tailored_summary
    assert packet.approved_claim_ids
    assert packet_claim_violations(packet, inventory) == []
    assert "grew revenue" not in packet.cover_letter.lower()


def test_unverified_requirements_become_claim_gaps():
    job = fixture_jobs()[3]
    result = score_job(job, DEFAULT_CONFIG)
    job.score = result.score
    job.verdict = str(result.verdict)
    job.score_details_json = json.dumps({"dimensions": result.dimensions})
    inventory = load_claim_inventory(CLAIMS)
    assessment = assess_packet(
        job,
        DEFAULT_CONFIG,
        evaluate_job_submission_policy(job, DEFAULT_CONFIG),
        inventory,
    )
    assert assessment.status == PacketStatus.REVIEW_PACKET_CLAIM_GAPS
    assert assessment.claim_gaps == ["years_of_experience"]
    assert assessment.should_export is True


def test_realistic_senior_target_roles_export_ready_packets(tmp_path):
    result = run_fixture_pipeline(tmp_path)
    assert result["packets_ready"] >= 3
    ready_names = {
        Path(path).name
        for path in result["packet_paths"]
        if "/ready/" in path
    }
    assert any("senior-director-growth-marketing" in name for name in ready_names)
    assert any("vp-demand-generation" in name for name in ready_names)
    assert any("head-of-gtm-systems" in name for name in ready_names)


def test_claim_gap_role_exports_review_packet(tmp_path):
    result = run_fixture_pipeline(tmp_path)
    assert result["review_packets_claim_gaps"] >= 1
    review_paths = [path for path in result["packet_paths"] if "/review/" in path]
    assert any("director-marketing-operations" in path for path in review_paths)


def test_low_fit_jobs_have_no_packet_reasons(tmp_path):
    run_fixture_pipeline(tmp_path)
    database = Database(tmp_path / "crm.sqlite")
    rows = database.review_queue_rows()
    account_executive = next(row for row in rows if row["title"] == "Account Executive")
    coordinator = next(
        row for row in rows if row["title"] == "Marketing Coordinator"
    )
    assert account_executive["packet_status"] == "NOT_WORTH_PACKET"
    assert account_executive["reason_codes"]
    assert coordinator["packet_status"] == "NOT_WORTH_PACKET"
    assert "WRONG_OR_UNCLEAR_LEVEL" in coordinator["reason_codes"]


def test_source_registry_preserves_target_relevance():
    registry = load_company_registry("config/live_company_registry.yaml")
    assert len(registry) >= 10
    assert all("target_relevance" in entry for entry in registry)
    assert all("notes" in entry and "source_url" in entry for entry in registry)
    assert {entry["ats"] for entry in registry} == {"greenhouse", "lever", "ashby"}


def test_review_queue_and_csv_exports(tmp_path):
    run_fixture_pipeline(tmp_path)
    database = Database(tmp_path / "crm.sqlite")
    queue = export_review_queue(database, tmp_path / "review")
    csv_result = export_review_csv(database, tmp_path / "review.csv")
    assert Path(queue["markdown_path"]).exists()
    assert Path(queue["json_path"]).exists()
    assert csv_result["jobs"] == 8
    with Path(csv_result["csv_path"]).open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["packet_status"]
    assert "recommended_next_action" in rows[0]


def test_source_report_contains_measured_conversion_fields(tmp_path):
    run_fixture_pipeline(tmp_path)
    database = Database(tmp_path / "crm.sqlite")
    report = source_report(database)
    expected = {
        "sources_attempted",
        "sources_succeeded",
        "jobs_discovered",
        "jobs_after_dedupe",
        "target_level_matches",
        "function_matches",
        "apply_priority",
        "good_fit",
        "maybe",
        "packets_ready",
        "review_packets_claim_gaps",
        "blocked",
        "no_packet_reason_counts",
    }
    assert expected <= set(report)
    assert report["jobs_after_dedupe"] == 8
    assert report["packets_ready"] >= 3


def test_packet_thresholds_are_configurable(tmp_path):
    config = deepcopy(DEFAULT_CONFIG)
    config["packet_thresholds"]["ready_min_score"] = 99
    result = run_fixture_pipeline(tmp_path, config)
    assert result["packets_ready"] == 0
    assert result["review_packets_claim_gaps"] >= 3


def test_exact_target_function_in_title_gets_review_fallback():
    job = Job(
        external_id="sparse-title-match",
        source="lever",
        source_url="https://example.com/job",
        apply_url="https://example.com/apply",
        company="Sparse Posting Co",
        title="Senior Director, Growth Marketing",
        location="Remote - United States",
        remote_type="remote",
        description="Own the global program.",
    )
    result = score_job(job, DEFAULT_CONFIG)
    job.score = max(result.score, 45)
    job.verdict = "MAYBE"
    job.score_details_json = json.dumps({"dimensions": result.dimensions})
    assessment = assess_packet(
        job,
        DEFAULT_CONFIG,
        evaluate_job_submission_policy(job, DEFAULT_CONFIG),
        load_claim_inventory(CLAIMS),
    )
    assert assessment.status == PacketStatus.REVIEW_PACKET_CLAIM_GAPS
    assert "MAYBE_STRONG_TITLE_FUNCTION_MATCH" in assessment.reason_codes


def test_generic_sales_director_does_not_receive_packet():
    job = Job(
        external_id="sales-director",
        source="greenhouse",
        source_url="https://example.com/job",
        apply_url="https://example.com/apply",
        company="Sales Co",
        title="Director, Mid-Market Sales",
        location="Remote - United States",
        remote_type="remote",
        description="Lead a sales organization and coordinate GTM strategy.",
    )
    result = score_job(job, DEFAULT_CONFIG)
    job.score = result.score
    job.verdict = str(result.verdict)
    job.score_details_json = json.dumps({"dimensions": result.dimensions})
    assessment = assess_packet(
        job,
        DEFAULT_CONFIG,
        evaluate_job_submission_policy(job, DEFAULT_CONFIG),
        load_claim_inventory(CLAIMS),
    )
    assert assessment.status == PacketStatus.NOT_WORTH_PACKET
    assert assessment.reason_codes == ["GENERIC_SALES_ROLE"]


def test_workday_friction_penalizes_without_blocking():
    job = fixture_jobs()[7]
    result = score_job(job, DEFAULT_CONFIG)
    assert result.dimensions["friction"] == -8
    assert result.verdict != "BLOCKED"
