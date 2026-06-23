#!/usr/bin/env bash
# Build a dockable macOS .app launcher for the Job Apply Assistant.
#
# It is an AppleScript applet (compiled with osacompile) — a *real* app bundle
# that Launchpad recognizes and that triggers the macOS "allow access to your
# Documents folder" prompt on first launch. A bare shell-script bundle can't:
# this repo lives under ~/Documents, which macOS protects (TCC), so a plain
# script app gets "Operation not permitted".
#
#   ./make_macos_app.sh                 # builds into ~/Applications
#   ./make_macos_app.sh /some/dir       # builds into /some/dir
#
# First launch will prompt to allow Documents access — click OK. Rebuild if you
# move the repo.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-$HOME/Applications}"
APP="$DEST/Job Apply Assistant.app"

mkdir -p "$DEST"
rm -rf "$APP"

TMP="$(mktemp -d)"
cat > "$TMP/launcher.applescript" <<OSA
set repoRoot to "$REPO"
with timeout of 86400 seconds
	do shell script "cd " & quoted form of repoRoot & " && ./run_app.sh >/tmp/jobapply-app.log 2>&1"
end timeout
OSA

osacompile -o "$APP" "$TMP/launcher.applescript"
rm -rf "$TMP"

echo "Built: $APP"
echo "Drag it from $DEST (or Launchpad) onto your dock."
echo "First launch: click OK on the 'access your Documents folder' prompt."
