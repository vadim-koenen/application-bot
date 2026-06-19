from __future__ import annotations

from typing import Any

from application_bot.adapters.base import SourceAdapter
from application_bot.adapters.util import (
    infer_remote_type,
    lever_salary_fields,
    strip_html,
)
from application_bot.models import Job


class LeverAdapter(SourceAdapter):
    source_name = "lever"
    submission_mode = "AUTO_PACKET_ONLY"

    def discover_jobs(self, **kwargs: Any) -> list[Job]:
        site = kwargs["site"]
        company = kwargs.get("company") or site
        url = f"https://api.lever.co/v0/postings/{site}?mode=json"
        payload = self.transport(url)
        return [
            self.normalize_job(row, company=company, site=site)
            for row in payload
        ]

    def normalize_job(self, payload: dict[str, Any], **kwargs: Any) -> Job:
        categories = payload.get("categories") or {}
        location = str(categories.get("location") or "")
        lists = payload.get("lists") or []
        requirements: list[str] = []
        responsibilities: list[str] = []
        for section in lists:
            heading = str(section.get("text") or "").lower()
            content = strip_html(section.get("content"))
            if "require" in heading or "qualif" in heading:
                requirements.append(content)
            elif "respons" in heading or "what you" in heading:
                responsibilities.append(content)
        description = strip_html(
            payload.get("descriptionPlain")
            or payload.get("description")
            or payload.get("additionalPlain")
        )
        apply_url = str(payload.get("applyUrl") or payload.get("hostedUrl") or "")
        salary_min, salary_max, currency = lever_salary_fields(payload)
        return Job(
            external_id=str(payload.get("id") or apply_url),
            source=self.source_name,
            source_url=str(payload.get("hostedUrl") or apply_url),
            apply_url=apply_url,
            company=str(kwargs.get("company") or payload.get("company") or "Unknown"),
            title=str(payload.get("text") or "Unknown role"),
            department=str(categories.get("team") or categories.get("department") or ""),
            location=location,
            remote_type=infer_remote_type(
                location, str(payload.get("workplaceType") or "")
            ),
            salary_min=salary_min,
            salary_max=salary_max,
            currency=currency,
            description=description,
            requirements=" ".join(requirements),
            responsibilities=" ".join(responsibilities),
            posted_at=payload.get("createdAt"),
            raw_payload_json=self._raw_json(payload),
        )
