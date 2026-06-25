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


def _content_width(pdf: Any) -> float:
    return pdf.w - pdf.l_margin - pdf.r_margin


def _section_header(pdf: Any, label: str) -> None:
    pdf.ln(9)
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 13, normalize_text(label.upper()), new_x="LMARGIN", new_y="NEXT")
    # Accent rule under the header, full content width.
    y = pdf.get_y() + 1
    pdf.set_draw_color(*_ACCENT)
    pdf.set_line_width(0.7)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(5)
    pdf.set_text_color(*_INK)


def _bold_lead_markdown(text: str) -> str:
    """Bold the lead-in phrase up to the first colon, executive-bullet style.

    "Pioneered agentic AI: …" -> "**Pioneered agentic AI:** …". Bullets without
    a colon are returned unchanged (no forced bold)."""
    text = normalize_text(text)
    head, sep, tail = text.partition(": ")
    return f"**{head}:** {tail}" if sep else text


def _ensure_room(pdf: Any, needed: float) -> None:
    """Start a new page if fewer than `needed` points remain, so a marker we
    draw manually can't be orphaned at the page bottom while its text flows on."""
    if pdf.get_y() + needed > pdf.h - pdf.b_margin:
        pdf.add_page()


def _bullets(pdf: Any, items: list[str], *, bold_lead: bool = True) -> None:
    dot_r = 1.3
    indent = 12
    width = _content_width(pdf) - indent
    for item in items:
        # Keep the bullet dot with its first line across a page break.
        _ensure_room(pdf, 14)
        y = pdf.get_y()
        # A small filled accent dot as the bullet marker (latin-1 core fonts
        # can't encode a real bullet glyph, so we draw one).
        pdf.set_fill_color(*_ACCENT)
        pdf.ellipse(pdf.l_margin + 2, y + 4.5, dot_r * 2, dot_r * 2, style="F")
        pdf.set_xy(pdf.l_margin + indent, y)
        pdf.set_font("Helvetica", size=9.5)
        pdf.set_text_color(*_INK)
        pdf.multi_cell(
            width, 13,
            _bold_lead_markdown(item) if bold_lead else normalize_text(item),
            new_x="LMARGIN", new_y="NEXT", markdown=bold_lead,
        )


def _letterhead(pdf: Any, document: dict[str, Any], *, name_size: float = 22) -> None:
    """Centered name / headline / contact + a rule — shared by the résumé and the
    cover letter so the two artifacts read as a matched set."""
    pdf.set_font("Helvetica", "B", name_size)
    pdf.set_text_color(*_INK)
    pdf.cell(0, name_size + 4, normalize_text(document.get("name", "")),
             new_x="LMARGIN", new_y="NEXT", align="C")
    if document.get("headline"):
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(*_ACCENT)
        pdf.multi_cell(0, 14, normalize_text(document["headline"]),
                       new_x="LMARGIN", new_y="NEXT", align="C")
    if document.get("contact_bits"):
        pdf.set_font("Helvetica", size=8.5)
        pdf.set_text_color(*_MUTED)
        pdf.multi_cell(0, 12, normalize_text("  |  ".join(document["contact_bits"])),
                       new_x="LMARGIN", new_y="NEXT", align="C")
    y = pdf.get_y() + 3
    pdf.set_draw_color(*_INK)
    pdf.set_line_width(0.8)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(2)
    pdf.set_text_color(*_INK)


