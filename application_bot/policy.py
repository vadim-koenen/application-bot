from __future__ import annotations

import os
from typing import Any

from application_bot.compliance import prohibited_requested, review_triggers
from application_bot.models import PolicyResult, SubmissionDecision


def evaluate_submission_policy(
    source: str,
    *,
    flags: list[str] | set[str] | None = None,
    capabilities: list[str] | set[str] | None = None,
    live_apply_enabled: bool = False,
    recipient: str | None = None,
    adapter_allows_submission: bool = False,
    credentials_present: bool = False,
    required_questions_known: bool = False,
) -> PolicyResult:
    flags = set(flags or [])
    capabilities = set(capabilities or [])

    prohibited = prohibited_requested(capabilities)
    if prohibited:
        return PolicyResult(
            SubmissionDecision.BLOCKED,
            [f"Prohibited automation capability requested: {name}" for name in prohibited],
            True,
        )

    review = review_triggers(flags)
    if review:
        return PolicyResult(
            SubmissionDecision.REVIEW_REQUIRED,
            [f"Human review trigger present: {name}" for name in review],
            True,
        )

    if source == "linkedin_review_queue":
        return PolicyResult(
            SubmissionDecision.REVIEW_REQUIRED,
            ["LinkedIn opportunities are review-queue only; no scraping or click automation."],
            True,
        )
    if source in {"indeed_connector", "zip_connector"}:
        return PolicyResult(
            SubmissionDecision.BLOCKED,
            [f"Direct {source.replace('_connector', '')} automation is not permitted."],
            True,
        )
    if source == "email_to_apply":
        smtp_present = all(
            os.getenv(name)
            for name in (
                "SMTP_HOST",
                "SMTP_PORT",
                "SMTP_USERNAME",
                "SMTP_PASSWORD",
                "FROM_EMAIL",
            )
        )
        if live_apply_enabled and recipient and smtp_present:
            return PolicyResult(
                SubmissionDecision.AUTO_SUBMIT_EMAIL,
                ["Explicit live flag, recipient, and SMTP configuration are present."],
                False,
            )
        return PolicyResult(
            SubmissionDecision.AUTO_PACKET_ONLY,
            ["Email application remains dry-run until live flag and email config are present."],
            False,
        )
    if source in {"greenhouse", "lever", "ashby"}:
        if (
            adapter_allows_submission
            and credentials_present
            and required_questions_known
            and live_apply_enabled
        ):
            return PolicyResult(
                SubmissionDecision.AUTO_SUBMIT_ALLOWED,
                ["Adapter explicitly allows submission and all safety preconditions are met."],
                False,
            )
        return PolicyResult(
            SubmissionDecision.AUTO_PACKET_ONLY,
            ["Public ATS adapters are discovery and packet generation only by default."],
            False,
        )
    if source == "manual_json":
        return PolicyResult(
            SubmissionDecision.AUTO_PACKET_ONLY,
            ["Manually imported opportunities generate packets but are not auto-submitted."],
            False,
        )
    return PolicyResult(
        SubmissionDecision.REVIEW_REQUIRED,
        ["Unknown or ambiguous source defaults to human review."],
        True,
    )
