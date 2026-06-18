from __future__ import annotations

from typing import Any

from application_bot.adapters.base import SourceAdapter
from application_bot.adapters.util import infer_remote_type, strip_html
from application_bot.models import Job


class AshbyAdapter(SourceAdapter):
    source_name = "ashby"
    submission_mode = "AUTO_PACKET_ONLY"

    def discover_jobs(self, **kwargs: Any) -> list[Job]:
        board_name = kwargs["board_name"]
        company = kwargs.get("company") or board_name
        url = f"https://api.ashbyhq.com/posting-api/job-board/{board_name}"
        payload = self.transport(url)
        return [
            self.normalize_job(row, company=company, board_name=board_name)
            for row in payload.get("jobs", [])
        ]

    def normalize_job(self, payload: dict[str, Any], **kwargs: Any) -> Job:
        location = str(payload.get("location") or "")
        workplace = str(payload.get("workplaceType") or "")
        apply_url = str(payload.get("applyUrl") or payload.get("jobUrl") or "")
        return Job(
            external_id=str(payload.get("id") or apply_url),
            source=self.source_name,
            source_url=str(payload.get("jobUrl") or apply_url),
            apply_url=apply_url,
            company=str(kwargs.get("company") or payload.get("company") or "Unknown"),
            title=str(payload.get("title") or "Unknown role"),
            department=str(payload.get("department") or payload.get("team") or ""),
            location=location,
            remote_type=infer_remote_type(location, workplace),
            description=strip_html(
                payload.get("descriptionPlain") or payload.get("descriptionHtml")
            ),
            posted_at=payload.get("publishedAt"),
            raw_payload_json=self._raw_json(payload),
        )
