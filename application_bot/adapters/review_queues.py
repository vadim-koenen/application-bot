from __future__ import annotations

from typing import Any

from application_bot.adapters.manual_json import ManualJsonAdapter
from application_bot.models import Job, JobStatus


class _ReviewImportAdapter(ManualJsonAdapter):
    def normalize_job(self, payload: dict[str, Any], **kwargs: Any) -> Job:
        job = super().normalize_job(payload, **kwargs)
        job.source = self.source_name
        job.status = JobStatus.REVIEW_REQUIRED
        return job


class LinkedInReviewQueueAdapter(_ReviewImportAdapter):
    source_name = "linkedin_review_queue"
    submission_mode = "REVIEW_REQUIRED"


class IndeedConnectorAdapter(_ReviewImportAdapter):
    source_name = "indeed_connector"
    submission_mode = "BLOCKED"


class ZipConnectorAdapter(_ReviewImportAdapter):
    source_name = "zip_connector"
    submission_mode = "BLOCKED"
