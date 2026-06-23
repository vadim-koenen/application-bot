"""M31: hard location gate — remote or DFW metroplex only.

A role must be remote or in the DFW metroplex; anything else (onsite or hybrid
elsewhere) scores NOT_WORTH_TIME regardless of fit. The gate is config-toggleable.
"""

from __future__ import annotations

from copy import deepcopy

from application_bot.config import DEFAULT_CONFIG
from application_bot.models import FitVerdict, Job
from application_bot.scoring import score_job

INLANE = "Own revenue operations, GTM systems, and marketing operations."


def _verdict(location: str, remote_type: str, config=None) -> FitVerdict:
    job = Job(
        external_id=location + remote_type,
        source="greenhouse",
        source_url="",
        apply_url="https://x/apply",
        company="Acme",
        title="Director, Marketing Operations",
        location=location,
        remote_type=remote_type,
        salary_min=180000,
        salary_max=220000,
        description=INLANE,
        requirements=INLANE,
    )
    return score_job(job, config or deepcopy(DEFAULT_CONFIG)).verdict


def test_remote_and_dfw_pass():
    assert _verdict("Remote - United States", "remote") != FitVerdict.NOT_WORTH_TIME
    assert _verdict("Plano, TX", "onsite") != FitVerdict.NOT_WORTH_TIME
    assert _verdict("Frisco, TX (Hybrid)", "hybrid") != FitVerdict.NOT_WORTH_TIME


def test_offsite_elsewhere_is_excluded():
    # Strong in-lane fit, but onsite/hybrid in a non-DFW city -> excluded.
    assert _verdict("New York, NY", "onsite") == FitVerdict.NOT_WORTH_TIME
    assert _verdict("Chicago, IL", "hybrid") == FitVerdict.NOT_WORTH_TIME
    assert _verdict("Austin, TX", "onsite") == FitVerdict.NOT_WORTH_TIME  # TX but not DFW


def test_unknown_location_is_not_excluded():
    # Curated roles imported without a location field must not be geo-gated out
    # (we only hard-exclude CONFIRMED onsite/hybrid-elsewhere).
    assert _verdict("", "unknown") != FitVerdict.NOT_WORTH_TIME
    assert _verdict("United States", "unknown") != FitVerdict.NOT_WORTH_TIME


def test_gate_can_be_disabled():
    config = deepcopy(DEFAULT_CONFIG)
    config["require_remote_or_dfw"] = False
    assert _verdict("New York, NY", "onsite", config) != FitVerdict.NOT_WORTH_TIME
