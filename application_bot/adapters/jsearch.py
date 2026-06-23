from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from application_bot.adapters.base import SourceAdapter
from application_bot.adapters.util import infer_remote_type
from application_bot.models import Job


def rapidapi_transport(api_key: str, host: str = "jsearch.p.rapidapi.com") -> Callable[[str], Any]:
    """A transport that adds the RapidAPI auth headers JSearch requires."""

    def _transport(url: str) -> Any:
        request = Request(
            url,
            headers={
                "X-RapidAPI-Key": api_key,
                "X-RapidAPI-Host": host,
                "Accept": "application/json",
            },
        )
        with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed API host
            return json.loads(response.read().decode("utf-8"))

    return _transport


class JSearchAdapter(SourceAdapter):
    """Market-wide discovery via JSearch (RapidAPI), which aggregates Google for
    Jobs — i.e. listings from LinkedIn, Indeed, ZipRecruiter, Glassdoor, and
    company sites — without scraping those sites directly. Needs a RapidAPI key
    (passed via the transport headers). Descriptions are full-ish; treat
    cross-board duplicates as expected (the DB dedupes on content).
    """

    source_name = "jsearch"
    submission_mode = "AUTO_PACKET_ONLY"

    def discover_jobs(self, **kwargs: Any) -> list[Job]:
        params = {
            "query": str(kwargs.get("what") or ""),
            "page": int(kwargs.get("page") or 1),
            "num_pages": int(kwargs.get("num_pages") or 1),
            "date_posted": str(kwargs.get("date_posted") or "today"),
        }
        if kwargs.get("remote_only"):
            params["remote_jobs_only"] = "true"
        url = "https://jsearch.p.rapidapi.com/search?" + urlencode(params)
        payload = self.transport(url)
        return [self.normalize_job(row) for row in payload.get("data", [])]

    def normalize_job(self, payload: dict[str, Any], **kwargs: Any) -> Job:
        is_remote = bool(payload.get("job_is_remote"))
        city = str(payload.get("job_city") or "")
        state = str(payload.get("job_state") or "")
        country = str(payload.get("job_country") or "")
        if is_remote:
            location = "Remote"
        else:
            location = ", ".join(p for p in (city, state, country) if p)
        apply_link = str(payload.get("job_apply_link") or "")
        salary_min = payload.get("job_min_salary")
        salary_max = payload.get("job_max_salary")
        return Job(
            external_id=f"jsearch:{payload.get('job_id')}",
            source=self.source_name,
            source_url=apply_link,
            apply_url=apply_link,
            company=str(payload.get("employer_name") or "Unknown"),
            title=str(payload.get("job_title") or "Unknown role"),
            location=location,
            remote_type="remote" if is_remote else infer_remote_type(location, ""),
            salary_min=int(salary_min) if salary_min is not None else None,
            salary_max=int(salary_max) if salary_max is not None else None,
            description=str(payload.get("job_description") or ""),
            posted_at=payload.get("job_posted_at_datetime_utc"),
            raw_payload_json=self._raw_json(payload),
        )
