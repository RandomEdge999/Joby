#!/usr/bin/env bash
# restart.sh — Free dev ports and bring the stack back up.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bash "$ROOT/scripts/kill-ports.sh" 3000 8000
exec bash "$ROOT/scripts/dev-up.sh"
