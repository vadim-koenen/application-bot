# Scheduler

The repository does not install or start a scheduler. The built-in command can
inspect configuration or execute one dry cycle:

```bash
python3 -m application_bot.main scheduler --config config/default.yaml

python3 -m application_bot.main scheduler \
  --config config/default.yaml \
  --run-once \
  --registry config/live_company_registry.yaml \
  --db data/application_bot.sqlite \
  --out exports
```

## macOS launchctl example

Create a user-owned plist only after reviewing paths:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.vadim.application-bot-dry-run</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/env</string>
    <string>python3</string>
    <string>-m</string>
    <string>application_bot.main</string>
    <string>scheduler</string>
    <string>--config</string>
    <string>config/default.yaml</string>
    <string>--run-once</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/absolute/path/to/application-bot</string>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>8</integer></dict>
</dict>
</plist>
```

This file is documentation only and is not installed.

## cron example

```cron
0 8 * * * cd /absolute/path/to/application-bot && /usr/bin/env python3 -m application_bot.main scheduler --config config/default.yaml --run-once >> /tmp/application-bot.log 2>&1
```

Use one scheduler mechanism, keep live flags false, and inspect reports after
each run.
