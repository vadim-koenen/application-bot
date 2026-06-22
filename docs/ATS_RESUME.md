# ATS Resume v2 Generator

Produces an ATS-clean, JD-keyword-aligned resume per role. It reshapes a
structured **master resume** of approved content — it never invents claims.
JD keywords not supported by the master are reported as gaps (for your review),
never inserted into the resume.

## Inputs

- `data/private/resume_master.yaml` — structured approved resume (gitignored;
  holds contact PII). Required fields: `identity`, `contact`, `summary`,
  `skills`, `experience`. Path is configurable via `resume_master`.

## Generate

```bash
# All PACKET_READY roles in the DB:
python3 -m application_bot.main ats-resume --db data/private/vadim_pipeline.sqlite --out exports/vadim_pipeline

# One specific role:
python3 -m application_bot.main ats-resume --db <db> --out <out> --job-id 1
```

Each role yields two files under `exports/<...>/ats_resumes/<date>/`:

- `<company>_<title>.md` — review copy (with a per-role "Relevant to This Role"
  line and a "JD Keywords Not Supported" gap list).
- `<company>_<title>.txt` — plain, single-column, standard-header text for
  pasting into ATS forms.

## How tailoring works (and its limits)

- **Core Competencies** are reordered so JD-relevant approved skills lead.
- **Keyword alignment** counts a JD term as matched if the master contains it
  *or* an equivalent phrasing (e.g. JD "go-to-market" ↔ resume "GTM",
  "marketing technology" ↔ "MarTech", "revenue operations" ↔ "RevOps").
- **True gaps** are JD terms with no support in the master. They are listed for
  your review and never added — adding evidence is your decision.

The generator changes ordering, emphasis, and format only. All experience,
metrics, education, and certifications come verbatim from the master resume.
