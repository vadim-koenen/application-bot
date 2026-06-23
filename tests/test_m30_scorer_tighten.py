"""M30: tighten the scorer against off-lane false positives.

Director/Head titles in off-lane functions (finance, design, engineering, legal,
recruiting, account management) carry seniority points and were reaching MAYBE.
They must now resolve to NOT_WORTH_TIME, while genuine in-lane roles are unaffected.
"""

from __future__ import annotations

from copy import deepcopy

from application_bot.config import DEFAULT_CONFIG
from application_bot.models import FitVerdict, Job
from application_bot.scoring import score_job


def _verdict(title: str, description: str = "") -> FitVerdict:
    job = Job(
        external_id=title,
        source="greenhouse",
        source_url="",
        apply_url="https://x/apply",
        company="Acme",
        title=title,
        location="Remote - United States",
        remote_type="remote",
        description=description or "Drive strategy and operations for the team.",
    )
    return score_job(job, deepcopy(DEFAULT_CONFIG)).verdict


OFF_LANE = [
    "Director, R&D Finance",
    "Head of Design",
    "Software Security Engineer",
    "Sr. Growth Engineer",
    "Business Recruiter",
    "Litigation and E-Discovery Counsel",
    "Director, Strategic Account Management",
    "Head of People Operations",
]


def test_off_lane_director_titles_are_not_worth_time():
    for title in OFF_LANE:
        assert _verdict(title) == FitVerdict.NOT_WORTH_TIME, title


def test_in_lane_roles_still_pass():
    inlane = "Own revenue operations, GTM systems, and marketing operations."
    assert _verdict("Director, Marketing Operations", inlane) != FitVerdict.NOT_WORTH_TIME
    assert _verdict("Senior Revenue Operations Manager", inlane) != FitVerdict.NOT_WORTH_TIME
    assert _verdict("Director, Marketing Technology", inlane) != FitVerdict.NOT_WORTH_TIME
