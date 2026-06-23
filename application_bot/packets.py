from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import re
from typing import Any

from application_bot.claims import (
    approved_evidence_claims,
    blocked_claim_ids,
    claim_is_approved,
    detect_claim_gaps,
    matched_approved_keywords,
    packet_claim_violations,
    safe_rewrites_for_gaps,
    text_claim_violations,
    unresolved_claim_gaps,
)
from application_bot.answers import build_answer_draft
from application_bot.config import (
    load_answer_bank,
    load_claim_evidence,
    load_claim_inventory,
)
from application_bot.models import (
    ApplicationPacket,
    Job,
    PacketAssessment,
    PacketStatus,
    PolicyResult,
    utc_now,
)


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:80] or "unknown"


# A theme-specific opening clause keyed by the operator's approved positioning
# themes. The clause that leads the letter is chosen by which theme the JD most
# emphasizes (the first matched approved keyword), so different roles get a
# different, on-point opening. Every clause describes approved *function* only —
# no metrics, tenure, employers, or credentials — so they can never trip the
# claim auditor.
_THEME_LEAD: dict[str, str] = {
    "demand generation": (
        "designing the demand and pipeline systems that turn marketing "
        "investment into qualified, trackable revenue"
    ),
    "revenue systems": (
        "architecting the revenue systems — CRM, attribution, and the data "
        "model beneath them — that sales and finance can actually trust"
    ),
    "gtm systems": (
        "building the GTM systems and automation that let go-to-market teams "
        "move without waiting on operations"
    ),
    "gtm strategy": (
        "connecting go-to-market strategy to the systems that execute it, so "
        "the plan and the pipeline tell the same story"
    ),
    "marketing operations": (
        "running the marketing operations and data layer that keeps campaigns, "
        "routing, and reporting accurate at scale"
    ),
    "lifecycle marketing": (
        "owning the lifecycle and nurture architecture that moves prospects "
        "from first touch to closed-won"
    ),
    "marketing technology": (
        "owning the martech stack and the integrations that keep every system "
        "speaking the same language"
    ),
    "ai-enabled gtm workflows": (
        "putting AI to work inside go-to-market operations — scoring, routing, "
        "enrichment, and content — without losing data integrity"
    ),
}
_DEFAULT_LEAD = (
    "architecting the revenue and GTM systems beneath the platform so "
    "marketing and sales can move quickly and trust the same numbers"
)

# Terms the cover letter must never volunteer (legal/comp-sensitive). The claim
# auditor covers metrics/tenure/credentials; this guards the JD-derived snippet
# against leaking compensation, work-authorization, or relocation language.
_COVER_SENSITIVE = (
    "salary", "compensation", "visa", "sponsor", "authoriz", "wage",
    "relocat", "clearance",
)


def _lead_clause(matched: list[str]) -> str:
    """Pick the opening clause from the JD's most-emphasized approved theme."""
    for theme in matched:
        clause = _THEME_LEAD.get(str(theme).strip().lower())
        if clause:
            return clause
    return _DEFAULT_LEAD


def _role_focus_snippet(job: Job, inventory: dict[str, Any]) -> str:
    """A short, claim-safe phrase quoting what the JD says the role is about.

    Pulls the first sentence of the responsibilities/requirements (not the
    'about us' description), then drops it entirely if it contains anything the
    claim auditor flags or any comp/legal-sensitive term — so it's always safe
    to quote back in the letter."""
    raw = (job.responsibilities or job.requirements or "").strip()
    if not raw:
        return ""
    snippet = re.split(r"(?<=[.!?])\s+", raw)[0].strip()
    snippet = re.sub(r"\s+", " ", snippet)[:200].rstrip(" .,;:")
    if len(snippet) < 20:
        return ""
    if text_claim_violations(snippet, inventory):
        return ""
    if any(term in snippet.lower() for term in _COVER_SENSITIVE):
        return ""
    return snippet


def _approved_tenure_years(evidence: dict[str, Any]) -> int:
    claim_text = next(
        (
            str(claim.get("claim_text") or "")
            for claim in evidence.get("claims", [])
            if claim.get("claim_id") == "years_of_experience"
        ),
        "",
    )
    years = [
        int(value)
        for value in re.findall(r"\b(\d{1,2})\+?\s+years?\b", claim_text)
    ]
    return max(years) if years else 0


