#!/bin/zsh

set -euo pipefail

ROOT_DIR="${1:?root dir required}"
LOG_PATH="${2:?log path required}"
PID_PATH="${3:?pid path required}"

zsh -lc ": > '$LOG_PATH'; ROOT_DIR='$ROOT_DIR' WEB_LOG='$LOG_PATH' '$ROOT_DIR/scripts/run_web_forever.sh' </dev/null >> '$LOG_PATH' 2>&1 &! echo \$$! > '$PID_PATH'"
