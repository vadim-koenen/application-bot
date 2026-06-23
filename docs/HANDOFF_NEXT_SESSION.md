# Handoff — Job Apply Assistant (resume in a fresh session)

Read this first. It is self-contained; you should not need the prior chat.

## 0. Environment gotchas

- **Work happens in `/Users/vadimkoenen/Documents/Application Agent`** (the repo).
  A fresh session may open in a different cwd (an Investing project) — `cd` here
  first. `Bash` resets cwd between calls, so prefix commands with the path.
- Python is **`python3`** (Homebrew, 3.14, no venv). Deps in user-site:
  PyYAML, **fpdf2** (PDFs), **pywebview** (desktop window). Install more with
  `python3 -m pip install --user --break-system-packages <pkg>`.
- Repo: https://github.com/vadim-koenen/application-bot (public). **`main` is now
  the default branch** and contains everything (M1–M35). Per-milestone branch →
  PR → `gh pr merge --merge` into `main`. End commits with the Co-Authored-By
  trailer.
- **Run tests:** `python3 -m pytest -q` (currently **148 passing**).
- **Load `.env` for live runs:** `set -a; . ./.env; set +a` before commands that
  hit the DB/APIs (the app's `run_app.sh` sources it automatically).

## 1. What this project is now

A **desktop job-search app** (pywebview), mirroring the operator's investment bot
pattern. Pipeline: **discover (last 24h) → score → tailor ATS résumé + cover
letter (PDF) → apply (human, on the company form) → track**. It is the operator's
(Vadim Koenen) personal RevOps/marketing-ops/GTM-systems job search.

Launch: `./run_app.sh` (window) · `./run_app.sh --cli` (headless) ·
`./run_app.sh --discover` (live scan). Dock app:
`~/Applications/Job Apply Assistant.app` (rebuild with `./make_macos_app.sh`).

## 2. Hard boundaries (do not cross)

- **No auto-submit of web-form applications** (Greenhouse/BambooHR/Workday/etc.):
  CAPTCHA/login + ToS + the attestation must be the human's act. The app gives a
  direct **Apply →** link; the human submits and clicks **Mark applied**.
- **No scraping LinkedIn/Indeed/ZipRecruiter** — ToS + account bans. The built-in
  `linkedin_review_queue`/`indeed_connector`/`zip_connector` adapters stay
  import-only (BLOCKED/REVIEW). To pull those sources, use the **JSearch** adapter
  (RapidAPI / Google-for-Jobs aggregation), not a crawler.
- **No fabricated claims.** Résumé/cover come only from the approved
  `data/private/resume_master.yaml` + claim inventory.
- **The email element was removed** (M28) — the app does not email; it downloads
  PDFs + opens apply links. `email_service.send_apply_digest` remains as dormant
  library code; don't wire it back into the app without being asked.
- **Private data** stays in `data/private/` + `.env` (gitignored) — never commit.

## 3. Architecture

- **Desktop shell:** `app_main.py` (pywebview window + headless CLI:
  `--cli`/`--discover`/`--auto`) → `app_api.py` (`JobAppAPI` js_api bridge:
  `get_status`, `list_roles(new|outstanding|applied)`, `run_discovery`,
  `make_artifacts`, `open_artifact`, `mark_applied`) → `app_ui/index.html`
  (single-file HTML/JS UI; tabs New/Outstanding/Applied/Settings; 15s
  auto-refresh + Refresh button).
- **Backend package `application_bot/`:** `pipeline.py` (scan_registry +
  `discover_adzuna` + `discover_jsearch`; 24h `posted_within_hours` filter),
  `scoring.py` (fit score + **off-lane** + **remote-or-DFW geo gate**),
  `resume.py` (ATS résumé), `packets.py` (cover letter / answers),
  `pdf.py` (fpdf2), `database.py` (SQLite CRM; JobStatus incl. APPLIED),
  `config.py`/`config/default.yaml` (tuning).
- **Discovery sources:** `config/live_company_registry.yaml` = **27 enabled** ATS
  boards (Greenhouse/Lever/Ashby; RevOps/martech curated) + Adzuna + JSearch.
- **Packaging:** `make_macos_app.sh` (AppleScript applet), `setup_app.py` (py2app),
  `launchd/com.vadim.jobapply-daily.plist` (daily 8am `--auto` discover).

## 4. Discovery stack + .env keys (live status)

| Source | Status | Notes |
|---|---|---|
| 27 ATS boards | ✅ live | Full JDs, clean scoring |
| Adzuna | ✅ live | `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` set; market breadth (incl. non-SaaS noise, filtered by fit bar) |
| JSearch (LinkedIn/Indeed/Zip via RapidAPI) | ⚠️ key set but wrong sub | `RAPIDAPI_KEY` valid but the subscribed listing lacks `/search` (only `/job-details`). Needs the canonical JSearch (OpenWeb Ninja) free Basic plan. Operator wants to stay free. |

`.env` (gitignored) holds `APPLICATION_BOT_DB=data/private/vadim_pipeline.sqlite`,
the Adzuna keys, `RAPIDAPI_KEY`/`RAPIDAPI_JSEARCH_HOST`, and (unused) SMTP fields.

## 5. Filters (current behavior)

- **24h freshness** on discovery (`posted_within_hours=24`).
- **Geo gate (hard):** exclude only **confirmed** onsite/hybrid-non-DFW roles;
  remote, DFW metroplex (suburbs + Tarrant/Collin/Rockwall/Kaufman counties), and
  unknown-location roles pass. `require_remote_or_dfw` toggles it.
- **Off-lane scorer:** Director/Head titles in off-lane functions (finance, design,
  engineer, legal, recruiter, account-mgmt, exec assistant, …) → NOT_WORTH_TIME.
- **New tab** = fresh + verdict in {APPLY_PRIORITY, GOOD_FIT, MAYBE}. Genuinely
  yields only a few/day (this is correct, not a bug). **Outstanding (~14)** is the
  curated working pile.

## 6. Local private data (gitignored — NOT in the repo)

- `.env` — DB path + API keys (+ unused SMTP).
- `data/private/vadim_pipeline.sqlite` — the live CRM (boards+Adzuna roles, 13–14
  curated Outstanding, applied tracking).
- `data/private/resume_master.yaml` — approved structured résumé + contact PII
  (incl. street address 2116 Houlton Ln, Plano TX 75025; email
  vadimkoenen@proton.me; phone). Used to tailor PDFs.
- `exports/vadim_pipeline/` — generated packets, ATS résumés, PDFs.

## 7. NEXT TASK — redesign the app UX to mirror the 6sense sales dashboard

The operator wants the app's look/feel to **mirror the 6sense (ABM/revenue)
sales dashboard, adapted for a personal job search.** Current UI is a plain
tabbed list (`app_ui/index.html`). Target a dashboard feel:

- **Left sidebar nav** (not top tabs): Dashboard / New (24h) / Pipeline /
  Applied / Analytics / Settings.
- **Top KPI tiles** (6sense-style summary cards): roles discovered (24h),
  Outstanding, Applied, by-source counts, avg fit score.
- **Pipeline/funnel view** mirroring 6sense buying stages → job stages:
  **New → Outstanding → Applied → Responded/Interview** (the DB has APPLIED;
  may need to add a "responded/interview" status for the funnel).
- **Score badges** like 6sense intent grades (color-coded A/B/C or the 0–100
  fit score with green/amber/grey), sortable/filterable table (by source,
  score, location, recency).
- **Per-role detail panel** (slide-over) with the JD excerpt, fit reasons,
  Apply →, Résumé/Cover PDF, Mark applied — instead of inline action buttons.
- **Analytics**: simple charts (applications over time, by source, fit
  distribution) — keep it dependency-light (inline SVG/Canvas; no heavy JS libs;
  the app is offline pywebview).

Keep it a **single-file `app_ui/index.html`** (inline CSS/JS calling
`window.pywebview.api`), no Node/build step, offline. Reuse the existing
`JobAppAPI` methods; add API methods only as needed (e.g. an analytics summary,
a "responded" status). Ask the operator for a 6sense screenshot/reference if the
layout is ambiguous — don't guess the exact 6sense visuals; infer the dashboard
pattern (sidebar + KPI tiles + funnel + scored table + detail panel) and confirm.

Verification: `./run_app.sh` opens the redesigned window populated from the real
pipeline (point at `data/private/vadim_pipeline.sqlite`); `python3 -m pytest -q`
stays green.

## 8. Key commands

```bash
cd "/Users/vadimkoenen/Documents/Application Agent"
python3 -m pytest -q                                  # 148 tests
./run_app.sh                                          # desktop window
./run_app.sh --cli                                    # headless status + outstanding
./run_app.sh --discover --hours 24                    # live scan (boards+Adzuna; JSearch when fixed)
set -a; . ./.env; set +a                              # load keys/DB for manual python
python3 -m application_bot.main scan-adzuna --db data/private/vadim_pipeline.sqlite
python3 -m application_bot.main make-pdf --job-id N --db data/private/vadim_pipeline.sqlite --out exports/vadim_pipeline
./make_macos_app.sh                                   # rebuild dock app
```
