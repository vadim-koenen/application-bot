from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest
import yaml

from application_bot.adapters.ashby import AshbyAdapter
from application_bot.adapters.greenhouse import GreenhouseAdapter
from application_bot.adapters.lever import LeverAdapter
from application_bot.config import DEFAULT_CONFIG, load_config
from application_bot.confirmations import ImportedEmailConfirmationTracker
from application_bot.database import Database
from application_bot.email_service import (
    queue_email_applications,
    send_email_applications,
)
from application_bot.main import build_parser
from application_bot.models import Job
from application_bot.packets import generate_packet, packet_to_dict
from application_bot.pipeline import _job_relevance_score, run_dry_pipeline, scan_registry
from application_bot.policy import evaluate_job_submission_policy
from application_bot.reporting import write_daily_report
from application_bot.scheduler import run_scheduler_once
from application_bot.scoring import score_job


def write_registry(tmp_path: Path, ats: str) -> Path:
    identifiers = {
        "greenhouse": {"board_token": "mock-board"},
        "lever": {"site": "mock-site"},
        "ashby": {"board_name": "mock-board"},
    }
    path = tmp_path / f"{ats}.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "companies": [
                    {
                        "name": "Acme AI",
                        "ats": ats,
                        "enabled": True,
                        **identifiers[ats],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def adapter_for(ats: str):
    if ats == "greenhouse":
        return GreenhouseAdapter(
            transport=lambda _: {
                "jobs": [
                    {
                        "id": 1,
                        "title": "Senior Director, Growth Marketing",
                        "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                        "location": {"name": "Remote - United States"},
                        "content": (
                            "<p>Lead demand generation, GTM strategy, growth marketing, "
                            "marketing operations, and revenue systems transformation.</p>"
                        ),
                    }
                ]
            }
        )
    if ats == "lever":
        return LeverAdapter(
            transport=lambda _: [
                {
                    "id": "lever-1",
                    "text": "VP, Demand Generation",
                    "hostedUrl": "https://jobs.lever.co/acme/lever-1",
                    "applyUrl": "https://jobs.lever.co/acme/lever-1/apply",
                    "descriptionPlain": (
                        "Lead demand generation, GTM strategy, growth marketing, "
                        "marketing operations, and revenue systems transformation."
                    ),
                    "categories": {"team": "Marketing", "location": "Remote - US"},
                    "workplaceType": "remote",
                }
            ]
        )
    return AshbyAdapter(
        transport=lambda _: {
            "jobs": [
                {
                    "id": "ashby-1",
                    "title": "Head of GTM Systems",
                    "location": "Remote - United States",
                    "workplaceType": "Remote",
                    "department": "Revenue",
                    "jobUrl": "https://jobs.ashbyhq.com/acme/ashby-1",
                    "applyUrl": "https://jobs.ashbyhq.com/acme/ashby-1/application",
                    "descriptionPlain": (
                        "Lead demand generation, GTM strategy, growth marketing, "
                        "marketing operations, and revenue systems transformation."
                    ),
                }
            ]
        }
    )


@pytest.mark.parametrize("ats", ["greenhouse", "lever", "ashby"])
def test_run_dry_pipeline_with_mocked_ats(tmp_path, ats):
    registry = write_registry(tmp_path, ats)
    result = run_dry_pipeline(
        database_path=tmp_path / "crm.sqlite",
        registry_path=registry,
        output_root=tmp_path / "exports",
        config=deepcopy(DEFAULT_CONFIG),
        adapters={ats: adapter_for(ats)},
    )
    assert result["real_network_scan"] is True
    assert result["network_status"] == "complete"
    assert result["jobs_inserted"] == 1
    assert result["jobs_scored"] == 1
    assert result["packets_exported"] == 1
    assert result["applications_submitted"] == 0
    assert Path(result["daily_report_markdown"]).exists()
    assert Path(result["daily_report_json"]).exists()


def test_network_failure_is_recorded_and_pipeline_continues(tmp_path):
    class FailingAdapter:
        def discover_jobs(self, **kwargs):
            raise OSError("offline")

    registry = write_registry(tmp_path, "greenhouse")
    database = Database(tmp_path / "crm.sqlite")
    database.initialize()
    result = scan_registry(
        database,
        registry,
        adapters={"greenhouse": FailingAdapter()},
    )
    assert result["network_status"] == "failed"
    assert result["real_network_scan"] is False
    assert result["sources"][0]["error"] == "offline"
    assert database.report()["source_runs"]["FAILED"] == 1


def test_scan_relevance_demotes_off_lane_titles():
    config = deepcopy(DEFAULT_CONFIG)
    in_lane = Job(
        external_id="in-lane",
        source="greenhouse",
        source_url="https://example.com/in-lane",
        apply_url="https://example.com/in-lane/apply",
        company="Acme",
        title="Director, Business Systems",
        description="Own GTM systems and revenue operations.",
    )
    off_lane = Job(
        external_id="off-lane",
        source="greenhouse",
        source_url="https://example.com/off-lane",
        apply_url="https://example.com/off-lane/apply",
        company="Acme",
        title="Director, Product - Enterprise",
        description="Own GTM systems and revenue operations.",
    )
    assert _job_relevance_score(in_lane, config) > _job_relevance_score(
        off_lane, config
    )


def _scored(title: str, description: str = "") -> int:
    config = deepcopy(DEFAULT_CONFIG)
    job = Job(
        external_id=title,
        source="manual_json",
        source_url="",
        apply_url="",
        company="Acme",
        title=title,
        location="Remote - United States",
        remote_type="remote",
        description=description or "Own revenue operations and GTM systems.",
    )
    return score_job(job, config).score


def test_systems_lane_manager_titles_are_not_rejected():
    # A systems/ops function in the title keeps a Manager/Lead role in-lane,
    # scoring it well above a generic rejected Manager title.
    systems_manager = _scored("GTM Systems Manager")
    revops_manager = _scored("Revenue Operations Manager")
    martech_lead = _scored("Martech Enablement Operations Lead")
    generic_manager = _scored(
        "Social Media Manager", description="Own brand social content."
    )
    assert systems_manager > generic_manager
    assert revops_manager > generic_manager
    assert martech_lead > generic_manager
    # Still below a true Director-level in-lane role.
    assert _scored("Director, Marketing Operations") > systems_manager


def make_email_job() -> Job:
    return Job(
        external_id="email-1",
        source="email_to_apply",
        source_url="mailto:jobs@example.com",
        apply_url="mailto:jobs@example.com",
        company="Acme AI",
        title="Senior Director, Growth Marketing",
        department="Marketing",
        location="Remote - United States",
        remote_type="remote",
        salary_min=180000,
        salary_max=220000,
        description=(
            "Lead growth marketing, demand generation, GTM strategy, marketing "
            "operations, and revenue systems transformation."
        ),
        requirements="Executive leadership.",
        responsibilities="Build the function and align the leadership team.",
    )


def prepare_email_queue(tmp_path: Path) -> tuple[Database, dict]:
    config = deepcopy(DEFAULT_CONFIG)
    database = Database(tmp_path / "crm.sqlite")
    database.initialize()
    job = make_email_job()
    job_id, _ = database.upsert_job(job)
    result = score_job(job, config)
    database.save_score(job_id, result)
    saved = database.get_job(job_id)
    assert saved is not None
    policy = evaluate_job_submission_policy(saved, config)
    packet = generate_packet(saved, config, policy)
    packet_path = tmp_path / "packet.md"
    packet_path.write_text("packet", encoding="utf-8")
    database.save_packet(job_id, str(packet_path), packet_to_dict(packet))
    queue_result = queue_email_applications(database, config)
    assert queue_result["queued"] == 1
    return database, config


def test_email_previews_are_generated_without_sending(tmp_path):
    database, config = prepare_email_queue(tmp_path)
    result = send_email_applications(
        database,
        config,
        output_root=tmp_path / "exports",
        live=False,
    )
    assert result["mode"] == "DRY_RUN"
    assert result["email_previews_generated"] == 1
    assert result["applications_submitted"] == 0
    preview = Path(result["preview_paths"][0])
    assert preview.exists()
    assert "X-Application-Bot-Mode: DRY_RUN" in preview.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("live_apply", "live_email", "phrase", "configured"),
    [
        (False, True, "APPROVE", "APPROVE"),
        (True, False, "APPROVE", "APPROVE"),
        (True, True, "WRONG", "APPROVE"),
        (True, True, "", ""),
    ],
)
def test_live_email_requires_all_flags_and_approval_phrase(
    tmp_path,
    live_apply,
    live_email,
    phrase,
    configured,
):
    database, config = prepare_email_queue(tmp_path)
    config["live_apply_enabled"] = live_apply
    config["live_email_send_enabled"] = live_email
    config["email_send_approval_phrase"] = configured
    result = send_email_applications(
        database,
        config,
        output_root=tmp_path / "exports",
        live=True,
        approval_phrase=phrase,
    )
    assert result["mode"] == "LIVE_BLOCKED"
    assert result["applications_submitted"] == 0


