from __future__ import annotations

from typing import Any

from application_bot.adapters.base import SourceAdapter
from application_bot.adapters.util import infer_remote_type, strip_html
from application_bot.models import Job


class GreenhouseAdapter(SourceAdapter):
    source_name = "greenhouse"
    submission_mode = "AUTO_PACKET_ONLY"

    def discover_jobs(self, **kwargs: Any) -> list[Job]:
        board_token = kwargs["board_token"]
        company = kwargs.get("company") or board_token
        url = (
            f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
            "?content=true"
        )
        payload = self.transport(url)
        return [
            self.normalize_job(row, company=company, board_token=board_token)
            for row in payload.get("jobs", [])
        ]

    def normalize_job(self, payload: dict[str, Any], **kwargs: Any) -> Job:
        company = str(kwargs.get("company") or payload.get("company_name") or "Unknown")
        location = str((payload.get("location") or {}).get("name") or "")
        metadata = payload.get("metadata") or []
        departments = payload.get("departments") or []
        department = ", ".join(
            str(item.get("name") or "").strip()
            for item in departments
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        )
        if not department:
            for item in metadata:
                if str(item.get("name", "")).lower() == "department":
                    department = str(item.get("value") or "")
                    break
        description = strip_html(payload.get("content"))
        absolute_url = str(payload.get("absolute_url") or "")
        return Job(
            external_id=str(payload.get("id") or absolute_url),
            source=self.source_name,
            source_url=absolute_url,
            apply_url=absolute_url,
            company=company,
            title=str(payload.get("title") or "Unknown role"),
            department=department,
            location=location,
            remote_type=infer_remote_type(location),
            description=description,
            posted_at=payload.get("updated_at"),
            raw_payload_json=self._raw_json(payload),
        )
