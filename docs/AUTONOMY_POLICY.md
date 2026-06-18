# Autonomy Policy

## Default posture

`dry_run: true` and `LIVE_APPLY_ENABLED=false` are the defaults. Discovery, scoring, CRM updates, and packet generation may run autonomously. External application submission may not.

## Decisions

- `AUTO_SUBMIT_ALLOWED`: an explicitly submit-capable ATS adapter has credentials, known required questions, live mode, and no review trigger.
- `AUTO_SUBMIT_EMAIL`: a real recipient, live mode, and complete SMTP configuration are present.
- `AUTO_PACKET_ONLY`: the bot may prepare artifacts but not submit.
- `REVIEW_REQUIRED`: a human must resolve ambiguity or provide an answer.
- `BLOCKED`: the requested automation is prohibited.

## Source defaults

| Source | Default |
|---|---|
| Greenhouse public board | `AUTO_PACKET_ONLY` |
| Lever public postings | `AUTO_PACKET_ONLY` |
| Ashby public job board | `AUTO_PACKET_ONLY` |
| Manual JSON | `AUTO_PACKET_ONLY` |
| Email to apply | `AUTO_PACKET_ONLY` until explicitly live and configured |
| LinkedIn review queue | `REVIEW_REQUIRED` |
| Indeed connector | `BLOCKED` for direct automation |
| ZipRecruiter connector | `BLOCKED` for direct automation |

## Mandatory human review

CAPTCHA, login requirements, unknown legal attestations, unknown required questions, ambiguous consent, and unverified work-authorization or compensation answers require review.

## Absolute no-go boundaries

No LinkedIn scraper or click-bot. No direct Indeed or ZipRecruiter scraping. No CAPTCHA/login/rate-limit/bot-detection bypass. No stealth browser evasion, proxy rotation, cookie harvesting, credential scraping, or session-protection bypass. No fabricated application facts.

The bot may retain a blocked opportunity for audit or manual consideration, but blocked status never becomes submission permission.
