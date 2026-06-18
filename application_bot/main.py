from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from application_bot.adapters import (
    AshbyAdapter,
    EmailToApplyAdapter,
    GreenhouseAdapter,
    IndeedConnectorAdapter,
    LeverAdapter,
    LinkedInReviewQueueAdapter,
    ManualJsonAdapter,
    ZipConnectorAdapter,
)
from application_bot.config import load_company_registry, load_config
from application_bot.database import Database
from application_bot.packets import export_packet, generate_packet, packet_to_dict
from application_bot.policy import evaluate_submission_policy
from application_bot.scoring import score_job


ADAPTERS = {
    "manual_json": ManualJsonAdapter,
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "ashby": AshbyAdapter,
    "email_to_apply": EmailToApplyAdapter,
    "linkedin_review_queue": LinkedInReviewQueueAdapter,
    "indeed_connector": IndeedConnectorAdapter,
    "zip_connector": ZipConnectorAdapter,
}


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _db(args: argparse.Namespace, config: dict[str, Any]) -> Database:
    path = args.db or config["database_path"]
    database = Database(path)
    database.initialize()
    return database


def command_init_db(args: argparse.Namespace, config: dict[str, Any]) -> int:
    database = _db(args, config)
    _print({"database": str(database.path), "initialized": True})
    return 0


def _scan_registry(
    database: Database,
    source: str,
    registry_path: str,
) -> tuple[int, int, list[str]]:
    jobs_seen = 0
    jobs_written = 0
    companies_scanned: list[str] = []
    for company in load_company_registry(registry_path):
        database.register_company(company)
        if not company.get("enabled", False) or company.get("ats") != source:
            continue
        adapter = ADAPTERS[source]()
        kwargs = {"company": company["name"]}
        if source == "greenhouse":
            kwargs["board_token"] = company["board_token"]
        elif source == "lever":
            kwargs["site"] = company["site"]
        elif source == "ashby":
            kwargs["board_name"] = company["board_name"]
        jobs = adapter.discover_jobs(**kwargs)
        companies_scanned.append(company["name"])
        jobs_seen += len(jobs)
        for job in jobs:
            _, created = database.upsert_job(job)
            jobs_written += int(created)
    return jobs_seen, jobs_written, companies_scanned


def command_scan(args: argparse.Namespace, config: dict[str, Any]) -> int:
    database = _db(args, config)
    run_id = database.start_source_run(
        args.source,
        {"input": args.input, "company_registry": args.company_registry},
    )
    try:
        if args.source in {"greenhouse", "lever", "ashby"}:
            if not args.company_registry:
                raise ValueError(f"{args.source} requires --company-registry")
            seen, written, companies = _scan_registry(
                database, args.source, args.company_registry
            )
            details = {"companies_scanned": companies}
        else:
            adapter = ADAPTERS[args.source]()
            jobs = adapter.discover_jobs(input_path=args.input)
            seen = len(jobs)
            written = 0
            for job in jobs:
                _, created = database.upsert_job(job)
                written += int(created)
            details = {}
        database.finish_source_run(
            run_id,
            status="COMPLETED",
            jobs_seen=seen,
            jobs_written=written,
            details=details,
        )
    except Exception as exc:
        database.finish_source_run(
            run_id,
            status="FAILED",
            jobs_seen=0,
            jobs_written=0,
            details={"error": str(exc)},
        )
        raise
    _print(
        {
            "source": args.source,
            "jobs_seen": seen,
            "jobs_inserted": written,
            "duplicates": seen - written,
            **details,
        }
    )
    return 0


def command_score(args: argparse.Namespace, config: dict[str, Any]) -> int:
    database = _db(args, config)
    jobs = database.list_jobs()
    results = []
    for job in jobs:
        result = score_job(job, config)
        database.save_score(int(job.id), result)
        results.append(
            {
                "job_id": job.id,
                "company": job.company,
                "title": job.title,
                "score": result.score,
                "verdict": str(result.verdict),
            }
        )
    _print({"scored": len(results), "jobs": results})
    return 0


