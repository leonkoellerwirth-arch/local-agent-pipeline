#!/usr/bin/env bash
#
# Launch the Audit Console: the Python audit API + the Vite dashboard.
#
#   web/start.sh              start both; open the browser
#   web/start.sh --no-open    don't open a browser
#   web/start.sh --free-port  stop whatever holds the ports first (opt-in)
#   web/start.sh -h|--help    show this help
#
# No Docker, no framework — the API is stdlib Python (web/api_server.py) run
# through the project's .venv, and Vite proxies /api to it. Ctrl-C stops both.

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$APP_DIR/.." && pwd)"
API_PORT="${API_PORT:-18082}"
FE_PORT="${FE_PORT:-5173}"
OPEN=1
FREE_PORT=0

for arg in "$@"; do
  case "$arg" in
    --no-open) OPEN=0 ;;
    --free-port) FREE_PORT=1 ;;
    -h|--help) sed -n '3,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

VENV_PY="$ROOT_DIR/.venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  echo "No .venv found. Run ./setup.sh in the repo root first." >&2
  exit 1
fi

# Shared session token: the API requires it and the Vite proxy forwards it, so
# the browser never sees it and other local processes can't drive the API.
# Override by exporting API_TOKEN yourself.
export API_TOKEN="${API_TOKEN:-$("$VENV_PY" -c 'import secrets; print(secrets.token_urlsafe(24))')}"

# Never kill a process we didn't start. If a port is taken, say so and stop —
# unless the user explicitly opted in with --free-port.
ensure_port_free() {
  local port="$1" name="$2" pids
  command -v lsof >/dev/null 2>&1 || return 0   # can't check; let the bind fail instead
  pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
  [ -z "$pids" ] && return 0
  if [ "$FREE_PORT" = 1 ]; then
    echo "Freeing $name port $port (PID(s): $pids) — you passed --free-port."
    kill $pids 2>/dev/null || true
    sleep 1
    return 0
  fi
  {
    echo "Port $port ($name) is already in use by PID(s): $pids."
    echo "Refusing to kill a process this script didn't start. Either:"
    echo "  - stop it yourself, or"
    echo "  - re-run with --free-port to have this script stop it, or"
    echo "  - set ${name}_PORT to a free port."
  } >&2
  exit 1
}

ensure_port_free "$API_PORT" API
ensure_port_free "$FE_PORT" FE

echo "Starting audit API on :$API_PORT ..."
API_PORT="$API_PORT" "$VENV_PY" "$APP_DIR/api_server.py" &
API_PID=$!

cleanup() { kill "$API_PID" 2>/dev/null || true; [ -n "${FE_PID:-}" ] && kill "$FE_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

# Wait for the API to answer /health.
for _ in $(seq 1 30); do
  curl -sf "http://127.0.0.1:${API_PORT}/health" -o /dev/null 2>/dev/null && break
  sleep 0.3
done

cd "$APP_DIR"
[ -d node_modules ] || { echo "Installing frontend deps..."; npm install; }

OPEN_FLAG=""; [ "$OPEN" = 1 ] && OPEN_FLAG="--open"
echo "Dashboard: http://127.0.0.1:${FE_PORT}  (API on :${API_PORT})"
API_PORT="$API_PORT" npm run dev -- --host 127.0.0.1 --port "$FE_PORT" --strictPort $OPEN_FLAG &
FE_PID=$!
wait "$FE_PID"
