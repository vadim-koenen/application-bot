"""M46: pipeline integrity — stable dedupe + off-lane scoring.

Two operator-reported bugs:
- Re-discovery created duplicate rows and resurfaced applied roles, because the
  dedupe key hashed the volatile JD text. The key is now stable (company + title
  + apply URL), so a re-scan with shifted JD text updates the SAME row and keeps
  its status.
- "Senior Executive Business Partner" (a modern executive-assistant title)
  scored as a fit. "business partner" / "chief of staff" are now off-lane.
"""

from __future__ import annotations

from copy import deepcopy

from application_bot.config import DEFAULT_CONFIG
from application_bot.database import Database
from application_bot.models import Job, JobStatus
from application_bot.scoring import score_job


def _job(description: str, *, external_id: str = "a") -> Job:
    return Job(
        external_id=external_id,
        source="greenhouse",
        source_url="https://lattice.com/job?gh_jid=123",
        apply_url="https://lattice.com/job?gh_jid=123",
        company="Lattice",
        title="Senior Revenue Operations Manager",
        location="Remote - US",
        description=description,
    )


def test_dedupe_is_stable_across_jd_text_changes(tmp_path):
    database = Database(tmp_path / "crm.sqlite")
    database.initialize()
    # Same posting, JD text drifted between scans (whitespace / "posted N days ago").
    first_id, created1 = database.upsert_job(_job("Own revenue operations. Posted 2 days ago."))
    second_id, created2 = database.upsert_job(_job("Own revenue operations.  Posted 5 days ago.", external_id="b"))
    assert created1 is True and created2 is False
    assert first_id == second_id
    assert len(database.list_jobs()) == 1


def test_applied_status_survives_rediscovery(tmp_path):
    database = Database(tmp_path / "crm.sqlite")
    database.initialize()
    job_id, _ = database.upsert_job(_job("Own revenue operations."))
    database.mark_applied(job_id)
    assert database.get_job(job_id).status == "APPLIED"
    # A later scan with shifted JD text must NOT create a new row or reset status.
    again_id, created = database.upsert_job(_job("Own revenue operations — updated.", external_id="c"))
    assert again_id == job_id and created is False
    assert database.get_job(job_id).status == "APPLIED"
    assert len(database.list_jobs()) == 1


def test_executive_business_partner_is_off_lane():
    config = deepcopy(DEFAULT_CONFIG)
    job = Job(
        external_id="ebp", source="ashby", source_url="u", apply_url="https://jobs.ashbyhq.com/vanta/x",
        company="Vanta", title="Senior Executive Business Partner",
        location="Remote - US",
        description="Support executives with scheduling, travel, and operations.",
    )
    result = score_job(job, config)
    assert str(result.verdict) == "NOT_WORTH_TIME"


def test_revops_title_still_scores_as_fit():
    config = deepcopy(DEFAULT_CONFIG)
    job = Job(
        external_id="ro", source="greenhouse", source_url="u", apply_url="https://x/apply",
        company="Acme", title="Director, Revenue Operations",
        location="Remote - US",
        description="Own revenue operations, GTM systems, and marketing operations.",
    )
    result = score_job(job, config)
    assert str(result.verdict) != "NOT_WORTH_TIME"
