# Application CRM

SQLite is the default system of record. The database path comes from `config/default.yaml`, `APPLICATION_BOT_DB`, or `--db`.

## Tables

- `companies`: configured company registry entries.
- `jobs`: normalized job data, dedupe key, score, verdict, and lifecycle status.
- `application_packets`: exported packet path and serialized packet.
- `applications`: confirmed application activity.
- `events`: append-oriented job activity such as discovery, scoring, export, and marking applied.
- `confirmations`: reserved for Gmail or other confirmation ingestion.
- `source_runs`: scan status, counts, and failure details.

## Deduplication

The unique key is a SHA-256 hash of normalized:

1. company
2. title
3. location
4. apply URL
5. job content hash

Re-scanning the same canonical opportunity updates source metadata without creating a second CRM row.

## Status lifecycle

Typical local lifecycle:

```text
NEW -> SCORED -> PACKET_EXPORTED -> APPLIED
```

Review-queue adapters may enter as `REVIEW_REQUIRED`. `BLOCKED` is reserved for opportunities that must not proceed through automation.

## Reporting

`application-bot report` returns totals, status counts, verdict counts, packet/application counts, and the top twenty scored jobs. `--out` writes the same report as JSON.
