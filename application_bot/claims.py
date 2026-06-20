from __future__ import annotations

import re
from typing import Any

from application_bot.models import ApplicationPacket, Job


def approved_claim_map(inventory: dict[str, Any]) -> dict[str, str]:
    return {
        str(claim["id"]): str(claim["text"])
        for claim in inventory.get("approved_experience_claims", [])
        if claim.get("id") and claim.get("text")
    }


def approved_keywords(inventory: dict[str, Any]) -> list[str]:
    values = (
        inventory.get("approved_skill_keywords", [])
        + inventory.get("approved_positioning_themes", [])
        + inventory.get("approved_tools_platforms", [])
    )
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def matched_approved_keywords(job: Job, inventory: dict[str, Any]) -> list[str]:
    corpus = " ".join(
        (
            job.title,
            job.department,
            job.description,
            job.requirements,
            job.responsibilities,
        )
    ).lower()
    return [
        keyword
        for keyword in approved_keywords(inventory)
        if keyword.lower() in corpus
    ][:12]


def detect_claim_gaps(job: Job, inventory: dict[str, Any]) -> list[str]:
    corpus = " ".join(
        (job.description, job.requirements, job.responsibilities)
    )
    gaps: list[str] = []
    for claim in inventory.get("prohibited_or_unverified_claims", []):
        claim_id = str(claim.get("id") or "").strip()
        if not claim_id:
            continue
        for pattern in claim.get("patterns", []):
            if re.search(str(pattern), corpus, flags=re.IGNORECASE | re.DOTALL):
                gaps.append(claim_id)
                break
    return sorted(set(gaps))


def packet_claim_violations(
    packet: ApplicationPacket,
    inventory: dict[str, Any],
) -> list[str]:
    generated = " ".join(
        (
            packet.tailored_summary,
            packet.cover_email,
            packet.cover_letter,
            " ".join(packet.tailored_skills),
        )
    )
    violations: list[str] = []
    for claim in inventory.get("prohibited_or_unverified_claims", []):
        claim_id = str(claim.get("id") or "")
        for pattern in claim.get("patterns", []):
            if re.search(str(pattern), generated, flags=re.IGNORECASE | re.DOTALL):
                violations.append(claim_id)
                break
    return sorted(set(violations))
