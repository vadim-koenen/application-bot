"""M17: ATS resume v2 generator.

Verifies the generator reshapes only approved master content, aligns JD keywords
(including phrasing synonyms), reports true gaps, and never fabricates claims.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

from application_bot.config import DEFAULT_CONFIG
from application_bot.models import Job
from application_bot.resume import (
    export_ats_resume,
    keyword_alignment,
    load_resume_master,
    render_ats_resume_text,
)


MASTER = {
    "identity": {"name": "Test Person", "headline": "Revenue Systems Architect"},
    "contact": {
        "location": "Plano, TX (Remote)",
        "email": "t@example.com",
        "website": "example.com",
        "linkedin": "linkedin.com/in/test",
    },
    "summary": "Operations leader building revenue systems with Marketo and GTM workflows.",
    "selected_impact": ["$51M pipeline activated"],
    "skills": {
        "Revenue Systems": ["Salesforce", "marketing operations", "attribution readiness"],
        "ABM": ["6sense", "intent scoring"],
    },
    "experience": [
        {
            "company": "Mitel",
            "title": "Senior Manager, Global Marketing Operations",
            "dates": "08/2020 - 05/2025",
            "bullets": ["Led a global data operations team of 6."],
        }
    ],
    "education": ["MBA, Maryville University"],
    "certifications": ["2x Marketo Certified Expert"],
}


def _job(**kw) -> Job:
    base = dict(
        external_id="t1",
        source="manual_json",
        source_url="",
        apply_url="",
        company="Acme",
        title="Director, Marketing Operations",
        description="Own marketing operations, go-to-market systems, and attribution.",
        requirements="Salesforce, paid media, and media mix modeling.",
    )
    base.update(kw)
    return Job(**base)


def _config() -> dict:
    return deepcopy(DEFAULT_CONFIG)


def test_master_loads_and_requires_core_fields(tmp_path):
    path = tmp_path / "m.yaml"
    path.write_text(yaml.safe_dump(MASTER), encoding="utf-8")
    master = load_resume_master(path)
    assert master["identity"]["name"] == "Test Person"


def test_keyword_alignment_matches_synonyms_and_reports_true_gaps():
    align = keyword_alignment(_job(), MASTER, _config())
    # "go-to-market" in JD; master says "GTM" -> supported via synonym (matched).
    assert "go-to-market" in align["matched"]
    # "marketing operations" present verbatim -> matched.
    assert "marketing operations" in align["matched"]
    # "paid media" / "media mix modeling" are real gaps (not in master at all).
    assert "paid media" in align["gaps"]
    assert "media mix modeling" in align["gaps"]
    # A real gap must never be reported as matched.
    assert "paid media" not in align["matched"]


def test_resume_text_uses_only_master_content_no_fabrication():
    text = render_ats_resume_text(_job(), MASTER, _config())
    # Real approved content is present.
    assert "Led a global data operations team of 6." in text
    assert "Senior Manager, Global Marketing Operations" in text
    assert "Test Person".upper() in text
    # JD-only gap keywords must NOT be injected into the resume body.
    assert "paid media" not in text.lower()
    assert "media mix modeling" not in text.lower()
    # JD-relevant real skills are surfaced in competencies.
    assert "marketing operations" in text.lower()


def test_export_writes_md_and_txt(tmp_path):
    result = export_ats_resume(_job(), MASTER, _config(), tmp_path)
    assert Path(result["markdown_path"]).exists()
    assert Path(result["text_path"]).exists()
    assert result["matched_keywords"]
