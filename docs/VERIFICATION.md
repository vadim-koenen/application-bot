# Verification

All automated tests are offline. ATS responses are injected as mocked JSON; no external credentials or live network calls are needed.

## Required verification

```bash
python3 -m pytest -q
python3 -m application_bot.main --help
python3 -m application_bot.main init-db --db /tmp/application_bot_ops.sqlite
python3 -m application_bot.main run-dry-pipeline --registry config/live_company_registry.yaml --db /tmp/application_bot_ops.sqlite --out /tmp/application_bot_ops_exports --limit 25
python3 -m application_bot.main queue-email-applications --db /tmp/application_bot_ops.sqlite
python3 -m application_bot.main send-email-applications --db /tmp/application_bot_ops.sqlite --dry-run
python3 -m application_bot.main daily-report --db /tmp/application_bot_ops.sqlite --out /tmp/application_bot_ops_report
python3 -m application_bot.main report --db /tmp/application_bot_ops.sqlite
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

## Safe test cleanup

Verification uses `/tmp/application_bot_ops.sqlite`,
`/tmp/application_bot_ops_exports`, and `/tmp/application_bot_ops_report.*`.
Removing those test artifacts does not affect the repository or configured CRM.
