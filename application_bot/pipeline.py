from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
from typing import Any

from application_bot.adapters import (
    AdzunaAdapter,
    AshbyAdapter,
    GreenhouseAdapter,
    JSearchAdapter,
    LeverAdapter,
)
from application_bot.adapters.jsearch import rapidapi_transport
from application_bot.config import (
    load_answer_bank,
    load_claim_evidence,
    load_claim_inventory,
    load_company_registry,
)
from application_bot.claims import claim_counts
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
from application_bot.policy import evaluate_job_submission_policy
from application_bot.reporting import write_daily_report
from application_bot.scoring import score_job


ATS_ADAPTERS = {
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "ashby": AshbyAdapter,
}


def _adapter_kwargs(company: dict[str, Any]) -> dict[str, Any]:
    ats = str(company.get("ats") or "")
    kwargs: dict[str, Any] = {"company": company["name"]}
    if ats == "greenhouse":
        kwargs["board_token"] = company["board_token"]
    elif ats == "lever":
        kwargs["site"] = company["site"]
    elif ats == "ashby":
        kwargs["board_name"] = company["board_name"]
    else:
        raise ValueError(f"Unsupported ATS type: {ats}")
    return kwargs


def _new_adapter(factory: Any) -> Any:
    return factory() if isinstance(factory, type) else factory


def _job_relevance_score(job: Any, config: dict[str, Any] | None) -> int:
    if not config:
        return 0
    title = job.title.lower()
    corpus = " ".join(
        (
            job.title,
            job.department,
            job.description,
            job.requirements,
            job.responsibilities,
        )
    ).lower()
    title_points = sum(
        10 for value in config.get("target_titles", []) if value.lower() in title
    )
    function_points = sum(
        3 for value in config.get("target_keywords", []) if value.lower() in corpus
    )
    reject_points = sum(
        8 for value in config.get("reject_titles", []) if value.lower() in title
    )
    off_lane_points = sum(
        20
        for value in config.get("off_lane_titles", [])
        if value.lower() in title
    )
    mismatch_points = sum(
        5
        for value in config.get("reject_keywords", [])
        if value.lower() in corpus
    )
    return (
        title_points
        + function_points
        - reject_points
        - off_lane_points
        - mismatch_points
    )


