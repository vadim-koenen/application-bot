from __future__ import annotations

from html import unescape
import re
from typing import Any


def strip_html(value: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", unescape(text)).strip()


def salary_fields(payload: dict[str, Any]) -> tuple[int | None, int | None, str]:
    minimum = payload.get("salary_min") or payload.get("salaryMin")
    maximum = payload.get("salary_max") or payload.get("salaryMax")
    currency = payload.get("currency") or "USD"
    try:
        minimum = int(minimum) if minimum is not None else None
    except (TypeError, ValueError):
        minimum = None
    try:
        maximum = int(maximum) if maximum is not None else None
    except (TypeError, ValueError):
        maximum = None
    return minimum, maximum, str(currency)


def infer_remote_type(location: str, workplace_type: str = "") -> str:
    value = f"{location} {workplace_type}".lower()
    if "remote" in value:
        return "remote"
    if "hybrid" in value:
        return "hybrid"
    if location:
        return "onsite"
    return "unknown"
