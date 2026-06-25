"""M53: executive résumé formatting.

The structured document now carries categorized skills + phone/links, and the
PDF renderer styles them into an executive single-column layout — centered
header, inline bold-metric impact line, categorized competencies, company/date
experience headers with accent role titles, and bold lead-in bullets. Still
ATS-safe (selectable text, one column, no tables) and grounded only in the
approved master.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

pytest.importorskip("fpdf")

from application_bot.config import DEFAULT_CONFIG
from application_bot.models import Job
from application_bot.pdf import _bold_lead_markdown, render_resume_pdf
from application_bot.resume import build_resume_document

MASTER = {
    "identity": {"name": "Vadim Koenen", "headline": "Revenue Systems Architect"},
    "contact": {"location": "Plano, TX", "phone": "(945) 344-3699",
                "email": "v@example.com", "website": "example.com",
                "linkedin": "linkedin.com/in/v", "github": ""},
    "summary": "Operations leader with 14 years building revenue systems.",
    "selected_impact": ["$51M pipeline activated", "35% faster time-to-market"],
    "skills": {
        "AI + Automation": ["Agentic AI", "OpenAI API", "Python"],
        "Revenue Systems": ["Salesforce", "marketing operations", "6sense"],
    },
    "experience": [
        {"company": "Mitel", "title": "Senior Manager, Marketing Ops",
         "dates": "2020-2025", "location": "Remote",
         "bullets": ["Drove $51M pipeline: via intent data.", "Led a 6-person team."]},
    ],
    "education": ["MBA, Maryville University"],
    "certifications": ["Marketo Certified", "6sense Admin"],
}


def _job() -> Job:
    return Job(
        external_id="t1", source="manual_json", source_url="",
        apply_url="https://example.com/apply", company="Acme & Co",
        title="Director, Marketing Operations",
        description="Own revenue operations.", id=3,
    )


def test_bold_lead_markdown_bolds_pre_colon():
    assert _bold_lead_markdown("Pioneered agentic AI: did things.") == (
        "**Pioneered agentic AI:** did things."
    )
    # No colon -> unchanged (no forced bold).
    assert _bold_lead_markdown("Founded a practice for B2B teams") == (
        "Founded a practice for B2B teams"
    )


def test_document_carries_categorized_skills_and_phone():
    doc = build_resume_document(_job(), MASTER, deepcopy(DEFAULT_CONFIG))
    labels = [c["label"] for c in doc["skill_categories"]]
    assert labels == ["AI + Automation", "Revenue Systems"]
    assert doc["skill_categories"][0]["items"] == ["Agentic AI", "OpenAI API", "Python"]
    # Phone is included; the empty github is filtered out.
    assert "(945) 344-3699" in doc["contact_bits"]
    assert "" not in doc["contact_bits"]


def test_flat_skills_master_yields_no_categories():
    flat = {**MASTER, "skills": {"All": ["Salesforce", "Marketo"]}}
    # A single-bucket dict still produces one labeled category.
    doc = build_resume_document(_job(), flat, deepcopy(DEFAULT_CONFIG))
    assert [c["label"] for c in doc["skill_categories"]] == ["All"]


def test_render_executive_resume_is_valid_pdf(tmp_path):
    doc = build_resume_document(_job(), MASTER, deepcopy(DEFAULT_CONFIG))
    path = render_resume_pdf(doc, tmp_path / "resume.pdf")
    data = Path(path).read_bytes()
    assert data[:5] == b"%PDF-"
    assert len(data) > 900


def test_render_without_categories_falls_back_to_competencies(tmp_path):
    # No skill_categories key -> renderer uses the flat competencies list.
    doc = build_resume_document(_job(), MASTER, deepcopy(DEFAULT_CONFIG))
    doc.pop("skill_categories")
    path = render_resume_pdf(doc, tmp_path / "resume.pdf")
    assert Path(path).read_bytes()[:5] == b"%PDF-"
