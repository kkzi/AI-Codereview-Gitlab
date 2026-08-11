#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# 导出 conf/.env 中的配置，供 gunicorn 绑定端口使用
if [ -f conf/.env ]; then
  set -a
  source conf/.env
  set +a
fi

if command -v gunicorn >/dev/null 2>&1; then
  gunicorn -w "${GUNICORN_WORKERS:-2}" -b "0.0.0.0:${SERVER_PORT:-5001}" api:app &
else
  python api.py &
fi
API_PID=$!

python worker.py &
WORKER_PID=$!

trap 'kill "$API_PID" "$WORKER_PID" 2>/dev/null' INT TERM EXIT
wait
