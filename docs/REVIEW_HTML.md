# Static Review HTML

Generate a local dashboard:

```bash
application-bot export-review-html \
  --db data/application_bot.sqlite \
  --out exports/review.html
```

The standalone HTML contains summary cards, job and claim-gap tables, packet
links, apply links, and filters for verdict, packet status, source, and
company. It uses no JavaScript framework and requires no server or credentials.

The HTML is a review surface only. It contains no submit or email action.
