# Autonomy Policy

## Default posture

`dry_run: true`, `LIVE_APPLY_ENABLED=false`, and
`LIVE_EMAIL_SEND_ENABLED=false` are the defaults. Discovery, scoring, CRM
updates, packet generation, email previews, imported confirmation parsing, and
daily reports may run autonomously. External application submission may not.

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

## Email live-send gates

A future email send is blocked unless every condition is true:

1. `live_apply_enabled=true`
2. `LIVE_EMAIL_SEND_ENABLED=true`
3. SMTP host, port, username, password, and from address exist
4. The command approval phrase exactly matches `EMAIL_SEND_APPROVAL_PHRASE`
5. The job has a recipient and saved packet
6. The policy result is `AUTO_SUBMIT_EMAIL`
7. No CAPTCHA, login, legal-attestation, consent, or unknown-question flag exists

Possessing credentials alone never grants send authority.

## Absolute no-go boundaries

No LinkedIn scraper or click-bot. No direct Indeed or ZipRecruiter scraping. No CAPTCHA/login/rate-limit/bot-detection bypass. No stealth browser evasion, proxy rotation, cookie harvesting, credential scraping, or session-protection bypass. No fabricated application facts.

The bot may retain a blocked opportunity for audit or manual consideration, but blocked status never becomes submission permission.
