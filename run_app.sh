#!/usr/bin/env bash
# Launch the Job Apply Assistant desktop app from the repo.
#   ./run_app.sh             # opens the app window
#   ./run_app.sh --cli       # headless: status + outstanding roles
#   ./run_app.sh --discover  # live last-24h scan
#   ./run_app.sh --email     # dry-run the apply digest to yourself
set -euo pipefail
cd "$(dirname "$0")"

if [ -x .venv/bin/python3 ]; then
  PY=.venv/bin/python3
else
  PY=python3
fi

# GUI dep (no-op if already installed; the CLI paths work without it).
if [[ "${1:-}" != "--cli" && "${1:-}" != "--discover" && "${1:-}" != "--email" ]]; then
  if ! "$PY" -c "import webview" 2>/dev/null; then
    echo "[run_app] installing pywebview…"
    "$PY" -m pip install --quiet --user --break-system-packages pywebview || \
      echo "[run_app] pip install failed; for the window: $PY -m pip install pywebview"
  fi
fi

exec "$PY" app_main.py "$@"
