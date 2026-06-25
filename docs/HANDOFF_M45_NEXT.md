# Handoff — Job Apply Assistant (resume in a fresh session)

Self-contained for continuing. For original environment/architecture basics see
`docs/HANDOFF_NEXT_SESSION.md` (M1–M38). This file covers M39–M48.

## 0. Environment

- Work in `/Users/vadimkoenen/Documents/Application Agent`. `Bash` resets cwd —
  prefix commands with the path. Python `python3` (no venv); install with
  `python3 -m pip install --user --break-system-packages <pkg>`.
- Repo https://github.com/vadim-koenen/application-bot (`main` default).
  Per-milestone branch → PR → `gh pr merge --merge`. Co-Authored-By trailer.
- Tests: `python3 -m pytest -q` — **202 passing** (as of M48).
- Live: `set -a; . ./.env; set +a`. Window: `./run_app.sh` (runs as "Python";
  opens on secondary display "C32F391" on this machine). Optional deps now
  installed by operator: **anthropic** (cover letters), **playwright** +
  chromium (auto-apply).

## 1. What's on `main` (M39–M48)

- **M39** 6sense dashboard (`app_ui/index.html`): sidebar nav, KPI tiles,
  funnel, Hot/Warm/Cold chips + filters, scored list, slide-over drawer.
  `JobStatus.RESPONDED`, `dashboard_summary`, `job_detail`, `mark_responded`,
  `_grade`, `_is_new_fit`.
- **M40** real cover-letter prose; `_is_new_fit` excludes APPLIED/RESPONDED;
  in-drawer "Saved to Downloads"; `claims.text_claim_violations`.
- **M41** `start_application` (open form + save both PDFs + paste-ready answers
  via M18 submit-free fill plan; never submits). JD-theme-tailored cover.
- **M42** manual capture: `pipeline.ingest_manual_job` + `JobAppAPI.add_job` +
  "+ Add job" modal. Paste a role → scored/tailored/in pipeline. Source
  `manual_add`. ToS-clean (no fetch).
- **M43** autofill bookmarklet: `apply_helper.build_autofill_spec/_bookmarklet`
  + Settings card. Fills standard fields across shadow DOM + same-origin
  iframes; can't do cross-origin iframes or file upload; never submits.
- **M44** Claude cover letters: `cover_letter_llm.draft_cover_letter_llm` +
  `validate_cover_letter` (fabrication guard: every number must be in the
  approved source; degree/cert/employer/comp/visa rejected). `_cover_letter`
  prefers the validated draft, falls back to the template. `cover_letter_status`
  + Settings card. `open_artifact` downloads only (no Preview).
- **M45** Playwright auto-attach (beta): `auto_apply.fill_page` fills text +
  selects + **attaches résumé/cover** across **all frames** (incl. cross-origin
  iframes); `auto_fill_application` launches headed chromium in a daemon thread,
  leaves it open, never submits. `JobAppAPI.auto_apply` + drawer "Auto-fill in
  browser (beta)". **Verified live** on a real Greenhouse form (filled 7 fields
  + attached both PDFs).
- **M46** pipeline integrity: stable `Job.dedupe_key` (company+title+apply_url —
  no more duplicate rows / resurrected applied roles); off-lane adds
  "business partner" + "chief of staff" (config.py AND config/default.yaml).
  The live DB was de-duplicated + re-scored in-session (applied statuses kept).
- **M47** `auto_apply.reveal_form`: on a JD page (no form), clicks an "Apply"
  control to reveal the form before filling. Never clicks Submit.
- **M48** configurable JSearch endpoint: `JSearchAdapter(search_url=...)`;
  `discover_jsearch` builds it from `RAPIDAPI_JSEARCH_URL`, or
  `RAPIDAPI_JSEARCH_HOST`+`RAPIDAPI_JSEARCH_PATH` (default `/search`). Any free
  RapidAPI jobs API can be pointed in without code.

## 2. Apply flow — three paths (operator-facing; document clearly)

1. **Start application** — opens the form URL + saves both PDFs to Downloads.
   Does NOT fill. (Recruiter-routed roles → "Prepare application": downloads +
   shows paste answers, no browser.)
2. **Auto-fill in browser (beta)** — launches a SEPARATE chromium, fills +
   attaches the résumé/cover, stops at Submit. The automatic path. Look for the
   second browser window (may be on the other display).
3. **Bookmarklet** (Settings → Copy) — fills the tab in the operator's own
   logged-in Chrome; they attach the résumé themselves.

## 3. Hard boundaries (unchanged)

No auto-submit (every path stops at Submit; the M45/M47 driver only fills/
selects/attaches/clicks-Apply — there is no submit path, asserted by tests). No
fabricated claims (cover-letter guard + claim inventory). No scraping.

## 4. Operator unlocks (gate the remaining big wins)

- **API credits** — key is in `.env` and valid, but the Anthropic *account
  balance is $0*, so Claude cover letters fall back to the template. Add credits
  at console.anthropic.com → Plans & Billing (~cents/letter). This also gates
  the LLM screening-answers idea (§5).
- **JSearch** — code is ready (M48). Operator subscribes to the free JSearch
  (OpenWeb Ninja) Basic plan on RapidAPI, sets `RAPIDAPI_KEY` in `.env`
  (optionally `RAPIDAPI_JSEARCH_URL/HOST/PATH`), then discovery pulls
  LinkedIn/Indeed/Zip via Google-for-Jobs.

## 5. NEXT opportunities (operator's prioritized list; #1/#2 already done)

- **LLM screening-question answers** (needs credits) — draft per-role essay/
  screening answers from the approved profile, claim-filtered like the cover
  letter, for human review. Reuse `cover_letter_llm` patterns + the guard.
- **Cover-letter text box fill** — some forms have a "Cover letter" *textarea*
  (paste) not a file input; have the auto-apply driver fill it with the letter.
- **Follow-up / interview tracking** — RESPONDED stage exists but there's no
  notes/next-action/reminder field. Make it a real pipeline CRM.
- **"Clean pipeline" button** — expose the re-score + dedup maintenance
  (done by hand in M46) as an in-app action.

## 6. Commands

```bash
cd "/Users/vadimkoenen/Documents/Application Agent"
python3 -m pytest -q                 # 202 tests
./run_app.sh                         # window (display C32F391)
set -a; . ./.env; set +a
```

## 7. Git state at handoff

`main` has M39–M47. **M48 is on `feature/application-bot-m48-jsearch-config`**
(PR open / being merged at handoff). Confirm with `gh pr list` and
`git log --oneline -3`. Housekeeping: `data/private/*.bak` (DB + .env backups
from M46/M44 cleanups) can be deleted once the operator is satisfied.
