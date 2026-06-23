#!/usr/bin/env bash
# Build a lightweight, dockable macOS .app launcher for the Job Apply Assistant.
# This is a thin wrapper bundle (no py2app needed): it just launches run_app.sh,
# which opens the pywebview window. Run it once; then drag the app to your dock.
#
#   ./make_macos_app.sh                 # builds into ~/Applications
#   ./make_macos_app.sh /some/dir       # builds into /some/dir
#
# The bundle hard-codes this repo's path, so rebuild if you move the repo.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-$HOME/Applications}"
APP="$DEST/Job Apply Assistant.app"
MACOS="$APP/Contents/MacOS"

mkdir -p "$MACOS"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Job Apply Assistant</string>
  <key>CFBundleDisplayName</key><string>Job Apply Assistant</string>
  <key>CFBundleIdentifier</key><string>com.vadim.jobapply</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>launch</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

cat > "$MACOS/launch" <<LAUNCH
#!/bin/bash
# Open the Job Apply Assistant window. Logs to /tmp/jobapply-app.log.
exec "$REPO/run_app.sh" >> /tmp/jobapply-app.log 2>&1
LAUNCH
chmod +x "$MACOS/launch"

echo "Built: $APP"
echo "Drag it from $DEST (or Launchpad) onto your dock."
