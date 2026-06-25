"""M21: PDF artifacts.

Render the tailored ATS résumé text and the claim-safe cover letter to clean,
ATS-parseable PDFs using fpdf2 (pure Python, no system libraries). Text is
ASCII-normalized (curly quotes, em dashes) so the core latin-1 fonts render it
and ATS parsers read it cleanly — the content still comes only from the approved
résumé/packet, nothing is added.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from application_bot.packets import slugify

# Common typographic characters the latin-1 core fonts can't encode.
_UNICODE_MAP = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", "•": "-",
    "…": "...", " ": " ",
}


def normalize_text(text: str) -> str:
    for src, dst in _UNICODE_MAP.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", "ignore").decode("latin-1")


def render_text_pdf(text: str, path: str | Path, *, title: str | None = None) -> Path:
    """Render plain text to a single, readable PDF document."""
    from fpdf import FPDF  # optional dep; imported lazily so the core stays light

    pdf = FPDF(format="Letter", unit="pt")
    pdf.set_auto_page_break(auto=True, margin=54)
    pdf.set_margins(54, 54, 54)
    pdf.add_page()
    if title:
        pdf.set_font("Helvetica", "B", 14)
        pdf.multi_cell(0, 18, normalize_text(title), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(8)
    pdf.set_font("Helvetica", size=10.5)
    for line in normalize_text(text).split("\n"):
        if line.strip() == "":
            pdf.ln(7)
        else:
            pdf.multi_cell(0, 14, line, new_x="LMARGIN", new_y="NEXT")
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))
    return out


# Single-column résumé palette. Dark slate ink + one navy accent for section
# rules and role companies — text + thin lines only, so the PDF stays fully
# ATS-parseable (no tables, columns, or text boxes).
_INK = (17, 24, 39)
_MUTED = (90, 99, 114)
_ACCENT = (31, 58, 95)


def _section_header(pdf: Any, label: str) -> None:
    pdf.ln(7)
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.set_text_color(*_ACCENT)
    # multi_cell so an unusually long label (e.g. "Relevant to <company> — <title>")
    # wraps instead of overrunning the right margin.
    pdf.multi_cell(0, 13, normalize_text(label.upper()), new_x="LMARGIN", new_y="NEXT")
    # Hairline rule under the header, full content width.
    y = pdf.get_y() + 1
    pdf.set_draw_color(*_ACCENT)
    pdf.set_line_width(0.6)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(5)
    pdf.set_text_color(*_INK)


def _bullets(pdf: Any, items: list[str]) -> None:
    indent = 12
    width = pdf.w - pdf.l_margin - pdf.r_margin - indent
    for item in items:
        y = pdf.get_y()
        pdf.set_font("Helvetica", size=9.5)
        pdf.set_xy(pdf.l_margin, y)
        pdf.cell(indent, 13, normalize_text("-"))
        pdf.set_xy(pdf.l_margin + indent, y)
        pdf.multi_cell(width, 13, normalize_text(item), new_x="LMARGIN", new_y="NEXT")


def render_resume_pdf(document: dict[str, Any], path: str | Path) -> Path:
    """Render a structured résumé document to a polished single-column PDF.

    ATS-safe by construction — selectable text in reading order, one column, no
    tables or text boxes. The content comes entirely from `document` (built from
    the approved master); this function only styles it."""
    from fpdf import FPDF  # optional dep; imported lazily

    pdf = FPDF(format="Letter", unit="pt")
    pdf.set_auto_page_break(auto=True, margin=48)
    pdf.set_margins(54, 50, 54)
    pdf.add_page()

    # Header: name, headline, contact line, then a rule.
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*_INK)
    pdf.cell(0, 24, normalize_text(document.get("name", "")),
             new_x="LMARGIN", new_y="NEXT")
    if document.get("headline"):
        pdf.set_font("Helvetica", size=11)
        pdf.set_text_color(*_ACCENT)
        pdf.cell(0, 15, normalize_text(document["headline"]),
                 new_x="LMARGIN", new_y="NEXT")
    if document.get("contact_bits"):
        pdf.set_font("Helvetica", size=8.5)
        pdf.set_text_color(*_MUTED)
        pdf.cell(0, 13, normalize_text("  |  ".join(document["contact_bits"])),
                 new_x="LMARGIN", new_y="NEXT")
    y = pdf.get_y() + 3
    pdf.set_draw_color(*_INK)
    pdf.set_line_width(0.8)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(2)
    pdf.set_text_color(*_INK)

    if document.get("relevant"):
        _section_header(pdf, document.get("relevant_label") or "Relevant skills")
        pdf.set_font("Helvetica", size=9.5)
        pdf.multi_cell(0, 13, normalize_text("  •  ".join(document["relevant"])),
                       new_x="LMARGIN", new_y="NEXT")

    if document.get("summary"):
        _section_header(pdf, "Summary")
        pdf.set_font("Helvetica", size=9.5)
        pdf.multi_cell(0, 13.5, normalize_text(document["summary"]),
                       new_x="LMARGIN", new_y="NEXT", align="J")

    if document.get("competencies"):
        _section_header(pdf, "Core competencies")
        pdf.set_font("Helvetica", size=9.5)
        pdf.multi_cell(0, 13, normalize_text("  •  ".join(document["competencies"])),
                       new_x="LMARGIN", new_y="NEXT")

    if document.get("impact"):
        _section_header(pdf, "Selected impact")
        _bullets(pdf, document["impact"])

    if document.get("experience"):
        _section_header(pdf, "Professional experience")
        for role in document["experience"]:
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 10.5)
            pdf.set_text_color(*_INK)
            pdf.multi_cell(0, 13, normalize_text(role.get("title", "")),
                           new_x="LMARGIN", new_y="NEXT")
            meta = "  ·  ".join(
                p for p in (role.get("company"), role.get("location"), role.get("dates")) if p
            )
            if meta:
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(*_ACCENT)
                pdf.cell(0, 12, normalize_text(meta), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*_INK)
            _bullets(pdf, role.get("bullets", []))

    if document.get("education"):
        _section_header(pdf, "Education")
        _bullets(pdf, document["education"])

    if document.get("certifications"):
        _section_header(pdf, "Certifications")
        pdf.set_font("Helvetica", size=9.5)
        pdf.multi_cell(0, 13, normalize_text("  •  ".join(document["certifications"])),
                       new_x="LMARGIN", new_y="NEXT")

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))
    return out


def export_application_pdfs(
    job: Any,
    resume_text: str,
    cover_letter: str,
    output_root: str | Path,
    *,
    resume_document: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a résumé PDF and a cover-letter PDF for one role.

    When `resume_document` (a structured résumé) is given, the résumé is rendered
    with the polished single-column layout; otherwise it falls back to the plain
    text renderer for backward compatibility."""
    folder = Path(output_root) / "pdf" / date.today().isoformat()
    base = f"{slugify(job.company)}_{slugify(job.title)}"
    resume_path = (
        render_resume_pdf(resume_document, folder / f"{base}_resume.pdf")
        if resume_document is not None
        else render_text_pdf(resume_text, folder / f"{base}_resume.pdf")
    )
    cover_path = render_text_pdf(
        cover_letter,
        folder / f"{base}_cover.pdf",
        title=f"{job.company} — {job.title}",
    )
    return {
        "job_id": getattr(job, "id", None),
        "company": job.company,
        "title": job.title,
        "resume_pdf": str(resume_path),
        "cover_pdf": str(cover_path),
    }
