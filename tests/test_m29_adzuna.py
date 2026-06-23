"""M29: Adzuna market-wide adapter + discovery.

The adapter normalizes Adzuna results to Job; discover_adzuna keeps only fresh
roles, scores them, and is a no-op without API keys. Uses an injected transport
(no network, no real key).
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from application_bot.adapters import AdzunaAdapter
from application_bot.config import DEFAULT_CONFIG
from application_bot.database import Database
from application_bot.pipeline import discover_adzuna


def _result(ext: str, title: str, created: str) -> dict:
    return {
        "id": ext,
        "title": title,
        "company": {"display_name": "Acme"},
        "location": {"display_name": "Remote - United States"},
        "description": "Own marketing operations, revenue operations, GTM systems.",
        "redirect_url": f"https://www.adzuna.com/land/ad/{ext}",
        "created": created,
        "salary_min": 180000,
        "salary_max": 220000,
    }


def test_adapter_normalizes_result():
    now = datetime.now(UTC).isoformat()
    payload = {"results": [_result("1", "Director, Marketing Operations", now)]}
    jobs = AdzunaAdapter(transport=lambda _url: payload).discover_jobs(
        app_id="x", app_key="y", what="marketing operations director"
    )
    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "adzuna"
    assert job.external_id == "adzuna:1"
    assert job.apply_url.startswith("https://www.adzuna.com/land/ad/")
    assert job.company == "Acme"


def test_adapter_requires_keys():
    try:
        AdzunaAdapter(transport=lambda _u: {"results": []}).discover_jobs(what="x")
    except ValueError as exc:
        assert "app_id" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError without keys")


def test_discover_adzuna_keeps_fresh_scores_and_inserts(tmp_path):
    now = datetime.now(UTC)
    payload = {
        "results": [
            _result("fresh", "Director, Marketing Operations", now.isoformat()),
            _result("stale", "Director, RevOps", (now - timedelta(days=5)).isoformat()),
        ]
    }
    database = Database(tmp_path / "crm.sqlite")
    database.initialize()
    result = discover_adzuna(
        database,
        deepcopy(DEFAULT_CONFIG),
        hours=24,
        queries=["marketing operations director"],
        transport=lambda _url: payload,
        app_id="x",
        app_key="y",
    )
    assert result["enabled"] is True
    assert result["jobs_inserted"] == 1
    assert result["dropped_stale"] == 1
    jobs = database.list_jobs()
    assert [j.external_id for j in jobs] == ["adzuna:fresh"]
    assert jobs[0].score is not None  # scored


def test_discover_adzuna_noop_without_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    database = Database(tmp_path / "crm.sqlite")
    database.initialize()
    result = discover_adzuna(database, deepcopy(DEFAULT_CONFIG))
    assert result["enabled"] is False
    assert "ADZUNA_APP_ID" in result["reason"]
