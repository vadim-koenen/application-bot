# Application Bot

Application Bot is a compliance-first, Git-backed job discovery and application workflow for Vadim Koenen. It discovers roles from permitted public ATS APIs or user-supplied files, normalizes and deduplicates them into a SQLite CRM, scores fit, evaluates a separate submission policy, and exports tailored Markdown application packets.

The default runtime is dry-run. Public ATS adapters never gain submit authority merely because they can discover a job.

## What it does

- Discovers jobs from Greenhouse, Lever, and Ashby public job-board APIs.
- Imports jobs from JSON or CSV, including connector-fed review queues.
- Scores roles against executive growth, demand generation, revenue systems, GTM systems, marketing operations, and AI-enabled transformation targets.
- Penalizes junior roles, pure sales roles, low salary ranges, onsite-only work, and Workday friction.
- Creates a local SQLite CRM with jobs, companies, packets, applications, events, confirmations, and source-run history.
- Produces Markdown application packets and JSON reports.
- Provides an explicitly configured email-to-apply extension point.

## What it does not do

- Scrape or auto-click LinkedIn.
- Scrape Indeed or ZipRecruiter.
- Bypass CAPTCHA, login walls, bot detection, rate limits, consent, or required questions.
- Use proxy rotation, stealth browsing, cookie harvesting, or credential scraping.
- Invent resume claims, legal answers, work authorization, compensation history, degrees, employers, or dates.
- Auto-submit to Greenhouse, Lever, or Ashby by default.

## Quickstart

Python 3.11+ and PyYAML are required. Pytest is needed for development.

```bash
python3 -m application_bot.main init-db --db /tmp/application_bot.sqlite
python3 -m application_bot.main scan \
  --source manual_json \
  --input examples/jobs.example.json \
  --db /tmp/application_bot.sqlite
python3 -m application_bot.main score --db /tmp/application_bot.sqlite
python3 -m application_bot.main export-packets \
  --db /tmp/application_bot.sqlite \
  --out /tmp/application_bot_packets
python3 -m application_bot.main report --db /tmp/application_bot.sqlite
```

The repository also includes an executable `application-bot` wrapper. A normal package installation exposes the same name through `pyproject.toml`:

```bash
python3 -m pip install -e ".[dev]"
application-bot --help
```

## CLI

```text
application-bot init-db [--db PATH]
application-bot scan --source SOURCE [--input FILE] [--company-registry FILE] [--db PATH]
application-bot score [--db PATH]
application-bot export-packets [--db PATH] [--out DIRECTORY]
application-bot report [--db PATH] [--out REPORT.json]
application-bot policy-check --job-id ID [--db PATH]
application-bot mark-applied --job-id ID [--notes TEXT] [--db PATH]
```

ATS scans read enabled companies from `config/company_registry.yaml`. The included companies are deliberately disabled examples; tests use mocked responses.

## Configuration

`config/default.yaml` controls target/reject titles and keywords, location preferences, salary thresholds, source policy, database path, and export path. Environment variables override sensitive or machine-specific settings. Copy `.env.example` into your secret-management workflow; the bot does not automatically read `.env`.

Real external submission remains disabled unless `LIVE_APPLY_ENABLED=true` and the relevant adapter-specific requirements are all satisfied. SMTP credentials are needed for email delivery. Unknown legal or required questions always route to review.

## Compliance model

Fit score and submission authority are independent:

- A high-scoring LinkedIn role remains `REVIEW_REQUIRED`.
- Indeed and ZipRecruiter direct automation remains `BLOCKED`.
- Greenhouse, Lever, and Ashby remain `AUTO_PACKET_ONLY` by default.
- Email remains `AUTO_PACKET_ONLY` unless the live flag, recipient, and SMTP configuration exist.
- CAPTCHA, login, unknown legal attestations, ambiguous consent, and unknown required questions route to review.

See [docs/AUTONOMY_POLICY.md](docs/AUTONOMY_POLICY.md).

## Development

```bash
python3 -m pytest -q
python3 -m compileall -q application_bot tests
```

## Next milestones

1. Connect a verified master resume/claim inventory so packet drafts can include evidence-backed achievements.
2. Add explicit authenticated submit adapters only for APIs whose terms and question schemas permit them.
3. Add a Gmail confirmation connector that writes to the existing `confirmations` table.
4. Add review UI or queue exports for connector-fed LinkedIn, Indeed, and ZipRecruiter opportunities.
5. Add scheduling and observability around source runs without widening submission authority.
