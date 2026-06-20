from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any

import yaml

from application_bot.database import Database
from application_bot.models import ApplicationPacket, Job


APPROVED_STATUSES = {"APPROVED", "APPROVED_FROM_USER_CONTEXT"}
VALID_STATUSES = APPROVED_STATUSES | {
    "PENDING_USER_APPROVAL",
    "REJECTED",
    "DO_NOT_USE",
}


def evidence_claim_map(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(claim["claim_id"]): claim
        for claim in evidence.get("claims", [])
        if claim.get("claim_id")
    }


def claim_is_approved(
    claim_id: str,
    evidence: dict[str, Any],
    *,
    context: str = "packet_text",
    corpus: str | None = None,
) -> bool:
    claim = evidence_claim_map(evidence).get(claim_id)
    if not claim or claim.get("approval_status") not in APPROVED_STATUSES:
        return False
    if context not in set(claim.get("allowed_contexts") or []):
        return False
    approval_patterns = claim.get("approval_match_patterns") or []
    if corpus is not None and approval_patterns:
        return any(
            re.search(str(pattern), corpus, flags=re.IGNORECASE | re.DOTALL)
            for pattern in approval_patterns
        )
    return True


def approved_evidence_claims(
    evidence: dict[str, Any],
    *,
    context: str,
) -> list[dict[str, Any]]:
    return [
        claim
        for claim in evidence.get("claims", [])
        if claim.get("approval_status") in APPROVED_STATUSES
        and context in set(claim.get("allowed_contexts") or [])
    ]


def unresolved_claim_gaps(
    gap_ids: list[str],
    evidence: dict[str, Any],
    *,
    corpus: str | None = None,
) -> list[str]:
    return sorted(
        gap_id
        for gap_id in set(gap_ids)
        if not claim_is_approved(
            gap_id,
            evidence,
            context="packet_text",
            corpus=corpus,
        )
    )


def safe_rewrites_for_gaps(
    gap_ids: list[str],
    evidence: dict[str, Any],
) -> list[str]:
    claims = evidence_claim_map(evidence)
    rewrites: list[str] = []
    for gap_id in gap_ids:
        claim = claims.get(gap_id)
        rewrite = (
            claim.get("safe_rewrite")
            if claim
            else "Keep the requirement in review status and use only approved positioning."
        )
        if rewrite and rewrite not in rewrites:
            rewrites.append(str(rewrite))
    return rewrites


def blocked_claim_ids(
    gap_ids: list[str],
    evidence: dict[str, Any],
) -> list[str]:
    claims = evidence_claim_map(evidence)
    return sorted(
        gap_id
        for gap_id in set(gap_ids)
        if claims.get(gap_id, {}).get("approval_status") in {"REJECTED", "DO_NOT_USE"}
    )


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


def claim_counts(evidence: dict[str, Any]) -> dict[str, int]:
    counts = {status: 0 for status in sorted(VALID_STATUSES)}
    for claim in evidence.get("claims", []):
        status = str(claim.get("approval_status") or "")
        counts[status] = counts.get(status, 0) + 1
    return counts


def list_claims(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "counts": claim_counts(evidence),
        "claims": evidence.get("claims", []),
    }


