"""ATS resume v2 generator.

Reshapes Vadim's approved master resume into an ATS-clean, JD-keyword-aligned
version per role. It never invents content: every line comes from the master
resume. JD keywords that are NOT supported by the master are reported as gaps
for the user's review, never inserted into the resume.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml

from application_bot.models import Job
from application_bot.packets import slugify


# Common MarTech / RevOps / demand-gen terms used only to detect JD keyword
# coverage and honest gaps. Presence in a resume is decided by the master only.
ROLE_VOCAB_EXTRA = [
    "salesforce marketing cloud",
    "adobe analytics",
    "google analytics",
    "ga4",
    "tableau",
    "looker",
    "cdp",
    "dam",
    "tessitura",
    "pardot",
    "eloqua",
    "segmentation",
    "attribution",
    "lead routing",
    "lead scoring",
    "quote-to-cash",
    "cpq",
    "data governance",
    "sql",
    "abm",
    "paid media",
    "seo",
    "sem",
    "programmatic",
    "media mix modeling",
    "incrementality",
]


# A JD term is "supported" if the master contains it OR an equivalent phrasing.
# This separates literal ATS phrasing gaps (you have it, add the exact term) from
# true capability gaps (no evidence at all).
TERM_SYNONYMS: dict[str, list[str]] = {
    "go-to-market": ["gtm"],
    "gtm systems": ["gtm", "revenue systems", "revenue-systems"],
    "gtm strategy": ["gtm"],
    "marketing technology": ["martech"],
    "lifecycle operations": ["lifecycle"],
    "lifecycle marketing": ["lifecycle"],
    "revenue operations": ["revops", "revenue systems", "revenue-systems"],
    "revops": ["revenue systems", "revenue-systems"],
    "marketing operations": ["marketing-operations", "marketing ops"],
}


def _term_supported(term: str, corpus: str) -> bool:
    if term.lower() in corpus:
        return True
    return any(syn in corpus for syn in TERM_SYNONYMS.get(term.lower(), []))


def load_resume_master(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        master = yaml.safe_load(handle) or {}
    for field in ("identity", "contact", "summary", "skills", "experience"):
        if field not in master:
            raise ValueError(f"Resume master is missing required field: {field}")
    return master


def _flat_skills(master: dict[str, Any]) -> list[str]:
    flat: list[str] = []
    seen: set[str] = set()
    for group in master.get("skills", {}).values():
        for skill in group:
            key = str(skill).strip().lower()
            if key and key not in seen:
                seen.add(key)
                flat.append(str(skill).strip())
    return flat


def _master_corpus(master: dict[str, Any]) -> str:
    parts: list[str] = [
        str(master["identity"].get("headline", "")),
        str(master.get("summary", "")),
        " ".join(master.get("selected_impact", [])),
        " ".join(_flat_skills(master)),
        " ".join(master.get("certifications", [])),
    ]
    for role in master.get("experience", []):
        parts.append(str(role.get("title", "")))
        parts.extend(str(b) for b in role.get("bullets", []))
    return " ".join(parts).lower()


def keyword_alignment(
    job: Job,
    master: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, list[str]]:
    jd = " ".join(
        (job.title, job.department, job.description, job.requirements, job.responsibilities)
    ).lower()
    corpus = _master_corpus(master)
    candidate_terms: list[str] = []
    seen: set[str] = set()
    for term in (
        list(config.get("target_keywords", []))
        + list(config.get("systems_lane_functions", []))
        + ROLE_VOCAB_EXTRA
    ):
        key = term.lower()
        if key not in seen:
            seen.add(key)
            candidate_terms.append(term)
    jd_terms = [t for t in candidate_terms if t.lower() in jd]
    matched = [t for t in jd_terms if _term_supported(t, corpus)]
    gaps = [t for t in jd_terms if not _term_supported(t, corpus)]
    return {"matched": matched, "gaps": gaps}


def _ordered_competencies(job: Job, master: dict[str, Any]) -> list[str]:
    jd = " ".join((job.title, job.description, job.requirements, job.responsibilities)).lower()
    flat = _flat_skills(master)
    relevant = [s for s in flat if s.lower() in jd]
    other = [s for s in flat if s.lower() not in jd]
    return relevant + other


def build_resume_document(
    job: Job,
    master: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Structured, role-tailored résumé for a formatted (non-flat) renderer.

    Same approved content and ordering as render_ats_resume_text — header,
    role-relevant keyword line, summary, competencies, selected impact,
    experience, education, certifications — but as typed sections a PDF layout
    can style with real hierarchy. Introduces no new content: everything is read
    from the approved master and the same keyword/competency helpers."""
    identity = master["identity"]
    contact = master["contact"]
    align = keyword_alignment(job, master, config)
    contact_bits = [
        contact.get("location"), contact.get("phone"), contact.get("email"),
        contact.get("website"), contact.get("linkedin"), contact.get("github"),
    ]
    # Categorized skills (Platforms / Lifecycle / …) for the executive layout;
    # falls back to the flat competency list if the master uses a plain list.
    raw_skills = master.get("skills")
    skill_categories = (
        [
            {"label": str(label), "items": [str(s) for s in items]}
            for label, items in raw_skills.items()
            if items
        ]
        if isinstance(raw_skills, dict)
        else []
    )
    experience = [
        {
            "company": str(role.get("company", "")),
            "title": str(role.get("title", "")),
            "dates": str(role.get("dates", "")),
            "location": str(role.get("location", "")),
            "bullets": [str(b) for b in role.get("bullets", [])],
        }
        for role in master.get("experience", [])
    ]
    return {
        "name": identity["name"],
        "headline": identity["headline"],
        "contact_bits": [b for b in contact_bits if b],
        "relevant_label": (
            f"Relevant to {job.company} — {job.title}" if align["matched"] else ""
        ),
        "relevant": list(align["matched"][:10]),
        "summary": " ".join(str(master.get("summary", "")).split()),
        "competencies": _ordered_competencies(job, master),
        "skill_categories": skill_categories,
        "impact": [str(x) for x in master.get("selected_impact", [])],
        "experience": experience,
        "education": [str(x) for x in master.get("education", [])],
        "certifications": [str(x) for x in master.get("certifications", [])],
    }


