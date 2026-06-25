"""M54: cover letter under the same letterhead as the résumé.

render_cover_letter_pdf renders the approved letter body beneath the shared
centered name/headline/contact letterhead, so the résumé and cover letter read
as a matched set. export_application_pdfs uses it whenever a résumé document is
available, and still falls back to the titled text renderer otherwise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fpdf")

import application_bot.pdf as pdfmod
from application_bot.models import Job
from application_bot.pdf import export_application_pdfs, render_cover_letter_pdf

DOC = {
    "name": "Vadim Koenen",
    "headline": "Revenue Systems Architect",
    "contact_bits": ["Plano, TX", "(945) 344-3699", "v@example.com"],
}
LETTER = (
    "Dear Acme Hiring Team,\n\nThrough Koenen Revenue Systems I activated $51M in "
    "pipeline.\n\nSincerely,\nVadim Koenen"
)


def _job() -> Job:
    return Job(
        external_id="t1", source="manual_json", source_url="",
        apply_url="https://example.com/apply", company="Acme & Co",
        title="Director, Marketing Operations", id=3,
    )


def test_render_cover_letter_pdf_is_valid(tmp_path):
    path = render_cover_letter_pdf(LETTER, DOC, tmp_path / "cover.pdf")
    data = Path(path).read_bytes()
    assert data[:5] == b"%PDF-"
    assert len(data) > 700


def test_render_cover_letter_handles_minimal_header(tmp_path):
    minimal = {"name": "Jane Doe", "headline": "", "contact_bits": []}
    path = render_cover_letter_pdf("Dear Team,\n\nHi.\n\nBest,\nJane", minimal,
                                   tmp_path / "c.pdf")
    assert Path(path).read_bytes()[:5] == b"%PDF-"


def test_export_uses_letterhead_cover_when_document_given(tmp_path, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(pdfmod, "render_cover_letter_pdf",
                        lambda *a, **k: (calls.append("letterhead"), a[-1])[1])
    monkeypatch.setattr(pdfmod, "render_resume_pdf", lambda *a, **k: a[-1])
    export_application_pdfs(
        _job(), resume_text="x", cover_letter=LETTER, output_root=tmp_path,
        resume_document=DOC,
    )
    assert calls == ["letterhead"]


def test_export_falls_back_to_titled_text_without_document(tmp_path, monkeypatch):
    used: list[str] = []
    monkeypatch.setattr(pdfmod, "render_cover_letter_pdf",
                        lambda *a, **k: used.append("letterhead"))
    monkeypatch.setattr(pdfmod, "render_text_pdf",
                        lambda *a, **k: (used.append("text"), a[1])[1])
    export_application_pdfs(
        _job(), resume_text="x", cover_letter=LETTER, output_root=tmp_path,
    )
    # No document -> both résumé and cover go through the plain text renderer.
    assert "letterhead" not in used
    assert used.count("text") == 2
