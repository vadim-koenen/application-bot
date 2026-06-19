from __future__ import annotations

from abc import ABC, abstractmethod
import json
from pathlib import Path
from typing import Any

from application_bot.database import Database
from application_bot.models import ConfirmationStatus


class ConfirmationTracker(ABC):
    @abstractmethod
    def import_messages(
        self,
        input_path: str | Path,
        database: Database,
    ) -> dict[str, Any]:
        raise NotImplementedError


def classify_message(subject: str, body: str) -> ConfirmationStatus:
    text = f"{subject} {body}".lower()
    if any(
        phrase in text
        for phrase in (
            "not moving forward",
            "decided not to proceed",
            "other candidates",
            "unfortunately",
            "position has been filled",
        )
    ):
        return ConfirmationStatus.REJECTION
    if any(
        phrase in text
        for phrase in (
            "schedule an interview",
            "interview availability",
            "invite you to interview",
            "next interview",
        )
    ):
        return ConfirmationStatus.INTERVIEW_REQUEST
    if any(
        phrase in text
        for phrase in (
            "assessment",
            "take-home",
            "take home",
            "skills test",
            "case study",
        )
    ):
        return ConfirmationStatus.ASSESSMENT_REQUEST
    if any(
        phrase in text
        for phrase in (
            "application received",
            "received your application",
            "thank you for applying",
            "thanks for applying",
        )
    ):
        return ConfirmationStatus.CONFIRMATION_RECEIVED
    if any(
        phrase in text
        for phrase in (
            "recruiter",
            "your background",
            "discuss the opportunity",
            "interested in speaking",
        )
    ):
        return ConfirmationStatus.RECRUITER_REPLY
    return ConfirmationStatus.FOLLOW_UP_NEEDED


class ImportedEmailConfirmationTracker(ConfirmationTracker):
    def import_messages(
        self,
        input_path: str | Path,
        database: Database,
    ) -> dict[str, Any]:
        with Path(input_path).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        messages = payload.get("messages", []) if isinstance(payload, dict) else payload
        counts: dict[str, int] = {}
        imported = 0
        for message in messages:
            subject = str(message.get("subject") or "")
            body = str(message.get("body") or message.get("snippet") or "")
            status = classify_message(subject, body)
            database.save_confirmation(
                source=str(message.get("source") or "gmail_fixture"),
                external_id=(
                    str(message.get("id")) if message.get("id") is not None else None
                ),
                subject=subject,
                sender=str(message.get("from") or message.get("sender") or ""),
                body=body,
                classification=str(status),
                received_at=message.get("received_at") or message.get("date"),
                raw_payload=message,
                job_id=message.get("job_id"),
            )
            counts[str(status)] = counts.get(str(status), 0) + 1
            imported += 1
        return {"imported": imported, "classifications": counts}
