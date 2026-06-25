"""M50: follow-up / interview tracking — the post-application pipeline CRM.

Per-role notes / next-action / reminder fields, persisted on the job, surfaced
back through job_detail, the enriched row (reminder_due badge), and a
dashboard "follow-ups due" count. Nothing here is outward-facing — it's the
operator's own log.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta

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
}

YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
TODAY = date.today().isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def _seed_ready_job(database: Database, config: dict) -> int:
    job = Job(
        external_id="ready-1", source="greenhouse",
        source_url="https://example.com/r1",
        apply_url="https://boards.greenhouse.io/acme/jobs/1",
        company="Acme", title="Director, Marketing Operations",
        location="Remote - United States", remote_type="remote",
        description="Own revenue operations, GTM systems, and marketing operations.",
        responsibilities="Build lifecycle operations and revenue systems.",
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


def _api(tmp_path) -> tuple[JobAppAPI, int]:
    db_path = tmp_path / "crm.sqlite"
    database = Database(db_path)
    database.initialize()
    config = deepcopy(DEFAULT_CONFIG)
    jid = _seed_ready_job(database, config)
    api = JobAppAPI(db_path=db_path)
    api.config = config
    master_path = tmp_path / "master.yaml"
    master_path.write_text(yaml.safe_dump(MASTER), encoding="utf-8")
    api.config["resume_master"] = str(master_path)
    return api, jid


# --- reminder-due logic ------------------------------------------------------

@pytest.mark.parametrize(
    "reminder,due",
    [(YESTERDAY, True), (TODAY, True), (TOMORROW, False), ("", False), (None, False)],
)
def test_reminder_due(reminder, due):
    assert JobAppAPI._reminder_due(reminder) is due


# --- database layer ----------------------------------------------------------

def test_set_followup_persists_and_logs_event(tmp_path):
    db = Database(tmp_path / "c.sqlite")
    db.initialize()
    config = deepcopy(DEFAULT_CONFIG)
    jid = _seed_ready_job(db, config)
    db.set_followup(
        jid, notes="Recruiter call Tue", next_action="Send portfolio",
        reminder_at=TOMORROW,
    )
    job = db.get_job(jid)
    assert job.followup_notes == "Recruiter call Tue"
    assert job.followup_next_action == "Send portfolio"
    assert job.followup_reminder_at == TOMORROW
    with db.connect() as conn:
        kinds = [r["event_type"] for r in conn.execute(
            "SELECT event_type FROM events WHERE job_id = ?", (jid,)).fetchall()]
    assert "FOLLOWUP_UPDATED" in kinds


def test_set_followup_clears_reminder(tmp_path):
    db = Database(tmp_path / "c.sqlite")
    db.initialize()
    jid = _seed_ready_job(db, deepcopy(DEFAULT_CONFIG))
    db.set_followup(jid, reminder_at=TOMORROW)
    db.set_followup(jid, notes="kept", reminder_at="")
    job = db.get_job(jid)
    assert job.followup_reminder_at is None
    assert job.followup_notes == "kept"


def test_set_followup_rejects_bad_date(tmp_path):
    db = Database(tmp_path / "c.sqlite")
    db.initialize()
    jid = _seed_ready_job(db, deepcopy(DEFAULT_CONFIG))
    with pytest.raises(ValueError, match="ISO date"):
        db.set_followup(jid, reminder_at="next tuesday")


def test_set_followup_unknown_job(tmp_path):
    db = Database(tmp_path / "c.sqlite")
    db.initialize()
    with pytest.raises(ValueError, match="does not exist"):
        db.set_followup(999999, notes="x")


# --- API + UI payload --------------------------------------------------------

def test_save_followup_roundtrips_to_job_detail(tmp_path):
    api, jid = _api(tmp_path)
    r = api.save_followup(jid, "Interview 6/30", "Prep STAR stories", TOMORROW)
    assert r["ok"] is True and r["reminder_due"] is False
    d = api.job_detail(jid)
    assert d["followup_notes"] == "Interview 6/30"
    assert d["followup_next_action"] == "Prep STAR stories"
    assert d["followup_reminder_at"] == TOMORROW


def test_save_followup_invalid_date_returns_error(tmp_path):
    api, jid = _api(tmp_path)
    r = api.save_followup(jid, "", "", "soon")
    assert r["ok"] is False and "ISO date" in r["error"]


def test_save_followup_missing_job(tmp_path):
    api, _ = _api(tmp_path)
    assert api.save_followup(999999, "x")["ok"] is False


def test_due_reminder_surfaces_in_row_and_dashboard(tmp_path):
    api, jid = _api(tmp_path)
    # A past-due reminder shows on the row and counts on the dashboard.
    api.save_followup(jid, "", "Chase recruiter", YESTERDAY)
    row = api.list_roles("outstanding")["roles"][0]
    assert row["reminder_at"] == YESTERDAY and row["reminder_due"] is True
    assert api.dashboard_summary()["followups_due"] == 1


def test_future_reminder_not_due(tmp_path):
    api, jid = _api(tmp_path)
    api.save_followup(jid, "", "", TOMORROW)
    row = api.list_roles("outstanding")["roles"][0]
    assert row["reminder_due"] is False
    assert api.dashboard_summary()["followups_due"] == 0
