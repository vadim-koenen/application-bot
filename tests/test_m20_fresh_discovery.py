"""M20: last-24h discovery filter.

The scanner can keep only roles posted within the last N hours. Date parsing
handles ISO strings (Greenhouse/Ashby) and epoch-millis (Lever); roles with no
parseable date are excluded from a fresh-only scan and counted separately.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import yaml

from application_bot.config import DEFAULT_CONFIG
from application_bot.database import Database
from application_bot.models import Job
from application_bot.pipeline import is_fresh, parse_posted_at, scan_registry


NOW = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)


def test_parse_posted_at_handles_iso_and_epoch_millis():
    iso = parse_posted_at("2026-06-22T08:00:00Z")
    assert iso == datetime(2026, 6, 22, 8, 0, tzinfo=UTC)
    # Lever createdAt: epoch milliseconds.
    epoch_ms = int(datetime(2026, 6, 22, 8, 0, tzinfo=UTC).timestamp() * 1000)
    assert parse_posted_at(epoch_ms) == datetime(2026, 6, 22, 8, 0, tzinfo=UTC)
    assert parse_posted_at(None) is None
    assert parse_posted_at("not-a-date") is None


def test_is_fresh_window():
    two_hours_ago = (NOW - timedelta(hours=2)).isoformat()
    three_days_ago = (NOW - timedelta(days=3)).isoformat()
    assert is_fresh(two_hours_ago, 24, now=NOW) is True
    assert is_fresh(three_days_ago, 24, now=NOW) is False
    assert is_fresh(None, 24, now=NOW) is None


class FakeAdapter:
    """Returns pre-built jobs with controlled posted_at values."""

    def __init__(self, jobs: list[Job]) -> None:
        self._jobs = jobs

    def discover_jobs(self, **kwargs) -> list[Job]:
        return self._jobs


def _job(ext: str, posted_at) -> Job:
    return Job(
        external_id=ext,
        source="greenhouse",
        source_url=f"https://example.com/{ext}",
        apply_url=f"https://example.com/{ext}/apply",
        company="Acme",
        title="Director, Marketing Operations",
        description="Own revenue operations and GTM systems.",
        posted_at=posted_at,
    )


def _registry(tmp_path):
    path = tmp_path / "reg.yaml"
    path.write_text(
        yaml.safe_dump(
            {"companies": [{"name": "Acme", "ats": "greenhouse",
                            "board_token": "acme", "enabled": True}]}
        ),
        encoding="utf-8",
    )
    return path


def test_scan_keeps_only_fresh_roles(tmp_path):
    now = datetime.now(UTC)
    jobs = [
        _job("fresh", (now - timedelta(hours=2)).isoformat()),
        _job("stale", (now - timedelta(days=3)).isoformat()),
        _job("undated", None),
    ]
    database = Database(tmp_path / "crm.sqlite")
    database.initialize()
    result = scan_registry(
        database,
        _registry(tmp_path),
        adapters={"greenhouse": FakeAdapter(jobs)},
        selection_config=deepcopy(DEFAULT_CONFIG),
        posted_within_hours=24,
    )
    assert result["jobs_inserted"] == 1
    assert result["dropped_stale"] == 1
    assert result["dropped_undated"] == 1
    titles = [j.external_id for j in database.list_jobs()]
    assert titles == ["fresh"]


def test_scan_without_filter_keeps_all(tmp_path):
    jobs = [_job("a", None), _job("b", "2020-01-01T00:00:00Z")]
    database = Database(tmp_path / "crm.sqlite")
    database.initialize()
    result = scan_registry(
        database,
        _registry(tmp_path),
        adapters={"greenhouse": FakeAdapter(jobs)},
        selection_config=deepcopy(DEFAULT_CONFIG),
    )
    assert result["jobs_inserted"] == 2
    assert result["posted_within_hours"] is None
