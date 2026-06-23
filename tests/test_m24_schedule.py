"""M24/M28: scheduler entrypoint + launchd plist.

`--auto` runs a live last-N-hours discovery to populate the app (no email). The
daily launchd plist invokes it. Tested with a fake API (no network) plus a plist
sanity check.
"""

from __future__ import annotations

from pathlib import Path
import plistlib

import app_main


class FakeAPI:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def run_discovery(self, hours: int = 24, limit: int = 600) -> dict:
        self.calls.append(("discover", hours))
        return {
            "jobs_inserted": 2,
            "packets_ready": 1,
            "dropped_stale": 0,
            "dropped_undated": 0,
            "network_status": "complete",
        }


def test_auto_runs_discovery(monkeypatch):
    fake = FakeAPI()
    monkeypatch.setattr(app_main, "build_api", lambda: fake)
    rc = app_main.main(["--auto", "--hours", "24"])
    assert rc == 0
    assert fake.calls == [("discover", 24)]


def test_daily_plist_is_valid_and_calls_auto():
    path = Path("launchd/com.vadim.jobapply-daily.plist")
    data = plistlib.loads(path.read_bytes())
    assert data["Label"] == "com.vadim.jobapply-daily"
    assert "--auto" in data["ProgramArguments"]
    assert "--live" not in data["ProgramArguments"]  # email removed
    assert data["StartCalendarInterval"]["Hour"] == 8
