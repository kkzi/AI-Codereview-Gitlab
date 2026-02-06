#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

python api.py &
API_PID=$!

python worker.py &
WORKER_PID=$!

trap 'kill "$API_PID" "$WORKER_PID" 2>/dev/null' INT TERM EXIT
wait