def _policy_for_job(job: Any, config: dict[str, Any]):
    flags: list[str] = []
    corpus = f"{job.description} {job.requirements}".lower()
    if "captcha" in corpus:
        flags.append("captcha")
    if "login required" in corpus or "create an account" in corpus:
        flags.append("login_required")
    if "legal attestation" in corpus:
        flags.append("unknown_legal_attestation")
    recipient = None
    if job.apply_url.lower().startswith("mailto:"):
        recipient = job.apply_url.split(":", 1)[1].split("?", 1)[0]
    else:
        try:
            raw_payload = json.loads(job.raw_payload_json or "{}")
            recipient = (
                raw_payload.get("recipient")
                or raw_payload.get("apply_email")
                or raw_payload.get("email")
            )
        except json.JSONDecodeError:
            recipient = None
    return evaluate_submission_policy(
        job.source,
        flags=flags,
        live_apply_enabled=bool(config.get("live_apply_enabled")),
        recipient=recipient,
    )


def command_export_packets(args: argparse.Namespace, config: dict[str, Any]) -> int:
    database = _db(args, config)
    output_root = args.out or config["export_path"]
    exported: list[str] = []
    skipped: list[dict[str, Any]] = []
    for job in database.list_jobs(scored_only=True):
        policy = _policy_for_job(job, config)
        if str(job.verdict) in {"NOT_WORTH_TIME", "BLOCKED"} or str(policy.decision) == "BLOCKED":
            skipped.append(
                {"job_id": job.id, "verdict": job.verdict, "policy": str(policy.decision)}
            )
            continue
        packet = generate_packet(job, config, policy)
        path = export_packet(job, packet, output_root)
        database.save_packet(int(job.id), str(path), packet_to_dict(packet))
        exported.append(str(path))
    _print({"exported": len(exported), "paths": exported, "skipped": skipped})
    return 0


def command_report(args: argparse.Namespace, config: dict[str, Any]) -> int:
    database = _db(args, config)
    report = database.report()
    if args.out:
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        report["exported_to"] = str(output)
    _print(report)
    return 0


def command_mark_applied(args: argparse.Namespace, config: dict[str, Any]) -> int:
    database = _db(args, config)
    database.mark_applied(args.job_id, args.notes)
    _print({"job_id": args.job_id, "status": "APPLIED"})
    return 0


def command_policy_check(args: argparse.Namespace, config: dict[str, Any]) -> int:
    database = _db(args, config)
    job = database.get_job(args.job_id)
    if not job:
        raise ValueError(f"Job {args.job_id} does not exist")
    policy = _policy_for_job(job, config)
    _print(
        {
            "job_id": job.id,
            "source": job.source,
            "decision": str(policy.decision),
            "reasons": policy.reasons,
            "requires_human_review": policy.requires_human_review,
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="application-bot",
        description="Compliance-first job discovery, scoring, packet generation, and CRM.",
    )
    parser.add_argument("--config", default=None, help="YAML configuration path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser("init-db", help="Initialize the SQLite CRM")
    init_db.add_argument("--db")
    init_db.set_defaults(handler=command_init_db)

    scan = subparsers.add_parser("scan", help="Discover and import jobs")
    scan.add_argument("--source", choices=sorted(ADAPTERS), required=True)
    scan.add_argument("--input", help="JSON file for manual/review/email sources")
    scan.add_argument("--company-registry", help="YAML company registry for ATS sources")
    scan.add_argument("--db")
    scan.set_defaults(handler=command_scan)

    score = subparsers.add_parser("score", help="Score all jobs in the CRM")
    score.add_argument("--db")
    score.set_defaults(handler=command_score)

    export = subparsers.add_parser("export-packets", help="Export eligible packets")
    export.add_argument("--db")
    export.add_argument("--out")
    export.set_defaults(handler=command_export_packets)

    report = subparsers.add_parser("report", help="Print a JSON CRM report")
    report.add_argument("--db")
    report.add_argument("--out", help="Optional JSON export path")
    report.set_defaults(handler=command_report)

    applied = subparsers.add_parser("mark-applied", help="Record a completed application")
    applied.add_argument("--job-id", type=int, required=True)
    applied.add_argument("--notes", default="")
    applied.add_argument("--db")
    applied.set_defaults(handler=command_mark_applied)

    policy = subparsers.add_parser("policy-check", help="Evaluate submission policy")
    policy.add_argument("--job-id", type=int, required=True)
    policy.add_argument("--db")
    policy.set_defaults(handler=command_policy_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)
    try:
        return int(args.handler(args, config))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
