from __future__ import annotations

from html import unescape
import re
from typing import Any


def strip_html(value: str | None) -> str:
    text = value or ""
    # Greenhouse commonly returns HTML encoded as entities. Decode before
    # removing tags, and decode twice to handle content such as &amp;lt;p&amp;gt;.
    for _ in range(2):
        decoded = unescape(text)
        if decoded == text:
            break
        text = decoded
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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


def lever_salary_fields(payload: dict[str, Any]) -> tuple[int | None, int | None, str]:
    salary_range = payload.get("salaryRange") or {}
    if not isinstance(salary_range, dict):
        return None, None, "USD"
    return salary_fields(
        {
            "salary_min": salary_range.get("min"),
            "salary_max": salary_range.get("max"),
            "currency": salary_range.get("currency") or "USD",
        }
    )


def ashby_salary_fields(payload: dict[str, Any]) -> tuple[int | None, int | None, str]:
    compensation = payload.get("compensation") or {}
    if not isinstance(compensation, dict):
        return None, None, "USD"
    components = compensation.get("summaryComponents") or []
    for component in components:
        if not isinstance(component, dict):
            continue
        if str(component.get("compensationType") or "").lower() != "salary":
            continue
        interval = str(component.get("interval") or "").upper()
        if interval and interval not in {"1 YEAR", "YEAR", "ANNUAL"}:
            continue
        return salary_fields(
            {
                "salary_min": component.get("minValue"),
                "salary_max": component.get("maxValue"),
                "currency": component.get("currencyCode") or "USD",
            }
        )
    return None, None, "USD"


def infer_remote_type(location: str, workplace_type: str = "") -> str:
    value = f"{location} {workplace_type}".lower()
    if "remote" in value:
        return "remote"
    if "hybrid" in value:
        return "hybrid"
    if location:
        return "onsite"
    return "unknown"
