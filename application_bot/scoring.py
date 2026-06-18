from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any

from application_bot.models import FitVerdict, Job, ScoreResult


def _contains_any(text: str, values: list[str]) -> list[str]:
    lowered = text.lower()
    return [value for value in values if value.lower() in lowered]


def _salary_minimum(title: str, config: dict[str, Any]) -> int:
    salaries = config.get("salary_minimums", {})
    lowered = title.lower()
    if "vice president" in lowered or re.search(r"\bvp\b", lowered):
        return int(salaries.get("vp", salaries.get("default", 140000)))
    if "senior director" in lowered or "sr director" in lowered:
        return int(salaries.get("senior_director", salaries.get("default", 140000)))
    if "director" in lowered:
        return int(salaries.get("director", salaries.get("default", 140000)))
    return int(salaries.get("default", 140000))


def score_job(job: Job, config: dict[str, Any]) -> ScoreResult:
    dimensions: dict[str, int] = {}
    reasons: list[str] = []
    risk_flags: list[str] = []
    title = job.title.lower()
    corpus = " ".join(
        [
            job.title,
            job.department,
            job.description,
            job.requirements,
            job.responsibilities,
        ]
    ).lower()
    score = 15

    target_titles = _contains_any(title, config.get("target_titles", []))
    if ("account executive" in title or "sales executive" in title) and "executive" in target_titles:
        target_titles.remove("executive")
    reject_titles = _contains_any(title, config.get("reject_titles", []))
    if target_titles:
        dimensions["seniority"] = 20
        reasons.append(f"Target seniority matched: {', '.join(target_titles[:3])}")
    elif reject_titles:
        dimensions["seniority"] = -25
        risk_flags.append(f"Wrong-level title: {', '.join(reject_titles[:3])}")
    else:
        dimensions["seniority"] = -5
        risk_flags.append("Target executive seniority is not explicit.")

    target_keywords = _contains_any(corpus, config.get("target_keywords", []))
    function_points = min(22, len(target_keywords) * 5)
    dimensions["function_fit"] = function_points
    if target_keywords:
        reasons.append(f"Function fit: {', '.join(target_keywords[:5])}")
    else:
        risk_flags.append("No strong target-function keyword match.")

    reject_keywords = _contains_any(corpus, config.get("reject_keywords", []))
    if reject_keywords:
        dimensions["role_mismatch"] = -18
        risk_flags.append(f"Role mismatch signal: {', '.join(reject_keywords[:3])}")
    else:
        dimensions["role_mismatch"] = 0

    location = f"{job.location} {job.remote_type}".lower()
    preferences = config.get("location_preferences", {})
    if _contains_any(location, preferences.get("remote_us", [])):
        dimensions["location"] = 12
        reasons.append("Remote-compatible location.")
    elif _contains_any(location, preferences.get("dfw", [])):
        dimensions["location"] = 7
        reasons.append("Dallas/Plano/DFW location fit.")
    elif job.remote_type.lower() == "onsite" or "onsite" in location:
        dimensions["location"] = -12
        risk_flags.append("Onsite-only location.")
    else:
        dimensions["location"] = -2
        risk_flags.append("Location arrangement is unclear.")

    minimum = _salary_minimum(job.title, config)
    if job.salary_max is not None and job.salary_max < minimum:
        dimensions["salary"] = -15
        risk_flags.append(f"Salary maximum is below configured minimum ${minimum:,}.")
    elif job.salary_min is not None and job.salary_min >= minimum:
        dimensions["salary"] = 8
        reasons.append("Salary floor meets configured minimum.")
    elif job.salary_max is not None and job.salary_max >= minimum:
        dimensions["salary"] = 4
        reasons.append("Salary range reaches configured minimum.")
    else:
        dimensions["salary"] = 0
        risk_flags.append("Salary is not disclosed.")

    if "workday" in job.apply_url.lower():
        dimensions["friction"] = -8
        risk_flags.append("Workday application friction.")
    else:
        dimensions["friction"] = 2

    overlap_tokens = {
        keyword
        for keyword in config.get("target_keywords", [])
        if keyword.lower() in corpus
    }
    dimensions["keyword_overlap"] = min(8, len(overlap_tokens) * 2)

    quality_signal = any(
        marker in corpus
        for marker in ("leadership team", "transformation", "build the function", "strategy")
    )
    dimensions["company_quality"] = 4 if quality_signal else 0

    freshness = 0
    if job.posted_at:
        try:
            posted = datetime.fromisoformat(
                str(job.posted_at).replace("Z", "+00:00")
            )
            if posted.tzinfo is None:
                posted = posted.replace(tzinfo=UTC)
            age = (datetime.now(UTC) - posted).days
            freshness = 4 if age <= 14 else 2 if age <= 30 else -2 if age > 90 else 0
        except (TypeError, ValueError):
            risk_flags.append("Posted date could not be parsed.")
    dimensions["freshness"] = freshness

    score += sum(dimensions.values())
    score = max(0, min(100, int(score)))
    if str(job.status) == "BLOCKED":
        verdict = FitVerdict.BLOCKED
    elif score >= 80:
        verdict = FitVerdict.APPLY_PRIORITY
    elif score >= 65:
        verdict = FitVerdict.GOOD_FIT
    elif score >= 45:
        verdict = FitVerdict.MAYBE
    else:
        verdict = FitVerdict.NOT_WORTH_TIME
    return ScoreResult(score, verdict, dimensions, reasons, risk_flags)
