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


def export_application_pdfs(
    job: Any,
    resume_text: str,
    cover_letter: str,
    output_root: str | Path,
) -> dict[str, Any]:
    """Write a résumé PDF and a cover-letter PDF for one role."""
    folder = Path(output_root) / "pdf" / date.today().isoformat()
    base = f"{slugify(job.company)}_{slugify(job.title)}"
    resume_path = render_text_pdf(resume_text, folder / f"{base}_resume.pdf")
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
