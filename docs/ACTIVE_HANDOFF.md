# Active Handoff

## Repository state

- Branch: `feature/application-bot-m1-m5-core`
- Build commit: `Build application bot core` (current feature-branch HEAD; exact hash is reported after commit)
- Milestones: M1–M5 core complete

## Completed

- Python package and named CLI entry point.
- SQLite CRM and deduplication.
- Manual, Greenhouse, Lever, Ashby, email, and connector/review adapters.
- Fit scoring and verdicts.
- Independent submission policy and compliance guards.
- Markdown packet and JSON report export.
- Mocked offline test suite.
- Configuration, sample jobs, and operator documentation.

## Commands run

```bash
python3 -m pytest -q
python3 -m compileall -q application_bot tests
python3 -m application_bot.main init-db --db /tmp/application_bot_test.sqlite
python3 -m application_bot.main scan --source manual_json --input examples/jobs.example.json --db /tmp/application_bot_test.sqlite
python3 -m application_bot.main score --db /tmp/application_bot_test.sqlite
python3 -m application_bot.main export-packets --db /tmp/application_bot_test.sqlite --out /tmp/application_bot_packets
python3 -m application_bot.main report --db /tmp/application_bot_test.sqlite
PATH="$PWD:$PATH" application-bot --help
```

The verification shell has no `python` alias; `python3` is Python 3.14.5.

## Test result

The final exact pytest and CLI results are recorded in the completion report and should be regenerated with the commands in `docs/VERIFICATION.md` after any change.

## Known gaps

- Packet achievements are intentionally generic until a verified resume/claim inventory is connected.
- No authenticated ATS submission adapter is enabled.
- Gmail confirmation ingestion has a schema extension point but no connector implementation.
- No scheduler or review UI is included in the local M1–M5 core.
- Email submission is implemented at adapter level but is not exposed as an unattended bulk-submit CLI command.

## Next recommended task

Build a versioned, user-approved claim inventory from Vadim’s source resume and use it to generate evidence-backed role-specific summaries and achievement bullets.

## Exact no-go boundaries

No LinkedIn scraper or click-bot. No direct Indeed or ZipRecruiter scraping. No CAPTCHA, login, bot-detection, rate-limit, or session-protection bypass. No proxy rotation, stealth evasion, cookie harvesting, or credential scraping. No fabricated resume or legal claims. No real external submission without explicit adapter authority, complete configuration, and `LIVE_APPLY_ENABLED=true`.