def parse_posted_at(value: Any) -> datetime | None:
    """Parse an adapter's posted_at into a tz-aware UTC datetime, or None.

    Adapters disagree on format: Greenhouse ``updated_at`` and Ashby
    ``publishedAt`` are ISO strings; Lever ``createdAt`` is a Unix epoch in
    milliseconds. Anything unparseable returns None (treated as "date unknown").
    """
    if value is None or value == "":
        return None
    # Numeric epoch (Lever): seconds or milliseconds.
    if isinstance(value, (int, float)) or (
        isinstance(value, str) and value.strip().isdigit()
    ):
        epoch = float(value)
        if epoch > 1e11:  # milliseconds
            epoch /= 1000.0
        try:
            return datetime.fromtimestamp(epoch, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def is_fresh(value: Any, hours: int, *, now: datetime | None = None) -> bool | None:
    """True if posted_at is within the last ``hours``; None if date unknown."""
    posted = parse_posted_at(value)
    if posted is None:
        return None
    now = now or datetime.now(UTC)
    return (now - posted) <= timedelta(hours=hours) and posted <= now + timedelta(
        hours=1
    )


DEFAULT_ADZUNA_QUERIES = [
    "marketing operations director",
    "revenue operations director",
    "marketing operations manager",
    "marketing technology director",
    "gtm systems",
]


def discover_adzuna(
    database: Database,
    config: dict[str, Any],
    *,
    hours: int = 24,
    queries: list[str] | None = None,
    transport: Any = None,
    app_id: str | None = None,
    app_key: str | None = None,
    country: str = "us",
) -> dict[str, Any]:
    """Market-wide, function-targeted discovery via Adzuna. Skipped if no key.

    Searches each query for roles posted within ``hours``, keeps the fresh ones,
    upserts, and scores them. Adzuna descriptions are truncated, so these score
    rougher than ATS-board roles — they are discovery leads.
    """
    app_id = app_id or os.getenv("ADZUNA_APP_ID")
    app_key = app_key or os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        return {"source": "adzuna", "enabled": False,
                "reason": "ADZUNA_APP_ID / ADZUNA_APP_KEY not set"}
    queries = queries or config.get("adzuna_queries") or DEFAULT_ADZUNA_QUERIES
    adapter = AdzunaAdapter(transport=transport) if transport else AdzunaAdapter()
    now = datetime.now(UTC)
    max_days = max(1, (hours + 23) // 24)
    seen = inserted = dropped_stale = 0
    for query in queries:
        try:
            jobs = adapter.discover_jobs(
                app_id=app_id,
                app_key=app_key,
                what=query,
                max_days_old=max_days,
                results_per_page=50,
                country=country,
            )
        except (OSError, ValueError):  # network/source isolation
            continue
        for job in jobs:
            seen += 1
            if is_fresh(job.posted_at, hours, now=now) is not True:
                dropped_stale += 1
                continue
            _, created = database.upsert_job(job)
            inserted += int(created)
    scored = 0
    for job in database.list_jobs():
        if str(job.source) == "adzuna" and job.score is None:
            database.save_score(int(job.id), score_job(job, config))
            scored += 1
    return {
        "source": "adzuna",
        "enabled": True,
        "queries": len(queries),
        "jobs_seen": seen,
        "jobs_inserted": inserted,
        "dropped_stale": dropped_stale,
        "scored": scored,
    }


DEFAULT_JSEARCH_QUERIES = [
    "marketing operations director",
    "revenue operations director",
    "marketing operations manager",
    "marketing technology director",
    "gtm systems",
]


def discover_jsearch(
    database: Database,
    config: dict[str, Any],
    *,
    hours: int = 24,
    queries: list[str] | None = None,
    transport: Any = None,
    api_key: str | None = None,
    host: str | None = None,
) -> dict[str, Any]:
    """Market-wide discovery via JSearch (Google-for-Jobs: LinkedIn/Indeed/
    ZipRecruiter/Glassdoor). No-op without RAPIDAPI_KEY. Keeps fresh, scores,
    inserts. The geography gate still applies downstream.
    """
    api_key = api_key or os.getenv("RAPIDAPI_KEY")
    if not api_key:
        return {"source": "jsearch", "enabled": False,
                "reason": "RAPIDAPI_KEY not set"}
    queries = queries or config.get("jsearch_queries") or DEFAULT_JSEARCH_QUERIES
    if transport is None:
        host = host or os.getenv("RAPIDAPI_JSEARCH_HOST", "jsearch.p.rapidapi.com")
        transport = rapidapi_transport(api_key, host)
    adapter = JSearchAdapter(transport=transport)
    date_posted = "today" if hours <= 24 else "3days" if hours <= 72 else "week"
    now = datetime.now(UTC)
    seen = inserted = dropped_stale = 0
    for query in queries:
        try:
            jobs = adapter.discover_jobs(what=query, date_posted=date_posted)
        except (OSError, ValueError):
            continue
        for job in jobs:
            seen += 1
            if is_fresh(job.posted_at, hours, now=now) is not True:
                dropped_stale += 1
                continue
            _, created = database.upsert_job(job)
            inserted += int(created)
    scored = 0
    for job in database.list_jobs():
        if str(job.source) == "jsearch" and job.score is None:
            database.save_score(int(job.id), score_job(job, config))
            scored += 1
    return {
        "source": "jsearch",
        "enabled": True,
        "queries": len(queries),
        "jobs_seen": seen,
        "jobs_inserted": inserted,
        "dropped_stale": dropped_stale,
        "scored": scored,
    }


def scan_registry(
    database: Database,
    registry_path: str | Path,
    *,
    limit: int = 25,
    source_filter: str | None = None,
    adapters: dict[str, Any] | None = None,
    selection_config: dict[str, Any] | None = None,
    posted_within_hours: int | None = None,
) -> dict[str, Any]:
    registry = load_company_registry(registry_path)
    adapter_map = adapters or ATS_ADAPTERS
    jobs_seen = 0
    jobs_inserted = 0
    attempted = 0
    succeeded = 0
    dropped_stale = 0
    dropped_undated = 0
    sources: list[dict[str, Any]] = []
    now = datetime.now(UTC)

    for company in registry:
        database.register_company(company)
        ats = str(company.get("ats") or "")
        if not company.get("enabled", False):
            continue
        if source_filter and ats != source_filter:
            continue
        if limit >= 0 and jobs_seen >= limit:
            break

        attempted += 1
        run_id = database.start_source_run(
            ats,
            {
                "company": company.get("name"),
                "registry": str(registry_path),
                "dry_run": True,
            },
        )
        try:
            factory = adapter_map[ats]
            adapter = _new_adapter(factory)
            jobs = adapter.discover_jobs(**_adapter_kwargs(company))
            if posted_within_hours is not None:
                fresh: list[Any] = []
                for job in jobs:
                    verdict = is_fresh(job.posted_at, posted_within_hours, now=now)
                    if verdict is True:
                        fresh.append(job)
                    elif verdict is None:
                        dropped_undated += 1
                    else:
                        dropped_stale += 1
                jobs = fresh
            remaining = max(0, limit - jobs_seen) if limit >= 0 else len(jobs)
            per_source_limit = int(company.get("scan_limit") or remaining)
            selected_limit = min(remaining, per_source_limit)
            ranked = sorted(
                jobs,
                key=lambda job: _job_relevance_score(job, selection_config),
                reverse=True,
            )
            selected = ranked[:selected_limit] if limit >= 0 else ranked[:per_source_limit]
            written = 0
            for job in selected:
                _, created = database.upsert_job(job)
                written += int(created)
            jobs_seen += len(selected)
            jobs_inserted += written
            succeeded += 1
            details = {
                "company": company["name"],
                "jobs_returned": len(jobs),
                "jobs_selected": len(selected),
                "target_relevance": company.get("target_relevance", []),
                "source_url": company.get("source_url"),
            }
            database.finish_source_run(
                run_id,
                status="COMPLETED",
                jobs_seen=len(selected),
                jobs_written=written,
                details=details,
            )
            sources.append({"ats": ats, "status": "COMPLETED", **details})
        except Exception as exc:  # Network/source isolation is intentional.
            details = {"company": company.get("name"), "error": str(exc)}
            database.finish_source_run(
                run_id,
                status="FAILED",
                jobs_seen=0,
                jobs_written=0,
                details=details,
            )
            sources.append({"ats": ats, "status": "FAILED", **details})

    if attempted == 0:
        network_status = "not_attempted"
    elif succeeded == attempted:
        network_status = "complete"
    elif succeeded:
        network_status = "partial"
    else:
        network_status = "failed"
    return {
        "registry": str(registry_path),
        "jobs_seen": jobs_seen,
        "jobs_inserted": jobs_inserted,
        "duplicates": jobs_seen - jobs_inserted,
        "sources_attempted": attempted,
        "sources_succeeded": succeeded,
        "sources": sources,
        "real_network_scan": succeeded > 0,
        "network_status": network_status,
        "posted_within_hours": posted_within_hours,
        "dropped_stale": dropped_stale,
        "dropped_undated": dropped_undated,
    }


def run_dry_pipeline(
    *,
    database_path: str | Path,
    registry_path: str | Path,
    output_root: str | Path,
    config: dict[str, Any],
    limit: int = 25,
    adapters: dict[str, Any] | None = None,
    posted_within_hours: int | None = None,
) -> dict[str, Any]:
    runtime_config = deepcopy(config)
    runtime_config["dry_run"] = True
    runtime_config["live_apply_enabled"] = False
    runtime_config["live_email_send_enabled"] = False

    database = Database(database_path)
    database.initialize()
    scan = scan_registry(
        database,
        registry_path,
        limit=limit,
        adapters=adapters,
        selection_config=runtime_config,
        posted_within_hours=posted_within_hours,
    )

    scored = 0
    policies: dict[str, int] = {}
    for job in database.list_jobs():
        result = score_job(job, runtime_config)
        database.save_score(int(job.id), result)
        scored += 1
        policy = evaluate_job_submission_policy(job, runtime_config)
        decision = str(policy.decision)
        policies[decision] = policies.get(decision, 0) + 1
        database.record_event(
            "POLICY_EVALUATED",
            job_id=int(job.id),
            details={"decision": decision, "reasons": policy.reasons},
        )
        if decision == "BLOCKED":
            database.record_event(
                "COMPLIANCE_BLOCK",
                job_id=int(job.id),
                details={"reasons": policy.reasons},
            )

    inventory = load_claim_inventory(runtime_config["resume_claim_inventory"])
    evidence = load_claim_evidence(runtime_config["claim_evidence"])
    answer_bank = load_answer_bank(runtime_config["application_answer_bank"])
    packet_paths: list[str] = []
    packet_status_counts: dict[str, int] = {}
    no_packet_reason_counts: dict[str, int] = {}
    packet_root = Path(output_root) / "packets"
    for job in database.list_jobs(scored_only=True):
        policy = evaluate_job_submission_policy(job, runtime_config)
        assessment = assess_packet(
            job, runtime_config, policy, inventory, evidence
        )
        packet_status = str(assessment.status)
        packet_status_counts[packet_status] = (
            packet_status_counts.get(packet_status, 0) + 1
        )
        database.save_packet_assessment(
            int(job.id),
            packet_status=packet_status,
            claim_gaps=assessment.claim_gaps,
            reason_codes=assessment.reason_codes,
            recommended_next_action=assessment.recommended_next_action,
            submission_policy=str(policy.decision),
        )
        if not assessment.should_export:
            for reason in assessment.reason_codes:
                no_packet_reason_counts[reason] = (
                    no_packet_reason_counts.get(reason, 0) + 1
                )
            continue
        packet = generate_packet(
            job,
            runtime_config,
            policy,
            inventory=inventory,
            evidence=evidence,
            answer_bank=answer_bank,
            assessment=assessment,
        )
        category = (
            "ready"
            if packet_status == "PACKET_READY"
            else "review"
        )
        path = export_packet(job, packet, packet_root / category)
        database.save_packet(int(job.id), str(path), packet_to_dict(packet))
        packet_paths.append(str(path))

    queue_result = queue_email_applications(database, runtime_config)
    email_result = send_email_applications(
        database,
        runtime_config,
        output_root=output_root,
        live=False,
    )
    quality = database.source_quality_report()
    pipeline_summary = {
        **scan,
        **quality,
        "jobs_scored": scored,
        "source_quality": quality,
        "submission_policies": policies,
        "packets_exported": len(packet_paths),
        "packet_statuses": packet_status_counts,
        "packets_ready": packet_status_counts.get("PACKET_READY", 0),
        "review_packets_claim_gaps": packet_status_counts.get(
            "REVIEW_PACKET_CLAIM_GAPS", 0
        ),
        "no_packet_reason_counts": no_packet_reason_counts,
        "packet_paths": packet_paths,
        "email_queue": queue_result,
        "email_ready_manual_review": (
            queue_result["queued"] + queue_result["already_queued"]
        ),
        "email_previews_generated": email_result["email_previews_generated"],
        "email_preview_paths": email_result["preview_paths"],
        "applications_submitted": 0,
        "dry_run": True,
        "live_apply_enabled": False,
        "live_email_send_enabled": False,
    }
    report = write_daily_report(
        database,
        Path(output_root) / "reports",
        pipeline=pipeline_summary,
        claim_readiness=claim_counts(evidence),
        directory_mode=True,
    )
    pipeline_summary["daily_report_markdown"] = report["markdown_path"]
    pipeline_summary["daily_report_json"] = report["json_path"]
    return pipeline_summary


def refresh_packets(
    *,
    database: Database,
    output_root: str | Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    inventory = load_claim_inventory(config["resume_claim_inventory"])
    evidence = load_claim_evidence(config["claim_evidence"])
    answer_bank = load_answer_bank(config["application_answer_bank"])
    paths: list[str] = []
    statuses: dict[str, int] = {}
    for job in database.list_jobs(scored_only=True):
        policy = evaluate_job_submission_policy(job, config)
        assessment = assess_packet(job, config, policy, inventory, evidence)
        status = str(assessment.status)
        statuses[status] = statuses.get(status, 0) + 1
        database.save_packet_assessment(
            int(job.id),
            packet_status=status,
            claim_gaps=assessment.claim_gaps,
            reason_codes=assessment.reason_codes,
            recommended_next_action=assessment.recommended_next_action,
            submission_policy=str(policy.decision),
        )
        if not assessment.should_export:
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
        category = "ready" if status == "PACKET_READY" else "review"
        path = export_packet(job, packet, Path(output_root) / category)
        database.save_packet(int(job.id), str(path), packet_to_dict(packet))
        paths.append(str(path))
    return {
        "jobs_reassessed": len(database.list_jobs(scored_only=True)),
        "packet_statuses": statuses,
        "packets_exported": len(paths),
        "packet_paths": paths,
        "applications_submitted": 0,
    }
