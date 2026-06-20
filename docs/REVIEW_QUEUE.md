# Review Queue

The review queue prevents silence between scoring and packet generation. Every
scored job exposes company, title, score, verdict, submission policy, packet
status, claim gaps, apply URL, recommended action, and reason codes.

## Packet statuses

- `PACKET_READY`: target fit and approved claims support a claim-safe packet.
- `REVIEW_PACKET_CLAIM_GAPS`: a packet is exported, but listed gaps or fit questions require review.
- `NOT_WORTH_PACKET`: no packet is exported; reason codes explain why.
- `BLOCKED`: compliance or submission policy prevents progression.

## Commands

```bash
python3 -m application_bot.main source-report --db data/application_bot.sqlite
python3 -m application_bot.main review-queue --db data/application_bot.sqlite --out exports/review
python3 -m application_bot.main export-review-csv --db data/application_bot.sqlite --out exports/review.csv
```

Review ready packets first, then claim-gap packets. A review packet is not
permission to answer an unsupported question. No-packet rows remain visible so
source selection and thresholds can be tuned from evidence.

Generate a filterable static dashboard with:

```bash
python3 -m application_bot.main export-review-html \
  --db data/application_bot.sqlite \
  --out exports/review.html
```
