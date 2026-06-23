"""M32: JSearch (RapidAPI / Google-for-Jobs) adapter + discovery.

Aggregates LinkedIn/Indeed/ZipRecruiter/Glassdoor listings via a legitimate API
(no scraping). The adapter normalizes results to Job; discover_jsearch keeps only
fresh roles, scores them, and is a no-op without RAPIDAPI_KEY. Injected transport,
no network/key.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from application_bot.adapters import JSearchAdapter
from application_bot.config import DEFAULT_CONFIG
from application_bot.database import Database
from application_bot.pipeline import discover_jsearch


def _result(jid: str, title: str, posted: str, remote: bool = True) -> dict:
    return {
        "job_id": jid,
        "job_title": title,
        "employer_name": "Acme",
        "job_description": "Own marketing operations, revenue operations, GTM systems.",
        "job_apply_link": f"https://www.linkedin.com/jobs/view/{jid}",
        "job_city": "Dallas",
        "job_state": "Texas",
        "job_country": "US",
        "job_is_remote": remote,
        "job_posted_at_datetime_utc": posted,
        "job_min_salary": 180000,
        "job_max_salary": 220000,
    }


def test_adapter_normalizes_result():
    now = datetime.now(UTC).isoformat()
    payload = {"data": [_result("1", "Director, Marketing Operations", now)]}
    jobs = JSearchAdapter(transport=lambda _u: payload).discover_jobs(
        what="marketing operations director"
    )
    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "jsearch"
    assert job.external_id == "jsearch:1"
    assert job.apply_url.startswith("https://www.linkedin.com/jobs/view/")
    assert job.location == "Remote"  # job_is_remote -> Remote (passes geo gate)
    assert job.remote_type == "remote"


def test_discover_jsearch_keeps_fresh_scores_and_inserts(tmp_path):
    now = datetime.now(UTC)
    payload = {
        "data": [
            _result("fresh", "Director, Marketing Operations", now.isoformat()),
            _result("stale", "Director, RevOps", (now - timedelta(days=5)).isoformat()),
        ]
    }
    database = Database(tmp_path / "crm.sqlite")
    database.initialize()
    result = discover_jsearch(
        database,
        deepcopy(DEFAULT_CONFIG),
        hours=24,
        queries=["marketing operations director"],
        transport=lambda _u: payload,
        api_key="rapid-key",
    )
    assert result["enabled"] is True
    assert result["jobs_inserted"] == 1
    assert result["dropped_stale"] == 1
    jobs = database.list_jobs()
    assert [j.external_id for j in jobs] == ["jsearch:fresh"]
    assert jobs[0].score is not None


def test_discover_jsearch_noop_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    database = Database(tmp_path / "crm.sqlite")
    database.initialize()
    result = discover_jsearch(database, deepcopy(DEFAULT_CONFIG))
    assert result["enabled"] is False
    assert "RAPIDAPI_KEY" in result["reason"]
