"""M44: LLM-drafted cover letters with a fabrication guard.

The Claude draft is only used if it passes validate_cover_letter (no invented
numbers, no degree/cert/employer/comp/visa). No key / SDK-absent / failed guard
all fall back to the deterministic claim-safe template — the no-fabrication
boundary holds either way.
"""

from __future__ import annotations

import application_bot.cover_letter_llm as cl
from application_bot.config import load_claim_inventory
from application_bot.cover_letter_llm import draft_cover_letter_llm, validate_cover_letter
from application_bot.models import Job

INVENTORY = load_claim_inventory("config/resume_claim_inventory.yaml")
PROFILE = {
    "identity": {"name": "Vadim Koenen", "headline": "Revenue Systems Architect"},
    "summary": "Operations leader with 14 years building revenue systems.",
    "selected_impact": [
        "$51M pipeline activated via intent + identity resolution",
        "35% faster campaign time-to-market",
    ],
}


def _job() -> Job:
    return Job(
        external_id="x", source="s", source_url="u", apply_url="u",
        company="Acme", title="Director, Revenue Operations",
        description="Own revenue operations and GTM systems.",
    )


def test_validator_accepts_clean_letter_with_approved_metric():
    letter = (
        "Dear Acme Hiring Team,\n\nThrough Koenen Revenue Systems I delivered "
        "$51M pipeline activated via intent and cut campaign time-to-market by "
        "35%.\n\nSincerely,\nVadim Koenen"
    )
    assert validate_cover_letter(letter, PROFILE, INVENTORY) is True


def test_validator_rejects_fabricated_number():
    letter = "Dear Acme Hiring Team,\n\nI generated $99M in revenue.\n\nSincerely,\nVadim"
    assert validate_cover_letter(letter, PROFILE, INVENTORY) is False


def test_validator_rejects_degree_cert_and_comp():
    for bad in (
        "Dear Acme Hiring Team,\n\nI hold an MBA.\n\nSincerely,\nVadim",
        "Dear Acme Hiring Team,\n\nI am Marketo certified.\n\nSincerely,\nVadim",
        "Dear Acme Hiring Team,\n\nMy salary expectation is flexible.\n\nSincerely,\nVadim",
        "Dear Acme Hiring Team,\n\nI will need visa sponsorship.\n\nSincerely,\nVadim",
    ):
        assert validate_cover_letter(bad, PROFILE, INVENTORY) is False


def test_validator_rejects_empty():
    assert validate_cover_letter("", PROFILE, INVENTORY) is False
    assert validate_cover_letter("   ", PROFILE, INVENTORY) is False


def test_draft_returns_none_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert draft_cover_letter_llm(_job(), PROFILE, INVENTORY) is None


def test_draft_returns_validated_letter(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    clean = (
        "Dear Acme Hiring Team,\n\nThrough Koenen Revenue Systems I activated "
        "$51M in pipeline.\n\nSincerely,\nVadim Koenen"
    )
    monkeypatch.setattr(cl, "_call_claude", lambda *a, **k: clean)
    assert draft_cover_letter_llm(_job(), PROFILE, INVENTORY) == clean


def test_draft_rejects_fabricated_llm_output(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fabricated = "Dear Acme Hiring Team,\n\nI grew revenue 250%.\n\nSincerely,\nVadim"
    monkeypatch.setattr(cl, "_call_claude", lambda *a, **k: fabricated)
    # Falls back (None) rather than letting an invented metric through.
    assert draft_cover_letter_llm(_job(), PROFILE, INVENTORY) is None


def test_draft_handles_sdk_absent(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(cl, "_call_claude", lambda *a, **k: None)  # SDK/network failure
    assert draft_cover_letter_llm(_job(), PROFILE, INVENTORY) is None
