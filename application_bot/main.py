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
from application_bot.config import (
    load_answer_bank,
    load_claim_evidence,
    load_claim_inventory,
    load_config,
)
from application_bot.claims import (
    claim_counts,
    claim_gap_rows,
    export_approval_pack,
    import_claim_approvals,
    list_claims,
    update_claim_status,
)
from application_bot.confirmations import ImportedEmailConfirmationTracker
from application_bot.database import Database
from application_bot.email_service import (
    queue_email_applications,
    send_email_applications,
)
from application_bot.packets import (
    assess_packet,
    export_packet,
    generate_packet,
    packet_to_dict,
)
from application_bot.pipeline import refresh_packets, run_dry_pipeline, scan_registry
from application_bot.policy import evaluate_job_submission_policy
from application_bot.reporting import write_daily_report
from application_bot.review import (
    export_review_csv,
    export_review_html,
    export_review_queue,
    source_report,
)
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
            selection_config=config,
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
    inventory = load_claim_inventory(config["resume_claim_inventory"])
    evidence = load_claim_evidence(config["claim_evidence"])
    answer_bank = load_answer_bank(config["application_answer_bank"])
    exported: list[str] = []
    skipped: list[dict[str, Any]] = []
    for job in database.list_jobs(scored_only=True):
        policy = evaluate_job_submission_policy(job, config)
        assessment = assess_packet(job, config, policy, inventory, evidence)
        database.save_packet_assessment(
            int(job.id),
            packet_status=str(assessment.status),
            claim_gaps=assessment.claim_gaps,
            reason_codes=assessment.reason_codes,
            recommended_next_action=assessment.recommended_next_action,
            submission_policy=str(policy.decision),
        )
        if not assessment.should_export:
            skipped.append(
                {
                    "job_id": job.id,
                    "verdict": job.verdict,
                    "policy": str(policy.decision),
                    "packet_status": str(assessment.status),
                    "reason_codes": assessment.reason_codes,
                }
            )
            continue
        packet = generate_packet(
            job,
            config,
            policy,
            inventory=inventory,
            evidence=evidence,
            answer_bank=answer_bank,
            assessment=assessment,
        )
        category = (
            "ready"
            if str(assessment.status) == "PACKET_READY"
            else "review"
        )
        path = export_packet(job, packet, Path(output_root) / category)
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
    evidence = load_claim_evidence(config["claim_evidence"])
    _print(
        write_daily_report(
            database,
            args.out,
            claim_readiness=claim_counts(evidence),
        )
    )
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


def command_source_report(args: argparse.Namespace, config: dict[str, Any]) -> int:
    database = _db(args, config)
    _print(source_report(database))
    return 0


def command_review_queue(args: argparse.Namespace, config: dict[str, Any]) -> int:
    database = _db(args, config)
    _print(export_review_queue(database, args.out))
    return 0


def command_export_review_csv(
    args: argparse.Namespace,
    config: dict[str, Any],
) -> int:
    database = _db(args, config)
    _print(export_review_csv(database, args.out))
    return 0


def command_claims(args: argparse.Namespace, config: dict[str, Any]) -> int:
    evidence_path = config["claim_evidence"]
    evidence = load_claim_evidence(evidence_path)
    if args.claims_command == "list":
        _print(list_claims(evidence))
        return 0
    if args.claims_command == "gaps":
        database = _db(args, config)
        gaps = claim_gap_rows(database, evidence)
        _print({"claim_gaps_found": len(gaps), "gaps": gaps})
        return 0
    if args.claims_command == "export-approval-pack":
        database = _db(args, config)
        _print(export_approval_pack(database, evidence, args.out))
        return 0
    if args.claims_command == "approve":
        claim = update_claim_status(
            evidence_path,
            args.claim_id,
            "APPROVED_FROM_USER_CONTEXT",
            source=args.source,
            note=args.note,
        )
        _print({"updated": True, "claim": claim})
        return 0
    if args.claims_command == "reject":
        claim = update_claim_status(
            evidence_path,
            args.claim_id,
            "REJECTED",
            source="user_rejection",
            note=args.note,
        )
        _print({"updated": True, "claim": claim})
        return 0
    if args.claims_command == "import-approvals":
        _print(import_claim_approvals(evidence_path, args.input))
        return 0
    raise ValueError(f"Unknown claims command: {args.claims_command}")


