from __future__ import annotations

import json
from pathlib import Path

import pytest

from application_bot.adapters.ashby import AshbyAdapter
from application_bot.adapters.greenhouse import GreenhouseAdapter
from application_bot.adapters.lever import LeverAdapter
from application_bot.config import DEFAULT_CONFIG
from application_bot.database import Database
from application_bot.main import main
from application_bot.models import FitVerdict, Job, SubmissionDecision
from application_bot.packets import export_packet, generate_packet
from application_bot.policy import evaluate_submission_policy
from application_bot.scoring import score_job


def make_job(**overrides):
    values = {
        "external_id": "job-1",
        "source": "manual_json",
        "source_url": "https://example.com/job",
        "apply_url": "https://example.com/apply",
        "company": "Acme",
        "title": "Senior Director, Growth Marketing",
        "department": "Marketing",
        "location": "Remote - United States",
        "remote_type": "remote",
        "salary_min": 180000,
        "salary_max": 220000,
        "description": (
            "Lead demand generation, growth marketing, lifecycle marketing, "
            "GTM strategy, and revenue systems transformation."
        ),
        "requirements": "Marketing operations and executive leadership.",
        "responsibilities": "Build the function and align the leadership team.",
        "posted_at": "2026-06-12T00:00:00+00:00",
    }
    values.update(overrides)
    return Job(**values)


@pytest.mark.parametrize(
    "title",
    [
        "Director of Demand Generation",
        "Senior Director, Growth",
        "VP, Marketing Operations",
        "Head of GTM Systems",
        "Executive, Revenue Systems",
    ],
)
def test_scoring_accepts_target_seniority(title):
    result = score_job(make_job(title=title), DEFAULT_CONFIG)
    assert result.score >= 65
    assert result.verdict in {FitVerdict.APPLY_PRIORITY, FitVerdict.GOOD_FIT}


@pytest.mark.parametrize(
    "title",
    ["Marketing Coordinator", "Growth Specialist", "Marketing Associate", "Marketing Manager"],
)
def test_scoring_rejects_wrong_level(title):
    result = score_job(
        make_job(
            title=title,
            salary_min=60000,
            salary_max=90000,
            location="Onsite - Phoenix",
            remote_type="onsite",
        ),
        DEFAULT_CONFIG,
    )
    assert result.score < 45
    assert result.verdict == FitVerdict.NOT_WORTH_TIME


def test_remote_us_beats_onsite_only():
    remote = score_job(make_job(), DEFAULT_CONFIG)
    onsite = score_job(
        make_job(location="Onsite - Boston", remote_type="onsite"), DEFAULT_CONFIG
    )
    assert remote.score > onsite.score


def test_marketing_gtm_revenue_systems_scores_high():
    result = score_job(make_job(), DEFAULT_CONFIG)
    assert result.score >= 80


def test_pure_sales_ae_scores_lower():
    strong = score_job(make_job(), DEFAULT_CONFIG)
    sales = score_job(
        make_job(
            title="Account Executive",
            department="Sales",
            description="Pure sales role focused on cold calling and closing quota.",
            requirements="Account executive experience.",
            responsibilities="Prospecting and sales calls.",
        ),
        DEFAULT_CONFIG,
    )
    assert sales.score < strong.score
    assert sales.verdict == FitVerdict.NOT_WORTH_TIME


def test_workday_adds_friction_penalty():
    normal = score_job(make_job(), DEFAULT_CONFIG)
    workday = score_job(
        make_job(apply_url="https://company.wd5.myworkdayjobs.com/en-US/job/123"),
        DEFAULT_CONFIG,
    )
    assert normal.score - workday.score == 10
    assert "Workday application friction." in workday.risk_flags


def test_linkedin_routes_to_review_required():
    result = evaluate_submission_policy("linkedin_review_queue")
    assert result.decision == SubmissionDecision.REVIEW_REQUIRED


@pytest.mark.parametrize("source", ["indeed_connector", "zip_connector"])
def test_job_board_connectors_never_auto_submit(source):
    result = evaluate_submission_policy(
        source,
        live_apply_enabled=True,
        adapter_allows_submission=True,
        credentials_present=True,
        required_questions_known=True,
    )
    assert result.decision in {
        SubmissionDecision.BLOCKED,
        SubmissionDecision.REVIEW_REQUIRED,
    }
    assert result.decision != SubmissionDecision.AUTO_SUBMIT_ALLOWED


def test_email_auto_submit_requires_explicit_complete_configuration(monkeypatch):
    dry = evaluate_submission_policy(
        "email_to_apply", recipient="jobs@example.com", live_apply_enabled=False
    )
    assert dry.decision == SubmissionDecision.AUTO_PACKET_ONLY

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("FROM_EMAIL", "vadim@example.com")
    live = evaluate_submission_policy(
        "email_to_apply", recipient="jobs@example.com", live_apply_enabled=True
    )
    assert live.decision == SubmissionDecision.AUTO_SUBMIT_EMAIL


def test_greenhouse_mocked_response_normalizes():
    payload = {
        "jobs": [
            {
                "id": 42,
                "title": "Director, Demand Generation",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/42",
                "location": {"name": "Remote - US"},
                "content": "<p>Lead demand generation.</p>",
                "updated_at": "2026-06-10T00:00:00Z",
            }
        ]
    }
    jobs = GreenhouseAdapter(transport=lambda _: payload).discover_jobs(
        board_token="acme", company="Acme"
    )
    assert jobs[0].company == "Acme"
    assert jobs[0].title == "Director, Demand Generation"
    assert jobs[0].description == "Lead demand generation."


