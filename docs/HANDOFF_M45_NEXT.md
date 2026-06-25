# Handoff — Job Apply Assistant (resume in a fresh session)

Read this first. It is self-contained for continuing the work. For the original
project/environment basics (repo layout, boundaries, discovery stack), also see
`docs/HANDOFF_NEXT_SESSION.md` (the M1–M38 handoff) — still accurate for
environment, hard boundaries, and the discovery pipeline.

## 0. Environment (unchanged)

- Work in `/Users/vadimkoenen/Documents/Application Agent`. `Bash` resets cwd
  between calls — prefix commands with the path. Python is `python3` (Homebrew,
  no venv); install deps with `python3 -m pip install --user --break-system-packages <pkg>`.
- Repo: https://github.com/vadim-koenen/application-bot (`main` is default).
  Per-milestone branch → PR → `gh pr merge --merge`. End commits with the
  Co-Authored-By trailer.
- Tests: `python3 -m pytest -q` (**184 passing** as of M44).
- Live runs: `set -a; . ./.env; set +a` (run_app.sh sources it automatically).
  Launch the window: `./run_app.sh`. The desktop window runs as "Python"
  (pywebview); on this machine it opens on the secondary display "C32F391".

## 1. What shipped since the M38 handoff (M39–M44, all on `main` except M44)

