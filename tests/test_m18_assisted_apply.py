"""M18: assisted-apply fill plan.

Verifies the fill plan pre-fills only approved answers, leaves every
REVIEW_REQUIRED answer blank for the human, resolves the role's ATS resume,
flags non-form (recruiter-email) apply URLs, and never carries a submit action.
"""

from __future__ import annotations

from application_bot.assisted_apply import (
    SUBMIT_ACTION,
    build_fill_plan,
    fill_plan_to_dict,
    render_fill_plan_markdown,
    resolve_resume_text,
)
from application_bot.models import Job


def _job(**kw) -> Job:
    base = dict(
        external_id="t1",
        source="manual_json",
        source_url="",
        apply_url="https://boards.greenhouse.io/acme/jobs/123",
        company="Acme",
        title="Director, Marketing Operations",
        id=7,
        packet_status="PACKET_READY",
    )
    base.update(kw)
    return Job(**base)


def _packet(**kw) -> dict:
    base = {
        "packet_status": "PACKET_READY",
        "suggested_answers": {
            "Name": "Vadim Koenen",
            "Website": "https://vadimkoenen.com/",
            "Work authorization": "Authorized to work in the United States.",
            "Compensation expectations": "REVIEW_REQUIRED — confirm range.",
            "Background check": "REVIEW_REQUIRED — answer personally.",
            "Why interested": "The role aligns with approved positioning.",
        },
    }
    base.update(kw)
    return base


def test_approved_fields_autofill_review_fields_left_for_human(tmp_path):
    plan = build_fill_plan(_job(), _packet(), tmp_path)
    autofill = {f.label: f.value for f in plan.autofill_fields}
    human = {f.label: f.value for f in plan.human_fields}

    assert autofill["Name"] == "Vadim Koenen"
    assert autofill["Work authorization"] == "Authorized to work in the United States."
    # REVIEW_REQUIRED answers are never pre-filled.
    assert "Compensation expectations" in human
    assert "Background check" in human
    assert human["Compensation expectations"] == ""
    assert all(f.note for f in plan.human_fields)


def test_plan_never_carries_a_submit_action(tmp_path):
    plan = build_fill_plan(_job(), _packet(), tmp_path)
    assert plan.submit_action == SUBMIT_ACTION == "STOP_AT_SUBMIT_FOR_HUMAN"
    md = render_fill_plan_markdown(plan)
    assert "never submits" in md.lower()


def test_recruiter_email_url_is_flagged_not_a_form(tmp_path):
    plan = build_fill_plan(
        _job(apply_url="recruiter:Savannah@Mondo"), _packet(), tmp_path
    )
    assert any("not an http" in w.lower() for w in plan.warnings)


def test_resume_txt_is_resolved_from_latest_date_folder(tmp_path):
    root = tmp_path / "ats_resumes"
    old = root / "2026-06-20"
    new = root / "2026-06-22"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    base = "acme_director-marketing-operations.txt"
    (old / base).write_text("old", encoding="utf-8")
    (new / base).write_text("new", encoding="utf-8")

    resolved = resolve_resume_text(_job(), tmp_path)
    assert resolved == str(new / base)

    plan = build_fill_plan(_job(), _packet(), tmp_path)
    assert plan.resume_attached is True
    assert plan.resume_text_path == str(new / base)


def test_missing_resume_and_not_ready_status_warn(tmp_path):
    plan = build_fill_plan(
        _job(packet_status="REVIEW_PACKET_CLAIM_GAPS"),
        _packet(packet_status="REVIEW_PACKET_CLAIM_GAPS"),
        tmp_path,
    )
    assert plan.resume_attached is False
    assert any("not PACKET_READY" in w for w in plan.warnings)
    assert any("No ATS resume" in w for w in plan.warnings)


def test_plan_dict_reports_field_counts(tmp_path):
    data = fill_plan_to_dict(build_fill_plan(_job(), _packet(), tmp_path))
    assert data["autofill_field_count"] == 4
    assert data["human_field_count"] == 2
    assert data["submit_action"] == "STOP_AT_SUBMIT_FOR_HUMAN"
