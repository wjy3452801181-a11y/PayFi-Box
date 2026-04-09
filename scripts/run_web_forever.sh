#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="${ROOT_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
LOG_PATH="${WEB_LOG:-/tmp/payfi_web.log}"
RESTART_DELAY="${WEB_RESTART_DELAY:-2}"
WEB_PORT="${WEB_PORT:-3000}"
WEB_DIR="$ROOT_DIR/apps/web"

cd "$ROOT_DIR"

while true; do
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] starting web server" >> "$LOG_PATH"
  (cd "$WEB_DIR" && "$ROOT_DIR/node_modules/.bin/next" start --port "$WEB_PORT") >> "$LOG_PATH" 2>&1 || true
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] web server exited, restarting in ${RESTART_DELAY}s" >> "$LOG_PATH"
  sleep "$RESTART_DELAY"
done
