# Handoff — M49: LLM screening-question answers

Self-contained brief for the next build. For full project state see
`docs/HANDOFF_M45_NEXT.md` (M39–M48); for original basics
`docs/HANDOFF_NEXT_SESSION.md` (M1–M38).

## 0. Environment (quick)

- Dir `/Users/vadimkoenen/Documents/Application Agent` (`Bash` resets cwd —
  prefix paths). `python3`, no venv. Repo
  https://github.com/vadim-koenen/application-bot, `main` default, per-milestone
  branch → PR → `gh pr merge --merge`, Co-Authored-By trailer.
- `python3 -m pytest -q` → **202 passing**. `./run_app.sh` (window on display
  "C32F391"). `set -a; . ./.env; set +a` for live runs.
- `anthropic` SDK is installed; `ANTHROPIC_API_KEY` is in `.env` but the
  **account balance is $0**, so live Claude calls 400 and fall back. Build + test
  with a **mocked** client (see §4); real output needs the operator to add API
  credits (console.anthropic.com → Plans & Billing).

## 1. The task

Draft answers to a role's **screening / essay questions** ("Why are you
interested in this role?", "Describe your RevOps experience", custom prompts)
from the operator's *approved* profile + the JD — claim-filtered, for the human
to review and paste. Same philosophy as the M44 cover letter: Claude drafts,
a hard guard rejects anything fabricated, and it falls back to leaving the
question for the human (never invents).

This is the operator's chosen next item. It extends M44 directly.

## 2. What already exists (reuse, don't reinvent)

- **`application_bot/cover_letter_llm.py`** — the template to copy:
  - `_call_claude(system, user, model) -> str | None` (lazy-imports anthropic,
    returns None on missing SDK / any error). **Reuse this exact helper** —
    consider moving it to a shared `llm.py` if both modules need it, or import it.
  - `validate_cover_letter(text, profile, inventory)` — the fabrication guard:
    every numeric token in the output must appear in the approved corpus
    (`_numeric_tokens`, `_approved_corpus`), and degree/cert/employer + comp/visa
    terms are rejected. **Generalize this** into a reusable
    `validate_against_profile(text, profile, inventory)` (it's almost there).
  - `draft_cover_letter_llm(...)` — the no-key → None, draft → validate → fall
    back flow. Mirror it.
  - `DEFAULT_MODEL = "claude-opus-4-8"`, env override `COVER_LETTER_MODEL`.
- **`application_bot/answers.py`** `build_answer_draft(answer_bank, evidence)` →
  dict of approved answers, with the `REVIEW_REQUIRED` sentinel for
  comp/legal-sensitive ones (Compensation, Background check, Legal-sensitive,
  Unknown required questions). It also has reusable "Why interested"/"Why fit"
  approved blurbs.
- **`application_bot/assisted_apply.py`** `build_fill_plan` →
  `autofill_fields` (paste-ready) and `human_fields` (REVIEW_REQUIRED). The app
  already surfaces paste-ready answers in the drawer
  (`start_application` → UI `renderApplyHelper`).
- **`application_bot/claims.py`** `text_claim_violations(text, inventory)` — the
  shared prohibited-claim matcher.
- Approved sources: `data/private/resume_master.yaml` (identity, contact,
  summary, selected_impact, skills) + `config/resume_claim_inventory.yaml`
  (off-lane, prohibited claims, approved themes).

## 3. Suggested design

- New `application_bot/screening_llm.py` (or extend `cover_letter_llm.py`):
  `draft_screening_answers(job, profile, inventory, questions, *, model=None)
  -> dict[str, str]` — for each question:
  - Skip (leave for human) if it's comp/legal/identity-sensitive — detect via
    keywords (salary, compensation, visa, sponsor, authoriz, race, gender,
    veteran, disability, felony, background check) → never auto-draft these.
  - Otherwise prompt Claude with the approved facts + JD + the question; system
    prompt mirrors `cover_letter_llm._SYSTEM` (only approved facts, no invented
    numbers/degrees/employers, concise).
  - Validate each answer with the generalized guard; drop any that fail.
  - Return only the answers that passed (the UI shows them as drafts to review).
  - No key / SDK / all-failed → return `{}` (operator answers manually).
- **`JobAppAPI.draft_answers(job_id, questions: list[str]) -> dict`** — load
  master + inventory + JD, call the drafter, return `{ "answers": {...},
  "skipped": [...], "ok": True }`. Add a `cover_letter_status`-style note so the
  UI can say whether Claude drafting is active.
- **UI**: in the slide-over (near the apply helper / Prepare application), add a
  small textarea "Paste the role's questions (one per line)" + a "Draft answers"
  button → calls `draft_answers` → renders each question + drafted answer to
  copy, and lists skipped (sensitive) ones for the human. Keep it offline-safe
  (works with no key → shows "add API credits to enable"; the standard approved
  answers still come from `build_answer_draft`).

## 4. Boundaries + tests

- **No fabrication**: every drafted answer passes the guard (numbers must be in
  the approved corpus; no degree/cert/employer/comp). Sensitive questions are
  never auto-answered.
- Tests (mock `_call_claude` via monkeypatch, as in
  `tests/test_m44_llm_cover_letter.py`): validator accepts approved-grounded
  answers / rejects fabricated; sensitive questions are skipped not drafted;
  no-key returns `{}`; a fabricated LLM answer is dropped (falls back). Keep the
  full suite green.

## 5. Git state at handoff

`main` is at M48 (PR #37 merged); `git log --oneline -3` to confirm. Start a new
branch `feature/application-bot-m49-screening-answers`. Housekeeping:
`data/private/*.bak` backups can be deleted.
