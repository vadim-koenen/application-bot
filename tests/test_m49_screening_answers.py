"""M49: LLM-drafted screening/essay answers with the M44 fabrication guard.

Each drafted answer is only kept if it passes validate_against_profile (no
invented numbers, no degree/cert/employer/comp/visa). Comp/legal/identity
questions are never drafted — they're filtered before any model call and
returned for the human. No key / SDK-absent / failed-guard → the question is
left for the human. Nothing is ever submitted.
"""

from __future__ import annotations

from copy import deepcopy

import yaml

import application_bot.cover_letter_llm as cl
from app_api import JobAppAPI
from application_bot.config import DEFAULT_CONFIG, load_claim_inventory
from application_bot.cover_letter_llm import validate_against_profile
from application_bot.database import Database
from application_bot.models import Job
from application_bot.screening_llm import (
    draft_screening_answers,
    is_sensitive_question,
)

INVENTORY = load_claim_inventory("config/resume_claim_inventory.yaml")
PROFILE = {
    "identity": {"name": "Vadim Koenen", "headline": "Revenue Systems Architect"},
    "summary": "Operations leader with 14 years building revenue systems.",
    "selected_impact": [
        "$51M pipeline activated via intent + identity resolution",
        "35% faster campaign time-to-market",
    ],
}

_CLEAN = (
    "I'm drawn to this role because Koenen Revenue Systems is built on exactly "
    "this work — I activated $51M in pipeline via intent and identity resolution "
    "and cut campaign time-to-market by 35%."
)


def _job() -> Job:
    return Job(
        external_id="x", source="s", source_url="u", apply_url="u",
        company="Acme", title="Director, Revenue Operations",
        description="Own revenue operations and GTM systems.",
    )


# --- sensitive-question gate -------------------------------------------------

def test_sensitive_questions_detected():
    for q in (
        "What is your expected salary?",
        "What are your compensation expectations?",
        "Will you require visa sponsorship?",
        "Are you authorized to work in the US?",
        "Please disclose your race and gender.",
        "Are you a protected veteran?",
        "Do you have a disability?",
        "Have you ever been convicted of a felony?",
        "Will you consent to a background check?",
    ):
        assert is_sensitive_question(q) is True, q


def test_normal_questions_not_sensitive():
    for q in (
        "Why are you interested in this role?",
        "Describe your RevOps experience.",
        "What is your approach to building a martech stack?",
    ):
        assert is_sensitive_question(q) is False, q


# --- guard reuse -------------------------------------------------------------

def test_guard_accepts_grounded_and_rejects_fabricated():
    assert validate_against_profile(_CLEAN, PROFILE, INVENTORY) is True
    assert validate_against_profile(
        "I personally generated $99M in net-new revenue.", PROFILE, INVENTORY
    ) is False


# --- drafter -----------------------------------------------------------------

def test_draft_returns_empty_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert draft_screening_answers(
        _job(), PROFILE, INVENTORY, ["Why are you interested?"]
    ) == {}


def test_draft_keeps_validated_answer(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(cl, "_call_claude", lambda *a, **k: _CLEAN)
    out = draft_screening_answers(
        _job(), PROFILE, INVENTORY, ["Why are you interested in this role?"]
    )
    assert out == {"Why are you interested in this role?": _CLEAN}


def test_draft_drops_fabricated_answer(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fabricated = "I drove 250% revenue growth in 6 months."
    monkeypatch.setattr(cl, "_call_claude", lambda *a, **k: fabricated)
    # Falls back (omits the question) rather than letting an invented metric pass.
    assert draft_screening_answers(
        _job(), PROFILE, INVENTORY, ["Describe your impact."]
    ) == {}


def test_sensitive_question_never_drafted_or_called(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    seen: list[str] = []

    def fake(system, user, model):  # noqa: ANN001
        seen.append(user)
        return _CLEAN

    monkeypatch.setattr(cl, "_call_claude", fake)
    out = draft_screening_answers(
        _job(), PROFILE, INVENTORY,
        ["Why are you interested?", "What is your expected salary?"],
    )
    assert "Why are you interested?" in out
    assert "What is your expected salary?" not in out
    # The sensitive question was filtered before any model call.
    assert len(seen) == 1
    assert all("salary" not in user.lower() for user in seen)


# --- API bridge --------------------------------------------------------------

def _api(tmp_path) -> tuple[JobAppAPI, int]:
    db_path = tmp_path / "crm.sqlite"
    database = Database(db_path)
    database.initialize()
    job = Job(
        external_id="j1", source="greenhouse", source_url="https://x/r",
        apply_url="https://x/apply", company="Acme",
        title="Director, Revenue Operations",
        description="Own revenue operations and GTM systems.",
    )
    job_id, _ = database.upsert_job(job)
    config = deepcopy(DEFAULT_CONFIG)
    api = JobAppAPI(db_path=db_path)
    api.config = config
    # load_resume_master validates a full résumé shape; carry PROFILE's approved
    # impact/summary (what _CLEAN is grounded in) into a complete master.
    master = {
        **PROFILE,
        "contact": {"location": "Plano, TX", "email": "t@example.com",
                    "website": "example.com", "linkedin": "linkedin.com/in/test"},
        "skills": {"Revenue Systems": ["Salesforce", "marketing operations"]},
        "experience": [{"company": "KRS", "title": "Founder",
                        "dates": "2020-2025", "bullets": ["Built revenue systems."]}],
    }
    master_path = tmp_path / "master.yaml"
    master_path.write_text(yaml.safe_dump(master), encoding="utf-8")
    api.config["resume_master"] = str(master_path)
    return api, job_id


def test_draft_answers_api_drafts_and_skips(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(cl, "_call_claude", lambda *a, **k: _CLEAN)
    api, jid = _api(tmp_path)
    r = api.draft_answers(
        jid,
        ["Why are you interested in this role?", "What is your expected salary?"],
    )
    assert r["ok"] is True
    assert r["answers"] == [
        {"question": "Why are you interested in this role?", "answer": _CLEAN}
    ]
    assert r["skipped"] == ["What is your expected salary?"]


def test_draft_answers_api_accepts_newline_string(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(cl, "_call_claude", lambda *a, **k: _CLEAN)
    api, jid = _api(tmp_path)
    r = api.draft_answers(jid, "Why are you interested?\n\nDescribe your experience.")
    assert r["ok"] is True
    assert {a["question"] for a in r["answers"]} == {
        "Why are you interested?", "Describe your experience.",
    }


def test_draft_answers_api_missing_job(tmp_path):
    api, _ = _api(tmp_path)
    assert api.draft_answers(999999, ["Why?"])["ok"] is False
