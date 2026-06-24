"""M39: 6sense-style dashboard API surface.

Headless tests for the additions that back the dashboard UI: fit-grade
temperature, the enriched role row, dashboard_summary (KPI tiles + funnel +
segment breakdowns), job_detail (slide-over payload), and the RESPONDED
funnel stage via mark_responded.
"""

from __future__ import annotations

from copy import deepcopy

import pytest
import yaml

from app_api import JobAppAPI
from application_bot.config import DEFAULT_CONFIG
from application_bot.database import Database
from application_bot.models import Job
from application_bot.packets import generate_packet, packet_to_dict
from application_bot.policy import evaluate_job_submission_policy
from application_bot.scoring import score_job


MASTER = {
    "identity": {"name": "Test Person", "headline": "Revenue Systems Architect"},
    "contact": {"location": "Plano, TX", "email": "t@example.com",
                "website": "example.com", "linkedin": "linkedin.com/in/test"},
    "summary": "Operations leader building revenue systems and GTM workflows.",
    "selected_impact": ["$51M pipeline activated"],
    "skills": {"Revenue Systems": ["Salesforce", "marketing operations"]},
    "experience": [{"company": "Mitel", "title": "Senior Manager, Marketing Ops",
                    "dates": "2020-2025", "bullets": ["Led a data ops team of 6."]}],
    "education": ["MBA"],
    "certifications": ["Marketo Certified"],
}


def _seed_ready_job(database: Database, config: dict) -> int:
    job = Job(
        external_id="ready-1",
        source="greenhouse",
        source_url="https://example.com/r1",
        apply_url="https://boards.greenhouse.io/acme/jobs/1",
        company="Acme",
        title="Director, Marketing Operations",
        location="Remote - United States",
        remote_type="remote",
        salary_min=180000,
        salary_max=220000,
        description="Own revenue operations, GTM systems, and marketing operations.",
        requirements="Marketing operations leadership.",
        responsibilities="Build lifecycle operations and revenue systems.",
    )
    job_id, _ = database.upsert_job(job)
    saved = database.get_job(job_id)
    database.save_score(job_id, score_job(saved, config))
    saved = database.get_job(job_id)
    policy = evaluate_job_submission_policy(saved, config)
    database.save_packet_assessment(
        job_id,
        packet_status="PACKET_READY",
        claim_gaps=[],
        reason_codes=["TARGET_FIT"],
        recommended_next_action="Apply.",
        submission_policy=str(policy.decision),
    )
    packet = generate_packet(saved, config, policy)
    database.save_packet(job_id, "packet.md", packet_to_dict(packet))
    return job_id


def _api(tmp_path) -> JobAppAPI:
    db_path = tmp_path / "crm.sqlite"
    database = Database(db_path)
    database.initialize()
    config = deepcopy(DEFAULT_CONFIG)
    _seed_ready_job(database, config)
    api = JobAppAPI(db_path=db_path)
    api.config = config
    master_path = tmp_path / "master.yaml"
    master_path.write_text(yaml.safe_dump(MASTER), encoding="utf-8")
    api.config["resume_master"] = str(master_path)
    return api


@pytest.mark.parametrize(
    "score,grade",
    [(95, "Hot"), (80, "Hot"), (79, "Warm"), (65, "Warm"),
     (64, "Cold"), (45, "Cold"), (44, None), (None, None)],
)
def test_grade_thresholds(score, grade):
    assert JobAppAPI._grade(score) == grade


def test_row_is_enriched_for_dashboard(tmp_path):
    api = _api(tmp_path)
    row = api.list_roles("outstanding")["roles"][0]
    for key in ("grade", "source", "location", "remote_type", "score"):
        assert key in row
    assert row["source"] == "greenhouse"
    assert row["remote_type"] == "remote"
    assert row["grade"] in {"Hot", "Warm", "Cold"}


def test_dashboard_summary_shape_and_funnel(tmp_path):
    api = _api(tmp_path)
    s = api.dashboard_summary()
    assert set(s["pipeline"]) == {"new", "outstanding", "applied", "responded"}
    assert s["pipeline"]["outstanding"] == 1
    assert s["pipeline"]["applied"] == 0
    assert s["pipeline"]["responded"] == 0
    # The one ready greenhouse role is reflected in the segment breakdowns.
    assert s["by_source"].get("greenhouse") == 1
    assert sum(s["by_grade"].values()) == 1
    assert s["avg_score"] is not None
    assert s["total_scored"] == 1


def test_job_detail_payload(tmp_path):
    api = _api(tmp_path)
    job_id = api.list_roles("outstanding")["roles"][0]["id"]
    d = api.job_detail(job_id)
    assert d["ok"] is True
    assert d["company"] == "Acme"
    assert d["description"]  # JD excerpt present
    assert isinstance(d["reasons"], list) and d["reasons"]
    assert isinstance(d["risk_flags"], list)
    assert d["grade"] in {"Hot", "Warm", "Cold"}


def test_job_detail_missing_id(tmp_path):
    api = _api(tmp_path)
    assert api.job_detail(99999)["ok"] is False


def test_mark_responded_advances_funnel(tmp_path):
    api = _api(tmp_path)
    job_id = api.list_roles("outstanding")["roles"][0]["id"]
    api.mark_applied(job_id)
    # Applied roles leave the Outstanding pile.
    assert api.list_roles("outstanding")["roles"] == []
    assert api.dashboard_summary()["pipeline"]["applied"] == 1

    result = api.mark_responded(job_id)
    assert result["ok"] is True and result["status"] == "RESPONDED"
    responded = api.list_roles("responded")["roles"]
    assert len(responded) == 1 and responded[0]["id"] == job_id
    # Now counted under responded, no longer under applied.
    pipeline = api.dashboard_summary()["pipeline"]
    assert pipeline["responded"] == 1
    assert pipeline["applied"] == 0
    assert api.list_roles("applied")["roles"] == []
