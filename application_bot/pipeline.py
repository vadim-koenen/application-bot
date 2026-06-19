from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from application_bot.adapters import AshbyAdapter, GreenhouseAdapter, LeverAdapter
from application_bot.config import load_company_registry
from application_bot.database import Database
from application_bot.email_service import (
    queue_email_applications,
    send_email_applications,
)
from application_bot.packets import export_packet, generate_packet, packet_to_dict
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


def scan_registry(
    database: Database,
    registry_path: str | Path,
    *,
    limit: int = 25,
    source_filter: str | None = None,
    adapters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = load_company_registry(registry_path)
    adapter_map = adapters or ATS_ADAPTERS
    jobs_seen = 0
    jobs_inserted = 0
    attempted = 0
    succeeded = 0
    sources: list[dict[str, Any]] = []

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
            remaining = max(0, limit - jobs_seen) if limit >= 0 else len(jobs)
            selected = jobs[:remaining] if limit >= 0 else jobs
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
    }


def run_dry_pipeline(
    *,
    database_path: str | Path,
    registry_path: str | Path,
    output_root: str | Path,
    config: dict[str, Any],
    limit: int = 25,
    adapters: dict[str, Any] | None = None,
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

    packet_paths: list[str] = []
    packet_root = Path(output_root) / "packets"
    for job in database.list_jobs(scored_only=True):
        if str(job.verdict) not in {"APPLY_PRIORITY", "GOOD_FIT"}:
            continue
        policy = evaluate_job_submission_policy(job, runtime_config)
        if str(policy.decision) == "BLOCKED":
            continue
        packet = generate_packet(job, runtime_config, policy)
        path = export_packet(job, packet, packet_root)
        database.save_packet(int(job.id), str(path), packet_to_dict(packet))
        packet_paths.append(str(path))

    queue_result = queue_email_applications(database, runtime_config)
    email_result = send_email_applications(
        database,
        runtime_config,
        output_root=output_root,
        live=False,
    )
    pipeline_summary = {
        **scan,
        "jobs_scored": scored,
        "submission_policies": policies,
        "packets_exported": len(packet_paths),
        "packet_paths": packet_paths,
        "email_queue": queue_result,
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
        directory_mode=True,
    )
    pipeline_summary["daily_report_markdown"] = report["markdown_path"]
    pipeline_summary["daily_report_json"] = report["json_path"]
    return pipeline_summary
