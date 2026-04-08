#!/bin/zsh

set -euo pipefail

ROOT_DIR="${1:?root dir required}"
LOG_PATH="${2:?log path required}"
PID_PATH="${3:?pid path required}"
API_PORT="${4:-8000}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$ROOT_DIR"
: > "$LOG_PATH"

"$PYTHON_BIN" - "$ROOT_DIR" "$LOG_PATH" "$PID_PATH" "$API_PORT" <<'PY'
import os
import subprocess
import sys

root_dir, log_path, pid_path, api_port = sys.argv[1:5]
env = os.environ.copy()
env.pop("DATABASE_URL", None)
env["PYTHONPATH"] = "."

log_file = open(log_path, "ab", buffering=0)

proc = subprocess.Popen(
    [
        os.path.join(root_dir, ".venv", "bin", "python"),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        api_port,
    ],
    cwd=os.path.join(root_dir, "apps", "api"),
    env=env,
    stdin=subprocess.DEVNULL,
    stdout=log_file,
    stderr=subprocess.STDOUT,
    start_new_session=True,
    close_fds=True,
)

with open(pid_path, "w", encoding="utf-8") as pid_file:
    pid_file.write(str(proc.pid))
PY
