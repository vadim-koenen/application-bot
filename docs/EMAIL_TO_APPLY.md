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

A queued job must have a recipient and saved packet.

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
