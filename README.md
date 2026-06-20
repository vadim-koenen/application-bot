# Application Bot

Application Bot is a compliance-first, Git-backed job discovery and application workflow for Vadim Koenen. It discovers roles from permitted public ATS APIs or user-supplied files, normalizes and deduplicates them into a SQLite CRM, scores fit, evaluates a separate submission policy, and exports tailored Markdown application packets.

M6–M9 makes the bot operational as a repeatable local dry-run workflow with
claim-safe packet conversion and an inspectable review queue. The default
runtime still submits zero applications and sends zero email.

## What it does

- Discovers jobs from Greenhouse, Lever, and Ashby public job-board APIs,
  including available department and compensation data.
- Imports jobs from JSON or CSV, including connector-fed review queues.
- Scores roles against executive growth, demand generation, revenue systems, GTM systems, marketing operations, and AI-enabled transformation targets.
- Penalizes junior roles, pure sales roles, low salary ranges, onsite-only work, and Workday friction.
- Creates a local SQLite CRM with jobs, companies, packets, applications, events, confirmations, and source-run history.
- Produces Markdown application packets and JSON reports.
- Queues email-to-apply opportunities and renders inspectable `.eml` previews.
- Classifies imported Gmail-style confirmation fixtures.
- Runs one complete dry pipeline cycle manually or from an external local
  scheduler such as launchctl or cron.
- Grounds packet language in a versioned approved claim inventory.
- Records a packet outcome and reason codes for every scored job.
- Exports review queues as Markdown, JSON, and CSV.

## What it does not do

- Scrape or auto-click LinkedIn.
- Scrape Indeed or ZipRecruiter.
- Bypass CAPTCHA, login walls, bot detection, rate limits, consent, or required questions.
- Use proxy rotation, stealth browsing, cookie harvesting, or credential scraping.
- Invent resume claims, legal answers, work authorization, compensation history, degrees, employers, or dates.
- Auto-submit to Greenhouse, Lever, or Ashby by default.
- Install or start a scheduler automatically.
- Send email merely because SMTP credentials exist.
- Copy unverified requirements into candidate claims.
- Silently discard a scored job without a packet-conversion reason.

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

Run the full operational pipeline:

```bash
python3 -m application_bot.main run-dry-pipeline \
  --registry config/live_company_registry.yaml \
  --db /tmp/application_bot_ops.sqlite \
  --out /tmp/application_bot_ops_exports \
  --limit 25
```

The registry contains measured public GET-only sources across Greenhouse,
Lever, and Ashby. Change only an entry’s `enabled` field to control scans.

Inspect conversion quality:

```bash
python3 -m application_bot.main source-report --db /tmp/application_bot_ops.sqlite
python3 -m application_bot.main review-queue \
  --db /tmp/application_bot_ops.sqlite \
  --out /tmp/application_bot_review
python3 -m application_bot.main export-review-csv \
  --db /tmp/application_bot_ops.sqlite \
  --out /tmp/application_bot_review.csv
```

The repository also includes an executable `application-bot` wrapper. A normal package installation exposes the same name through `pyproject.toml`:

```bash
python3 -m pip install -e ".[dev]"
application-bot --help
```

## CLI

```text
application-bot init-db [--db PATH]
application-bot scan [--source SOURCE] [--input FILE] [--registry FILE] [--dry-run] [--limit N] [--db PATH]
application-bot score [--db PATH]
application-bot export-packets [--db PATH] [--out DIRECTORY]
application-bot run-dry-pipeline --registry FILE [--db PATH] [--out DIRECTORY] [--limit N]
application-bot queue-email-applications [--db PATH]
application-bot send-email-applications [--db PATH] --dry-run [--out DIRECTORY]
application-bot daily-report --db PATH --out PATH
application-bot scheduler --config FILE [--run-once]
application-bot import-confirmations --input FILE [--db PATH]
application-bot source-report [--db PATH]
application-bot review-queue --db PATH --out PATH
application-bot export-review-csv --db PATH --out FILE.csv
application-bot report [--db PATH] [--out REPORT.json]
application-bot policy-check --job-id ID [--db PATH]
application-bot mark-applied --job-id ID [--notes TEXT] [--db PATH]
```

Operational ATS scans read enabled companies from
`config/live_company_registry.yaml`. Enabled identifiers were validated as
public GET endpoints; disabled candidates must be revalidated before use.
Per-source limits and relevance ranking keep scans bounded.

## Claim-safe packets

`config/resume_claim_inventory.yaml` is the only source for candidate
positioning language. Job-posting keywords are used only when already approved
in that inventory. Unsupported candidate facts become claim gaps.

- `PACKET_READY`: target fit and approved claims are sufficient.
- `REVIEW_PACKET_CLAIM_GAPS`: export a review packet; resolve listed gaps first.
- `NOT_WORTH_PACKET`: retain explicit reason codes without generating a packet.
- `BLOCKED`: policy or compliance prevents progression.

## Configuration

`config/default.yaml` controls target/reject titles and keywords, location preferences, salary thresholds, source policy, database path, and export path. Environment variables override sensitive or machine-specific settings. Copy `.env.example` into your secret-management workflow; the bot does not automatically read `.env`.

Real external submission remains disabled. Future email delivery requires all
of `LIVE_APPLY_ENABLED=true`, `LIVE_EMAIL_SEND_ENABLED=true`, complete SMTP
credentials, a recipient and packet, no unresolved compliance flags, an
`AUTO_SUBMIT_EMAIL` policy decision, and an exact configured approval phrase.
Unknown legal or required questions always route to review.

## Compliance model

Fit score and submission authority are independent:

- A high-scoring LinkedIn role remains `REVIEW_REQUIRED`.
- Indeed and ZipRecruiter direct automation remains `BLOCKED`.
- Greenhouse, Lever, and Ashby remain `AUTO_PACKET_ONLY` by default.
- Email remains preview-only unless every independent live-send gate passes.
- CAPTCHA, login, unknown legal attestations, ambiguous consent, and unknown required questions route to review.

See [docs/AUTONOMY_POLICY.md](docs/AUTONOMY_POLICY.md).

## Development

```bash
python3 -m pytest -q
python3 -m compileall -q application_bot tests
```

## Next milestones

1. Obtain user approval for additional experience claims and evidence-backed metrics.
2. Tune source selection from measured conversion results.
3. Connect Gmail read-only confirmation ingestion to the tested tracker interface.
4. Add a local review UI without widening submission authority.

See [docs/OPERATIONS.md](docs/OPERATIONS.md),
[docs/EMAIL_TO_APPLY.md](docs/EMAIL_TO_APPLY.md), and
[docs/SCHEDULER.md](docs/SCHEDULER.md),
[docs/CLAIM_INVENTORY.md](docs/CLAIM_INVENTORY.md), and
[docs/REVIEW_QUEUE.md](docs/REVIEW_QUEUE.md).
