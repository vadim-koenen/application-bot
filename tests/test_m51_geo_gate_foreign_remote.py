"""M51: tighten the geography gate — drop foreign-remote, keep US-remote.

The operator is DFW-based and not relocating, and curating a résumé + cover
letter costs tokens, so roles that aren't workable from DFW must be gated out
before curation. Extends the M31 gate: a "remote" role pinned to a foreign
country (no US eligibility marker) is now off-geography too. DFW, US-remote,
US-ambiguous remote, and genuinely unknown-location roles still pass.

rescore_all applies the tightened rule to roles already in the DB without
disturbing ones the operator has already acted on (APPLIED / RESPONDED).
"""

from __future__ import annotations

from copy import deepcopy

from application_bot.config import DEFAULT_CONFIG
from application_bot.database import Database
from application_bot.models import FitVerdict, Job
from application_bot.pipeline import rescore_all
from application_bot.scoring import score_job

INLANE = "Own revenue operations, GTM systems, and marketing operations."


def _job(location: str, remote_type: str) -> Job:
    return Job(
        external_id=location + remote_type, source="greenhouse", source_url="",
        apply_url="https://x/apply", company="Acme",
        title="Director, Marketing Operations",
        location=location, remote_type=remote_type,
        salary_min=180000, salary_max=220000,
        description=INLANE, requirements=INLANE,
    )


def _result(location: str, remote_type: str, config=None):
    return score_job(_job(location, remote_type), config or deepcopy(DEFAULT_CONFIG))


# --- foreign-remote is now dropped -------------------------------------------

def test_foreign_remote_is_excluded():
    for loc in (
        "Remote - Canada", "Remote - Japan", "Bengaluru, India",
        "London, United Kingdom", "Remote (Vancouver, BC)", "Remote - Mexico",
    ):
        assert _result(loc, "remote").verdict == FitVerdict.NOT_WORTH_TIME, loc


def test_foreign_remote_has_explanatory_flag():
    flags = _result("Remote - Canada", "remote").risk_flags
    assert any("Off-geography" in f for f in flags)


# --- any US remote passes, including roles that list a US city ---------------

def test_us_remote_passes():
    for loc in (
        "Remote - United States", "Remote - US", "Remote U.S.",
        "Remote - United States (must reside in eligible states incl. TX)", "",
    ):
        assert _result(loc, "remote").verdict != FitVerdict.NOT_WORTH_TIME, loc


def test_us_city_remote_is_kept():
    # M56: if the posting is remote it's workable from DFW even when it lists a
    # US city — the role itself is remote, so keep it.
    for loc in (
        "New York City, New York", "San Mateo, San Mateo County",
        "Seattle, Washington", "San Francisco, CA", "Bellevue, WA, USA",
    ):
        assert _result(loc, "remote").verdict != FitVerdict.NOT_WORTH_TIME, loc


# --- unchanged behaviour from M31 (regression guard) -------------------------

def test_dfw_and_unknown_still_pass():
    assert _result("Plano, TX", "onsite").verdict != FitVerdict.NOT_WORTH_TIME
    assert _result("Frisco, TX (Hybrid)", "hybrid").verdict != FitVerdict.NOT_WORTH_TIME
    assert _result("", "unknown").verdict != FitVerdict.NOT_WORTH_TIME
    assert _result("United States", "unknown").verdict != FitVerdict.NOT_WORTH_TIME


def test_onsite_elsewhere_still_excluded():
    assert _result("New York, NY", "onsite").verdict == FitVerdict.NOT_WORTH_TIME
    assert _result("Austin, TX", "hybrid").verdict == FitVerdict.NOT_WORTH_TIME


def test_dfw_suburb_name_collision_is_not_dfw():
    # "Arlington" alone (Arlington County, VA) must NOT count as DFW; the real
    # DFW Arlington carries a Texas marker.
    assert _result("Fort Myer, Arlington County", "onsite").verdict == (
        FitVerdict.NOT_WORTH_TIME
    )
    assert _result("Arlington, TX", "onsite").verdict != FitVerdict.NOT_WORTH_TIME


# --- rescore_all maintenance -------------------------------------------------

def _seed(db: Database, location: str, remote_type: str, *, status: str, verdict: str) -> int:
    job = _job(location, remote_type)
    # Distinct apply_url so the three seeds don't collide on the dedupe key.
    job.apply_url = f"https://x/apply/{status}-{verdict}-{location}"
    job_id, _ = db.upsert_job(job)
    with db.connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, verdict = ? WHERE id = ?",
            (status, verdict, job_id),
        )
    return job_id


def test_rescore_all_hides_foreign_remote_and_skips_acted_on(tmp_path):
    db = Database(tmp_path / "c.sqlite")
    db.initialize()
    config = deepcopy(DEFAULT_CONFIG)
    # A foreign-remote role that was previously (mis)graded GOOD_FIT.
    foreign = _seed(db, "Remote - Canada", "remote", status="SCORED", verdict="GOOD_FIT")
    # A US-remote role that should stay eligible.
    keep = _seed(db, "Remote - United States", "remote", status="SCORED", verdict="GOOD_FIT")
    # A role the operator already applied to — must be left untouched.
    applied = _seed(db, "Remote - Canada", "remote", status="APPLIED", verdict="GOOD_FIT")

    summary = rescore_all(db, config)

    assert db.get_job(foreign).verdict == str(FitVerdict.NOT_WORTH_TIME)
    assert db.get_job(keep).verdict != str(FitVerdict.NOT_WORTH_TIME)
    # The applied role is skipped: stage and verdict preserved.
    assert db.get_job(applied).status == "APPLIED"
    assert db.get_job(applied).verdict == "GOOD_FIT"
    assert summary["changed"] >= 1
    assert summary["rescored"] == 2  # applied one excluded
