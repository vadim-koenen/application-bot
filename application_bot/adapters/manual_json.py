from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from application_bot.adapters.base import SourceAdapter
from application_bot.adapters.util import infer_remote_type, salary_fields
from application_bot.models import Job


class ManualJsonAdapter(SourceAdapter):
    source_name = "manual_json"
    submission_mode = "AUTO_PACKET_ONLY"

    def discover_jobs(self, **kwargs: Any) -> list[Job]:
        input_path = kwargs.get("input_path") or kwargs.get("input")
        if not input_path:
            raise ValueError("manual_json requires --input")
        path = Path(input_path)
        with path.open("r", encoding="utf-8", newline="") as handle:
            if path.suffix.lower() == ".csv":
                rows = list(csv.DictReader(handle))
            else:
                payload = json.load(handle)
                rows = payload.get("jobs", []) if isinstance(payload, dict) else payload
        return [self.normalize_job(row) for row in rows]

    def normalize_job(self, payload: dict[str, Any], **kwargs: Any) -> Job:
        salary_min, salary_max, currency = salary_fields(payload)
        source = str(payload.get("source") or self.source_name)
        source_url = str(payload.get("source_url") or payload.get("url") or "")
        apply_url = str(payload.get("apply_url") or source_url)
        location = str(payload.get("location") or "")
        return Job(
            external_id=str(
                payload.get("external_id")
                or payload.get("id")
                or f"{payload.get('company', '')}:{payload.get('title', '')}"
            ),
            source=source,
            source_url=source_url,
            apply_url=apply_url,
            company=str(payload.get("company") or "Unknown company"),
            title=str(payload.get("title") or "Unknown role"),
            department=str(payload.get("department") or ""),
            location=location,
            remote_type=str(
                payload.get("remote_type")
                or infer_remote_type(location, str(payload.get("workplace_type") or ""))
            ),
            salary_min=salary_min,
            salary_max=salary_max,
            currency=currency,
            description=str(payload.get("description") or ""),
            requirements=str(payload.get("requirements") or ""),
            responsibilities=str(payload.get("responsibilities") or ""),
            posted_at=payload.get("posted_at"),
            raw_payload_json=self._raw_json(payload),
            status=str(payload.get("status") or "NEW"),
        )
