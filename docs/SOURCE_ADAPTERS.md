# Source Adapters

Every adapter implements:

- `source_name`
- `supports_submission`
- `submission_mode`
- `discover_jobs()`
- `normalize_job()`

## Working adapters

### `manual_json`

Reads a list or `{"jobs": [...]}` object from local JSON, or rows from a CSV
file. It is the import path for manually discovered roles and test fixtures.

### `greenhouse`

Uses the public Job Board endpoint:

```text
https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
```

Discovery only by default.

The normalizer reads the documented `departments` collection and safely
decodes HTML-entity-encoded job descriptions.

### `lever`

Uses the public postings endpoint:

```text
https://api.lever.co/v0/postings/{site}?mode=json
```

Discovery only by default.

When present, the documented `salaryRange` object is normalized into the CRM
salary fields.

### `ashby`

Uses the public job-board endpoint:

```text
https://api.ashbyhq.com/posting-api/job-board/{board_name}
```

Discovery only by default.

Discovery requests `includeCompensation=true`; annual salary summary components
are normalized into the CRM salary fields when Ashby publishes them.

### `email_to_apply`

Imports job data like the manual adapter and exposes an SMTP send method. The method returns a dry-run result unless live mode is explicitly passed. Live sending also requires a recipient and all SMTP variables.

### `linkedin_review_queue`

Accepts user-provided content or connector-fed JSON, marks it for review, and never scrapes or clicks LinkedIn.

### `indeed_connector` and `zip_connector`

Accept connector-fed or user-supplied content only. Direct automation is blocked; no scraping implementation exists.

## Registry scans

`config/company_registry.yaml` stores company-specific public board identifiers. Only entries with `enabled: true` and a matching `ats` are scanned. Sample entries are disabled and are not expected to represent real companies.

## Adding an adapter

Normalize every required `Job` field, preserve the raw JSON, keep network transport injectable, add mocked normalization tests, and define a conservative policy default. Discovery support does not imply submission support.
