#!/usr/bin/env bash
# dev-up.sh — Start API (uvicorn) and Web (next dev) for local development.
# Usage (Git Bash on Windows):   bash scripts/dev-up.sh
#
# Assumptions:
#   - Python venv at ./.venv  (Windows layout: .venv/Scripts/python.exe)
#   - Node 20+ on PATH
#   - Run from repo root
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"
NODE_CMD=""
NPM_CMD=""
API_PID=""

port_is_listening() {
  "$ROOT/$PY" -c "import socket,sys; s=socket.socket(); s.settimeout(0.2); sys.exit(0 if s.connect_ex(('127.0.0.1', int(sys.argv[1]))) == 0 else 1)" "$1"
}

resolve_node_commands() {
  if command -v node >/dev/null 2>&1; then
    NODE_CMD="$(command -v node)"
  fi
  if command -v npm >/dev/null 2>&1; then
    NPM_CMD="$(command -v npm)"
  fi
  if [ -n "$NODE_CMD" ] && [ -z "$NPM_CMD" ]; then
    local node_dir
    node_dir="$(cd "$(dirname "$NODE_CMD")" && pwd)"
    if [ -f "$node_dir/npm" ]; then
      NPM_CMD="$node_dir/npm"
    elif [ -f "$node_dir/npm.cmd" ]; then
      NPM_CMD="$node_dir/npm.cmd"
    fi
  fi

  if [ -n "$NODE_CMD" ] && [ -n "$NPM_CMD" ]; then
    return 0
  fi

  local windows_user="${USERNAME:-${USER:-}}"
  local candidate
  for candidate in \
    "/c/Program Files/nodejs" \
    "/mnt/c/Program Files/nodejs" \
    "/c/Program Files (x86)/nodejs" \
    "/mnt/c/Program Files (x86)/nodejs" \
    "/c/Users/$windows_user/AppData/Local/Programs/nodejs" \
    "/mnt/c/Users/$windows_user/AppData/Local/Programs/nodejs"; do
    if [ -x "$candidate/node.exe" ]; then
      NODE_CMD="$candidate/node.exe"
      if [ -f "$candidate/npm" ]; then
        NPM_CMD="$candidate/npm"
      elif [ -f "$candidate/npm.cmd" ]; then
        NPM_CMD="$candidate/npm.cmd"
      fi
      if [ -n "$NPM_CMD" ]; then
        return 0
      fi
    fi
  done

  return 1
}

# Resolve python — prefer Windows-layout venv
if [ -x ".venv/Scripts/python.exe" ]; then
  PY=".venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  echo "!! No .venv found. Create one with:  python -m venv .venv  &&  .venv\\Scripts\\pip install -e apps/api"
  exit 1
fi

resolve_node_commands || { echo "!! node not on PATH"; exit 1; }

echo "== alembic upgrade head =="
(cd apps/api && "$ROOT/$PY" -m alembic upgrade head) || echo "(alembic skipped/failed — continuing)"

if port_is_listening "$API_PORT"; then
  echo "== API already running on :$API_PORT; reusing existing process =="
else
  echo "== starting API on :$API_PORT =="
  (cd apps/api && "$ROOT/$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$API_PORT" --reload) &
  API_PID=$!
  echo "   api pid=$API_PID"
fi

trap 'echo "stopping..."; if [ -n "$API_PID" ]; then kill "$API_PID" 2>/dev/null || true; fi; exit 0' INT TERM

echo "== installing web deps (if needed) =="
(cd apps/web && [ -d node_modules ] || "$NPM_CMD" install --silent)

if port_is_listening "$WEB_PORT"; then
  echo "== web already running on :$WEB_PORT; reusing existing process =="
  if [ -n "$API_PID" ]; then
    wait "$API_PID"
  fi
else
  echo "== starting web on :$WEB_PORT =="
  (cd apps/web && "$NPM_CMD" run dev -- --port "$WEB_PORT")
fi
