# Handoff — Application Bot (resume in a fresh session)

Read this first. It is self-contained; you should not need the prior chat.

## 0. Environment gotchas

- **Work happens in `/Users/vadimkoenen/Documents/Application Agent`** (the repo).
  A fresh session may open in a different cwd (e.g. an Investing project) — `cd`
  here first. `Bash` resets cwd between calls, so prefix commands with the path.
- Python is **`python3`** (no venv). Only runtime dep: PyYAML. `pypdf` is
  installed to user site (for reading the resume PDF).
- Repo: https://github.com/vadim-koenen/application-bot (now **public**).
- **No `main` branch.** Default is `feature/application-bot-m1-m5-core`; all
  milestones stack on each other. Current tip = `feature/application-bot-m17-ats-resume`.

## 1. What this project is

Compliance-first job-search assistant: **discover → score → packet → ATS resume
→ assisted apply (human submits)**. Builds pipeline + kills tailoring toil; does
NOT autonomously submit. Full status: `docs/PROJECT_STATE.md`.

## 2. Hard boundaries (do not cross)

- **Apply model = assisted apply only.** Bot fills the form in the user's own
  logged-in browser and **stops at Submit** for a human click. Do NOT build
  headless/auto-submit to Indeed/ZipRecruiter/LinkedIn/ATS (ToS violation,
  CAPTCHA/login circumvention, account-ban + attestation risk). User chose this.
- `APPLICATIONS_SUBMITTED` stays 0 until explicit, per-send human approval.
  Live-send gates (`LIVE_APPLY_ENABLED`, `LIVE_EMAIL_SEND_ENABLED`, approval
  phrase, SMTP) stay OFF.
- No fabricated claims. Compensation + legal/background answers stay
  `REVIEW_REQUIRED`. Work auth (US citizen, authorized, no sponsorship) is
  approved but scoped to `application_answer` only — never proactive packet text.
- Private data stays in `data/private/` (gitignored) — never commit it, even
  though the repo is public.

## 3. Built so far (108 tests passing; `python3 -m pytest -q`)

- **M15** (PR #8): email-to-apply manual-review lane; approved binary answers;
  `EMAIL_READY_MANUAL_REVIEW` reporting.
- **M16** (PR #9): title gate scores in-lane systems/ops "Manager"/"Lead" roles
  (config: `systems_lane_titles`/`systems_lane_functions`/`systems_lane_points`).
- **M17** (PR #10): ATS resume v2 generator — `ats-resume` CLI; module
  `application_bot/resume.py`; doc `docs/ATS_RESUME.md`.

## 4. Local private data (gitignored — NOT in the repo)

- `data/private/vadim_active_jobs.json` — 23 real target roles (manual_json).
- `data/private/vadim_pipeline.sqlite` — scored DB (13 PACKET_READY).
- `data/private/resume_master.yaml` — structured approved resume (+contact PII).
- `exports/vadim_pipeline/` — packets + ATS resumes (`ats_resumes/<date>/`).

Source files on the user's machine (if re-import needed): resume PDF at
`~/Desktop/Vadim-Koenen-Resume-June-2026.pdf`; JD archives in `~/Downloads/`.

## 5. Pipeline snapshot (top ready roles)

Mondo 95 (11/11 ATS match, 0 gaps) · Refine Labs 87 · Blackhawk 83 · Level
Access 81 · Helix 81 · McDermott 75 · Brightspeed 75 · Clio 72 · CertainPath
71 · Canyon Ranch 69 · Lundbeck 67 · Nerdio 66 · HubSearch 65 (gap: quote-to-cash).

## 6. Next step (what to build)

**Assisted-apply prototype.** Drive the user's logged-in browser (Claude-in-Chrome
extension) to: open one real posting → fill fields from the packet answer pack →
attach that role's ATS resume `.txt` → **stop at Submit** for the user's click.
Needs from user: one live application URL + go-ahead. Mondo is the top fit but is
a recruiter *email* (Savannah) — for a true form test pick a live ATS posting URL.

Also open/optional: schedule hands-off discovery→score→packet→ats-resume (cron via
`scheduler.py`); create a `main` branch and merge the stacked PRs.

## 7. Key commands

```bash
cd "/Users/vadimkoenen/Documents/Application Agent"
python3 -m pytest -q
python3 -m application_bot.main run-dry-pipeline --registry config/live_company_registry.yaml --db data/private/vadim_pipeline.sqlite --out exports/vadim_pipeline --limit 100
python3 -m application_bot.main scan --source manual_json --input data/private/vadim_active_jobs.json --db data/private/vadim_pipeline.sqlite --limit 100
python3 -m application_bot.main score --db data/private/vadim_pipeline.sqlite
python3 -m application_bot.main refresh-packets --db data/private/vadim_pipeline.sqlite --out exports/vadim_pipeline
python3 -m application_bot.main ats-resume --db data/private/vadim_pipeline.sqlite --out exports/vadim_pipeline
python3 -m application_bot.main report --db data/private/vadim_pipeline.sqlite
```
