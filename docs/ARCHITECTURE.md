# Architecture

## Design goals

Application Bot is local-first, auditable, dry-run by default, and deliberately separates opportunity quality from automation authority.

```text
Permitted sources / user imports
              |
       Source adapters
              |
       normalized Job model
              |
     deduplicating SQLite CRM
          /           \
   scoring engine   policy engine
          \           /
        packet generator
              |
    Markdown + JSON exports
```

## Package map

- `application_bot.models`: normalized data classes and enums.
- `application_bot.adapters`: source interface and concrete adapters.
- `application_bot.database`: SQLite schema and CRM operations.
- `application_bot.scoring`: deterministic 0–100 fit scoring.
- `application_bot.policy`: submission authority and review/block decisions.
- `application_bot.compliance`: prohibited capabilities and review triggers.
- `application_bot.packets`: truthful-profile packet drafting and Markdown export.
- `application_bot.pipeline`: resilient ATS scans and complete dry-run orchestration.
- `application_bot.email_service`: persistent queue, previews, and live-send gates.
- `application_bot.confirmations`: Gmail-ready interface and fixture parser.
- `application_bot.reporting`: Markdown and JSON daily operations reports.
- `application_bot.scheduler`: disabled-by-default run-once scheduling entry point.
- `application_bot.main`: CLI orchestration.
- `application_bot.config`: YAML defaults and environment overrides.

## Data flow

1. `scan` selects an adapter.
2. The adapter discovers or imports raw jobs and normalizes every result to `Job`.
3. SQLite calculates uniqueness from normalized company, title, location, apply URL, and content hash.
4. `score` writes score, verdict, dimensions, reasons, and flags.
5. `policy-check` evaluates source and form-risk conditions independently.
6. `export-packets` exports eligible scored jobs and records the packet event.
7. Email opportunities enter a persistent queue and generate `.eml` previews.
8. Daily reports summarize operational and safety state.
9. `mark-applied` records a confirmed application; it never performs the external submission.

## Network boundaries

Only Greenhouse, Lever, and Ashby discovery adapters perform HTTP calls. Their transport is injectable, allowing all tests to remain offline. Manual and review-queue adapters read local JSON. Email delivery is isolated behind an explicit method that checks live mode and SMTP configuration before opening a connection.

## Extension points

New sources implement `SourceAdapter.discover_jobs()` and `SourceAdapter.normalize_job()`. Any future submit-capable adapter must still pass the central policy engine and must explicitly prove credentials, known required questions, live mode, and absence of review triggers.
