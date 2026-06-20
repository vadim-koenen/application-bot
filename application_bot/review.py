from __future__ import annotations

import csv
from html import escape
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
        "source",
        "score",
        "verdict",
        "submission_policy",
        "packet_status",
        "claim_gaps",
        "apply_url",
        "recommended_next_action",
        "reason_codes",
        "packet_path",
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


def export_review_html(
    database: Database,
    output: str | Path,
) -> dict[str, Any]:
    rows = database.review_queue_rows()
    target = Path(output)
    if target.suffix.lower() != ".html":
        target = target.with_suffix(".html")
    target.parent.mkdir(parents=True, exist_ok=True)
    statuses = _status_counts(rows)
    verdicts: dict[str, int] = {}
    for row in rows:
        verdict = str(row["verdict"])
        verdicts[verdict] = verdicts.get(verdict, 0) + 1

    cards = "".join(
        f'<div class="metric"><strong>{escape(label)}</strong><span>{value}</span></div>'
        for label, value in (
            ("Total", len(rows)),
            ("Packet ready", statuses.get("PACKET_READY", 0)),
            ("Claim-gap review", statuses.get("REVIEW_PACKET_CLAIM_GAPS", 0)),
            ("Maybe", verdicts.get("MAYBE", 0)),
            ("Not worth time", verdicts.get("NOT_WORTH_TIME", 0)),
        )
    )
    companies = sorted({str(row["company"]) for row in rows})
    sources = sorted({str(row["source"]) for row in rows})
    options = lambda values: "".join(
        f'<option value="{escape(value)}">{escape(value)}</option>' for value in values
    )
    table_rows = []
    gap_rows = []
    for row in rows:
        packet_link = (
            f'<a href="{escape(str(row["packet_path"]))}">packet</a>'
            if row["packet_path"]
            else ""
        )
        gaps = ", ".join(row["claim_gaps"])
        table_rows.append(
            "<tr "
            f'data-verdict="{escape(str(row["verdict"]))}" '
            f'data-status="{escape(str(row["packet_status"]))}" '
            f'data-source="{escape(str(row["source"]))}" '
            f'data-company="{escape(str(row["company"]))}">'
            f"<td>{escape(str(row['company']))}</td>"
            f"<td>{escape(str(row['title']))}</td>"
            f"<td>{row['score']}</td>"
            f"<td>{escape(str(row['verdict']))}</td>"
            f"<td>{escape(str(row['packet_status']))}</td>"
            f"<td>{escape(gaps)}</td>"
            f'<td><a href="{escape(str(row["apply_url"]))}">apply</a> {packet_link}</td>'
            "</tr>"
        )
        for gap in row["claim_gaps"]:
            gap_rows.append(
                f"<tr><td>{escape(str(row['company']))}</td>"
                f"<td>{escape(str(row['title']))}</td>"
                f"<td>{escape(gap)}</td>"
                f"<td>{escape(str(row['recommended_next_action']))}</td></tr>"
            )
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Application Bot Review Queue</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem;color:#172033;background:#f5f7fb}}
h1,h2{{color:#101828}} .cards{{display:flex;gap:1rem;flex-wrap:wrap}}
.metric{{background:white;border:1px solid #dbe2ea;border-radius:10px;padding:1rem;min-width:140px;display:flex;flex-direction:column}}
.metric span{{font-size:1.7rem}} .filters{{margin:1rem 0;display:flex;gap:.75rem;flex-wrap:wrap}}
select{{padding:.5rem}} table{{border-collapse:collapse;width:100%;background:white}}
th,td{{border:1px solid #dbe2ea;padding:.55rem;text-align:left;vertical-align:top}}
th{{background:#e9eef6}} a{{color:#155eef}}
</style>
</head>
<body>
<h1>Application Bot Review Queue</h1>
<div class="cards">{cards}</div>
<div class="filters">
<select id="verdict"><option value="">All verdicts</option>{options(sorted(verdicts))}</select>
<select id="status"><option value="">All statuses</option>{options(sorted(statuses))}</select>
<select id="source"><option value="">All sources</option>{options(sources)}</select>
<select id="company"><option value="">All companies</option>{options(companies)}</select>
</div>
<h2>Jobs</h2>
<table><thead><tr><th>Company</th><th>Title</th><th>Score</th><th>Verdict</th><th>Packet status</th><th>Claim gaps</th><th>Links</th></tr></thead>
<tbody id="jobs">{''.join(table_rows)}</tbody></table>
<h2>Claim gaps</h2>
<table><thead><tr><th>Company</th><th>Title</th><th>Gap</th><th>Action</th></tr></thead><tbody>{''.join(gap_rows)}</tbody></table>
<script>
const ids=['verdict','status','source','company'];
function filterRows(){{
 const values=Object.fromEntries(ids.map(id=>[id,document.getElementById(id).value]));
 document.querySelectorAll('#jobs tr').forEach(row=>{{
  row.hidden=ids.some(id=>values[id] && row.dataset[id]!==values[id]);
 }});
}}
ids.forEach(id=>document.getElementById(id).addEventListener('change',filterRows));
</script>
</body></html>"""
    target.write_text(html, encoding="utf-8")
    return {
        "jobs": len(rows),
        "html_path": str(target),
        "packet_status_counts": statuses,
        "claim_gaps": sum(len(row["claim_gaps"]) for row in rows),
    }


def _status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row["packet_status"])
        counts[status] = counts.get(status, 0) + 1
    return counts
