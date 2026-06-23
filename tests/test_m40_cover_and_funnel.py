"""M40: stronger cover letter + funnel/new-tab hardening.

The cover letter now leads with approved positioning and renders approved
impact bullets (selected_impact), but every candidate bullet is filtered
through the prohibited-claim patterns first — so the letter can never assert
something the inventory hasn't approved. Separately, a role marked applied (or
replied) must drop out of the New bucket immediately.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from app_api import JobAppAPI
from application_bot.claims import packet_claim_violations
from application_bot.config import DEFAULT_CONFIG, load_claim_inventory
from application_bot.database import Database
from application_bot.models import Job, utc_now
from application_bot.packets import generate_packet
from application_bot.policy import evaluate_job_submission_policy
from application_bot.scoring import score_job

CLAIMS = Path("config/resume_claim_inventory.yaml")


def _scored_job() -> Job:
    job = Job(
        external_id="cover-1",
        source="greenhouse",
        source_url="https://x/1",
        apply_url="https://x/1/apply",
        company="Acme",
        title="Director, Marketing Operations",
        location="Remote - United States",
        remote_type="remote",
        description="Own revenue operations, GTM systems, and marketing operations.",
    )
    result = score_job(job, DEFAULT_CONFIG)
    job.score = result.score
    job.verdict = str(result.verdict)
    return job


def test_cover_letter_renders_approved_impact_and_drops_flagged():
    job = _scored_job()
    inventory = load_claim_inventory(CLAIMS)
    policy = evaluate_job_submission_policy(job, DEFAULT_CONFIG)
    highlights = [
        "$51M pipeline activated via intent + identity resolution",  # safe
        "improved conversion by 30%",   # quantified_achievements -> filtered
        "managed 12 direct reports",    # leadership_team_size -> filtered
        "14 years of experience",       # years_of_experience -> filtered
    ]
    packet = generate_packet(
        job, DEFAULT_CONFIG, policy, inventory=inventory, impact_highlights=highlights
    )
    # The clean, approved win is rendered…
    assert "$51M pipeline activated" in packet.cover_letter
    # …and every flagged candidate is stripped before it reaches the letter.
    assert "improved conversion" not in packet.cover_letter
    assert "managed 12" not in packet.cover_letter
    assert "14 years" not in packet.cover_letter
    # The self-defeating disclaimer paragraph is gone.
    assert "intentionally avoids" not in packet.cover_letter
    # And the letter still passes the packet claim auditor.
    assert packet_claim_violations(packet, inventory) == []


def test_cover_letter_without_highlights_is_clean():
    """No highlights (the path the claim-safety suite exercises) → no bullets,
    no violations, but still real prose rather than boilerplate."""
    job = _scored_job()
    inventory = load_claim_inventory(CLAIMS)
    policy = evaluate_job_submission_policy(job, DEFAULT_CONFIG)
    packet = generate_packet(job, DEFAULT_CONFIG, policy, inventory=inventory)
    assert packet_claim_violations(packet, inventory) == []
    assert "Acme" in packet.cover_letter
    assert "A few results from that work" not in packet.cover_letter


def test_applied_role_leaves_new_bucket(tmp_path):
    db_path = tmp_path / "crm.sqlite"
    database = Database(db_path)
    database.initialize()
    config = deepcopy(DEFAULT_CONFIG)
    fit = Job(
        external_id="fresh-fit",
        source="greenhouse",
        source_url="https://x/1",
        apply_url="https://x/1/apply",
        company="Acme",
        title="Director, Marketing Operations",
        location="Remote - United States",
        remote_type="remote",
        description="Own revenue operations, GTM systems, marketing operations.",
        posted_at=utc_now(),
    )
    jid, _ = database.upsert_job(fit)
    database.save_score(jid, score_job(database.get_job(jid), config))
    api = JobAppAPI(db_path=db_path)
    api.config = config

    new_ids = [r["id"] for r in api.list_roles("new")["roles"]]
    assert jid in new_ids
    api.mark_applied(jid)
    assert jid not in [r["id"] for r in api.list_roles("new")["roles"]]
    assert api.dashboard_summary()["pipeline"]["new"] == 0
