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
pattern. Pipeline: **discover (last 72h) → score → tailor ATS résumé + cover
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
  `discover_adzuna` + `discover_jsearch`; `posted_within_hours` 72h filter),
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

- **72h freshness** on discovery (config `discovery_window_hours: 72`,
  `JobAppAPI.window_hours`; was 24h). New tab now shows ~8 vs ~2.
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

## 7. PRIORITY NEXT TASK — close the discovery coverage gap

**The operator saw a "perfect" job on LinkedIn that the app did NOT capture.**
This is the #1 problem to solve. Root cause: discovery = 27 ATS boards (only
those companies) + Adzuna (broad but misses/laggy on LinkedIn) — and **JSearch
(the one that indexes LinkedIn/Indeed/ZipRecruiter via Google-for-Jobs) is not
working** because the operator's RapidAPI subscription lacks the `/search`
endpoint (only `/job-details`). So LinkedIn-posted roles, and roles at companies
not in the registry, slip through.

Fix paths (do these next, in order):
1. **Get JSearch working** — the clean way to catch LinkedIn/Indeed/Zip. The
   operator wants to **stay on a free tier** (fine: canonical JSearch by OpenWeb
   Ninja has a free Basic plan WITH `/search`). Action: confirm the operator
   subscribed to that listing, put the key in `.env` `RAPIDAPI_KEY=`, then
   `scan-jsearch` should return jobs. The adapter (`adapters/jsearch.py`) + wiring
   are built and tested — only the subscription/key is the blocker.
   - Make the JSearch **search endpoint path configurable** (env, default
     `/search`) so a different RapidAPI jobs API can be pointed in without code.
2. **One-off capture** — add an "Add this job" path so when the operator sees a
   role anywhere (LinkedIn etc.), they paste the URL/title/company and it's
   ingested (reuse the review-queue adapters; ToS-clean since human-initiated).
   Fetching arbitrary LinkedIn/Indeed URLs server-side is scraping — don't; have
   the operator paste the job details, or fetch only ATS/company-site URLs.
3. **Grow the registry** — add boards of companies the operator targets.

Honest framing for the operator: the only legitimate way to catch arbitrary
LinkedIn jobs is an aggregator API (JSearch); we do not scrape LinkedIn.

## 8. SECONDARY (optional) — 6sense-style dashboard redesign

The operator likes the **6sense sales dashboard** UX and said "configure if you
think it makes sense; if it overcomplicates, disregard." Use judgment — do it
only after coverage is solid, and keep it simple. Reference screenshot the
operator shared (6sense "Dashboards › CRM Accounts"):
- **Left sidebar filters**: Filter List / Saved filters; a **CRM** group (User
  type, Account type, Latest opportunity status, Salesforce fields) and a
  **6sense company info** group (**Temperature, Buying stage, Reach**).
- **Segment chips** across the top with counts: **Hot New (0) · Hot (1) ·
  Warm (13) · Cold (29)**.
- **Account list**: avatar + name + country, a **6QA Temp** column (a colored
  **W/Warm** badge), and a **Sales Activities** column (e.g. "47 · ✉ · 1 day ago").

Adapt to the job search (don't copy literally):
- Sidebar filters → Source (boards/Adzuna/JSearch), Score/fit grade, Location
  (remote/DFW), Recency.
- **Temperature → fit grade**: Hot/Warm/Cold from the 0–100 score (e.g. ≥80 Hot,
  65–79 Warm, 45–64 Cold) as colored badges (the 6QA-Temp equivalent).
- **Buying stage → pipeline stage**: New → Outstanding → Applied → Responded.
- Segment chips → counts per stage/grade. List → role + company + fit badge +
  posted-recency + source, with a slide-over detail panel (JD, fit reasons,
  Apply →, Résumé/Cover PDF, Mark applied).
- Keep it a single offline `app_ui/index.html` (inline CSS/JS; no Node/libs);
  reuse `JobAppAPI`, add methods only as needed (e.g. analytics summary, a
  "responded" status). The full original next-task spec is below.

### (original 6sense redesign spec)

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

## 9. Key commands

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
