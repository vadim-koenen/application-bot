from __future__ import annotations

from dataclasses import asdict
from datetime import date
import json
from pathlib import Path
import re
from typing import Any

from application_bot.models import ApplicationPacket, Job, PolicyResult


PROFILE_FACTS = {
    "name": "Vadim Koenen",
    "identity": "Koenen Revenue Systems (KRS)",
    "website": "https://vadimkoenen.com/",
    "linkedin": "https://linkedin.com/in/vadimkoenen",
}


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:80] or "unknown"


def _matched_keywords(job: Job, config: dict[str, Any]) -> list[str]:
    corpus = " ".join(
        [job.title, job.department, job.description, job.requirements, job.responsibilities]
    ).lower()
    return [
        keyword
        for keyword in config.get("target_keywords", [])
        if keyword.lower() in corpus
    ][:12]


def generate_packet(
    job: Job,
    config: dict[str, Any],
    policy: PolicyResult,
) -> ApplicationPacket:
    keywords = _matched_keywords(job, config)
    skills = keywords or [
        "GTM strategy",
        "revenue systems",
        "growth marketing",
        "marketing operations",
    ]
    summary = (
        f"Executive GTM and growth leader operating through {PROFILE_FACTS['identity']}, "
        f"positioned for the {job.title} role at {job.company}. "
        f"Relevant emphasis: {', '.join(skills[:6])}. "
        "This draft mirrors the role language without adding unverified claims."
    )
    cover_email = (
        f"Subject: {job.title} — Vadim Koenen\n\n"
        f"Hello {job.company} hiring team,\n\n"
        f"I’m interested in the {job.title} opportunity. My current work through "
        f"{PROFILE_FACTS['identity']} centers on GTM, growth, and revenue-system "
        f"leadership, with particular alignment to {', '.join(skills[:4])}. "
        f"Additional context is available at {PROFILE_FACTS['website']}\n\n"
        "I would welcome a conversation about the role and the outcomes your team "
        "needs from this leader.\n\nBest,\nVadim Koenen"
    )
    cover_letter = (
        f"Dear {job.company} Hiring Team,\n\n"
        f"I am writing to express interest in the {job.title} role. My current "
        f"consulting identity is {PROFILE_FACTS['identity']}, where my positioning "
        "focuses on growth marketing, GTM systems, revenue operations, and "
        "AI-enabled transformation. "
        f"The role’s emphasis on {', '.join(skills[:5])} is especially relevant.\n\n"
        "I would bring an executive, systems-oriented perspective to aligning "
        "strategy, operating process, measurement, and cross-functional execution. "
        "I have intentionally left role-specific achievements out of this draft "
        "until they can be verified against the source resume.\n\n"
        f"More information: {PROFILE_FACTS['website']}\n\nSincerely,\nVadim Koenen"
    )
    suggested_answers = {
        "Name": PROFILE_FACTS["name"],
        "Current company": PROFILE_FACTS["identity"],
        "Website": PROFILE_FACTS["website"],
        "LinkedIn": PROFILE_FACTS["linkedin"],
        "Location preference": "Remote US preferred; Dallas/Plano/DFW hybrid considered.",
        "Work authorization": "REVIEW_REQUIRED — not supplied in the verified profile.",
        "Compensation expectations": "REVIEW_REQUIRED — confirm against role range.",
        "Legal attestations": "REVIEW_REQUIRED — answer personally; never infer.",
    }
    score_details = json.loads(job.score_details_json or "{}")
    why_fit = list(score_details.get("reasons") or [])
    risk_flags = list(score_details.get("risk_flags") or [])
    why_not = [flag for flag in risk_flags if "salary" in flag.lower() or "level" in flag.lower()]
    role_notes = [
        f"Source: {job.source}",
        f"Location: {job.location or 'Not provided'} ({job.remote_type})",
        f"Department: {job.department or 'Not provided'}",
        "Validate every resume claim before submission.",
    ]
    if policy.requires_human_review:
        role_notes.append("Submission policy requires human review.")
    action = {
        "AUTO_SUBMIT_EMAIL": "Review packet and email fields, then permit configured email send.",
        "AUTO_SUBMIT_ALLOWED": "Review final answers and submit through the explicitly authorized adapter.",
        "AUTO_PACKET_ONLY": "Review packet and complete the application manually.",
        "REVIEW_REQUIRED": "Resolve flagged questions or access requirements before proceeding.",
        "BLOCKED": "Do not automate submission; retain for reference or discard.",
    }[str(policy.decision)]
    return ApplicationPacket(
        job_id=int(job.id or 0),
        tailored_summary=summary,
        tailored_skills=skills,
        cover_email=cover_email,
        cover_letter=cover_letter,
        suggested_answers=suggested_answers,
        role_notes=role_notes,
        why_fit=why_fit,
        why_not=why_not,
        risk_flags=risk_flags,
        recommended_next_action=action,
        policy=str(policy.decision),
    )


def render_packet_markdown(job: Job, packet: ApplicationPacket) -> str:
    excerpt = (job.description or job.requirements or "No job description supplied.")[:1500]
    skills = "\n".join(f"- {value}" for value in packet.tailored_skills)
    answers = "\n".join(
        f"- **{key}:** {value}" for key, value in packet.suggested_answers.items()
    )
    notes = "\n".join(f"- {value}" for value in packet.role_notes)
    why_fit = "\n".join(f"- {value}" for value in packet.why_fit) or "- No scored fit reasons."
    why_not = "\n".join(f"- {value}" for value in packet.why_not) or "- None identified."
    risks = "\n".join(f"- {value}" for value in packet.risk_flags) or "- None identified."
    return f"""# Application Packet: {job.company} — {job.title}

## Opportunity

- **Company:** {job.company}
- **Title:** {job.title}
- **Source:** {job.source}
- **Apply URL:** {job.apply_url or "Not provided"}
- **Score:** {job.score if job.score is not None else "Unscored"}
- **Verdict:** {job.verdict or "Unscored"}
- **Submission policy:** {packet.policy}

## Tailored Summary

{packet.tailored_summary}

## Tailored Skills

{skills}

## Cover Email

{packet.cover_email}

## Short Cover Letter

{packet.cover_letter}

## Suggested Answers

{answers}

## Why Fit

{why_fit}

## Why Not / Tradeoffs

{why_not}

## Risk Flags

{risks}

## Notes

{notes}

## Recommended Next Action

{packet.recommended_next_action}

## Raw Job Excerpt

{excerpt}
"""


def export_packet(
    job: Job,
    packet: ApplicationPacket,
    output_root: str | Path,
) -> Path:
    folder = Path(output_root) / date.today().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{slugify(job.company)}_{slugify(job.title)}.md"
    path.write_text(render_packet_markdown(job, packet), encoding="utf-8")
    return path


def packet_to_dict(packet: ApplicationPacket) -> dict[str, Any]:
    return asdict(packet)
