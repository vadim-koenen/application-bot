"""M44: LLM-drafted cover letters with a hard fabrication guard.

A rule-based template can't write a genuinely good cover letter, so when an
Anthropic API key is configured the app drafts the letter with Claude from the
operator's *approved* profile + the specific JD. The draft then passes a
fabrication guard before it's ever used:

- every number in the letter must already appear in the approved source text
  (so Claude can restate the approved impact metrics, but cannot invent a new
  one, a tenure figure, or a date);
- degree / certification / prior-employer claims and comp/legal-sensitive terms
  (salary, visa, sponsorship, …) are rejected outright.

If the key is missing, the SDK isn't installed, the call fails, or the draft
fails the guard, `draft_cover_letter_llm` returns None and the caller falls back
to the deterministic claim-safe template. The boundary (no fabricated claims) is
preserved either way.
"""

from __future__ import annotations

import os
import re
from typing import Any

# Default model — Anthropic's most capable Opus-tier model. Override via the
# `cover_letter_model` config key or the COVER_LETTER_MODEL env var.
DEFAULT_MODEL = "claude-opus-4-8"

_SYSTEM = (
    "You are writing a cover letter on behalf of a job candidate. You must use "
    "ONLY the approved facts provided. Hard rules, no exceptions:\n"
    "- Do NOT invent or estimate any number, metric, percentage, dollar figure, "
    "date, or years-of-experience. You may restate the approved impact metrics "
    "verbatim, but introduce no new ones.\n"
    "- Do NOT mention degrees, certifications, specific past employers, or "
    "employment dates.\n"
    "- Do NOT mention salary, compensation, visa, sponsorship, work "
    "authorization, or relocation.\n"
    "- Do not fabricate skills or claims not in the approved facts.\n"
    "Write a specific, confident, genuinely good cover letter: ~250-340 words, "
    "3-4 short paragraphs, addressed to the company's hiring team, tailored to "
    "the role using the approved positioning and the posting's focus. Plain "
    "prose, no markdown, no placeholders, no salutation line beyond 'Dear … "
    "Hiring Team,'. End with 'Sincerely,' and the candidate's name."
)

# Inventory claim ids whose patterns we still enforce on LLM output. We omit
# `quantified_achievements`, `leadership_team_size`, and `years_of_experience`
# here because the approved impact metrics legitimately match those patterns —
# the number guard below is what catches *fabricated* figures.
_ENFORCED_CLAIM_IDS = {"degrees", "certifications", "employment_history", "budget_ownership"}

_SENSITIVE_TERMS = (
    "salary", "compensation", "visa", "sponsor", "authoriz", "wage",
    "relocat", "clearance",
)

_NUM_RE = re.compile(r"\$?\s?\d[\d,]*\.?\d*\s?(?:%|[kKmMbB]\b)?")


def _numeric_tokens(text: str) -> set[str]:
    """Normalized numeric tokens in `text` ($51M -> 51m, 35% -> 35%, 14 -> 14)."""
    tokens: set[str] = set()
    for match in _NUM_RE.findall(text or ""):
        norm = match.lower().replace("$", "").replace(",", "").replace(" ", "")
        norm = norm.strip(".")
        if norm and any(ch.isdigit() for ch in norm):
            tokens.add(norm)
    return tokens


def _approved_corpus(profile: dict[str, Any]) -> str:
    parts = [
        str(profile.get("summary") or ""),
        " ".join(str(x) for x in (profile.get("selected_impact") or [])),
        str((profile.get("identity") or {}).get("headline") or ""),
    ]
    return " ".join(parts)


def validate_cover_letter(
    letter: str, profile: dict[str, Any], inventory: dict[str, Any]
) -> bool:
    """True iff the drafted letter introduces no fabricated/prohibited content."""
    if not letter or not letter.strip():
        return False
    low = letter.lower()
    if any(term in low for term in _SENSITIVE_TERMS):
        return False
    # Enforce the non-numeric prohibited-claim patterns (degrees, certs, etc.).
    for claim in inventory.get("prohibited_or_unverified_claims", []):
        if str(claim.get("id") or "") not in _ENFORCED_CLAIM_IDS:
            continue
        for pattern in claim.get("patterns", []):
            if re.search(str(pattern), letter, flags=re.IGNORECASE | re.DOTALL):
                return False
    # Every number in the letter must appear in the approved source text.
    approved_nums = _numeric_tokens(_approved_corpus(profile))
    if not _numeric_tokens(letter) <= approved_nums:
        return False
    return True


# The guard is content-agnostic — it rejects any text that introduces a number,
# degree/cert/employer, or comp/visa term not grounded in the approved profile.
# M49 reuses it verbatim for screening-question answers; this alias names that
# generalized intent without duplicating the logic.
validate_against_profile = validate_cover_letter


def _build_user_message(job: Any, profile: dict[str, Any], matched: list[str]) -> str:
    identity = profile.get("identity") or {}
    business = "Koenen Revenue Systems (KRS)"
    impact = "\n".join(f"- {x}" for x in (profile.get("selected_impact") or []))
    jd = (job.description or job.requirements or job.responsibilities or "").strip()
    return (
        "APPROVED FACTS (use only these):\n"
        f"Candidate name: {identity.get('name', '')}\n"
        f"Current professional identity: {business}\n"
        f"Approved positioning summary: {profile.get('summary', '')}\n"
        f"Approved impact metrics (you may restate these exactly):\n{impact}\n"
        f"Themes matched to this role: {', '.join(matched) or 'n/a'}\n\n"
        "THE ROLE:\n"
        f"Title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Job description:\n{jd[:2500]}\n\n"
        "Write the cover letter now."
    )


def _call_claude(system: str, user: str, model: str) -> str | None:
    """Single Messages API call. Returns the text, or None on any failure.

    Imported lazily so the app runs without the `anthropic` package; falls back
    to the template when the SDK is absent or the call errors.
    """
    try:
        import anthropic
    except ImportError:
        return None
    # Bound the call so a slow/hung request can't stall the caller — the SDK's
    # default timeout is 10 minutes, which would make "Start application" appear
    # to hang and never produce the downloaded PDFs. On timeout we fall back to
    # the deterministic template. Override with COVER_LETTER_TIMEOUT (seconds).
    try:
        timeout = float(os.environ.get("COVER_LETTER_TIMEOUT") or 45)
    except ValueError:
        timeout = 45.0
    try:
        client = anthropic.Anthropic(timeout=timeout, max_retries=1)
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()
    except Exception:  # noqa: BLE001 - any SDK/network/timeout error → template
        return None


def draft_cover_letter_llm(
    job: Any,
    profile: dict[str, Any],
    inventory: dict[str, Any],
    *,
    matched: list[str] | None = None,
    model: str | None = None,
) -> str | None:
    """Draft a cover letter with Claude, or None to fall back to the template.

    Returns None when no API key is set, the SDK is missing, the call fails, or
    the draft fails the fabrication guard."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    model = model or os.environ.get("COVER_LETTER_MODEL") or DEFAULT_MODEL
    user = _build_user_message(job, profile, matched or [])
    letter = _call_claude(_SYSTEM, user, model)
    if letter and validate_cover_letter(letter, profile, inventory):
        return letter
    return None
