# Operations

M6–M8 supports a repeatable local dry-run workflow. It does not submit real
applications.

## Daily dry pipeline

```bash
python3 -m application_bot.main run-dry-pipeline \
  --registry config/live_company_registry.yaml \
  --db data/application_bot.sqlite \
  --out exports \
  --limit 25
```

The command initializes SQLite, scans enabled public ATS boards, continues past
individual source failures, deduplicates and scores jobs, evaluates submission
policy, exports packets for `APPLY_PRIORITY` and `GOOD_FIT`, queues email
opportunities, renders email previews, and writes Markdown and JSON reports.
Every scored job receives a packet status and reason codes before reporting.

## Enable or disable sources

Edit only `enabled` in `config/live_company_registry.yaml`:

```yaml
- name: OpenAI
  ats: greenhouse
  board_token: openai
  enabled: true
```

Confirm the public careers URL before enabling a disabled company. Use
`target_relevance`, `notes`, `source_url`, and `scan_limit` to keep expansion
measured.

## Inspect output

- Packets: `exports/packets/YYYY-MM-DD/`
- Email previews: `exports/email_previews/YYYY-MM-DD/`
- Daily reports: `exports/reports/`
- CRM: `data/application_bot.sqlite`

```bash
python3 -m application_bot.main source-report --db data/application_bot.sqlite
python3 -m application_bot.main review-queue --db data/application_bot.sqlite --out exports/review
python3 -m application_bot.main export-review-csv --db data/application_bot.sqlite --out exports/review.csv
```

## Offline and partial runs

Disabling every company produces `real_network_scan=false` and
`network_status=not_attempted`. A failed company records its error and the
pipeline continues. Mixed success produces `network_status=partial`.

## Safety

The pipeline forcibly disables both live flags for its run and reports
`applications_submitted=0`. LinkedIn stays review-only. Indeed and ZipRecruiter
stay connector-only with direct automation blocked.
