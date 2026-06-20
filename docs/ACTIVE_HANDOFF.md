# Active Handoff

## Repository state

- Base branch: `feature/application-bot-m6-m8-ops`
- Work branch: `feature/application-bot-m9-claim-source-review`
- Base commit: `97db7eb`
- Core build commit: `4b6cff2` (`Build application bot core`)
- Current feature-branch HEAD: run `git rev-parse --short HEAD`; the exact
  completion hash is also reported in the final build report.
- Milestones: M1–M9 claim-safe operational dry-run complete

## Completed

- Python package and named CLI entry point.
- SQLite CRM and deduplication.
- Manual, Greenhouse, Lever, Ashby, email, and connector/review adapters.
- Fit scoring and verdicts.
- Independent submission policy and compliance guards.
- Markdown packet and JSON report export.
- Mocked offline test suite.
- Hardened ATS normalization for Greenhouse departments/encoded HTML and
  Lever/Ashby compensation.
- Correct remote-US versus onsite/unclear-geography scoring.
- Review and blocked CRM states remain intact after scoring and packet export.
- Configuration, sample jobs, and operator documentation.
- Expanded curated ATS registry with six validated public GET sources enabled,
  bounded per-source limits, and additional disabled candidates.
- Resilient multi-source dry pipeline with partial/offline reporting.
- Persistent email queue and `.eml` dry-run previews.
- Independent live-email flags and exact approval-phrase gate.
- Disabled-by-default scheduler command plus launchctl/cron examples.
- Markdown and JSON daily reports.
- Gmail-ready confirmation tracker with imported fixture classification.
- Versioned approved resume claim inventory and claim-gap detection.
- Explicit packet conversion outcomes and no-packet reason codes.
- Measured source-quality reporting and expanded public ATS registry.
- Markdown, JSON, and CSV review queue exports.

## Commands run

```bash
python3 -m pytest -q
python3 -m compileall -q application_bot tests
python3 -m application_bot.main --help
python3 -m application_bot.main init-db --db /tmp/application_bot_m9.sqlite
python3 -m application_bot.main run-dry-pipeline --registry config/live_company_registry.yaml --db /tmp/application_bot_m9.sqlite --out /tmp/application_bot_m9_exports --limit 50
python3 -m application_bot.main source-report --db /tmp/application_bot_m9.sqlite
python3 -m application_bot.main review-queue --db /tmp/application_bot_m9.sqlite --out /tmp/application_bot_m9_review
python3 -m application_bot.main export-review-csv --db /tmp/application_bot_m9.sqlite --out /tmp/application_bot_m9_review.csv
python3 -m application_bot.main daily-report --db /tmp/application_bot_m9.sqlite --out /tmp/application_bot_m9_report
python3 -m application_bot.main report --db /tmp/application_bot_m9.sqlite
PATH="$PWD:$PATH" application-bot --help
```

The verification shell has no `python` alias; `python3` is Python 3.14.5.

## Test result

The latest pre-commit audit passed 72 offline tests. Exact pytest and CLI results are
recorded in the completion report and should be regenerated with the commands
in `docs/VERIFICATION.md` after any change.

## Known gaps

- Exact employment history and metrics remain unapproved and are never inferred.
- No authenticated ATS submission adapter is enabled.
- Gmail parsing works for imported JSON fixtures; no real Gmail API connector is configured.
- The scheduler command runs one dry cycle but no launchctl/cron job is installed.
- The live company registry requires operator review before sources are enabled.
- No review UI is included.

## Next recommended task

Add user-approved evidence-backed employment history and metrics, then tune
source selection from packet-conversion data.

## Exact no-go boundaries

No LinkedIn scraper or click-bot. No direct Indeed or ZipRecruiter scraping. No
CAPTCHA, login, bot-detection, rate-limit, or session-protection bypass. No
proxy rotation, stealth evasion, cookie harvesting, or credential scraping. No
fabricated resume or legal claims. No real email without both live flags,
complete SMTP configuration, exact approval phrase, packet, recipient,
`AUTO_SUBMIT_EMAIL`, and zero unresolved compliance flags.
