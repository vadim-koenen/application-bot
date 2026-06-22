"""M19: sales-title penalty offset.

The "generic sales title" mismatch penalty must still bury pure sales roles with
weak function fit, but must NOT bury an on-lane RevOps/marketing-ops role that
merely carries a "Sales"-led title when its body shows strong function fit at a
target (director) seniority. Hard reject/off-lane signals are never softened.
"""

from __future__ import annotations

from copy import deepcopy

from application_bot.config import DEFAULT_CONFIG
from application_bot.models import FitVerdict, Job
from application_bot.scoring import score_job


def _config() -> dict:
    return deepcopy(DEFAULT_CONFIG)


def _job(**kw) -> Job:
    base = dict(
        external_id="t1",
        source="manual_json",
        source_url="",
        apply_url="https://example.com/apply",
        company="Acme",
        title="Director, Sales Enablement & Marketing",
        location="Remote - United States",
        remote_type="remote",
        description="",
        requirements="",
        responsibilities="",
    )
    base.update(kw)
    return Job(**base)


# A body rich in in-lane function keywords (drives function_fit >= strong).
STRONG_BODY = (
    "Own CRM strategy and revenue operations, pipeline management, marketing "
    "operations, go-to-market systems, lifecycle operations, and Salesforce "
    "and HubSpot administration across the go-to-market organization."
)


def test_sales_title_with_strong_fit_is_not_penalized():
    job = _job(description=STRONG_BODY, requirements=STRONG_BODY)
    result = score_job(job, _config())
    assert result.dimensions["seniority"] == 20
    assert result.dimensions["function_fit"] >= 10
    # The title-only penalty is offset; the dimension is neutral.
    assert result.dimensions["role_mismatch"] == 0
    assert any("offset" in flag.lower() for flag in result.risk_flags)
    # No longer dragged below the review floor by the title alone.
    assert result.verdict != FitVerdict.NOT_WORTH_TIME


def test_pure_sales_title_with_weak_fit_still_penalized():
    # Quota-carrying sales role: "Sales" title, no in-lane function fit.
    job = _job(
        title="Account Executive, Enterprise Sales",
        description="Carry a quota, close net-new logos, manage a sales territory.",
        requirements="5+ years quota-carrying SaaS sales experience.",
    )
    result = score_job(job, _config())
    assert result.dimensions["role_mismatch"] == int(
        _config()["role_mismatch_penalty"]
    )
    assert any("mismatch" in flag.lower() for flag in result.risk_flags)


def test_sales_title_strong_body_but_wrong_seniority_keeps_penalty():
    # Strong function body, but a coordinator-level (reject) title => seniority
    # is not a target level, so the offset must NOT apply.
    job = _job(
        title="Sales Operations Coordinator",
        description=STRONG_BODY,
        requirements=STRONG_BODY,
    )
    result = score_job(job, _config())
    assert result.dimensions["seniority"] <= 0
    assert result.dimensions["role_mismatch"] == int(
        _config()["role_mismatch_penalty"]
    )
