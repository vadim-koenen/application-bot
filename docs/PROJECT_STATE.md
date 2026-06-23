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
- **M26** — dock app: `make_macos_app.sh` builds a lightweight, dockable
  `Job Apply Assistant.app` launcher (no py2app) into `~/Applications`; it execs
  `run_app.sh`, which now sources `.env` and defaults to the real pipeline DB so
  the window opens populated. `main` is the default branch; M1–M25 PRs closed
  (consolidated into main).
- **M29** — Adzuna market-wide discovery: `AdzunaAdapter` + `pipeline.discover_adzuna`
  search the whole market (not just registry boards) for in-lane titles posted in
  the last N hours, keep fresh, score, insert. Wired into the app's Discover
  (no-op without `ADZUNA_APP_ID`/`ADZUNA_APP_KEY`) + `scan-adzuna` CLI. Complements
  the ATS boards (depth) with breadth. Note: Adzuna descriptions are truncated, so
  these score rougher — discovery leads. 4 tests (139 total). Needs a free key.
- **M28** — app = apply hub, email removed. Each role shows a direct **Apply →**
  link to the company form, **Résumé PDF** / **Cover Letter PDF** buttons (tailored
  on click and opened in the viewer to save/print), and **Mark applied**. Dropped
  the email surface from the app/CLI/scheduler (`open_artifact` replaces `email_me`;
  `--auto` is discovery-only; `send-digest` CLI removed). `email_service.send_apply_digest`
  remains as dormant library code. Verified apply URLs go straight to forms
  (e.g. asana.com/jobs/apply/…). 
- **M27** — curated registry: 27 RevOps/martech/B2B-SaaS boards (Klaviyo, ZoomInfo,
  Salesloft, Apollo, Clari, Lattice, Twilio, Pendo, Asana…), retired 7 off-lane
  eng/security boards. New tab now surfaces real in-lane roles.
  `run_discovery` limit raised to 600 so all 27 boards get scanned.
- **M26** — dockable AppleScript `.app` launcher (`make_macos_app.sh`); `run_app.sh`
  sources `.env` + defaults to the real pipeline DB; New tab filtered to fits.
- **M25** — validated registry: live-probed the candidate boards; enabled the 11
  that returned a valid response (now **17 enabled**: Figma, Datadog, Highspot,
  Outreach, Ramp, Deel, Braze, Wiz, Vanta, 6sense, Brex, Samsara, Airtable, Asana,
  Plaid, Mercury, Linear). 5 left disabled (Gong/dbt Labs/Snowflake/Netlify/Hex —
  404 on guessed token). Real 24h scan: 17/17 sources, 58 fresh roles.
- **M24** — schedule + package: `app_main.py --auto` (scheduler entrypoint:
  live last-N-hours scan → email digest) + `launchd/com.vadim.jobapply-daily.plist`
  (daily 08:00). `setup_app.py` packages a `.app` via py2app. 3 tests (135 total).
- **M23** — desktop app (pywebview, mirrors the investment bot): `app_main.py`
  (window + headless CLI: `--cli`/`--discover`/`--email`), `app_api.py`
  (`JobAppAPI` js_api bridge: get_status / list_roles / run_discovery /
  make_artifacts / email_me / mark_applied), `app_ui/index.html` (New-24h /
  Outstanding / Applied / Settings tabs, mark-applied). `run_app.sh`,
  `requirements-app.txt`, `setup_app.py` (py2app). 3 tests (132 total).
- **M22** — apply digest: `email_service.send_apply_digest` emails the user one
  ranked list of ready roles with the apply link + résumé/cover **PDFs attached**.
  New `send-digest --to … [--live]` CLI (dry-run writes an `.eml`; live needs
  SMTP). Self-notification — not behind the employer apply-approval phrase. The
  existing gated `send_email_applications` remains the auto-submit-where-possible
  (email-apply) path. 5 tests (129 total).
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

## Desktop app (M20–M24, built)

`./run_app.sh` opens the **Job Apply Assistant** (pywebview): Discover last-24h →
tailor ATS résumé + cover letter (PDF) → email yourself the apply link with both
attached → track New / Outstanding / Applied. Daily launchd schedule available.
The app emails you to apply; it auto-submits only gated email-apply roles, never
web forms (CAPTCHA/login + ToS).

To go live, the operator must: (1) put `SMTP_*` + `DIGEST_TO` in `.env` (Gmail app
password); (2) validate-and-enable the 16 candidate registry boards; optionally
(3) `python3 setup_app.py py2app` for a dock `.app`.

## Next step

- Validate the candidate ATS boards (live scan) and flip the good ones to
  `enabled: true` for real last-24h coverage.
- Optionally add a paid jobs-aggregator adapter for market-wide coverage.
- Establish a `main` branch and merge the stacked M15–M24 PRs.