def render_ats_resume_text(
    job: Job,
    master: dict[str, Any],
    config: dict[str, Any],
) -> str:
    identity = master["identity"]
    contact = master["contact"]
    align = keyword_alignment(job, master, config)
    competencies = _ordered_competencies(job, master)

    contact_bits = [
        contact.get("location"),
        contact.get("email"),
        contact.get("website"),
        contact.get("linkedin"),
    ]
    contact_line = " | ".join(b for b in contact_bits if b)

    lines: list[str] = []
    lines.append(identity["name"].upper())
    lines.append(identity["headline"])
    lines.append(contact_line)
    lines.append("")

    if align["matched"]:
        lines.append(f"RELEVANT TO {job.company.upper()} — {job.title.upper()}")
        lines.append(", ".join(align["matched"][:10]))
        lines.append("")

    lines.append("SUMMARY")
    lines.append(" ".join(str(master.get("summary", "")).split()))
    lines.append("")

    lines.append("CORE COMPETENCIES")
    lines.append(", ".join(competencies))
    lines.append("")

    if master.get("selected_impact"):
        lines.append("SELECTED IMPACT")
        for item in master["selected_impact"]:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("PROFESSIONAL EXPERIENCE")
    for role in master.get("experience", []):
        header = f"{role['company']} | {role['title']} | {role['dates']}"
        lines.append(header)
        for bullet in role.get("bullets", []):
            lines.append(f"- {bullet}")
        lines.append("")

    if master.get("education"):
        lines.append("EDUCATION")
        for item in master["education"]:
            lines.append(f"- {item}")
        lines.append("")

    if master.get("certifications"):
        lines.append("CERTIFICATIONS")
        lines.append(", ".join(master["certifications"]))
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def render_ats_resume_markdown(
    job: Job,
    master: dict[str, Any],
    config: dict[str, Any],
) -> str:
    identity = master["identity"]
    contact = master["contact"]
    align = keyword_alignment(job, master, config)
    competencies = _ordered_competencies(job, master)
    contact_bits = [
        contact.get("location"),
        contact.get("email"),
        contact.get("website"),
        contact.get("linkedin"),
    ]
    contact_line = " | ".join(b for b in contact_bits if b)

    out: list[str] = []
    out.append(f"# {identity['name']}")
    out.append(f"**{identity['headline']}**  ")
    out.append(contact_line)
    out.append("")
    out.append(
        f"> ATS-tuned for **{job.company} — {job.title}**. "
        "Built only from approved master-resume content; no claims added."
    )
    out.append("")
    if align["matched"]:
        out.append("## Relevant to This Role")
        out.append(", ".join(align["matched"][:12]))
        out.append("")
    out.append("## Summary")
    out.append(" ".join(str(master.get("summary", "")).split()))
    out.append("")
    out.append("## Core Competencies")
    out.append(", ".join(competencies))
    out.append("")
    if master.get("selected_impact"):
        out.append("## Selected Impact")
        out.extend(f"- {item}" for item in master["selected_impact"])
        out.append("")
    out.append("## Professional Experience")
    for role in master.get("experience", []):
        out.append(f"### {role['company']} — {role['title']}")
        out.append(f"_{role['dates']}_")
        out.extend(f"- {bullet}" for bullet in role.get("bullets", []))
        out.append("")
    if master.get("education"):
        out.append("## Education")
        out.extend(f"- {item}" for item in master["education"])
        out.append("")
    if master.get("certifications"):
        out.append("## Certifications")
        out.append(", ".join(master["certifications"]))
        out.append("")
    if align["gaps"]:
        out.append("## JD Keywords Not Supported by Your Resume (review — not added)")
        out.append(
            "These appear in the posting but are not in your approved master "
            "resume, so they were left out. Add real evidence if you have it:"
        )
        out.extend(f"- {gap}" for gap in align["gaps"])
        out.append("")
    return "\n".join(out).strip() + "\n"


def export_ats_resume(
    job: Job,
    master: dict[str, Any],
    config: dict[str, Any],
    output_root: str | Path,
) -> dict[str, Any]:
    folder = Path(output_root) / "ats_resumes" / date.today().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    base = f"{slugify(job.company)}_{slugify(job.title)}"
    md_path = folder / f"{base}.md"
    txt_path = folder / f"{base}.txt"
    md_path.write_text(render_ats_resume_markdown(job, master, config), encoding="utf-8")
    txt_path.write_text(render_ats_resume_text(job, master, config), encoding="utf-8")
    align = keyword_alignment(job, master, config)
    return {
        "job_id": job.id,
        "company": job.company,
        "title": job.title,
        "markdown_path": str(md_path),
        "text_path": str(txt_path),
        "matched_keywords": align["matched"],
        "gap_keywords": align["gaps"],
    }
