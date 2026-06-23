"""M41: one-click "Start application" — assisted, never auto-submit.

start_application tailors both PDFs into ~/Downloads, returns the pre-approved
answers to paste plus the fields the human must fill, and opens the company's
own form ONLY when the role has a real web-form URL. It must never submit.
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
                    "dates": "2020-2025", "bullets": ["Built revenue systems."]}],
    "education": ["MBA"],
    "certifications": ["Marketo Certified"],
}


def _seed(database: Database, config: dict, *, external_id: str, apply_url: str) -> int:
    job = Job(
        external_id=external_id,
        source="greenhouse",
        source_url="https://example.com/r",
        apply_url=apply_url,
        company="Acme",
        title="Director, Marketing Operations",
        location="Remote - United States",
        remote_type="remote",
        description="Own revenue operations, GTM systems, and marketing operations.",
        responsibilities="Own marketing operations and the martech stack.",
    )
    job_id, _ = database.upsert_job(job)
    database.save_score(job_id, score_job(database.get_job(job_id), config))
    saved = database.get_job(job_id)
    policy = evaluate_job_submission_policy(saved, config)
    database.save_packet_assessment(
        job_id, packet_status="PACKET_READY", claim_gaps=[],
        reason_codes=["TARGET_FIT"], recommended_next_action="Apply.",
        submission_policy=str(policy.decision),
    )
    database.save_packet(job_id, "packet.md",
                         packet_to_dict(generate_packet(saved, config, policy)))
    return job_id


def _api(tmp_path, apply_url: str) -> tuple[JobAppAPI, int]:
    db_path = tmp_path / "crm.sqlite"
    database = Database(db_path)
    database.initialize()
    config = deepcopy(DEFAULT_CONFIG)
    jid = _seed(database, config, external_id="j1", apply_url=apply_url)
    api = JobAppAPI(db_path=db_path)
    api.config = config
    master_path = tmp_path / "master.yaml"
    master_path.write_text(yaml.safe_dump(MASTER), encoding="utf-8")
    api.config["resume_master"] = str(master_path)
    api.export_root = str(tmp_path / "exports")
    api.downloads_dir = tmp_path / "downloads"
    return api, jid


def test_start_application_form_opens_and_downloads(tmp_path, monkeypatch):
    pytest.importorskip("fpdf")
    import app_api as mod
    opened: list = []
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: opened.append(a[0]))

    url = "https://boards.greenhouse.io/acme/jobs/1"
    api, jid = _api(tmp_path, url)
    r = api.start_application(jid)

    assert r["ok"] and r["opened"] is True and r["is_form"] is True
    assert r["apply_url"] == url
    assert len(r["downloaded"]) == 2
    assert all((api.downloads_dir / name).exists() for name in r["downloaded"])
    assert any(a["label"] == "Name" for a in r["answers"])
    assert "Compensation expectations" in r["leave_blank"]
    # The company's own form was opened — and nothing was ever submitted.
    assert ["open", url] in opened


def test_start_application_recruiter_role_does_not_open(tmp_path, monkeypatch):
    pytest.importorskip("fpdf")
    import app_api as mod
    opened: list = []
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: opened.append(a[0]))

    api, jid = _api(tmp_path, "recruiter:Savannah@Mondo")
    r = api.start_application(jid)

    assert r["ok"] and r["opened"] is False and r["is_form"] is False
    assert r["channel"] == "recruiter:Savannah@Mondo"
    assert len(r["downloaded"]) == 2
    # No browser opened for a recruiter-routed role.
    assert opened == []


def test_start_application_missing_job(tmp_path):
    api, _ = _api(tmp_path, "https://x/y")
    assert api.start_application(999999)["ok"] is False
