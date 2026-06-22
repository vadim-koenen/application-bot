# Project State — Application Bot

Durable status/memory for the application-bot project. Public-safe: no personal
targets, contact info, or resume content here (those live under `data/private/`,
which is gitignored).

_Last updated: 2026-06-22_

## Purpose

Compliance-first job-search assistant: **discover → score → packet → ATS resume
→ assisted apply** (the human submits). It builds pipeline and removes the
tailoring toil; it does not autonomously submit applications.

## Flow & what is / isn't hands-off

| Stage | Hands-off? |
|---|---|
| Discover live openings (Greenhouse/Lever/Ashby public boards) | ✅ yes (can schedule) |
| Score against tuned target lane | ✅ yes |
| Claim-safe packet (cover email/letter + answer pack) | ✅ yes |
| ATS resume v2 per role (keyword-aligned, gap report) | ✅ yes |
| **Submit application** | ❌ **human-in-the-loop by design** |

The apply step is **assisted apply**: the bot fills the form in the user's own
logged-in browser and stops at Submit for a one-click human review. We do NOT
build headless auto-submit to Indeed/ZipRecruiter/ATS — it violates their ToS,
needs CAPTCHA/login circumvention, risks account bans, and the application
attestations must be the user's personal act.

## Safety invariants (must stay true)

- `APPLICATIONS_SUBMITTED = 0` until an explicit, per-send human approval.
- `LIVE_APPLY_ENABLED` / `LIVE_EMAIL_SEND_ENABLED` off by default; live email
  send also requires an exact approval phrase + SMTP creds (three gates).
- No fabricated claims; compensation and legal/background answers stay locked to
  manual review.
- Work authorization: authorized to work in the US, no visa sponsorship required
  (user-confirmed). Scoped to answers-when-asked, never proactive packet text.
- Private job data (targets, contact PII, master resume) stays in `data/private/`
  (gitignored), never committed.

## Milestones / open draft PRs

- **M15** — first email-to-apply manual-review lane + approved binary answers (PR #8)
- **M16** — title gate scores in-lane systems/ops Manager & Lead roles (PR #9)
- **M17** — ATS resume v2 generator (`ats-resume` CLI) (PR #10)
- **M18** — assisted-apply fill plan (`assisted-apply` CLI; `application_bot/assisted_apply.py`).
  Deterministic, submit-free: pre-fills only approved answers, leaves every
  REVIEW_REQUIRED answer blank for the human, resolves the role's ATS `.txt`,
  flags non-form (recruiter-email) apply URLs. 6 tests (114 total).
- **M21** — PDF artifacts: `application_bot/pdf.py` renders the tailored ATS
  résumé + claim-safe cover letter to ATS-parseable PDFs via fpdf2 (optional dep,
  lazy-imported; text ASCII-normalized). New `make-pdf --job-id` CLI. 3 tests (124 total).
- **M20** — last-24h discovery: `scan_registry(posted_within_hours=N)` keeps only
  roles posted within N hours (defensive date parse handles Greenhouse/Ashby ISO
  + Lever epoch-millis; undated roles excluded + counted). `--posted-within-hours`
  on `scan`/`run-dry-pipeline`. Registry expanded to 22 companies (6 enabled, 16
  candidates to validate). First phase of the desktop "auto-apply" app. 4 tests (121 total).
- **M19** — scorer fix: the "generic sales title" mismatch penalty is offset when
  a Sales-led title also shows strong in-lane function fit (>= strong_function_points)
  at a target (director) seniority — it becomes an advisory flag, not a -30 hit.
  Hard reject/off-lane signals are never softened. Fixed a real false negative
  (a Director, Sales Enablement & Marketing role: 35/NOT_WORTH_TIME -> 65/GOOD_FIT);
  no change to the 13 prior ready roles. 3 tests (117 total).

Each stacks on the previous branch. NOTE: the repo has **no `main` branch** yet
— the default is `feature/application-bot-m1-m5-core` and all milestones stack
from there. Worth establishing a `main` and merging the stack when ready.

## Key commands

```bash
python3 -m pytest -q                       # full suite
python3 -m application_bot.main run-dry-pipeline --registry config/live_company_registry.yaml --db <db> --out <out>
python3 -m application_bot.main ats-resume --db <db> --out <out>   # ATS resumes for ready roles
python3 -m application_bot.main report --db <db>
```

## Next step

The fill-plan core is built (M18). Remaining: the **live browser drive** —
given one real http(s) ATS posting URL + user go-ahead, use Claude-in-Chrome to
open the posting, apply the fill plan (`assisted-apply --job-id N`) to the user's
own logged-in form, attach the role's ATS `.txt`, and **stop at Submit** for the
human click. Blocker: the 13 ready roles are `manual_json` placeholders with no
http form URL; a live posting URL must be supplied per role.