def assess_packet(
    job: Job,
    config: dict[str, Any],
    policy: PolicyResult,
    inventory: dict[str, Any],
    evidence: dict[str, Any] | None = None,
) -> PacketAssessment:
    evidence = evidence or load_claim_evidence(config["claim_evidence"])
    thresholds = config.get("packet_thresholds", {})
    ready_min = int(thresholds.get("ready_min_score", 65))
    review_min = int(thresholds.get("review_min_score", 45))
    strong_function = int(thresholds.get("strong_function_points", 10))
    score = int(job.score or 0)
    details = json.loads(job.score_details_json or "{}")
    dimensions = details.get("dimensions") or {}
    seniority = int(dimensions.get("seniority") or 0)
    function_fit = int(dimensions.get("function_fit") or 0)
    title_function_match = any(
        keyword.lower() in job.title.lower()
        for keyword in config.get("target_keywords", [])
    )
    generic_sales_title = "sales" in job.title.lower() and not title_function_match
    detected_gaps = detect_claim_gaps(job, inventory)
    claim_corpus = " ".join(
        (
            job.title,
            job.department,
            job.description,
            job.requirements,
            job.responsibilities,
        )
    )
    claim_gaps = unresolved_claim_gaps(
        detected_gaps,
        evidence,
        corpus=claim_corpus,
    )
    soft_requirement_claims = set(
        config.get("packet_soft_requirement_claims", [])
    )
    required_soft_tenure = int(
        config.get("years_requirement_scoring", {}).get(
            "approved_years",
            14,
        )
    )
    soft_claim_gaps = {
        claim_id
        for claim_id in claim_gaps
        if claim_id in soft_requirement_claims
        and claim_is_approved(
            claim_id,
            evidence,
            context="packet_text",
        )
        and (
            claim_id != "years_of_experience"
            or _approved_tenure_years(evidence) >= required_soft_tenure
        )
    }
    claim_gaps = [
        claim_id
        for claim_id in claim_gaps
        if claim_id not in soft_claim_gaps
    ]

    if str(policy.decision) == "BLOCKED" or str(job.verdict) == "BLOCKED":
        return PacketAssessment(
            PacketStatus.BLOCKED,
            claim_gaps,
            ["SUBMISSION_POLICY_BLOCKED"],
            "Do not proceed; retain the opportunity for audit only.",
            False,
        )

    if generic_sales_title:
        return PacketAssessment(
            PacketStatus.NOT_WORTH_PACKET,
            claim_gaps,
            ["GENERIC_SALES_ROLE"],
            "Do not generate a packet unless GTM or revenue-systems ownership is central.",
            False,
        )

    if (
        str(job.verdict) in {"APPLY_PRIORITY", "GOOD_FIT"}
        and score >= ready_min
    ):
        if claim_gaps:
            return PacketAssessment(
                PacketStatus.REVIEW_PACKET_CLAIM_GAPS,
                claim_gaps,
                ["TARGET_FIT", "UNVERIFIED_REQUIRED_CLAIMS"],
                "Review the listed claim gaps before using this packet.",
                True,
            )
        return PacketAssessment(
            PacketStatus.PACKET_READY,
            [],
            [
                "TARGET_FIT",
                "APPROVED_CLAIMS_SUFFICIENT",
                *(
                    ["SOFT_REQUIREMENT_MISMATCH"]
                    if soft_claim_gaps
                    else []
                ),
            ],
            "Review the claim-safe packet and complete the application manually.",
            True,
        )

    strong_match = seniority > 0 and (
        function_fit >= strong_function or title_function_match
    )
    if score >= review_min and strong_match:
        review_gaps = claim_gaps or ["manual_fit_review_required"]
        reasons = ["MAYBE_STRONG_TITLE_FUNCTION_MATCH"]
        if claim_gaps:
            reasons.append("UNVERIFIED_REQUIRED_CLAIMS")
        else:
            reasons.append("BELOW_PACKET_READY_THRESHOLD")
        return PacketAssessment(
            PacketStatus.REVIEW_PACKET_CLAIM_GAPS,
            review_gaps,
            reasons,
            "Review role fit and claim coverage before deciding whether to apply.",
            True,
        )

    reason_codes: list[str] = []
    if seniority <= 0:
        reason_codes.append("WRONG_OR_UNCLEAR_LEVEL")
    if function_fit < strong_function:
        reason_codes.append("WEAK_FUNCTION_MATCH")
    if score < review_min:
        reason_codes.append("BELOW_REVIEW_THRESHOLD")
    if "workday" in job.apply_url.lower():
        reason_codes.append("HIGH_APPLICATION_FRICTION")
    return PacketAssessment(
        PacketStatus.NOT_WORTH_PACKET,
        claim_gaps,
        reason_codes or ["NOT_WORTH_PACKET"],
        "Do not spend packet-review time unless new information materially changes fit.",
        False,
    )


