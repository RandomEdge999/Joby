# Joby one-shot installer for Windows PowerShell 5+ or PowerShell 7.
#
# Usage:  .\install.ps1
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

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Say($m)  { Write-Host "[install] $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "[install] $m" -ForegroundColor Yellow }

# --- Python ---------------------------------------------------------------
$py = $null
foreach ($c in @('py -3.12', 'py -3.13', 'python3.12', 'python3.13', 'python')) {
    try {
        $parts = $c.Split(' ')
        $out = & $parts[0] $parts[1..($parts.Length-1)] -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out -match '^3\.(1[2-9]|2[0-9])$') {
            $py = $c
            break
        }
    } catch { }
}
if (-not $py) {
    Warn "Python 3.12+ not found on PATH. Install from https://www.python.org/downloads/"
    exit 1
}
Say "using $py"

# --- venv -----------------------------------------------------------------
if (-not $env:VIRTUAL_ENV) {
    if (-not (Test-Path .venv)) {
        Say "creating .venv"
        $parts = $py.Split(' ')
        & $parts[0] $parts[1..($parts.Length-1)] -m venv .venv
    }
    & ".\.venv\Scripts\Activate.ps1"
    $py = 'python'
}

& python -m pip install --upgrade pip | Out-Null

# --- install joby CLI + run setup ----------------------------------------
Say "installing joby (editable)"
& python -m pip install -e "apps/api[scrapers]"
if ($LASTEXITCODE -ne 0) {
    Warn "[scrapers] extras failed (usually pandas/JobSpy); retrying without"
    & python -m pip install -e "apps/api"
}

Say "running joby install"
& python -m app.cli install @args
if ($LASTEXITCODE -ne 0) {
    Warn "joby install returned $LASTEXITCODE; inspect output above"
}

$directCli = ".\.venv\Scripts\joby.exe"

Write-Host ""
Write-Host "Joby installed. To start in a new PowerShell session:"
Write-Host ""
Write-Host "    .\.venv\Scripts\Activate.ps1    # if not already in the venv"
Write-Host "    joby                            # runs API + web UI"
Write-Host ""
Write-Host "Or run the CLI directly without activating:"
Write-Host ""
Write-Host "    $directCli"
Write-Host ""
Write-Host "Quick reference:"
Write-Host "    joby up        API (:8000) + web (:3000)"
Write-Host "    joby api       API only"
Write-Host "    joby web       web UI only"
Write-Host "    joby scrape    trigger one scrape run"
Write-Host "    joby doctor    print environment diagnostics"
Write-Host ""
Write-Host "Tip: add .venv\Scripts to PATH to use 'joby' from any shell without activating."
Write-Host ""
