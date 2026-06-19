from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Any

from application_bot.database import Database


def build_daily_report(
    database: Database,
    *,
    day: str | None = None,
    pipeline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = database.daily_metrics(day or date.today().isoformat())
    report["pipeline"] = pipeline or {}
    actions: list[str] = []
    if report["verdicts"]["APPLY_PRIORITY"]:
        actions.append("Review APPLY_PRIORITY packets first.")
    if report["verdicts"]["GOOD_FIT"]:
        actions.append("Review GOOD_FIT packets after priority roles.")
    if report["email_previews_generated"]:
        actions.append("Inspect email previews; do not send without explicit live approval.")
    if report["compliance_blocks"]:
        actions.append("Resolve compliance blocks manually; never bypass access controls.")
    if not actions:
        actions.append(
            "Enable another verified public ATS source or import additional jobs manually."
        )
    report["next_recommended_actions"] = actions
    return report


def render_daily_report_markdown(report: dict[str, Any]) -> str:
    verdicts = report["verdicts"]
    actions = "\n".join(
        f"- {action}" for action in report["next_recommended_actions"]
    )
    pipeline = report.get("pipeline") or {}
    network_status = pipeline.get("network_status", "not_reported")
    real_network_scan = bool(pipeline.get("real_network_scan", False))
    return f"""# Application Bot Daily Report — {report['date']}

## Activity

- Jobs discovered: {report['jobs_discovered']}
- Jobs scored: {report['jobs_scored']}
- APPLY_PRIORITY: {verdicts['APPLY_PRIORITY']}
- GOOD_FIT: {verdicts['GOOD_FIT']}
- MAYBE: {verdicts['MAYBE']}
- NOT_WORTH_TIME: {verdicts['NOT_WORTH_TIME']}
- BLOCKED: {verdicts['BLOCKED']}
- Packets exported: {report['packets_exported']}
- Email previews generated: {report['email_previews_generated']}
- Applications submitted: {report['applications_submitted']}
- Compliance blocks: {report['compliance_blocks']}

## Network Scan

- Real network scan: {str(real_network_scan).lower()}
- Network status: {network_status}

## Next Recommended Actions

{actions}

## Safety State

The operational pipeline is dry-run. It does not submit ATS applications or
send email without separate live flags, complete credentials, and an exact
approval phrase.
"""


def write_daily_report(
    database: Database,
    output: str | Path,
    *,
    day: str | None = None,
    pipeline: dict[str, Any] | None = None,
    directory_mode: bool = False,
) -> dict[str, Any]:
    report = build_daily_report(database, day=day, pipeline=pipeline)
    target = Path(output)
    if directory_mode or target.is_dir():
        base = target / f"daily-report-{report['date']}"
    elif target.suffix.lower() in {".md", ".json"}:
        base = target.with_suffix("")
    else:
        base = target
    base.parent.mkdir(parents=True, exist_ok=True)
    markdown_path = base.with_suffix(".md")
    json_path = base.with_suffix(".json")
    markdown_path.write_text(
        render_daily_report_markdown(report),
        encoding="utf-8",
    )
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        **report,
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
    }