def test_fully_authorized_email_path_uses_injected_adapter(tmp_path, monkeypatch):
    class FakeSender:
        def send(self, **kwargs):
            return {"sent": True, "recipient": kwargs["recipient"]}

    database, config = prepare_email_queue(tmp_path)
    config["live_apply_enabled"] = True
    config["live_email_send_enabled"] = True
    config["email_send_approval_phrase"] = "APPROVE ONE EMAIL"
    for name, value in {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_USERNAME": "user",
        "SMTP_PASSWORD": "secret",
        "FROM_EMAIL": "vadim@example.com",
    }.items():
        monkeypatch.setenv(name, value)
    result = send_email_applications(
        database,
        config,
        output_root=tmp_path / "exports",
        live=True,
        approval_phrase="APPROVE ONE EMAIL",
        adapter=FakeSender(),
    )
    assert result["applications_submitted"] == 1
    assert database.report()["application_count"] == 1


def test_scheduler_run_once_uses_dry_pipeline(tmp_path):
    registry = write_registry(tmp_path, "greenhouse")
    result = run_scheduler_once(
        config=deepcopy(DEFAULT_CONFIG),
        registry_path=registry,
        database_path=tmp_path / "crm.sqlite",
        output_root=tmp_path / "exports",
        adapters={"greenhouse": adapter_for("greenhouse")},
    )
    assert result["scheduler"]["run_once"] is True
    assert result["scheduler"]["installed"] is False
    assert result["scheduler"]["running"] is False
    assert result["pipeline"]["applications_submitted"] == 0


