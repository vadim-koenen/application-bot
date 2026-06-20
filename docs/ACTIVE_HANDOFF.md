# Active Handoff

## Repository state

- Base branch: `feature/application-bot-m11-evidence-approval`
- Work branch: `feature/application-bot-m12-tenure-activation`
- Base commit: `fe4ea2b`
- Core build commit: `4b6cff2` (`Build application bot core`)
- Current feature-branch HEAD: run `git rev-parse --short HEAD`; the exact
  completion hash is also reported in the final build report.
- Milestones: M1–M10 complete; M11 and M12 evidence activations measured

## Completed

- Python package and named CLI entry point.
- SQLite CRM and deduplication.
- Manual, Greenhouse, Lever, Ashby, email, and connector/review adapters.
- Fit scoring and verdicts.
- Independent submission policy and compliance guards.
- Markdown packet and JSON report export.
- Mocked offline test suite.
- Hardened ATS normalization for Greenhouse departments/encoded HTML and
  Lever/Ashby compensation.
- Correct remote-US versus onsite/unclear-geography scoring.
- Review and blocked CRM states remain intact after scoring and packet export.
- Configuration, sample jobs, and operator documentation.
- Expanded curated ATS registry with six validated public GET sources enabled,
  bounded per-source limits, and additional disabled candidates.
- Resilient multi-source dry pipeline with partial/offline reporting.
- Persistent email queue and `.eml` dry-run previews.
- Independent live-email flags and exact approval-phrase gate.
- Disabled-by-default scheduler command plus launchctl/cron examples.
- Markdown and JSON daily reports.
- Gmail-ready confirmation tracker with imported fixture classification.
- Versioned approved resume claim inventory and claim-gap detection.
- Explicit packet conversion outcomes and no-packet reason codes.
- Measured source-quality reporting and expanded public ATS registry.
- Markdown, JSON, and CSV review queue exports.
- Structured claim evidence statuses and local approval/rejection/import commands.
- Markdown/JSON approval packs with risk and safe-rewrite guidance.
- Claim-safe reusable answer bank.
- Packet refresh after evidence changes.
- Filterable static HTML review dashboard.
- Exact evidence approvals for metrics, six-person leadership scope, two prior
  roles, approved certifications, approved degrees, and named tools.
- Scope-matched approval resolution so unrelated requirements remain review
  gaps even when a claim category contains some approved evidence.
- Date-backed tenure approval limited to October 2015 through February 2020:
  4+ years across approved marketing-automation, data, analytics, and
  revenue/marketing-systems contexts.

## Commands run

```bash
python3 -m pytest -q
python3 -m compileall -q application_bot tests
python3 -m application_bot.main --help
python3 -m application_bot.main init-db --db /tmp/application_bot_m10.sqlite
python3 -m application_bot.main run-dry-pipeline --registry config/live_company_registry.yaml --db /tmp/application_bot_m10.sqlite --out /tmp/application_bot_m10_exports --limit 50
python3 -m application_bot.main claims list
python3 -m application_bot.main claims gaps --db /tmp/application_bot_m10.sqlite
python3 -m application_bot.main claims export-approval-pack --db /tmp/application_bot_m10.sqlite --out /tmp/application_bot_m10_claims
python3 -m application_bot.main refresh-packets --db /tmp/application_bot_m10.sqlite --out /tmp/application_bot_m10_packets
python3 -m application_bot.main export-review-html --db /tmp/application_bot_m10.sqlite --out /tmp/application_bot_m10_review_html
PATH="$PWD:$PATH" application-bot --help
```

The verification shell has no `python` alias; `python3` is Python 3.14.5.

## Test result

The latest pre-commit audit passed 83 offline tests. Exact pytest and CLI results are
recorded in the completion report and should be regenerated with the commands
in `docs/VERIFICATION.md` after any change.

## Known gaps

- The measured default M10 scan produced zero `PACKET_READY` packets because
  every otherwise suitable packet retained at least one unapproved claim gap.
- The M11 activation pass also produced zero `PACKET_READY` packets: degree
  evidence cleared three matching gap occurrences, while exact tenure remained
  unresolved on all three `GOOD_FIT` jobs.
- The M12 activation approved 4+ years of date-backed tenure but produced zero
  `PACKET_READY` packets. The three `GOOD_FIT` jobs require 8–10+ years in
  business-systems, performance-marketing, or product-leadership contexts.
- Budget ownership remains pending. Approved tenure is limited to the exact
  date-backed 4+ year scope; higher, full-career, KRS, executive, and unrelated
  functional tenure remain scope mismatches. Compensation, work authorization,
  sponsorship, and legal-sensitive answers remain `DO_NOT_USE`.
  Evidence outside the explicitly approved history, metrics, leadership,
  credentials, and tool scope is never inferred.
- No authenticated ATS submission adapter is enabled.
- Gmail parsing works for imported JSON fixtures; no real Gmail API connector is configured.
- The scheduler command runs one dry cycle but no launchctl/cron job is installed.
- The live company registry requires operator review before sources are enabled.
- The review UI is static HTML only; no interactive application actions exist.

## Next recommended task

Review the exported approval pack and add evidence-backed claim decisions,
then refresh packets to convert appropriate jobs to `PACKET_READY`.

## Exact no-go boundaries

No LinkedIn scraper or click-bot. No direct Indeed or ZipRecruiter scraping. No
CAPTCHA, login, bot-detection, rate-limit, or session-protection bypass. No
proxy rotation, stealth evasion, cookie harvesting, or credential scraping. No
fabricated resume or legal claims. No real email without both live flags,
complete SMTP configuration, exact approval phrase, packet, recipient,
`AUTO_SUBMIT_EMAIL`, and zero unresolved compliance flags.