def command_refresh_packets(
    args: argparse.Namespace,
    config: dict[str, Any],
) -> int:
    database = _db(args, config)
    _print(
        refresh_packets(
            database=database,
            output_root=args.out,
            config=config,
        )
    )
    return 0


def command_export_review_html(
    args: argparse.Namespace,
    config: dict[str, Any],
) -> int:
    database = _db(args, config)
    _print(export_review_html(database, args.out))
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

    source_report_parser = subparsers.add_parser(
        "source-report",
        help="Report source quality, fit matches, and packet conversion",
    )
    source_report_parser.add_argument("--db")
    source_report_parser.set_defaults(handler=command_source_report)

    review_queue_parser = subparsers.add_parser(
        "review-queue",
        help="Export the scored-job review queue as Markdown and JSON",
    )
    review_queue_parser.add_argument("--db")
    review_queue_parser.add_argument("--out", required=True)
    review_queue_parser.set_defaults(handler=command_review_queue)

    review_csv = subparsers.add_parser(
        "export-review-csv",
        help="Export the scored-job review queue as CSV",
    )
    review_csv.add_argument("--db")
    review_csv.add_argument("--out", required=True)
    review_csv.set_defaults(handler=command_export_review_csv)

    claims_parser = subparsers.add_parser(
        "claims",
        help="Inspect and update the local claim evidence inventory",
    )
    claims_subparsers = claims_parser.add_subparsers(
        dest="claims_command", required=True
    )
    claims_list = claims_subparsers.add_parser("list", help="List claim evidence")
    claims_list.set_defaults(handler=command_claims)
    claims_gaps = claims_subparsers.add_parser(
        "gaps", help="List unresolved job claim gaps"
    )
    claims_gaps.add_argument("--db")
    claims_gaps.set_defaults(handler=command_claims)
    claims_pack = claims_subparsers.add_parser(
        "export-approval-pack",
        help="Export unresolved claim gaps as Markdown and JSON",
    )
    claims_pack.add_argument("--db")
    claims_pack.add_argument("--out", required=True)
    claims_pack.set_defaults(handler=command_claims)
    claims_approve = claims_subparsers.add_parser(
        "approve", help="Explicitly approve one claim with evidence"
    )
    claims_approve.add_argument("--claim-id", required=True)
    claims_approve.add_argument("--source", required=True)
    claims_approve.add_argument("--note", required=True)
    claims_approve.set_defaults(handler=command_claims)
    claims_reject = claims_subparsers.add_parser(
        "reject", help="Reject one claim"
    )
    claims_reject.add_argument("--claim-id", required=True)
    claims_reject.add_argument("--note", required=True)
    claims_reject.set_defaults(handler=command_claims)
    claims_import = claims_subparsers.add_parser(
        "import-approvals", help="Import explicit claim decisions from JSON"
    )
    claims_import.add_argument("--input", required=True)
    claims_import.set_defaults(handler=command_claims)

    refresh = subparsers.add_parser(
        "refresh-packets",
        help="Re-evaluate stored jobs after claim evidence changes",
    )
    refresh.add_argument("--db")
    refresh.add_argument("--out", required=True)
    refresh.set_defaults(handler=command_refresh_packets)

    review_html = subparsers.add_parser(
        "export-review-html",
        help="Export a filterable static HTML review queue",
    )
    review_html.add_argument("--db")
    review_html.add_argument("--out", required=True)
    review_html.set_defaults(handler=command_export_review_html)
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
