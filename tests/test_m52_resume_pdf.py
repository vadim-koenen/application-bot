"""M52: polished single-column résumé PDF.

build_resume_document turns the approved master + a role into typed sections
(no new content); render_resume_pdf styles them into an ATS-safe single-column
PDF. export_application_pdfs uses the formatted renderer when a document is
passed, and still falls back to plain text otherwise.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

pytest.importorskip("fpdf")

from application_bot.config import DEFAULT_CONFIG
from application_bot.models import Job
from application_bot.pdf import export_application_pdfs, render_resume_pdf
from application_bot.resume import build_resume_document

MASTER = {
    "identity": {"name": "Vadim Koenen", "headline": "Revenue Systems Architect"},
    "contact": {"location": "Plano, TX", "email": "v@example.com",
                "website": "example.com", "linkedin": "linkedin.com/in/v"},
    "summary": "Operations leader with 14 years building revenue systems.",
    "selected_impact": ["$51M pipeline activated", "35% faster time-to-market"],
    "skills": {"Revenue Systems": ["Salesforce", "marketing operations", "6sense"]},
    "experience": [
        {"company": "Mitel", "title": "Senior Manager, Marketing Ops",
         "dates": "2020-2025", "location": "Remote",
         "bullets": ["Activated $51M in pipeline.", "Led a 6-person team."]},
    ],
    "education": ["MBA, Maryville University"],
    "certifications": ["Marketo Certified", "6sense Admin"],
}


def _job() -> Job:
    return Job(
        external_id="t1", source="manual_json", source_url="",
        apply_url="https://example.com/apply", company="Acme & Co",
        title="Director, Marketing Operations",
        description="Own revenue operations and marketing operations.",
        id=3,
    )


def test_build_document_is_grounded_in_master():
    doc = build_resume_document(_job(), MASTER, deepcopy(DEFAULT_CONFIG))
    assert doc["name"] == "Vadim Koenen"
    assert doc["headline"] == "Revenue Systems Architect"
    assert doc["summary"] == MASTER["summary"]
    assert doc["impact"] == MASTER["selected_impact"]
    assert doc["education"] == MASTER["education"]
    assert doc["certifications"] == MASTER["certifications"]
    assert len(doc["experience"]) == 1
    role = doc["experience"][0]
    assert role["title"] == "Senior Manager, Marketing Ops"
    assert role["bullets"] == MASTER["experience"][0]["bullets"]
    # Role-relevant competencies surface (skills mentioned in the JD come first).
    assert "marketing operations" in doc["competencies"]


def test_render_resume_pdf_writes_valid_pdf(tmp_path):
    doc = build_resume_document(_job(), MASTER, deepcopy(DEFAULT_CONFIG))
    path = render_resume_pdf(doc, tmp_path / "resume.pdf")
    assert path.exists()
    data = path.read_bytes()
    assert data[:5] == b"%PDF-"
    assert len(data) > 800


def test_render_handles_minimal_document(tmp_path):
    # Only the required header — optional sections absent must not crash.
    minimal = {"name": "Jane Doe", "headline": "", "contact_bits": [],
               "summary": "", "competencies": [], "impact": [],
               "experience": [], "education": [], "certifications": []}
    path = render_resume_pdf(minimal, tmp_path / "min.pdf")
    assert path.read_bytes()[:5] == b"%PDF-"


def test_export_uses_formatted_renderer_when_document_given(tmp_path):
    doc = build_resume_document(_job(), MASTER, deepcopy(DEFAULT_CONFIG))
    result = export_application_pdfs(
        _job(),
        resume_text="fallback text",
        cover_letter="Dear Team,\n\nHi.\n\nSincerely,\nVadim",
        output_root=tmp_path,
        resume_document=doc,
    )
    resume = Path(result["resume_pdf"])
    cover = Path(result["cover_pdf"])
    assert resume.read_bytes()[:5] == b"%PDF-"
    assert cover.read_bytes()[:5] == b"%PDF-"
    assert "acme-co_director-marketing-operations_resume.pdf" in str(resume)


def test_export_falls_back_to_text_without_document(tmp_path):
    result = export_application_pdfs(
        _job(),
        resume_text="VADIM KOENEN\nRevenue Systems Architect\n\nExperience...",
        cover_letter="Dear Team,\n\nHi.\n\nSincerely,\nVadim",
        output_root=tmp_path,
    )
    assert Path(result["resume_pdf"]).read_bytes()[:5] == b"%PDF-"
