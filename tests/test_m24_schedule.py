"""M24: scheduler entrypoint + launchd plist.

`--auto` runs discovery then emails the digest; the daily launchd plist invokes
it. Tested with a fake API (no network) plus a plist sanity check.
"""

from __future__ import annotations

from pathlib import Path
import plistlib

import app_main


class FakeAPI:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def run_discovery(self, hours: int = 24, limit: int = 50) -> dict:
        self.calls.append(("discover", hours))
        return {
            "jobs_inserted": 2,
            "packets_ready": 1,
            "dropped_stale": 0,
            "dropped_undated": 0,
            "network_status": "complete",
        }

    def email_me(self, job_id=None, live: bool = False) -> dict:
        self.calls.append(("email", live))
        return {"mode": "LIVE" if live else "DRY_RUN", "roles": 1, "attachments": 2}


def test_auto_runs_discovery_then_email(monkeypatch):
    fake = FakeAPI()
    monkeypatch.setattr(app_main, "build_api", lambda: fake)
    rc = app_main.main(["--auto", "--hours", "24", "--live"])
    assert rc == 0
    assert fake.calls == [("discover", 24), ("email", True)]


def test_email_default_is_dry_run(monkeypatch):
    fake = FakeAPI()
    monkeypatch.setattr(app_main, "build_api", lambda: fake)
    app_main.main(["--email"])
    assert fake.calls == [("email", False)]


def test_daily_plist_is_valid_and_calls_auto():
    path = Path("launchd/com.vadim.jobapply-daily.plist")
    data = plistlib.loads(path.read_bytes())
    assert data["Label"] == "com.vadim.jobapply-daily"
    assert "--auto" in data["ProgramArguments"]
    assert data["StartCalendarInterval"]["Hour"] == 8
