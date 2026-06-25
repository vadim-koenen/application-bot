"""M23: desktop app js_api bridge (JobAppAPI).

Headless tests of the controller the pywebview UI calls: status counts, role
buckets (outstanding/applied), mark-applied transition, and the dry-run email
digest. No network (run_discovery is exercised separately/live).
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

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
    api.config["digest_to"] = "me@example.com"
    api.export_root = str(tmp_path / "exports")
    api.downloads_dir = tmp_path / "downloads"
    return api


def test_status_and_outstanding_bucket(tmp_path):
    api = _api(tmp_path)
    status = api.get_status()
    assert status["total"] == 1
    assert status["outstanding"] == 1
    assert status["applied"] == 0
    roles = api.list_roles("outstanding")["roles"]
    assert len(roles) == 1
    assert roles[0]["is_form"] is True
    assert api.list_roles("applied")["roles"] == []


def test_mark_applied_moves_role_to_applied(tmp_path):
    api = _api(tmp_path)
    job_id = api.list_roles("outstanding")["roles"][0]["id"]
    result = api.mark_applied(job_id)
    assert result["ok"] is True
    assert api.list_roles("outstanding")["roles"] == []
    applied = api.list_roles("applied")["roles"]
    assert len(applied) == 1 and applied[0]["id"] == job_id
    assert api.get_status()["applied"] == 1


def test_new_tab_shows_only_fresh_fits(tmp_path):
    from application_bot.models import utc_now

    db_path = tmp_path / "crm.sqlite"
    database = Database(db_path)
    database.initialize()
    config = deepcopy(DEFAULT_CONFIG)
    fresh = utc_now()  # ISO, now
    fit = Job(
        external_id="fresh-fit",
        source="greenhouse",
        source_url="https://x/1",
        apply_url="https://x/1/apply",
        company="Acme",
        title="Director, Marketing Operations",
        location="Remote - United States",
        remote_type="remote",
        salary_min=180000,
        salary_max=220000,
        description="Own revenue operations, GTM systems, marketing operations.",
        posted_at=fresh,
    )
    off = Job(
        external_id="fresh-offlane",
        source="greenhouse",
        source_url="https://x/2",
        apply_url="https://x/2/apply",
        company="Acme",
        title="Software Security Engineer",
        location="Remote - United States",
        remote_type="remote",
        description="Secure corporate platforms; vulnerability management.",
        posted_at=fresh,
    )
    for job in (fit, off):
        jid, _ = database.upsert_job(job)
        database.save_score(jid, score_job(database.get_job(jid), config))
    api = JobAppAPI(db_path=db_path)
    api.config = config
    new = api.list_roles("new")["roles"]
    titles = [r["title"] for r in new]
    assert "Director, Marketing Operations" in titles
    assert "Software Security Engineer" not in titles


def test_open_artifact_downloads_pdf_without_opening(tmp_path, monkeypatch):
    pytest.importorskip("fpdf")
    import app_api as app_api_module

    opened: list = []
    monkeypatch.setattr(
        app_api_module.subprocess, "run", lambda *a, **k: opened.append(a[0])
    )
    api = _api(tmp_path)
    job_id = api.list_roles("outstanding")["roles"][0]["id"]

    resume = api.open_artifact(job_id, "resume")
    cover = api.open_artifact(job_id, "cover")
    assert resume["ok"] and resume["path"].endswith("_resume.pdf")
    assert cover["ok"] and cover["path"].endswith("_cover.pdf")
    # The PDFs land in the Downloads folder…
    assert (api.downloads_dir / Path(resume["path"]).name).exists()
    assert (api.downloads_dir / Path(cover["path"]).name).exists()
    # …and are NOT opened in a viewer (no Preview popup — just the download).
    assert opened == []
