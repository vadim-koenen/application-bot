# Claim Approval Workflow

M9 produced review packets because live postings requested facts absent from
the approved inventory. M10 exports an approval pack and waits for evidence.

```bash
application-bot claims list
application-bot claims gaps --db data/application_bot.sqlite
application-bot claims export-approval-pack \
  --db data/application_bot.sqlite \
  --out exports/claim-approval
```

Each gap includes the job, requested claim, evidence deficiency, safe rewrite,
risk level, and recommended action.

Explicit decisions:

```bash
application-bot claims approve \
  --claim-id years_of_experience \
  --source verified_resume \
  --note "Vadim reviewed the supporting resume evidence."

application-bot claims reject \
  --claim-id certifications \
  --note "No verified certification should be claimed."
```

Approval requires a source and evidence note. High-risk claims are never
auto-approved. Decisions update only the local evidence YAML. Bulk decisions
can be imported from YAML or JSON with `claims import-approvals`.

An approval can include exact `claim_text` and `approval_match_patterns`.
Match patterns limit readiness conversion to posting requirements supported by
that exact evidence; an approved category does not become blanket permission
for unrelated credentials, platforms, metrics, or employment claims.

Refresh after evidence changes:

```bash
application-bot refresh-packets \
  --db data/application_bot.sqlite \
  --out exports/refreshed
```

Suitable jobs become `PACKET_READY` only when required gaps are approved. No
application is submitted.

The default M10 evidence set deliberately produces no ready packets in the
measured scan: every suitable review packet still needs at least one exact
claim approved. This is a safety result, not a pipeline failure.
