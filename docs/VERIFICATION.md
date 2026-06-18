# Verification

All automated tests are offline. ATS responses are injected as mocked JSON; no external credentials or live network calls are needed.

## Required verification

```bash
python3 -m pytest -q
python3 -m application_bot.main init-db --db /tmp/application_bot_test.sqlite
python3 -m application_bot.main scan --source manual_json --input examples/jobs.example.json --db /tmp/application_bot_test.sqlite
python3 -m application_bot.main score --db /tmp/application_bot_test.sqlite
python3 -m application_bot.main export-packets --db /tmp/application_bot_test.sqlite --out /tmp/application_bot_packets
python3 -m application_bot.main report --db /tmp/application_bot_test.sqlite
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

## Safe test cleanup

Verification uses `/tmp/application_bot_test.sqlite` and `/tmp/application_bot_packets`. Removing those test artifacts does not affect the repository or configured CRM.
