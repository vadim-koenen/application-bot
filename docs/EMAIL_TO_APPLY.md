# Email to Apply

Email-to-apply is a packet-backed queue. The safe default generates `.eml`
previews and sends nothing.

## Queue opportunities

Import email opportunities with source `email_to_apply`, score them, and export
packets. Then run:

```bash
python3 -m application_bot.main queue-email-applications \
  --db data/application_bot.sqlite
```

A queued job must have a recipient and a saved `PACKET_READY` packet. Review
packets with unresolved claim gaps are not eligible for email queueing.

`PACKET_READY` still does not authorize email. All live-send gates remain
separate and disabled by default.

`examples/email_jobs.example.json` contains a fake `example.com` recipient for
safe local preview testing.

## Generate previews

```bash
python3 -m application_bot.main send-email-applications \
  --db data/application_bot.sqlite \
  --out exports \
  --dry-run
```

Open the resulting `.eml` files under `exports/email_previews/`. Preview
generation records an event but never creates an application record.

## Future live sending

Live sending is intentionally disabled. It requires:

```text
LIVE_APPLY_ENABLED=true
LIVE_EMAIL_SEND_ENABLED=true
EMAIL_SEND_APPROVAL_PHRASE=<non-empty exact phrase>
SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, FROM_EMAIL
```

The command phrase must exactly match configuration, policy must be
`AUTO_SUBMIT_EMAIL`, recipient and packet must exist, and compliance flags must
be empty. Any failed gate blocks the send. Do not enable these settings without
separate, explicit approval for the specific live operation.

## M15: first email-to-apply manual-review lane

The live ATS registry (`config/live_company_registry.yaml`) is web-form only —
no discovered job has an email-to-apply channel. To prove the lane end to end
without contacting anyone, `examples/email_to_apply_seed.json` ships a
**review-only** seed whose recipient uses the IANA-reserved, non-deliverable
`example.com` domain. Run the full lane against it:

```bash
python3 -m application_bot.main scan --source email_to_apply \
  --input examples/email_to_apply_seed.json --db data/application_bot.sqlite
python3 -m application_bot.main score --db data/application_bot.sqlite
python3 -m application_bot.main export-packets --db data/application_bot.sqlite --out exports/packets
python3 -m application_bot.main queue-email-applications --db data/application_bot.sqlite
python3 -m application_bot.main send-email-applications --db data/application_bot.sqlite --out exports --dry-run
```

`report` then shows `email_ready_manual_review` and `email_previews_generated`.

The two user-confirmed binary answers — work authorization (yes) and visa
sponsorship (not required) — are approved **only** for the `application_answer`
context. They surface in a packet's *Suggested Answers* when a form/email asks,
and never in the proactive cover email/letter body. Compensation and
legal/background-sensitive answers stay locked to manual review.

To send for real, replace the seed with a real posting that has a real apply
email, regenerate the preview, and only then enable the live-send gates above
with the specific approval phrase. A real send is a separate, explicitly
approved operation — never automatic.
