from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import json
import re
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def content_hash(*values: str | None) -> str:
    material = "\n".join(clean_text(value).lower() for value in values)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class JobStatus(StrEnum):
    NEW = "NEW"
    SCORED = "SCORED"
    PACKET_EXPORTED = "PACKET_EXPORTED"
    APPLIED = "APPLIED"
    # Operator heard back (recruiter reply / interview request) — the final
    # funnel stage in the dashboard. Set manually via mark_responded.
    RESPONDED = "RESPONDED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


class FitVerdict(StrEnum):
    APPLY_PRIORITY = "APPLY_PRIORITY"
    GOOD_FIT = "GOOD_FIT"
    MAYBE = "MAYBE"
    NOT_WORTH_TIME = "NOT_WORTH_TIME"
    BLOCKED = "BLOCKED"


class SubmissionDecision(StrEnum):
    AUTO_SUBMIT_ALLOWED = "AUTO_SUBMIT_ALLOWED"
    AUTO_SUBMIT_EMAIL = "AUTO_SUBMIT_EMAIL"
    AUTO_PACKET_ONLY = "AUTO_PACKET_ONLY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


class EmailQueueStatus(StrEnum):
    QUEUED = "QUEUED"
    PREVIEW_GENERATED = "PREVIEW_GENERATED"
    SENT = "SENT"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


class ConfirmationStatus(StrEnum):
    CONFIRMATION_RECEIVED = "confirmation_received"
    RECRUITER_REPLY = "recruiter_reply"
    ASSESSMENT_REQUEST = "assessment_request"
    REJECTION = "rejection"
    INTERVIEW_REQUEST = "interview_request"
    FOLLOW_UP_NEEDED = "follow_up_needed"


class PacketStatus(StrEnum):
    PACKET_READY = "PACKET_READY"
    REVIEW_PACKET_CLAIM_GAPS = "REVIEW_PACKET_CLAIM_GAPS"
    NOT_WORTH_PACKET = "NOT_WORTH_PACKET"
    BLOCKED = "BLOCKED"


@dataclass(slots=True)
class Job:
    external_id: str
    source: str
    source_url: str
    apply_url: str
    company: str
    title: str
    department: str = ""
    location: str = ""
    remote_type: str = "unknown"
    salary_min: int | None = None
    salary_max: int | None = None
    currency: str = "USD"
    description: str = ""
    requirements: str = ""
    responsibilities: str = ""
    posted_at: str | None = None
    discovered_at: str = field(default_factory=utc_now)
    content_hash: str = ""
    raw_payload_json: str = "{}"
    status: str = JobStatus.NEW
    id: int | None = None
    score: int | None = None
    verdict: str | None = None
    score_details_json: str = "{}"
    submission_policy: str | None = None
    packet_status: str | None = None
    claim_gaps_json: str = "[]"
    packet_reason_codes_json: str = "[]"
    recommended_next_action: str | None = None

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = content_hash(
                self.company,
                self.title,
                self.location,
                self.description,
                self.requirements,
                self.responsibilities,
            )
        if not isinstance(self.raw_payload_json, str):
            self.raw_payload_json = json.dumps(self.raw_payload_json, sort_keys=True)

    @property
    def dedupe_key(self) -> str:
        return content_hash(
            self.company,
            self.title,
            self.location,
            self.apply_url,
            self.content_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScoreResult:
    score: int
    verdict: FitVerdict
    dimensions: dict[str, int]
    reasons: list[str]
    risk_flags: list[str]


@dataclass(slots=True)
class PolicyResult:
    decision: SubmissionDecision
    reasons: list[str]
    requires_human_review: bool


@dataclass(slots=True)
class ApplicationPacket:
    job_id: int
    fit_summary: str
    tailored_summary: str
    tailored_skills: list[str]
    cover_email: str
    cover_letter: str
    suggested_answers: dict[str, str]
    role_notes: list[str]
    why_fit: list[str]
    why_not: list[str]
    risk_flags: list[str]
    recommended_next_action: str
    policy: str
    packet_status: str = PacketStatus.PACKET_READY
    claim_gaps: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    approved_claim_ids: list[str] = field(default_factory=list)
    pending_claims_not_used: list[str] = field(default_factory=list)
    safe_substitutions: list[str] = field(default_factory=list)
    blocked_claims: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class PacketAssessment:
    status: PacketStatus
    claim_gaps: list[str]
    reason_codes: list[str]
    recommended_next_action: str
    should_export: bool


@dataclass(slots=True)
class EmailQueueItem:
    id: int
    job_id: int
    packet_id: int
    recipient: str
    status: str
    compliance_flags_json: str
    preview_path: str | None
    error: str | None
    queued_at: str
    updated_at: str
    sent_at: str | None
    company: str = ""
    title: str = ""
    apply_url: str = ""
    packet_json: str = "{}"