def generate_packet(
    job: Job,
    config: dict[str, Any],
    policy: PolicyResult,
    inventory: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    answer_bank: dict[str, Any] | None = None,
    assessment: PacketAssessment | None = None,
    impact_highlights: list[str] | None = None,
) -> ApplicationPacket:
    inventory = inventory or load_claim_inventory(config["resume_claim_inventory"])
    evidence = evidence or load_claim_evidence(config["claim_evidence"])
    answer_bank = answer_bank or load_answer_bank(config["application_answer_bank"])
    assessment = assessment or assess_packet(
        job, config, policy, inventory, evidence
    )
    identity = inventory["identity"]
    contact = inventory["contact_assets"]
    business = inventory["current_business_identity"]
    skills = matched_approved_keywords(job, inventory)
    if not skills:
        skills = list(inventory.get("approved_positioning_themes", []))[:4]
    approved_claim_ids = [
        str(claim["claim_id"])
        for claim in approved_evidence_claims(evidence, context="packet_text")
        if claim["claim_id"]
        in {
            "identity_name",
            "company_identity",
            "website",
            "linkedin",
            "current_positioning",
            "target_functions",
            "krs_positioning",
            "approved_platform_keywords",
            "geography_preference",
        }
    ]
    approved_claim_ids.extend(
        gap_id
        for gap_id in detect_claim_gaps(job, inventory)
        if gap_id not in assessment.claim_gaps
        and gap_id
        not in set(config.get("packet_soft_requirement_claims", []))
        and gap_id not in approved_claim_ids
    )
    current_positioning = business["approved_display"]
    if claim_is_approved(
        "current_positioning", evidence, context="packet_text"
    ):
        current_positioning = next(
            (
                str(claim["claim_text"])
                for claim in evidence.get("claims", [])
                if claim.get("claim_id") == "current_positioning"
            ),
            current_positioning,
        )
    fit_summary = (
        f"{job.title} at {job.company} scored {job.score if job.score is not None else 'unscored'} "
        f"with verdict {job.verdict or 'unscored'}. Packet outcome: "
        f"{assessment.status}."
    )
    summary = (
        f"{identity['name']} is positioned as {current_positioning} through "
        f"{business['approved_display']}. "
        f"For the {job.title} role at {job.company}, the approved positioning "
        f"themes that match the posting are {', '.join(skills[:6])}. "
        "This summary uses only the approved claim inventory and does not assert "
        "unverified tenure, achievements, credentials, employers, or metrics."
    )
    cover_email_entry = (
        answer_bank.get("answers", {}).get("cover_email_base", {})
    )
    cover_email_base = (
        str(cover_email_entry.get("value"))
        if cover_email_entry.get("status") == "APPROVED"
        and claim_is_approved(
            str(cover_email_entry.get("claim_id") or ""),
            evidence,
            context="application_answer",
        )
        else "I am interested in this opportunity and would welcome a conversation."
    )
    cover_email = (
        f"Subject: {job.title} — {identity['name']}\n\n"
        f"Hello {job.company} hiring team,\n\n"
        f"{cover_email_base} My current professional "
        f"positioning through {business['approved_display']} includes "
        f"{', '.join(skills[:4])}. Additional public context is available at "
        f"{contact['website']}\n\n"
        "I would welcome a conversation to assess mutual fit and the role’s "
        f"priorities.\n\nBest,\n{identity['name']}"
    )
    # Impact bullets are pulled from the approved résumé (selected_impact) by the
    # caller, then filtered here against the same prohibited-claim patterns the
    # packet auditor uses — so the cover letter can never assert anything the
    # inventory hasn't approved, no matter what the caller passes in.
    safe_highlights = [
        line.strip()
        for line in (impact_highlights or [])
        if line and line.strip() and not text_claim_violations(line, inventory)
    ][:3]
    lead = _lead_clause(skills)
    snippet = _role_focus_snippet(job, inventory)
    maps = ", ".join(skills[:5]) if skills else business["approved_display"]
    cover_parts = [
        f"Dear {job.company} Hiring Team,",
        (
            f"I'm writing to apply for the {job.title} role at {job.company}. "
            f"Through {business['approved_display']}, I focus on {lead}."
        ),
    ]
    if snippet:
        cover_parts.append(
            f"Your posting centers on “{snippet}” — that's exactly the "
            "operating layer I build and run."
        )
    if safe_highlights:
        bullets = "\n".join(f"  • {line}" for line in safe_highlights)
        cover_parts.append("A few results from that work:\n" + bullets)
    cover_parts.append(
        f"The parts of this role that map most directly to what I do: {maps}. "
        f"I'd welcome the chance to walk {job.company} through how I'd approach "
        "them."
    )
    cover_parts.append(
        f"More context is at {contact['website']}. Thank you for your "
        f"consideration.\n\nSincerely,\n{identity['name']}"
    )
    cover_letter = "\n\n".join(cover_parts)
    suggested_answers = {"Name": identity["name"], **build_answer_draft(answer_bank, evidence)}
    score_details = json.loads(job.score_details_json or "{}")
    why_fit = list(score_details.get("reasons") or [])
    risk_flags = list(score_details.get("risk_flags") or [])
    why_not = [flag for flag in risk_flags if "salary" in flag.lower() or "level" in flag.lower()]
    role_notes = [
        f"Source: {job.source}",
        f"Location: {job.location or 'Not provided'} ({job.remote_type})",
        f"Department: {job.department or 'Not provided'}",
        "Generated only from config/resume_claim_inventory.yaml.",
    ]
    if assessment.claim_gaps:
        role_notes.append(
            f"Claim gaps requiring review: {', '.join(assessment.claim_gaps)}."
        )
    if policy.requires_human_review:
        role_notes.append("Submission policy requires human review.")
    packet = ApplicationPacket(
        job_id=int(job.id or 0),
        fit_summary=fit_summary,
        tailored_summary=summary,
        tailored_skills=skills,
        cover_email=cover_email,
        cover_letter=cover_letter,
        suggested_answers=suggested_answers,
        role_notes=role_notes,
        why_fit=why_fit,
        why_not=why_not,
        risk_flags=risk_flags,
        recommended_next_action=assessment.recommended_next_action,
        policy=str(policy.decision),
        packet_status=str(assessment.status),
        claim_gaps=assessment.claim_gaps,
        reason_codes=assessment.reason_codes,
        approved_claim_ids=approved_claim_ids,
        pending_claims_not_used=assessment.claim_gaps,
        safe_substitutions=safe_rewrites_for_gaps(
            assessment.claim_gaps, evidence
        ),
        blocked_claims=blocked_claim_ids(assessment.claim_gaps, evidence),
    )
    violations = packet_claim_violations(packet, inventory)
    if violations:
        raise ValueError(
            "Generated packet contains unapproved claim patterns: "
            + ", ".join(violations)
        )
    return packet


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
- **Packet status:** {packet.packet_status}

## Claim Safety

- **Approved claim IDs:** {", ".join(packet.approved_claim_ids) or "None"}
- **Claim gaps:** {", ".join(packet.claim_gaps) or "None"}
- **Reason codes:** {", ".join(packet.reason_codes) or "None"}

## Fit Summary

{packet.fit_summary}

## Claim Audit

- **Approved claims used:** {", ".join(packet.approved_claim_ids) or "None"}
- **Pending claims not used:** {", ".join(packet.pending_claims_not_used) or "None"}
- **Safe substitutions used:** {", ".join(packet.safe_substitutions) or "None"}
- **Blocked claims:** {", ".join(packet.blocked_claims) or "None"}

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
    folder = Path(output_root) / utc_now()[:10]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{slugify(job.company)}_{slugify(job.title)}.md"
    path.write_text(render_packet_markdown(job, packet), encoding="utf-8")
    return path


def packet_to_dict(packet: ApplicationPacket) -> dict[str, Any]:
    return asdict(packet)
