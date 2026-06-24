"""M42: manual "Add this job" capture — close the discovery coverage gap.

When a role the automated sources miss is spotted anywhere (e.g. LinkedIn), the
operator pastes its details and the app scores + tailors it like any other.
ToS-clean: only pasted text is used; nothing is fetched. Covers the reusable
ingest_manual_job pipeline helper and the JobAppAPI.add_job UI bridge.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from app_api import JobAppAPI
from application_bot.config import DEFAULT_CONFIG
from application_bot.database import Database
from application_bot.packets import load_claim_inventory
from application_bot.pipeline import ingest_manual_job

CLAIMS = "config/resume_claim_inventory.yaml"

ON_LANE = (
    "Own revenue operations, GTM systems, marketing operations, lifecycle, "
    "attribution, and CRM integrity across the go-to-market organization."
)


def _api(tmp_path) -> JobAppAPI:
    db_path = tmp_path / "crm.sqlite"
    Database(db_path).initialize()
    api = JobAppAPI(db_path=db_path)
    api.config = deepcopy(DEFAULT_CONFIG)
    api.export_root = str(tmp_path / "exports")
    return api


def test_ingest_manual_job_scores_and_packets(tmp_path):
    database = Database(tmp_path / "crm.sqlite")
    database.initialize()
    config = deepcopy(DEFAULT_CONFIG)
    result = ingest_manual_job(
        database,
        config,
        {
            "title": "Director, Revenue Operations",
            "company": "Acme Robotics",
            "apply_url": "https://www.linkedin.com/jobs/view/123456",
            "location": "Remote - United States",
            "description": ON_LANE,
        },
        output_root=str(tmp_path / "exports"),
    )
    assert result["ok"] and result["job_id"]
    assert result["score"] is not None
    # Source is tagged so manual adds are distinguishable from registry pulls.
    job = database.get_job(result["job_id"])
    assert job.source == "manual_add"
    assert job.apply_url.startswith("https://")


def test_add_job_lands_in_pipeline_and_is_visible(tmp_path):
    api = _api(tmp_path)
    r = api.add_job(
        title="Director, Revenue Operations",
        company="Acme Robotics",
        url="https://www.linkedin.com/jobs/view/123456",
        location="Remote - United States",
        description=ON_LANE,
    )
    assert r["ok"] and r["bucket"] in {"outstanding", "new"}
    assert r["grade"] in {"Hot", "Warm", "Cold"}
    # It's actually retrievable in the bucket the API reported.
    ids = [x["id"] for x in api.list_roles(r["bucket"])["roles"]]
    assert r["job_id"] in ids
    # And the detail panel can open it (web-form URL → assisted apply will open it).
    detail = api.job_detail(r["job_id"])
    assert detail["ok"] and detail["is_form"] is True


def test_add_job_requires_title_and_company(tmp_path):
    api = _api(tmp_path)
    assert api.add_job("", "Acme")["ok"] is False
    assert api.add_job("Director", "")["ok"] is False


def test_manual_job_respects_claim_safety(tmp_path):
    """A pasted JD never lets unapproved claims into the tailored cover letter."""
    api = _api(tmp_path)
    r = api.add_job(
        title="Director, Marketing Operations",
        company="Acme",
        description=ON_LANE + " Requires 15+ years and an MBA.",
    )
    assert r["ok"]
    database = Database(api.db_path)
    job = database.get_job(r["job_id"])
    letter = api._cover_letter(database, job)
    inventory = load_claim_inventory(CLAIMS)
    from application_bot.claims import text_claim_violations

    assert text_claim_violations(letter, inventory) == []
    assert "15+ years" not in letter and "MBA" not in letter
