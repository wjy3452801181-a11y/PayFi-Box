#!/bin/zsh

set -euo pipefail

ROOT_DIR="${1:?root dir required}"
LOG_PATH="${2:?log path required}"
PID_PATH="${3:?pid path required}"
WEB_PORT="${4:-3000}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
WEB_DIR="$ROOT_DIR/apps/web"

cd "$ROOT_DIR"
: > "$LOG_PATH"

"$PYTHON_BIN" - "$ROOT_DIR" "$WEB_DIR" "$LOG_PATH" "$PID_PATH" "$WEB_PORT" <<'PY'
import os
import subprocess
import sys

root_dir, web_dir, log_path, pid_path, web_port = sys.argv[1:6]
log_file = open(log_path, "ab", buffering=0)

proc = subprocess.Popen(
    [os.path.join(root_dir, "node_modules", ".bin", "next"), "start", "--port", web_port],
    cwd=web_dir,
    stdin=subprocess.DEVNULL,
    stdout=log_file,
    stderr=subprocess.STDOUT,
    start_new_session=True,
    close_fds=True,
)

with open(pid_path, "w", encoding="utf-8") as pid_file:
    pid_file.write(str(proc.pid))
PY