def test_lever_mocked_response_normalizes():
    payload = [
        {
            "id": "lever-1",
            "text": "VP, Growth",
            "hostedUrl": "https://jobs.lever.co/acme/lever-1",
            "applyUrl": "https://jobs.lever.co/acme/lever-1/apply",
            "descriptionPlain": "Lead growth marketing.",
            "categories": {"team": "Marketing", "location": "Remote"},
            "workplaceType": "remote",
            "lists": [{"text": "Requirements", "content": "<li>GTM strategy</li>"}],
        }
    ]
    job = LeverAdapter(transport=lambda _: payload).discover_jobs(
        site="acme", company="Acme"
    )[0]
    assert job.department == "Marketing"
    assert job.requirements == "GTM strategy"
    assert job.remote_type == "remote"


def test_ashby_mocked_response_normalizes():
    payload = {
        "jobs": [
            {
                "id": "ashby-1",
                "title": "Head of Revenue Systems",
                "location": "United States",
                "workplaceType": "Remote",
                "department": "Revenue",
                "jobUrl": "https://jobs.ashbyhq.com/acme/ashby-1",
                "applyUrl": "https://jobs.ashbyhq.com/acme/ashby-1/application",
                "descriptionHtml": "<p>Own GTM systems.</p>",
            }
        ]
    }
    job = AshbyAdapter(transport=lambda _: payload).discover_jobs(
        board_name="acme", company="Acme"
    )[0]
    assert job.title == "Head of Revenue Systems"
    assert job.description == "Own GTM systems."
    assert job.apply_url.endswith("/application")


def test_deduplication_uses_canonical_job_fields(tmp_path):
    database = Database(tmp_path / "crm.sqlite")
    database.initialize()
    first_id, first_created = database.upsert_job(make_job())
    second_id, second_created = database.upsert_job(make_job(external_id="different-id"))
    assert first_created is True
    assert second_created is False
    assert first_id == second_id
    assert len(database.list_jobs()) == 1


def test_manual_import_accepts_csv(tmp_path):
    from application_bot.adapters.manual_json import ManualJsonAdapter

    path = tmp_path / "jobs.csv"
    path.write_text(
        "external_id,company,title,location,apply_url,description\n"
        "csv-1,Acme,\"Director, GTM Strategy\",Remote,"
        "https://example.com/apply,Lead go-to-market strategy\n",
        encoding="utf-8",
    )
    jobs = ManualJsonAdapter().discover_jobs(input_path=path)
    assert len(jobs) == 1
    assert jobs[0].external_id == "csv-1"
    assert jobs[0].title == "Director, GTM Strategy"


def test_packet_export_creates_markdown(tmp_path):
    job = make_job(id=1)
    result = score_job(job, DEFAULT_CONFIG)
    job.score = result.score
    job.verdict = str(result.verdict)
    job.score_details_json = json.dumps(
        {"reasons": result.reasons, "risk_flags": result.risk_flags}
    )
    policy = evaluate_submission_policy(job.source)
    packet = generate_packet(job, DEFAULT_CONFIG, policy)
    path = export_packet(job, packet, tmp_path)
    text = path.read_text(encoding="utf-8")
    assert path.exists()
    assert "# Application Packet: Acme" in text
    assert "Submission policy" in text
    assert "Raw Job Excerpt" in text


def test_cli_scan_score_export_flow(tmp_path, capsys):
    database = tmp_path / "crm.sqlite"
    output = tmp_path / "packets"
    input_path = tmp_path / "jobs.json"
    input_path.write_text(
        json.dumps({"jobs": [make_job().to_dict()]}), encoding="utf-8"
    )

    assert main(["init-db", "--db", str(database)]) == 0
    assert (
        main(
            [
                "scan",
                "--source",
                "manual_json",
                "--input",
                str(input_path),
                "--db",
                str(database),
            ]
        )
        == 0
    )
    assert main(["score", "--db", str(database)]) == 0
    assert (
        main(["export-packets", "--db", str(database), "--out", str(output)]) == 0
    )
    assert main(["report", "--db", str(database)]) == 0
    assert list(output.rglob("*.md"))
    assert '"total_jobs": 1' in capsys.readouterr().out


def test_no_external_credentials_required(monkeypatch):
    for name in (
        "GREENHOUSE_API_KEY",
        "LEVER_API_KEY",
        "ASHBY_API_KEY",
        "SMTP_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    job = GreenhouseAdapter(
        transport=lambda _: {"jobs": []}
    ).discover_jobs(board_token="mock")
    assert job == []


@pytest.mark.parametrize(
    "capability",
    [
        "captcha_bypass",
        "login_bypass",
        "bot_detection_evasion",
        "proxy_rotation",
        "cookie_harvesting",
        "linkedin_auto_click",
    ],
)
def test_compliance_blocks_bypass_behavior(capability):
    result = evaluate_submission_policy(
        "manual_json", capabilities={capability}, live_apply_enabled=True
    )
    assert result.decision == SubmissionDecision.BLOCKED


@pytest.mark.parametrize(
    "flag",
    [
        "captcha",
        "login_required",
        "unknown_legal_attestation",
        "unknown_required_question",
        "ambiguous_consent",
    ],
)
def test_compliance_routes_unknown_form_conditions_to_review(flag):
    result = evaluate_submission_policy("greenhouse", flags={flag})
    assert result.decision == SubmissionDecision.REVIEW_REQUIRED


def test_public_ats_default_to_packet_only():
    for source in ("greenhouse", "lever", "ashby"):
        result = evaluate_submission_policy(source)
        assert result.decision == SubmissionDecision.AUTO_PACKET_ONLY


def test_unknown_source_defaults_to_review():
    result = evaluate_submission_policy("mystery_source")
    assert result.decision == SubmissionDecision.REVIEW_REQUIRED
