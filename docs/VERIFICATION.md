# Verification

All automated tests are offline. ATS responses are injected as mocked JSON; no external credentials or live network calls are needed.

## Required verification

```bash
python3 -m pytest -q
python3 -m application_bot.main --help
python3 -m application_bot.main init-db --db /tmp/application_bot_m10.sqlite
python3 -m application_bot.main run-dry-pipeline --registry config/live_company_registry.yaml --db /tmp/application_bot_m10.sqlite --out /tmp/application_bot_m10_exports --limit 50
python3 -m application_bot.main claims list
python3 -m application_bot.main claims gaps --db /tmp/application_bot_m10.sqlite
python3 -m application_bot.main claims export-approval-pack --db /tmp/application_bot_m10.sqlite --out /tmp/application_bot_m10_claims
python3 -m application_bot.main refresh-packets --db /tmp/application_bot_m10.sqlite --out /tmp/application_bot_m10_packets
python3 -m application_bot.main export-review-html --db /tmp/application_bot_m10.sqlite --out /tmp/application_bot_m10_review_html
python3 -m application_bot.main export-review-csv --db /tmp/application_bot_m10.sqlite --out /tmp/application_bot_m10_review.csv
python3 -m application_bot.main daily-report --db /tmp/application_bot_m10.sqlite --out /tmp/application_bot_m10_report
python3 -m application_bot.main report --db /tmp/application_bot_m10.sqlite
PATH="$PWD:$PATH" application-bot --help
```

This repository was verified in a shell that provides `python3` but no `python`
alias. If your environment maps `python` to Python 3.11+, either spelling works.

## Coverage focus

- Target and reject seniority.
- Remote versus onsite location.
- Function fit and pure-sales mismatch.
- Salary and Workday friction.
- Greenhouse, Lever, and Ashby normalization.
- Canonical deduplication.
- Markdown packet export.
- End-to-end CLI flow.
- Email live-mode preconditions.
- LinkedIn review routing.
- Indeed and ZipRecruiter automation blocking.
- CAPTCHA, login, legal-question, and evasion safeguards.
- Mocked Greenhouse, Lever, and Ashby operational pipelines.
- Graceful failed/partial network source runs.
- Email queue, previews, live flags, and approval phrase.
- Scheduler run-once and daily report generation.
- Gmail fixture classification.
- Claim inventory loading and prohibited-claim guards.
- Ready/review/no-packet conversion outcomes.
- Realistic senior, manager, sales, onsite, and Workday fixtures.
- Source quality, review queue, and CSV exports.
- Configurable packet thresholds.
- Evidence approval, rejection, and imported decisions.
- Pending/rejected/DO_NOT_USE exclusion from packet text.
- Approval-pack export, packet refresh, and static HTML review.
- Answer-bank safeguards for sensitive questions.

## Safe test cleanup

Verification uses `/tmp/application_bot_m10.sqlite`,
`/tmp/application_bot_m10_exports`, and `/tmp/application_bot_m10_report.*`.
Removing those test artifacts does not affect the repository or configured CRM.