The app was redesigned into a **6sense-style dashboard** and the apply/cover
flows were heavily reworked. Merged to `main`: M39+M40+M41 (PR #32),
M42 (PR #33), M43 (PR #34). **Open PR #35 = M44** on branch
`feature/application-bot-m44-apply-experience` (not yet merged at handoff time).

- **M39 — 6sense dashboard** (`app_ui/index.html`, single offline file): left
  sidebar nav (Dashboard / New 72h / Pipeline / Applied / Replies / Analytics /
  Settings) with live counts; KPI tiles; pipeline funnel; Hot/Warm/Cold
  ("6QA Temp") segment chips + filter facets; scored account list; slide-over
  detail drawer. Backend: `JobStatus.RESPONDED` + `Database.mark_responded`;
  `JobAppAPI._grade` (Hot ≥80 / Warm 65–79 / Cold 45–64), `dashboard_summary`,
  `job_detail`, `mark_responded`, `_is_new_fit`, enriched `_row`.
- **M40 — stronger cover letters + fixes**: rewrote the cover letter from a
  disclaimer into real prose; `_is_new_fit` excludes APPLIED/RESPONDED (so
  "mark applied" removes a role from New); in-drawer "Saved to Downloads"
  confirmation. Added `claims.text_claim_violations`.
- **M41 — assisted apply + JD-tailored letters**: `start_application` (open the
  company form + save both PDFs + return paste-ready approved answers via the
  M18 submit-free fill plan; NEVER submits). Cover-letter opening clause chosen
  by the JD's emphasized theme; quotes the JD's focus (claim-filtered).
- **M42 — manual "Add this job" capture**: `pipeline.ingest_manual_job` +
  `JobAppAPI.add_job` + top-bar "+ Add job" modal. Paste a role seen anywhere
  (e.g. LinkedIn) → scored + tailored + in pipeline. ToS-clean (no fetch/scrape;
  only pasted text used). Source tagged `manual_add`.
- **M43 — autofill bookmarklet**: `application_bot/apply_helper.py`
  (`build_autofill_spec`, `build_autofill_bookmarklet`) + `apply_autofill_bookmarklet`
  API + Settings card. One saved bookmarklet fills standard ATS text fields
  (name/email/phone/LinkedIn/website/location/company + work-auth/sponsorship
  selects) on an open form. Recurses shadow DOM + same-origin iframes; CANNOT
  reach cross-origin iframes or upload files (browser security) and never ticks
  attestation or submits. Only approved values; REVIEW_REQUIRED dropped.
- **M44 — Claude-drafted cover letters + PDFs download-only** (PR #35):
  `application_bot/cover_letter_llm.py` drafts with Claude (Anthropic SDK,
  lazy-imported, default `claude-opus-4-8`) from the approved profile + JD;
  `validate_cover_letter` is a hard fabrication guard (every number in the
  letter must appear in the approved source text; degree/cert/employer + comp/
  visa/sponsorship rejected). `_cover_letter` prefers the validated draft, falls
  back to the deterministic claim-safe template on no-key/SDK-absent/error/fail.
  `cover_letter_status` + Settings "Cover letters" card show the active mode.
  `open_artifact` now downloads only (no Preview popup; `open_after=False`).

## 2. Cover-letter LLM enablement (operator has done this)

To use Claude drafting: `python3 -m pip install --user --break-system-packages anthropic`
and set `ANTHROPIC_API_KEY` in `.env` (optional `COVER_LETTER_MODEL`, default
`claude-opus-4-8`). The operator added the key during the M44 session. Verify:
Settings → Cover letters shows "✓ Claude drafting active", or
`JobAppAPI().cover_letter_status()` returns `enabled: True`. ~cents/letter;
sends approved profile + JD to Anthropic (the only non-local data path).

## 3. Hard boundaries (unchanged — do not cross)

- **No auto-submit** of applications. Every apply path stops at Submit for the
  human (attestation/login/CAPTCHA are the human's act). The M18 fill plan and
  the bookmarklet both encode this; keep it for the Playwright work below.
- **No fabricated claims** — résumé/cover only from approved
  `data/private/resume_master.yaml` + `config/resume_claim_inventory.yaml`. The
  LLM cover letter is guarded by `validate_cover_letter`.
- **No scraping** LinkedIn/Indeed/Zip. Manual capture uses pasted text only.

## 4. M45 — Playwright auto-attach — BUILT (beta, NOT yet tested live)

Implemented in the M44 session and committed to the same branch (PR #35 now
covers M44 + M45). `application_bot/auto_apply.py`:
- `fill_page(page, spec, resume_pdf, cover_pdf)` — fills text fields, selects
  yes/no answers, and `set_input_files` the résumé/cover into matching file
  inputs. NEVER clicks Submit / ticks attestation (load-bearing, unit-tested
  with a fake page in `tests/test_m45_auto_apply.py`).
- `auto_fill_application(...)` — lazy-imports Playwright, launches **headed**
  chromium in a daemon thread (dodges pywebview's event loop), fills, and leaves
  the browser open until the human closes it. Instructive error if Playwright
  isn't installed.
- `JobAppAPI.auto_apply(job_id)` (web-form roles only) + drawer button
  "Auto-fill in browser (beta)".

**REMAINING for M45 — verify live (could not e2e-test):**
1. Install: `python3 -m pip install --user --break-system-packages playwright`
   then `python3 -m playwright install chromium`.
2. Add a real public ATS role (Greenhouse/Lever/Ashby) via "+ Add job" with its
   real apply URL, open it, click "Auto-fill in browser (beta)", and confirm the
   browser opens, fields fill, and the résumé/cover attach — with NO submit.
3. Tune field/file synonyms in `auto_apply.py` (`_COVER_SYN`, `_RESUME_SYN`,
   and the spec syns in `apply_helper.build_autofill_spec`) per what the real
   form uses. The asyncio-in-pywebview thread approach is untested live — if the
   browser won't launch from the app, that's the first thing to check (consider
   a subprocess instead of a thread).

Honest framing for the operator: Playwright opens a SEPARATE automated browser
(not their logged-in Chrome), so it works best on public ATS forms; login/
CAPTCHA/enterprise-iframe forms still need the human. It's fragile per-ATS.

## 5. Other open threads (lower priority)

- **JSearch coverage** (from the original handoff #7): make the JSearch search
  endpoint path configurable (env, default `/search`) so a free jobs API drops
  in; the operator must subscribe to the free JSearch (OpenWeb Ninja) Basic plan
  and set `RAPIDAPI_KEY`. Code half is small; blocked on the operator's sub.
- **Bookmarklet field-matching**: tested live on a Greenhouse form (27 top-level
  fields, same-origin) — the shadow/iframe `gather` was added for that. Tune
  synonyms in `apply_helper.py` if the operator reports misses on a real form.

## 6. Key commands

```bash
cd "/Users/vadimkoenen/Documents/Application Agent"
python3 -m pytest -q                 # 184 tests
./run_app.sh                         # desktop window (opens on display C32F391)
set -a; . ./.env; set +a             # load keys/DB for manual python
gh pr merge 35 --merge --delete-branch   # merge M44 when ready
```

## 7. Git state at handoff

- `main`: M39–M43 merged.
- Open: PR #35 (M44) on `feature/application-bot-m44-apply-experience`.
- If `application_bot/auto_apply.py` / a `test_m45_*.py` exist uncommitted in the
  working tree, they're the start of M45 — branch off `main` (after merging #35),
  move them over, finish, test, PR.
