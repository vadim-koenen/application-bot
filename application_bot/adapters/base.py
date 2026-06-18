from __future__ import annotations

from abc import ABC, abstractmethod
import json
from typing import Any, Callable
from urllib.request import Request, urlopen

from application_bot.models import Job

JsonTransport = Callable[[str], Any]


def default_json_transport(url: str) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "application-bot/0.1 (+compliance-first job discovery)",
        },
    )
    with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed API URLs
        return json.loads(response.read().decode("utf-8"))


class SourceAdapter(ABC):
    source_name = "base"
    supports_submission = False
    submission_mode = "AUTO_PACKET_ONLY"

    def __init__(self, transport: JsonTransport | None = None) -> None:
        self.transport = transport or default_json_transport

    @abstractmethod
    def discover_jobs(self, **kwargs: Any) -> list[Job]:
        raise NotImplementedError

    @abstractmethod
    def normalize_job(self, payload: dict[str, Any], **kwargs: Any) -> Job:
        raise NotImplementedError

    def _raw_json(self, payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