def claim_gap_rows(
    database: Database,
    evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    claims = evidence_claim_map(evidence)
    gaps: list[dict[str, Any]] = []
    for job in database.review_queue_rows():
        for claim_id in job["claim_gaps"]:
            claim = claims.get(claim_id, {})
            approval_status = claim.get(
                "approval_status", "PENDING_USER_APPROVAL"
            )
            scope_mismatch = approval_status in APPROVED_STATUSES
            gaps.append(
                {
                    "gap_id": f"{job['job_id']}:{claim_id}",
                    "claim_id": claim_id,
                    "job_id": job["job_id"],
                    "company": job["company"],
                    "title": job["title"],
                    "requested_claim": claim.get(
                        "claim_text", claim_id.replace("_", " ")
                    ),
                    "why_needed": claim.get(
                        "evidence_detail",
                        "The posting requests information not approved for packet use.",
                    ),
                    "suggested_safe_rewrite": claim.get(
                        "safe_rewrite",
                        "Use approved positioning and retain this requirement for review.",
                    ),
                    "risk_level": claim.get("risk_level", "medium"),
                    "approval_status": (
                        "APPROVED_SCOPE_MISMATCH"
                        if scope_mismatch
                        else approval_status
                    ),
                    "recommended_action": (
                        "The posting requirement falls outside the exact approved "
                        "scope; keep it in review or provide matching evidence."
                        if scope_mismatch
                        else "Provide evidence and explicitly approve, reject, or keep pending."
                    ),
                }
            )
    return gaps


def export_approval_pack(
    database: Database,
    evidence: dict[str, Any],
    output: str | Path,
) -> dict[str, Any]:
    gaps = claim_gap_rows(database, evidence)
    target = Path(output)
    base = target.with_suffix("") if target.suffix else target
    base.parent.mkdir(parents=True, exist_ok=True)
    markdown_path = base.with_suffix(".md")
    json_path = base.with_suffix(".json")
    sections = ["# Claim Approval Pack", ""]
    if not gaps:
        sections.extend(["No unresolved claim gaps were found.", ""])
    for gap in gaps:
        sections.extend(
            [
                f"## {gap['company']} — {gap['title']}",
                "",
                f"- Gap ID: `{gap['gap_id']}`",
                f"- Claim ID: `{gap['claim_id']}`",
                f"- Requested claim: {gap['requested_claim']}",
                f"- Why needed: {gap['why_needed']}",
                f"- Safe rewrite: {gap['suggested_safe_rewrite']}",
                f"- Risk: {gap['risk_level']}",
                f"- Current status: {gap['approval_status']}",
                f"- Recommended action: {gap['recommended_action']}",
                "",
            ]
        )
    markdown_path.write_text("\n".join(sections), encoding="utf-8")
    json_path.write_text(
        json.dumps({"gaps": gaps}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "claim_gaps_found": len(gaps),
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
    }


def update_claim_status(
    evidence_path: str | Path,
    claim_id: str,
    status: str,
    *,
    source: str,
    note: str,
    claim_text: str | None = None,
    approval_match_patterns: list[str] | None = None,
    confidence: str | None = None,
    requires_user_approval: bool | None = None,
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid claim approval status: {status}")
    path = Path(evidence_path)
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    claim = next(
        (
            item
            for item in payload.get("claims", [])
            if str(item.get("claim_id")) == claim_id
        ),
        None,
    )
    if claim is None:
        raise ValueError(f"Unknown claim ID: {claim_id}")
    if status in APPROVED_STATUSES and (
        not source.strip() or len(note.strip()) < 5
    ):
        raise ValueError("Approving a claim requires a source and evidence note")
    claim["approval_status"] = status
    claim["evidence_source"] = source.strip()
    claim["evidence_detail"] = note.strip()
    claim["last_verified_at"] = datetime.now(UTC).date().isoformat()
    if claim_text is not None and claim_text.strip():
        claim["claim_text"] = claim_text.strip()
    if approval_match_patterns is not None:
        claim["approval_match_patterns"] = [
            str(pattern) for pattern in approval_match_patterns
        ]
    if confidence is not None:
        claim["confidence"] = confidence
    if requires_user_approval is not None:
        claim["requires_user_approval"] = requires_user_approval
    if status in APPROVED_STATUSES:
        allowed = set(claim.get("allowed_contexts") or [])
        allowed.update({"packet_text", "application_answer"})
        claim["allowed_contexts"] = sorted(allowed)
        prohibited = set(claim.get("prohibited_contexts") or [])
        prohibited.difference_update({"packet_text", "application_answer"})
        claim["prohibited_contexts"] = sorted(prohibited)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return claim


def import_claim_approvals(
    evidence_path: str | Path,
    input_path: str | Path,
) -> dict[str, Any]:
    with Path(input_path).open("r", encoding="utf-8") as handle:
        incoming = yaml.safe_load(handle)
    approvals = incoming.get("approvals", []) if isinstance(incoming, dict) else incoming
    updated: list[str] = []
    for approval in approvals:
        update_claim_status(
            evidence_path,
            str(approval["claim_id"]),
            str(approval["approval_status"]),
            source=str(approval.get("source") or "imported_approval"),
            note=str(approval.get("note") or approval.get("evidence_detail") or ""),
            claim_text=(
                str(approval["claim_text"])
                if approval.get("claim_text") is not None
                else None
            ),
            approval_match_patterns=(
                [str(pattern) for pattern in approval["approval_match_patterns"]]
                if approval.get("approval_match_patterns") is not None
                else None
            ),
            confidence=(
                str(approval["confidence"])
                if approval.get("confidence") is not None
                else None
            ),
            requires_user_approval=(
                bool(approval["requires_user_approval"])
                if approval.get("requires_user_approval") is not None
                else None
            ),
        )
        updated.append(str(approval["claim_id"]))
    return {"updated": len(updated), "claim_ids": updated}
