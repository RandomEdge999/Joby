#!/usr/bin/env bash
# Joby one-shot installer for macOS / Linux / WSL / Git Bash on Windows.
#
# Usage:  bash install.sh        (or `./install.sh` after chmod +x)
#
# What it does:
#   1. Verifies Python 3.12+ and (optionally) Node 20+.
#   2. Creates a local .venv if one isn't already active.
#   3. Installs the `joby` console script (apps/api) in editable mode.
#   4. Runs `joby install` to apply DB migrations, seed data, and
#      npm install for the web UI.
#
# Never blocks on optional failures: network hiccups during H-1B refresh
# or missing Node only print a warning; the core API still works.

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

say() { printf "\033[1;34m[install]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[install]\033[0m %s\n" "$*"; }

IS_WINDOWS_BASH=0
case "$(uname -s 2>/dev/null || echo '')" in
    MINGW*|MSYS*|CYGWIN*) IS_WINDOWS_BASH=1 ;;
esac

python_ok() {
    exe="$1"
    shift
    v=$("$exe" "$@" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo "")
    case "$v" in
        3.1[2-9]|3.2[0-9]) return 0 ;;
    esac
    return 1
}

# --- Python ---------------------------------------------------------------
PY=""
PY_ARGS=""

if [ "$IS_WINDOWS_BASH" -eq 1 ]; then
    for launcher in py.exe py; do
        if command -v "$launcher" >/dev/null 2>&1; then
            if python_ok "$launcher" -3.13; then
                PY="$launcher"
                PY_ARGS="-3.13"
                break
            fi
            if python_ok "$launcher" -3.12; then
                PY="$launcher"
                PY_ARGS="-3.12"
                break
            fi
        fi
    done
fi

if [ -z "$PY" ]; then
    for candidate in python3.13 python3.12 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && python_ok "$candidate"; then
            PY="$candidate"
            break
        fi
    done
fi

if [ -z "$PY" ]; then
    warn "Python 3.12+ not found on PATH. Install it from https://www.python.org/downloads/"
    exit 1
fi

if [ -n "$PY_ARGS" ]; then
    say "using $PY $PY_ARGS ($($PY $PY_ARGS --version 2>&1))"
else
    say "using $PY ($($PY --version 2>&1))"
fi

# --- venv -----------------------------------------------------------------
if [ -z "${VIRTUAL_ENV:-}" ]; then
    if [ ! -d .venv ]; then
        say "creating .venv"
        if [ -n "$PY_ARGS" ]; then
            "$PY" $PY_ARGS -m venv .venv
        else
            "$PY" -m venv .venv
        fi
    fi

    if [ -f .venv/Scripts/activate ]; then
        # shellcheck disable=SC1091
        . .venv/Scripts/activate
    elif [ -f .venv/bin/activate ]; then
        # shellcheck disable=SC1091
        . .venv/bin/activate
    else
        warn "Could not find a virtualenv activation script under .venv/"
        exit 1
    fi
    PY="$(command -v python)"
fi

if [ -f .venv/Scripts/activate ]; then
    ACTIVATE_CMD=". .venv/Scripts/activate"
    DIRECT_CLI="./.venv/Scripts/joby.exe"
    PATH_HINT=".venv/Scripts"
else
    ACTIVATE_CMD=". .venv/bin/activate"
    DIRECT_CLI="./.venv/bin/joby"
    PATH_HINT=".venv/bin"
fi

"$PY" -m pip install --upgrade pip >/dev/null

# --- install joby CLI + run setup ----------------------------------------
say "installing joby (editable)"
"$PY" -m pip install -e "apps/api[scrapers]" || {
    warn "[scrapers] extras failed (usually pandas/JobSpy); retrying without"
    "$PY" -m pip install -e "apps/api"
}

say "running joby install"
"$PY" -m app.cli install "$@" || warn "joby install returned non-zero; inspect output above"

cat <<EOF

Joby installed. To start in a new shell:

    $ACTIVATE_CMD
    joby                   # runs API + web UI

Or run the CLI directly without activating:

    $DIRECT_CLI

Quick reference:
    joby up        API (:8000) + web (:3000)
    joby api       API only
    joby web       web UI only
    joby scrape    trigger one scrape run
    joby doctor    print environment diagnostics

Tip: add $PATH_HINT to PATH to use `joby` from any shell without activating.

EOF
