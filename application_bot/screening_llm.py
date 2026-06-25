"""M49: LLM-drafted answers to a role's screening / essay questions.

Extends the M44 cover-letter pattern to the free-text questions an application
form asks ("Why are you interested in this role?", "Describe your RevOps
experience", custom prompts). Claude drafts each answer from the operator's
*approved* profile + the JD, and the same fabrication guard
(`cover_letter_llm.validate_against_profile`) rejects anything that introduces a
number, degree/cert/employer, or comp/visa term not grounded in the approved
facts. Answers that fail the guard are dropped — the question is left for the
human rather than answered with an invented claim.

Two hard boundaries, same as the cover letter:
- comp / legal / identity questions (salary, visa, sponsorship, race, gender,
  veteran, disability, felony, background check, …) are NEVER auto-drafted —
  `is_sensitive_question` filters them out *before* any model call, and the
  guard rejects them as a backstop;
- no key / SDK-absent / call failure / all-failed → return `{}` and the operator
  answers manually.
"""

from __future__ import annotations

import os
from typing import Any

# Reuse the cover-letter helpers wholesale. We reference `_call_claude` through
# the module (not by value) so a test can `monkeypatch.setattr(cl,
# "_call_claude", ...)` and have it take effect here too — the same hook the
# M44 tests already use.
import application_bot.cover_letter_llm as _cl
from application_bot.cover_letter_llm import DEFAULT_MODEL, validate_against_profile

# Questions we never auto-answer: compensation, work-authorization/legal, and
# protected-class / identity prompts. Detected by substring before any model
# call, so a sensitive question is left for the human and never sent to Claude.
_SENSITIVE_QUESTION_TERMS = (
    # compensation
    "salary", "compensation", "pay range", "desired pay", "expected pay",
    "rate expectation", "wage",
    # work authorization / legal status
    "visa", "sponsor", "authoriz", "right to work", "work permit",
    "relocat", "clearance", "citizen", "national origin",
    # protected class / identity
    "race", "ethnic", "gender", "veteran", "disab", "felon", "criminal",
    "background check", "date of birth", "social security",
    "sexual orientation", "marital status",
)

_SCREENING_SYSTEM = (
    "You are drafting an answer to an application screening/essay question on "
    "behalf of a job candidate. The answer will be reviewed by the candidate "
    "before use. You must use ONLY the approved facts provided. Hard rules, no "
    "exceptions:\n"
    "- Do NOT invent or estimate any number, metric, percentage, dollar figure, "
    "date, or years-of-experience. You may restate the approved impact metrics "
    "verbatim, but introduce no new ones.\n"
    "- Do NOT mention degrees, certifications, specific past employers, or "
    "employment dates.\n"
    "- Do NOT mention salary, compensation, visa, sponsorship, work "
    "authorization, or relocation.\n"
    "- Do not fabricate skills or claims not in the approved facts.\n"
    "Answer the specific question directly in 2-5 sentences of confident, "
    "specific plain prose, tailored to the role using the approved positioning. "
    "No markdown, no headings, no placeholders, no salutation, no sign-off — "
    "just the answer."
)


def is_sensitive_question(question: str) -> bool:
    """True if `question` asks for comp / legal / identity info we never draft."""
    low = (question or "").lower()
    return any(term in low for term in _SENSITIVE_QUESTION_TERMS)


def _build_user_message(job: Any, profile: dict[str, Any], question: str) -> str:
    identity = profile.get("identity") or {}
    business = "Koenen Revenue Systems (KRS)"
    impact = "\n".join(f"- {x}" for x in (profile.get("selected_impact") or []))
    jd = (job.description or job.requirements or job.responsibilities or "").strip()
    return (
        "APPROVED FACTS (use only these):\n"
        f"Candidate name: {identity.get('name', '')}\n"
        f"Current professional identity: {business}\n"
        f"Approved positioning summary: {profile.get('summary', '')}\n"
        f"Approved impact metrics (you may restate these exactly):\n{impact}\n\n"
        "THE ROLE:\n"
        f"Title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Job description:\n{jd[:2000]}\n\n"
        "THE SCREENING QUESTION:\n"
        f"{question}\n\n"
        "Write the answer now."
    )


def draft_screening_answers(
    job: Any,
    profile: dict[str, Any],
    inventory: dict[str, Any],
    questions: list[str],
    *,
    model: str | None = None,
) -> dict[str, str]:
    """Draft a claim-safe answer for each non-sensitive question.

    Returns `{question: answer}` for only the questions that (a) are not
    comp/legal/identity-sensitive and (b) produced a draft that passes the
    fabrication guard. Sensitive questions, dropped drafts, and the no-key /
    SDK-absent / call-failure cases are simply absent from the result (an empty
    dict means "answer them all yourself")."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {}
    model = (
        model
        or os.environ.get("SCREENING_MODEL")
        or os.environ.get("COVER_LETTER_MODEL")
        or DEFAULT_MODEL
    )
    answers: dict[str, str] = {}
    for raw in questions:
        question = str(raw).strip()
        if not question or is_sensitive_question(question):
            continue
        user = _build_user_message(job, profile, question)
        answer = _cl._call_claude(_SCREENING_SYSTEM, user, model)
        if answer and validate_against_profile(answer, profile, inventory):
            answers[question] = answer
    return answers
