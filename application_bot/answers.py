from __future__ import annotations

from typing import Any

from application_bot.claims import claim_is_approved


def build_answer_draft(
    answer_bank: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, str]:
    labels = {
        "website": "Website",
        "linkedin": "LinkedIn",
        "current_company": "Current company",
        "current_positioning": "Current positioning",
        "desired_role_type": "Desired role type",
        "location_preference": "Location preference",
        "salary_expectations": "Compensation expectations",
        "work_authorization": "Work authorization",
        "sponsorship": "Sponsorship",
        "background_check": "Background check",
        "legal_sensitive": "Legal-sensitive questions",
        "unknown_required_question": "Unknown required questions",
        "why_interested": "Why interested",
        "why_fit": "Why fit",
    }
    answers: dict[str, str] = {}
    for key, entry in answer_bank.get("answers", {}).items():
        if key == "cover_email_base":
            continue
        claim_id = str(entry.get("claim_id") or "")
        status = str(entry.get("status") or "REVIEW_REQUIRED")
        if status == "APPROVED" and claim_is_approved(
            claim_id, evidence, context="application_answer"
        ):
            value = str(entry.get("value") or "")
        else:
            value = str(
                entry.get("value")
                or "REVIEW_REQUIRED — no approved reusable answer."
            )
            if status == "APPROVED":
                value = "REVIEW_REQUIRED — supporting claim is not approved."
        answers[labels.get(key, key.replace("_", " ").title())] = value
    return answers
