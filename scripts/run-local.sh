#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
app_host="127.0.0.1"
app_port="8000"
app_url="http://${app_host}:${app_port}"
server_pid=""
health_python="${project_root}/.venv/bin/python"

cleanup() {
    exit_code=$?
    trap - EXIT INT TERM HUP
    if [ -n "$server_pid" ] && kill -0 "$server_pid" 2>/dev/null; then
        kill -TERM "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
    fi
    exit "$exit_code"
}

health_status="unavailable"

is_ready() {
    health_response=$(curl -fsS "${app_url}/health" 2>/dev/null) || return 1

    # HTTP success alone is insufficient: the app can intentionally report an
    # unavailable Codex account while returning a useful JSON health response.
    if health_status=$(printf '%s' "$health_response" | "$health_python" -c '
import json
import re
import sys

try:
    health = json.load(sys.stdin)
    status = health.get("status", "unknown")
    if not isinstance(status, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", status):
        status = "unknown"
    print(status)
    sys.exit(0 if health.get("ready") is True else 1)
except (AttributeError, json.JSONDecodeError, TypeError, ValueError):
    print("unavailable")
    sys.exit(1)
'); then
        return 0
    fi

    return 1
}

trap cleanup EXIT INT TERM HUP

cd "$project_root"
if [ ! -x "$health_python" ]; then
    echo "Project environment is missing. Run: uv sync --locked --python 3.12" >&2
    exit 1
fi

uv run --locked uvicorn app.main:app \
    --host "$app_host" \
    --port "$app_port" \
    --log-level warning \
    --no-access-log &
server_pid=$!

attempt=0
while [ "$attempt" -lt 120 ]; do
    if is_ready; then
        break
    fi
    if ! kill -0 "$server_pid" 2>/dev/null; then
        wait "$server_pid"
        exit $?
    fi
    attempt=$((attempt + 1))
    sleep 0.25
done

if [ "$attempt" -ge 120 ]; then
    if [ -n "$server_pid" ] && kill -0 "$server_pid" 2>/dev/null; then
        kill -TERM "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
    fi
    server_pid=""
    echo "Local chat did not become ready at ${app_url}/health (status: ${health_status}). Server stopped; check the local app logs and retry." >&2
    exit 1
fi

open "$app_url"
wait "$server_pid"