def test_daily_report_is_written(tmp_path):
    database = Database(tmp_path / "crm.sqlite")
    database.initialize()
    result = write_daily_report(database, tmp_path / "daily")
    assert Path(result["markdown_path"]).exists()
    assert Path(result["json_path"]).exists()
    assert result["applications_submitted"] == 0


def test_gmail_fixture_parser_classifies_all_statuses(tmp_path):
    database = Database(tmp_path / "crm.sqlite")
    database.initialize()
    fixture = Path(__file__).parent / "fixtures" / "gmail_messages.json"
    result = ImportedEmailConfirmationTracker().import_messages(fixture, database)
    assert result["imported"] == 6
    assert result["classifications"] == {
        "assessment_request": 1,
        "confirmation_received": 1,
        "follow_up_needed": 1,
        "interview_request": 1,
        "recruiter_reply": 1,
        "rejection": 1,
    }


def test_dedupe_is_source_independent(tmp_path):
    database = Database(tmp_path / "crm.sqlite")
    database.initialize()
    greenhouse = make_email_job()
    greenhouse.source = "greenhouse"
    lever = Job(**{**greenhouse.to_dict(), "source": "lever", "id": None})
    first_id, first_created = database.upsert_job(greenhouse)
    second_id, second_created = database.upsert_job(lever)
    assert first_created is True
    assert second_created is False
    assert first_id == second_id


def test_default_config_keeps_all_live_flags_off(monkeypatch):
    monkeypatch.delenv("LIVE_APPLY_ENABLED", raising=False)
    monkeypatch.delenv("LIVE_EMAIL_SEND_ENABLED", raising=False)
    config = load_config(Path("/does/not/exist.yaml"))
    assert config["live_apply_enabled"] is False
    assert config["live_email_send_enabled"] is False
    assert config["dry_run"] is True


def test_cli_help_includes_operational_commands():
    help_text = build_parser().format_help()
    assert "run-dry-pipeline" in help_text
    assert "queue-email-applications" in help_text
    assert "send-email-applications" in help_text
    assert "daily-report" in help_text
    assert "scheduler" in help_text
