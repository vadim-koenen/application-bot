from __future__ import annotations

import argparse
import json
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
from application_bot.config import load_config
from application_bot.confirmations import ImportedEmailConfirmationTracker
from application_bot.database import Database
from application_bot.email_service import (
    queue_email_applications,
    send_email_applications,
)
from application_bot.packets import export_packet, generate_packet, packet_to_dict
from application_bot.pipeline import run_dry_pipeline, scan_registry
from application_bot.policy import evaluate_job_submission_policy
from application_bot.reporting import write_daily_report
from application_bot.scheduler import run_scheduler_once, scheduler_status
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


def command_scan(args: argparse.Namespace, config: dict[str, Any]) -> int:
    database = _db(args, config)
    registry = args.registry or args.company_registry
    if registry:
        if args.source and args.source not in {"greenhouse", "lever", "ashby"}:
            raise ValueError("--registry can only be combined with an ATS source")
        result = scan_registry(
            database,
            registry,
            limit=args.limit,
            source_filter=args.source,
        )
        result["dry_run"] = True
        _print(result)
        return 0
    if not args.source:
        raise ValueError("scan requires --source or --registry")

    run_id = database.start_source_run(
        args.source,
        {"input": args.input, "dry_run": True},
    )
    try:
        if args.source in {"greenhouse", "lever", "ashby"}:
            raise ValueError(f"{args.source} requires --registry")
        adapter = ADAPTERS[args.source]()
        jobs = adapter.discover_jobs(input_path=args.input)
        jobs = jobs[: args.limit] if args.limit >= 0 else jobs
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


def command_export_packets(args: argparse.Namespace, config: dict[str, Any]) -> int:
    database = _db(args, config)
    output_root = args.out or config["export_path"]
    exported: list[str] = []
    skipped: list[dict[str, Any]] = []
    for job in database.list_jobs(scored_only=True):
        policy = evaluate_job_submission_policy(job, config)
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
    policy = evaluate_job_submission_policy(job, config)
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


def command_run_dry_pipeline(
    args: argparse.Namespace,
    config: dict[str, Any],
) -> int:
    result = run_dry_pipeline(
        database_path=args.db or config["database_path"],
        registry_path=args.registry or config["live_company_registry"],
        output_root=args.out or config["export_path"],
        config=config,
        limit=args.limit,
    )
    _print(result)
    return 0


def command_queue_email_applications(
    args: argparse.Namespace,
    config: dict[str, Any],
) -> int:
    database = _db(args, config)
    _print(queue_email_applications(database, config))
    return 0


def command_send_email_applications(
    args: argparse.Namespace,
    config: dict[str, Any],
) -> int:
    database = _db(args, config)
    result = send_email_applications(
        database,
        config,
        output_root=args.out or config["export_path"],
        live=bool(args.live),
        approval_phrase=args.approval_phrase or "",
    )
    _print(result)
    return 0


def command_daily_report(args: argparse.Namespace, config: dict[str, Any]) -> int:
    database = _db(args, config)
    _print(write_daily_report(database, args.out))
    return 0


def command_scheduler(args: argparse.Namespace, config: dict[str, Any]) -> int:
    if not args.run_once:
        _print(
            {
                "scheduler": scheduler_status(config),
                "message": (
                    "Scheduler is not installed or running. Use --run-once or "
                    "configure launchctl/cron from docs/SCHEDULER.md."
                ),
            }
        )
        return 0
    result = run_scheduler_once(
        config=config,
        registry_path=args.registry or config["live_company_registry"],
        database_path=args.db or config["database_path"],
        output_root=args.out or config["export_path"],
        limit=args.limit,
    )
    _print(result)
    return 0


def command_import_confirmations(
    args: argparse.Namespace,
    config: dict[str, Any],
) -> int:
    database = _db(args, config)
    tracker = ImportedEmailConfirmationTracker()
    _print(tracker.import_messages(args.input, database))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="application-bot",
        description="Compliance-first job discovery, scoring, packet generation, and CRM.",
    )
    parser.add_argument(
        "--config",
        dest="config_path",
        default=None,
        help="YAML configuration path",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser("init-db", help="Initialize the SQLite CRM")
    init_db.add_argument("--db")
    init_db.set_defaults(handler=command_init_db)

    scan = subparsers.add_parser("scan", help="Discover and import jobs")
    scan.add_argument("--source", choices=sorted(ADAPTERS))
    scan.add_argument("--input", help="JSON file for manual/review/email sources")
    scan.add_argument("--company-registry", help="Legacy alias for --registry")
    scan.add_argument("--registry", help="YAML company registry for ATS sources")
    scan.add_argument("--dry-run", action="store_true", help="Explicit safe scan mode")
    scan.add_argument("--limit", type=int, default=25)
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

    pipeline = subparsers.add_parser(
        "run-dry-pipeline",
        help="Run discovery, scoring, packets, previews, and reports without submission",
    )
    pipeline.add_argument("--registry")
    pipeline.add_argument("--db")
    pipeline.add_argument("--out")
    pipeline.add_argument("--limit", type=int, default=25)
    pipeline.set_defaults(handler=command_run_dry_pipeline)

    queue_email = subparsers.add_parser(
        "queue-email-applications",
        help="Queue packet-backed email-to-apply opportunities",
    )
    queue_email.add_argument("--db")
    queue_email.set_defaults(handler=command_queue_email_applications)

    send_email = subparsers.add_parser(
        "send-email-applications",
        help="Generate previews or request a separately authorized live email send",
    )
    send_email.add_argument("--db")
    send_email.add_argument("--out")
    mode = send_email.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Generate .eml previews")
    mode.add_argument("--live", action="store_true", help="Request guarded live sending")
    send_email.add_argument("--approval-phrase")
    send_email.set_defaults(handler=command_send_email_applications)

    daily = subparsers.add_parser(
        "daily-report",
        help="Write Markdown and JSON daily reports",
    )
    daily.add_argument("--db")
    daily.add_argument("--out", required=True)
    daily.set_defaults(handler=command_daily_report)

    scheduler = subparsers.add_parser(
        "scheduler",
        help="Inspect scheduler config or run one dry pipeline cycle",
    )
    scheduler.add_argument("--config", dest="scheduler_config_path")
    scheduler.add_argument("--run-once", action="store_true")
    scheduler.add_argument("--registry")
    scheduler.add_argument("--db")
    scheduler.add_argument("--out")
    scheduler.add_argument("--limit", type=int, default=25)
    scheduler.set_defaults(handler=command_scheduler)

    confirmations = subparsers.add_parser(
        "import-confirmations",
        help="Import and classify Gmail-style JSON fixtures",
    )
    confirmations.add_argument("--input", required=True)
    confirmations.add_argument("--db")
    confirmations.set_defaults(handler=command_import_confirmations)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config_path = getattr(args, "scheduler_config_path", None) or args.config_path
    config = load_config(config_path)
    try:
        return int(args.handler(args, config))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
