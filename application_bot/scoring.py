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


def _years_requirement(text: str) -> int | None:
    values = [
        int(match)
        for match in re.findall(r"\b(\d{1,2})\+?\s+years?\b", text)
    ]
    return max(values) if values else None


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
    # A "Manager"/"Lead"-titled role is still in-lane when its title names a
    # systems/operations function Vadim owns (RevOps, GTM systems, MarTech,
    # marketing operations, marketing data). Score it below Director but well
    # above the generic reject floor so strong skill-fit roles are reviewed.
    systems_lane_title = _contains_any(title, config.get("systems_lane_titles", []))
    systems_lane_function = _contains_any(
        title, config.get("systems_lane_functions", [])
    )
    is_systems_lane = bool(systems_lane_title and systems_lane_function)
    if target_titles:
        dimensions["seniority"] = 20
        reasons.append(f"Target seniority matched: {', '.join(target_titles[:3])}")
    elif is_systems_lane:
        dimensions["seniority"] = int(config.get("systems_lane_points", 12))
        reasons.append(
            "In-lane systems/operations role below Director "
            f"({', '.join(systems_lane_function[:2])}); review level and scope."
        )
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
    off_lane_titles = _contains_any(title, config.get("off_lane_titles", []))
    title_target_functions = _contains_any(
        title, config.get("target_keywords", [])
    )
    pure_sales_title = "sales" in title and not title_target_functions
    if reject_keywords or off_lane_titles or pure_sales_title:
        dimensions["role_mismatch"] = int(
            config.get("role_mismatch_penalty", -18)
        )
        mismatch = (
            off_lane_titles[:3]
            or reject_keywords[:3]
            or ["generic sales title"]
        )
        risk_flags.append(f"Role mismatch signal: {', '.join(mismatch)}")
    else:
        dimensions["role_mismatch"] = 0

    required_years = _years_requirement(corpus)
    if required_years is not None:
        years_config = config.get("years_requirement_scoring", {})
        approved_years = int(years_config.get("approved_years", 14))
        moderate_threshold = int(
            years_config.get("moderate_threshold", approved_years + 1)
        )
        high_threshold = int(years_config.get("high_threshold", 18))
        if required_years >= high_threshold:
            penalty = int(years_config.get("high_penalty", -15))
        elif required_years >= moderate_threshold:
            penalty = int(years_config.get("moderate_penalty", -6))
        else:
            penalty = 0
        dimensions["years_requirement"] = penalty
        if penalty:
            risk_flags.append(
                f"Posting requests {required_years}+ years; approved evidence "
                f"supports {approved_years} years. Treat as a fit penalty and "
                f"do not claim {required_years}+ years."
            )
        else:
            reasons.append(
                f"Years requirement ({required_years}+) is within the approved "
                f"{approved_years}-year evidence window."
            )

    location = f"{job.location} {job.remote_type}".lower()
    preferences = config.get("location_preferences", {})
    is_remote = job.remote_type.lower() == "remote" or "remote" in location
    is_hybrid = job.remote_type.lower() == "hybrid" or "hybrid" in location
    is_onsite = (
        job.remote_type.lower() in {"onsite", "on-site"}
        or "onsite" in location
        or "on-site" in location
    )
    is_dfw = bool(_contains_any(location, preferences.get("dfw", [])))
    explicit_us = any(
        marker in location
        for marker in (
            "united states",
            "usa",
            "u.s.",
            "us remote",
            "remote - us",
            "remote, us",
        )
    )
    generic_remote = job.location.strip().lower() in {"", "remote", "remote us"}
    if is_remote and (explicit_us or generic_remote):
        dimensions["location"] = 12
        reasons.append("Remote US-compatible location.")
    elif is_remote:
        dimensions["location"] = 6
        reasons.append("Remote role; US eligibility is not explicit.")
        risk_flags.append("Confirm that the remote geography includes the United States.")
    elif is_hybrid and is_dfw:
        dimensions["location"] = 7
        reasons.append("Dallas/Plano/DFW hybrid location fit.")
    elif is_onsite:
        dimensions["location"] = -12
        risk_flags.append("Onsite-only location.")
    elif is_dfw:
        dimensions["location"] = 4
        reasons.append("Dallas/Plano/DFW location fit; work arrangement is unclear.")
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
    elif off_lane_titles:
        verdict = FitVerdict.NOT_WORTH_TIME
    elif score >= 80:
        verdict = FitVerdict.APPLY_PRIORITY
    elif score >= 65:
        verdict = FitVerdict.GOOD_FIT
    elif score >= 45:
        verdict = FitVerdict.MAYBE
    else:
        verdict = FitVerdict.NOT_WORTH_TIME
    return ScoreResult(score, verdict, dimensions, reasons, risk_flags)