def render_resume_pdf(document: dict[str, Any], path: str | Path) -> Path:
    """Render a structured résumé document to an executive single-column PDF.

    ATS-safe by construction — selectable text in reading order, one column, no
    tables or text boxes. The content comes entirely from `document` (built from
    the approved master); this function only styles it."""
    from fpdf import FPDF  # optional dep; imported lazily

    pdf = FPDF(format="Letter", unit="pt")
    pdf.set_auto_page_break(auto=True, margin=46)
    pdf.set_margins(54, 46, 54)
    pdf.add_page()

    _letterhead(pdf, document)

    if document.get("summary"):
        _section_header(pdf, "Executive Summary")
        pdf.set_font("Helvetica", size=9.5)
        pdf.multi_cell(0, 13.5, normalize_text(document["summary"]),
                       new_x="LMARGIN", new_y="NEXT", align="J")

    # --- Selected impact: inline, metric figure bolded, centered ---
    if document.get("impact"):
        _section_header(pdf, "Selected Impact")
        pdf.set_font("Helvetica", size=9.5)
        parts = []
        for item in document["impact"]:
            metric, sep, rest = normalize_text(item).partition(" ")
            parts.append(f"**{metric}** {rest}" if sep else f"**{metric}**")
        pdf.multi_cell(0, 14, "    ·    ".join(parts),
                       new_x="LMARGIN", new_y="NEXT", align="C", markdown=True)

    # --- Core competencies: categorized (Platforms: …), or a flat fallback ---
    if document.get("skill_categories"):
        _section_header(pdf, "Core Competencies")
        for cat in document["skill_categories"]:
            line = f"**{cat['label']}:** {', '.join(cat['items'])}"
            pdf.set_font("Helvetica", size=9.5)
            pdf.set_text_color(*_INK)
            pdf.multi_cell(0, 13, normalize_text(line),
                           new_x="LMARGIN", new_y="NEXT", markdown=True)
    elif document.get("competencies"):
        _section_header(pdf, "Core Competencies")
        pdf.set_font("Helvetica", size=9.5)
        pdf.multi_cell(0, 13, normalize_text(", ".join(document["competencies"])),
                       new_x="LMARGIN", new_y="NEXT")

    # --- Professional experience ---
    if document.get("experience"):
        _section_header(pdf, "Professional Experience")
        cw = _content_width(pdf)
        for role in document["experience"]:
            pdf.ln(4)
            # Keep a role's header (company / title) with its first bullet.
            _ensure_room(pdf, 52)
            # Company (bold, left) + dates (bold, right) on one line.
            y = pdf.get_y()
            pdf.set_text_color(*_INK)
            pdf.set_font("Helvetica", "B", 10.5)
            pdf.set_xy(pdf.l_margin, y)
            pdf.cell(cw * 0.66, 13, normalize_text(role.get("company", "")), align="L")
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.cell(cw * 0.34, 13, normalize_text(role.get("dates", "")),
                     align="R", new_x="LMARGIN", new_y="NEXT")
            # Role title in accent, then optional location.
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.set_text_color(*_ACCENT)
            pdf.multi_cell(0, 12.5, normalize_text(role.get("title", "")),
                           new_x="LMARGIN", new_y="NEXT")
            if role.get("location"):
                pdf.set_font("Helvetica", "I", 8.5)
                pdf.set_text_color(*_MUTED)
                pdf.cell(0, 11, normalize_text(role["location"]),
                         new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*_INK)
            pdf.ln(1)
            _bullets(pdf, role.get("bullets", []))

    # --- Education + certifications (combined) ---
    if document.get("education") or document.get("certifications"):
        _section_header(pdf, "Education & Certifications")
        _bullets(pdf, document.get("education", []), bold_lead=False)
        if document.get("certifications"):
            pdf.ln(2)
            pdf.set_font("Helvetica", size=9.5)
            pdf.set_text_color(*_INK)
            pdf.multi_cell(
                0, 13,
                normalize_text("**Certifications:** " + "  |  ".join(document["certifications"])),
                new_x="LMARGIN", new_y="NEXT", markdown=True,
            )

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))
    return out


def render_cover_letter_pdf(
    letter: str, document: dict[str, Any], path: str | Path
) -> Path:
    """Render a cover letter under the same letterhead as the résumé.

    `document` supplies the centered name / headline / contact header (the
    résumé document is reused); `letter` is the approved letter body, rendered
    as justified paragraphs. Nothing is added to the letter — only styled."""
    from fpdf import FPDF  # optional dep; imported lazily

    pdf = FPDF(format="Letter", unit="pt")
    pdf.set_auto_page_break(auto=True, margin=54)
    pdf.set_margins(64, 54, 64)
    pdf.add_page()

    _letterhead(pdf, document, name_size=18)

    pdf.ln(6)
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(*_MUTED)
    pdf.cell(0, 13, date.today().strftime("%B %-d, %Y"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_text_color(*_INK)
    for line in normalize_text(letter).split("\n"):
        if line.strip() == "":
            pdf.ln(7)
        else:
            pdf.set_font("Helvetica", size=10.5)
            pdf.multi_cell(0, 15, line, new_x="LMARGIN", new_y="NEXT", align="J")

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

    When `resume_document` (a structured résumé) is given, the résumé uses the
    executive single-column layout and the cover letter is rendered under the
    same letterhead (a matched set); otherwise both fall back to the plain text
    renderer for backward compatibility."""
    folder = Path(output_root) / "pdf" / date.today().isoformat()
    base = f"{slugify(job.company)}_{slugify(job.title)}"
    resume_path = (
        render_resume_pdf(resume_document, folder / f"{base}_resume.pdf")
        if resume_document is not None
        else render_text_pdf(resume_text, folder / f"{base}_resume.pdf")
    )
    cover_path = (
        render_cover_letter_pdf(
            cover_letter, resume_document, folder / f"{base}_cover.pdf"
        )
        if resume_document is not None
        else render_text_pdf(
            cover_letter,
            folder / f"{base}_cover.pdf",
            title=f"{job.company} — {job.title}",
        )
    )
    return {
        "job_id": getattr(job, "id", None),
        "company": job.company,
        "title": job.title,
        "resume_pdf": str(resume_path),
        "cover_pdf": str(cover_path),
    }
