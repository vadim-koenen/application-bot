from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from application_bot.adapters.base import SourceAdapter
from application_bot.adapters.util import infer_remote_type
from application_bot.models import Job


class AdzunaAdapter(SourceAdapter):
    """Market-wide, function-targeted discovery via the Adzuna jobs API.

    Unlike the ATS adapters (which list one company's board), this searches the
    whole market for a title/keyword posted recently — catching in-lane roles at
    companies outside the curated registry. Needs free API credentials
    (ADZUNA_APP_ID / ADZUNA_APP_KEY). Descriptions are truncated by Adzuna, so
    scoring on these is rougher than on full ATS JDs — treat as discovery leads.
    """

    source_name = "adzuna"
    submission_mode = "AUTO_PACKET_ONLY"

    def discover_jobs(self, **kwargs: Any) -> list[Job]:
        app_id = kwargs.get("app_id")
        app_key = kwargs.get("app_key")
        if not app_id or not app_key:
            raise ValueError("adzuna requires app_id and app_key")
        country = str(kwargs.get("country") or "us")
        page = int(kwargs.get("page") or 1)
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "what": str(kwargs.get("what") or ""),
            "where": str(kwargs.get("where") or ""),
            "max_days_old": int(kwargs.get("max_days_old") or 1),
            "results_per_page": int(kwargs.get("results_per_page") or 50),
            "sort_by": "date",
            "content-type": "application/json",
        }
        url = (
            f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
            f"?{urlencode(params)}"
        )
        payload = self.transport(url)
        return [self.normalize_job(row) for row in payload.get("results", [])]

    def normalize_job(self, payload: dict[str, Any], **kwargs: Any) -> Job:
        company = str((payload.get("company") or {}).get("display_name") or "Unknown")
        location = str((payload.get("location") or {}).get("display_name") or "")
        description = str(payload.get("description") or "")
        redirect_url = str(payload.get("redirect_url") or "")
        salary_min = payload.get("salary_min")
        salary_max = payload.get("salary_max")
        return Job(
            external_id=f"adzuna:{payload.get('id')}",
            source=self.source_name,
            source_url=redirect_url,
            apply_url=redirect_url,
            company=company,
            title=str(payload.get("title") or "Unknown role"),
            location=location,
            remote_type=infer_remote_type(location, description),
            salary_min=int(salary_min) if salary_min is not None else None,
            salary_max=int(salary_max) if salary_max is not None else None,
            description=description,
            posted_at=payload.get("created"),
            raw_payload_json=self._raw_json(payload),
        )
