from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from application_bot.database import Database


def source_report(database: Database) -> dict[str, Any]:
    return database.source_quality_report()


def _review_base(output: str | Path) -> Path:
    target = Path(output)
    if target.suffix.lower() in {".md", ".json", ".csv"}:
        return target.with_suffix("")
    return target


def render_review_markdown(rows: list[dict[str, Any]]) -> str:
    sections = ["# Application Bot Review Queue", ""]
    if not rows:
        return "\n".join(sections + ["No scored jobs are available.", ""])
    for row in rows:
        sections.extend(
            [
                f"## {row['company']} — {row['title']}",
                "",
                f"- Score: {row['score']}",
                f"- Verdict: {row['verdict']}",
                f"- Submission policy: {row['submission_policy']}",
                f"- Packet status: {row['packet_status']}",
                f"- Claim gaps: {', '.join(row['claim_gaps']) or 'None'}",
                f"- Reason codes: {', '.join(row['reason_codes']) or 'None'}",
                f"- Apply URL: {row['apply_url'] or 'Not provided'}",
                f"- Recommended next action: {row['recommended_next_action']}",
                "",
            ]
        )
    return "\n".join(sections)


def export_review_queue(
    database: Database,
    output: str | Path,
) -> dict[str, Any]:
    rows = database.review_queue_rows()
    base = _review_base(output)
    base.parent.mkdir(parents=True, exist_ok=True)
    markdown_path = base.with_suffix(".md")
    json_path = base.with_suffix(".json")
    markdown_path.write_text(render_review_markdown(rows), encoding="utf-8")
    json_path.write_text(
        json.dumps({"jobs": rows}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "jobs": len(rows),
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
        "packet_status_counts": _status_counts(rows),
    }


def export_review_csv(
    database: Database,
    output: str | Path,
) -> dict[str, Any]:
    rows = database.review_queue_rows()
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "job_id",
        "company",
        "title",
        "score",
        "verdict",
        "submission_policy",
        "packet_status",
        "claim_gaps",
        "apply_url",
        "recommended_next_action",
        "reason_codes",
    ]
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            serialized = dict(row)
            serialized["claim_gaps"] = "|".join(row["claim_gaps"])
            serialized["reason_codes"] = "|".join(row["reason_codes"])
            writer.writerow(serialized)
    return {
        "jobs": len(rows),
        "csv_path": str(target),
        "packet_status_counts": _status_counts(rows),
    }


def _status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row["packet_status"])
        counts[status] = counts.get(status, 0) + 1
    return counts
