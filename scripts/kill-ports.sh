#!/usr/bin/env bash
# kill-ports.sh — Kill whatever is listening on the dev ports (Windows / Git Bash).
# Usage:  bash scripts/kill-ports.sh           (defaults to 3000 8000)
#         bash scripts/kill-ports.sh 5173 8080
set -u

find_pids() {
  local port="$1"
  if command -v netstat >/dev/null 2>&1; then
    netstat -ano | awk -v p=":$port" '$2 ~ p && $4=="LISTENING" {print $5}' | sort -u
    return 0
  fi

  powershell.exe -NoProfile -Command "Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique" 2>/dev/null \
    | tr -d '\r'
}

PORTS=("$@")
if [ "${#PORTS[@]}" -eq 0 ]; then
  PORTS=(3000 8000)
fi

for PORT in "${PORTS[@]}"; do
  echo "== port $PORT =="
  PIDS=$(find_pids "$PORT")
  if [ -z "$PIDS" ]; then
    echo "   (no listener)"
    continue
  fi
  for PID in $PIDS; do
    echo "   killing pid=$PID"
    # Git Bash needs //F //PID because of MSYS path conversion
    if taskkill //F //PID "$PID" >/dev/null 2>&1; then
      echo "   ok"
    elif powershell.exe -NoProfile -Command "Stop-Process -Id $PID -Force -ErrorAction Stop" >/dev/null 2>&1; then
      echo "   ok (powershell)"
    else
      echo "   could not kill $PID"
    fi
  done
done
