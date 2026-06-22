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

Assisted-apply prototype: drive the user's logged-in browser to fill one real
posting end-to-end, attach the role's ATS resume `.txt`, stop at Submit. Needs
one live target URL + user go-ahead.
