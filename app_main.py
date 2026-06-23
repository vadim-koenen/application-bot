#!/usr/bin/env python3
"""app_main.py — M23: desktop app entrypoint (pywebview) + headless CLI.

Runs the job-application assistant as a native macOS window (pywebview), or
headless for verification. The window loads app_ui/index.html and hands it a
`JobAppAPI` instance as `js_api`, so the UI calls Python directly (no server).

  GUI  (on the Mac):   python3 app_main.py             # opens the app window
  CLI  (headless):     python3 app_main.py --cli       # prints status + outstanding roles
                       python3 app_main.py --discover   # live last-24h scan
                       python3 app_main.py --email      # dry-run digest to yourself

Package into a dock app:  python3 setup_app.py py2app

BOUNDARY: discovers, scores, tailors, and emails the user. Never auto-submits
web-form applications (the only auto-submit is the gated email-apply path).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parent

from app_api import JobAppAPI

UI_INDEX = APP_DIR / "app_ui" / "index.html"


def build_api() -> JobAppAPI:
    return JobAppAPI()


def run_cli() -> int:
    api = build_api()
    status = api.get_status()
    print(
        f"Roles: {status['total']} total · {status['outstanding']} outstanding · "
        f"{status['applied']} applied\n"
    )
    roles = api.list_roles("outstanding")["roles"]
    for role in roles[:15]:
        link = role["apply_url"] if role["is_form"] else "email/recruiter"
        print(f"  [{role['score']}] {role['company']} — {role['title']}  ({link})")
    if not roles:
        print("  (no outstanding ready roles — run --discover)")
    return 0


def run_discovery(hours: int) -> int:
    result = build_api().run_discovery(hours=hours)
    print(
        f"[discover] inserted={result['jobs_inserted']} "
        f"stale_dropped={result['dropped_stale']} "
        f"undated_dropped={result['dropped_undated']} "
        f"ready={result['packets_ready']} net={result['network_status']}"
    )
    return 0


def run_auto(hours: int) -> int:
    """Scheduler entrypoint (launchd): live last-N-hours scan to populate the app."""
    scan = build_api().run_discovery(hours=hours)
    print(
        f"[auto] discovered={scan['jobs_inserted']} ready={scan['packets_ready']} "
        f"net={scan['network_status']}"
    )
    return 0


def run_gui() -> int:
    try:
        import webview  # pywebview
    except ImportError:
        print(
            "pywebview not installed. Run: pip install pywebview\n"
            "(or use the headless CLI: python3 app_main.py --cli)",
            file=sys.stderr,
        )
        return 1
    api = build_api()
    webview.create_window(
        "Job Apply Assistant",
        url=str(UI_INDEX),
        js_api=api,
        width=980,
        height=760,
        min_size=(760, 560),
    )
    webview.start()
    return 0


def main(argv=None) -> int:
    os.chdir(APP_DIR)  # resolve config/db/.env relative to the app dir
    parser = argparse.ArgumentParser(description="Job application desktop app")
    parser.add_argument("--cli", action="store_true", help="Headless: status + outstanding roles.")
    parser.add_argument("--discover", action="store_true", help="Live last-N-hours scan.")
    parser.add_argument("--hours", type=int, default=24, help="Discovery freshness window.")
    parser.add_argument("--auto", action="store_true", help="Scheduler: discover last-N-hours to populate the app.")
    args = parser.parse_args(argv)
    if args.auto:
        return run_auto(args.hours)
    if args.discover:
        return run_discovery(args.hours)
    return run_cli() if args.cli else run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
