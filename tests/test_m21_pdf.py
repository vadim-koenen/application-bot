"""M21: PDF résumé + cover letter generation."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fpdf")  # PDF rendering needs the optional fpdf2 dependency

from application_bot.models import Job
from application_bot.pdf import (
    export_application_pdfs,
    normalize_text,
    render_text_pdf,
)


def _job() -> Job:
    return Job(
        external_id="t1",
        source="manual_json",
        source_url="",
        apply_url="https://example.com/apply",
        company="Acme & Co",
        title="Director, Marketing Operations",
        id=3,
    )


def test_normalize_text_replaces_unicode_punctuation():
    out = normalize_text("Vadim’s “role” — RevOps • GTM")
    assert out == "Vadim's \"role\" - RevOps - GTM"
    # No characters outside latin-1 survive.
    out.encode("latin-1")


def test_render_text_pdf_writes_valid_pdf(tmp_path):
    path = render_text_pdf("Line one\n\nLine two", tmp_path / "x.pdf", title="Hello")
    assert path.exists()
    data = path.read_bytes()
    assert data[:5] == b"%PDF-"
    assert len(data) > 400


def test_export_application_pdfs_writes_both(tmp_path):
    result = export_application_pdfs(
        _job(),
        resume_text="VADIM KOENEN\nRevenue Systems Architect\n\nExperience...",
        cover_letter="Dear Hiring Team,\n\nI am interested.\n\nBest,\nVadim",
        output_root=tmp_path,
    )
    resume = Path(result["resume_pdf"])
    cover = Path(result["cover_pdf"])
    assert resume.exists() and cover.exists()
    assert resume.read_bytes()[:5] == b"%PDF-"
    assert cover.read_bytes()[:5] == b"%PDF-"
    # Filenames are slugified from company + title.
    assert "acme-co_director-marketing-operations_resume.pdf" in str(resume)
