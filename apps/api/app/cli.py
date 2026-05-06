"""Joby command-line interface.

Entry point installed as the `joby` console script via pyproject.toml.
Designed to work identically on Windows, macOS, and Linux: no shell-specific
syntax, no bash pipelines, subprocess-only. Never blocks on optional
dependencies; missing LLM / jobspy / network degrade gracefully.

Subcommands:
    joby up          start API + web together (default if no subcommand)
    joby api         start the API only
    joby web         start the web UI only
    joby install     one-shot setup: deps, DB migrations, seed data, web build
    joby scrape      trigger a one-off pipeline run
    joby doctor      print environment diagnostics
    joby version     print the Joby version
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.util
import os
import socket
import sqlite3
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse


VERSION = "0.1.0"


@dataclass
class DoctorCheck:
    name: str
    severity: str
    status: str
    detail: str
    next_step: Optional[str] = None


def _repo_root() -> Path:
    """Find repo root by walking up from this file until we see `apps/`."""
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "apps" / "api").is_dir() and (parent / "apps" / "web").is_dir():
            return parent
    # Fallback: assume installed editable from apps/api
    return here.parent.parent.parent


def _log(msg: str) -> None:
    print(f"[joby] {msg}", flush=True)


def _which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


def _capture(cmd: List[str], cwd: Optional[Path] = None,
             env: Optional[dict] = None) -> tuple[int, str]:
    try:
        r = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return 127, ""
    text = (r.stdout or r.stderr or "").strip()
    return r.returncode, text


def _run(cmd: List[str], cwd: Optional[Path] = None, check: bool = True,
         env: Optional[dict] = None) -> int:
    """Run a subprocess cross-platform. Never raises on non-zero unless check."""
    _log(f"$ {' '.join(cmd)}" + (f"   (cwd={cwd})" if cwd else ""))
    try:
        r = subprocess.run(cmd, cwd=cwd, env=env,
                           shell=False, check=False)
    except FileNotFoundError as e:
        _log(f"command not found: {cmd[0]} ({e})")
        if check:
            sys.exit(127)
        return 127
    if r.returncode != 0 and check:
        sys.exit(r.returncode)
    return r.returncode


def _python_exe() -> str:
    """The Python that's running us — guaranteed to match the installed venv."""
    return sys.executable


def _node_available() -> bool:
    return _which("node") is not None and _which("npm") is not None


def _command_version(name: str) -> Optional[str]:
    executable = _which(name)
    if not executable:
        return None
    code, text = _capture([executable, "--version"])
    if code != 0:
        return None
    return text.splitlines()[0].strip() if text else None


def _version_major(version: Optional[str]) -> Optional[int]:
    if not version:
        return None
    digits = "".join(ch if ch.isdigit() or ch == "." else "" for ch in version)
    if not digits:
        return None
    head = digits.split(".", 1)[0]
    return int(head) if head.isdigit() else None


def _jobspy_available() -> bool:
    return importlib.util.find_spec("jobspy") is not None


def _config_dir(root: Path) -> Path:
    raw = os.environ.get("CONFIG_DIR")
    if raw:
        path = Path(raw)
        return path if path.is_absolute() else (Path.cwd() / path).resolve()
    return (root / "config").resolve()


def _database_url() -> str:
    return os.environ.get("DATABASE_URL", "sqlite:///./data/joby.db")


def _sqlite_database_path(root: Path, database_url: str) -> Optional[Path]:
    if not database_url.startswith("sqlite:///"):
        return None
    raw = Path(database_url.replace("sqlite:///", "", 1))
    if raw.is_absolute():
        return raw
    return (root / "apps" / "api" / raw).resolve()


def _sqlite_table_count(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def _http_status(url: str) -> tuple[bool, str]:
    try:
        import httpx

        r = httpx.get(url, timeout=2.0)
        detail = f"{r.status_code} {r.reason_phrase}".strip()
        return r.is_success, detail
    except Exception as e:
        return False, str(e)


def _doctor_line(check: DoctorCheck) -> str:
    return f"[{check.status.upper()}][{check.severity}] {check.name}: {check.detail}"


def _doctor_checks(root: Path, args: argparse.Namespace) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []

    python_version = sys.version.split()[0]
    python_ok = sys.version_info >= (3, 12)
    checks.append(DoctorCheck(
        name="Python",
        severity="required",
        status="pass" if python_ok else "fail",
        detail=f"{python_version} ({_python_exe()})",
        next_step=None if python_ok else "Install Python 3.12+ and recreate the virtual environment.",
    ))

    node_version = _command_version("node")
    node_major = _version_major(node_version)
    node_ok = node_major is not None and node_major >= 20
    checks.append(DoctorCheck(
        name="Node.js",
        severity="optional",
        status="pass" if node_ok else "warn",
        detail=node_version or "not found",
        next_step=None if node_ok else "Install Node 20+ and re-run `joby install` to enable the web UI.",
    ))

    npm_version = _command_version("npm")
    npm_ok = npm_version is not None
    checks.append(DoctorCheck(
        name="npm",
        severity="optional",
        status="pass" if npm_ok else "warn",
        detail=npm_version or "not found",
        next_step=None if npm_ok else "Install Node 20+ so `npm` is available, then re-run `joby install`.",
    ))

    config_dir = _config_dir(root)
    config_ok = config_dir.exists()
    checks.append(DoctorCheck(
        name="Config dir",
        severity="required",
        status="pass" if config_ok else "fail",
        detail=str(config_dir),
        next_step=None if config_ok else "Set CONFIG_DIR or restore the repository's config directory.",
    ))

    database_url = _database_url()
    db_path = _sqlite_database_path(root, database_url)
    if db_path is not None:
        db_parent_ok = db_path.parent.exists()
        db_status = "pass" if db_path.exists() else ("pass" if db_parent_ok else "fail")
        db_next = None
        if not db_path.exists() and db_parent_ok:
            db_status = "warn"
            db_next = "Run `joby install` or `joby up` once to create the local database."
        elif not db_parent_ok:
            db_next = "Create the database directory or set DATABASE_URL to a writable location."
        checks.append(DoctorCheck(
            name="Database path",
            severity="required",
            status=db_status,
            detail=f"{database_url} -> {db_path}",
            next_step=db_next,
        ))
    else:
        checks.append(DoctorCheck(
            name="Database path",
            severity="required",
            status="pass",
            detail=database_url,
        ))

    alembic_ini = root / "apps" / "api" / "alembic.ini"
    checks.append(DoctorCheck(
        name="Migrations",
        severity="required",
        status="pass" if alembic_ini.exists() else "fail",
        detail=str(alembic_ini),
        next_step=None if alembic_ini.exists() else "Restore apps/api/alembic.ini or re-install the repository checkout.",
    ))

    if db_path is not None:
        table_count = _sqlite_table_count(db_path)
        schema_ready = table_count is not None and table_count > 0
        checks.append(DoctorCheck(
            name="Database schema",
            severity="required",
            status="pass" if schema_ready else "warn",
            detail=(f"{table_count} tables present" if table_count is not None else "database not initialized yet"),
            next_step=None if schema_ready else "Run `joby install` or start `joby up` to initialize the schema.",
        ))

    checks.append(DoctorCheck(
        name="JobSpy",
        severity="optional",
        status="pass" if _jobspy_available() else "warn",
        detail="installed" if _jobspy_available() else "not installed",
        next_step=None if _jobspy_available() else "Run `joby install` to add scraper extras, or ignore this if you only use direct sources.",
    ))

    lm_studio_url = os.environ.get("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
    parsed = urlparse(lm_studio_url)
    lm_probe = parsed._replace(path=f"{parsed.path.rstrip('/')}/models").geturl() if parsed.scheme else lm_studio_url
    lm_ok, lm_detail = _http_status(lm_probe)
    checks.append(DoctorCheck(
        name="LM Studio",
        severity="optional",
        status="pass" if lm_ok else "warn",
        detail=f"{lm_studio_url} ({lm_detail})",
        next_step=None if lm_ok else "Start LM Studio or ignore this if you are not using local model scoring.",
    ))

    api_port_open = _port_open(args.host, args.api_port)
    checks.append(DoctorCheck(
        name="API port",
        severity="optional",
        status="pass",
        detail=(f"{args.host}:{args.api_port} is accepting connections" if api_port_open else f"{args.host}:{args.api_port} is free"),
    ))
    api_ok, api_detail = _http_status(f"http://{args.host}:{args.api_port}/api/health")
    checks.append(DoctorCheck(
        name="API health",
        severity="optional",
        status="pass" if api_ok else "warn",
        detail=api_detail if api_ok else f"not reachable on :{args.api_port} ({api_detail})",
        next_step=None if api_ok else "Run `joby up` or `joby api` to start the backend.",
    ))

    web_port_open = _port_open(args.host, args.web_port)
    checks.append(DoctorCheck(
        name="Web port",
        severity="optional",
        status="pass",
        detail=(f"{args.host}:{args.web_port} is accepting connections" if web_port_open else f"{args.host}:{args.web_port} is free"),
    ))
    web_ok, web_detail = _http_status(f"http://{args.host}:{args.web_port}")
    checks.append(DoctorCheck(
        name="Web health",
        severity="optional",
        status="pass" if web_ok else "warn",
        detail=web_detail if web_ok else f"not reachable on :{args.web_port} ({web_detail})",
        next_step=None if web_ok else "Run `joby up` after `joby install` to start the web UI.",
    ))

    return checks


# --------------------------------------------------------------------------
# install
# --------------------------------------------------------------------------

def cmd_install(args: argparse.Namespace) -> int:
    root = _repo_root()
    api_dir = root / "apps" / "api"
    web_dir = root / "apps" / "web"
    issues: list[str] = []

    _log(f"repo root: {root}")
    _log(f"python:    {sys.version.split()[0]} ({_python_exe()})")

    # 1. Install API deps. If we're already running inside an editable install
    #    (which is how the user just invoked `joby`), pip install is idempotent.
    extras = "[scrapers]" if not args.no_scrapers else ""
    pip_target = f".{extras}" if extras else "."
    _run([_python_exe(), "-m", "pip", "install", "--upgrade", "pip"],
         cwd=api_dir, check=False)
    if _run([_python_exe(), "-m", "pip", "install", "-e", pip_target],
            cwd=api_dir, check=False) != 0:
        issues.append(
            "Python dependencies did not install cleanly. Re-run `joby install --no-scrapers` after fixing the pip error above."
        )

    # 2. Database migrations (best-effort — falls back to create_all at runtime).
    env = os.environ.copy()
    env.setdefault("CONFIG_DIR", str(root / "config"))
    if _run([_python_exe(), "-m", "alembic", "upgrade", "head"],
            cwd=api_dir, check=False, env=env) != 0:
        issues.append(
            "Database migrations did not complete. Re-run `joby install` after fixing Alembic, or start `joby up` to let the app create tables on first boot."
        )

    # 3. Seed + H-1B data. Never block install on network failures.
    seed = root / "scripts" / "seed_companies.py"
    if seed.exists():
        if _run([_python_exe(), str(seed)], cwd=root, check=False, env=env) != 0:
            issues.append(
                "Company seed data failed. Re-run `python scripts/seed_companies.py` after checking your source configuration."
            )
    h1b = root / "scripts" / "refresh_h1b.py"
    if h1b.exists() and not args.skip_h1b:
        _log("refreshing H-1B data (skip with --skip-h1b if offline)")
        if _run([_python_exe(), str(h1b)], cwd=root, check=False, env=env) != 0:
            issues.append(
                "H-1B refresh failed. Re-run `python scripts/refresh_h1b.py` later, or use `joby install --skip-h1b` when offline."
            )

    # 4. Web deps. Skip silently if Node isn't installed — the API still works.
    if _node_available():
        npm = "npm.cmd" if os.name == "nt" else "npm"
        if _run([npm, "install"], cwd=web_dir, check=False) != 0:
            issues.append(
                "Web dependencies failed. Run `cd apps/web && npm install`, then re-run `joby install`."
            )
        if args.build_web:
            if _run([npm, "run", "build"], cwd=web_dir, check=False) != 0:
                issues.append(
                    "Web build failed. Run `cd apps/web && npm run build` after fixing the reported frontend issue."
                )
    else:
        _log("Node.js not found. Install Node 20+ and re-run `joby install` "
             "to enable the web UI. The API alone still works via `joby api`.")
        issues.append(
            "Node.js 20+ is missing. Install it, then re-run `joby install` to enable the web UI."
        )

    if issues:
        _log("install finished with follow-up steps:")
        for issue in issues:
            _log(f"- {issue}")
    else:
        _log("install complete. Start with: joby")
    return 0


# --------------------------------------------------------------------------
# up / api / web
# --------------------------------------------------------------------------

def _spawn(cmd: List[str], cwd: Path, env: dict, label: str) -> subprocess.Popen:
    _log(f"starting {label}: {' '.join(cmd)}")
    creationflags = 0
    start_new_session = False
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        start_new_session = True
    return subprocess.Popen(
        cmd, cwd=cwd, env=env,
        creationflags=creationflags,
        start_new_session=start_new_session,
    )


def _terminate(p: Optional[subprocess.Popen], label: str) -> None:
    if p is None or p.poll() is not None:
        return
    _log(f"stopping {label} (pid={p.pid})")
    try:
        if os.name == "nt":
            p.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    except Exception:
        try:
            p.terminate()
        except Exception:
            pass
    try:
        p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            p.kill()
        except Exception:
            pass


def _api_cmd(host: str, port: int) -> List[str]:
    return [_python_exe(), "-m", "uvicorn", "app.main:app",
            "--host", host, "--port", str(port)]


def _web_cmd() -> List[str]:
    npm = "npm.cmd" if os.name == "nt" else "npm"
    return [npm, "run", "dev"]


def cmd_api(args: argparse.Namespace) -> int:
    root = _repo_root()
    api_dir = root / "apps" / "api"
    env = os.environ.copy()
    env.setdefault("CONFIG_DIR", str(root / "config"))
    return _run(_api_cmd(args.host, args.api_port), cwd=api_dir,
                check=False, env=env)


def cmd_web(args: argparse.Namespace) -> int:
    root = _repo_root()
    web_dir = root / "apps" / "web"
    if not _node_available():
        _log("Node.js not found. Install Node 20+ to run the web UI.")
        return 1
    env = os.environ.copy()
    env.setdefault("NEXT_PUBLIC_API_URL", f"http://localhost:{args.api_port}")
    env.setdefault("PORT", str(args.web_port))
    return _run(_web_cmd(), cwd=web_dir, check=False, env=env)


def cmd_up(args: argparse.Namespace) -> int:
    """Run API + web together. Ctrl-C cleanly stops both."""
    root = _repo_root()
    api_dir = root / "apps" / "api"
    web_dir = root / "apps" / "web"

    env = os.environ.copy()
    env.setdefault("CONFIG_DIR", str(root / "config"))

    api_p = _spawn(_api_cmd(args.host, args.api_port), cwd=api_dir,
                   env=env, label="api")

    web_p: Optional[subprocess.Popen] = None
    if _node_available() and not args.api_only:
        web_env = env.copy()
        web_env["NEXT_PUBLIC_API_URL"] = f"http://localhost:{args.api_port}"
        web_env["PORT"] = str(args.web_port)
        # Give the API a head start so the browser lands on a working backend.
        time.sleep(1.2)
        web_p = _spawn(_web_cmd(), cwd=web_dir, env=web_env, label="web")
    elif not _node_available():
        _log("Node.js not found; running API only. `joby install` after installing Node to enable the web UI.")

    _log("Joby is up.")
    _log(f"  API: http://localhost:{args.api_port}")
    if web_p is not None:
        _log(f"  Web: http://localhost:{args.web_port}")
    _log("Press Ctrl-C to stop.")

    try:
        while True:
            if api_p.poll() is not None:
                _log(f"api exited with code {api_p.returncode}")
                break
            if web_p is not None and web_p.poll() is not None:
                _log(f"web exited with code {web_p.returncode}")
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        _log("shutting down...")
    finally:
        _terminate(web_p, "web")
        _terminate(api_p, "api")
    return 0


# --------------------------------------------------------------------------
# scrape / doctor / version
# --------------------------------------------------------------------------

def cmd_scrape(args: argparse.Namespace) -> int:
    import httpx
    url = f"http://localhost:{args.api_port}/api/runs/start"
    try:
        r = httpx.post(url, timeout=10.0)
        r.raise_for_status()
        print(r.text)
        return 0
    except Exception as e:
        _log(f"could not reach API at {url}: {e}")
        _log("is `joby up` running?")
        return 1


def cmd_doctor(args: argparse.Namespace) -> int:
    root = _repo_root()
    checks = _doctor_checks(root, args)

    print(f"joby version: {VERSION}")
    print(f"repo root:    {root}")
    print(f"platform:     {sys.platform}")
    print("")
    for check in checks:
        print(_doctor_line(check))
        if check.next_step:
            print(f"  next: {check.next_step}")

    failures = sum(1 for check in checks if check.status == "fail")
    warnings = sum(1 for check in checks if check.status == "warn")
    passes = sum(1 for check in checks if check.status == "pass")
    print("")
    print(f"summary: {passes} pass, {warnings} warn, {failures} fail")
    if failures:
        print("doctor result: FAIL")
        return 1
    if warnings:
        print("doctor result: WARN")
    else:
        print("doctor result: PASS")
    return 0


def cmd_version(args: argparse.Namespace) -> int:
    print(VERSION)
    return 0


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    # Shared flags: usable either before or after the subcommand
    # (`joby --api-port 9000 up` and `joby up --api-port 9000` both work).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--api-port", type=int,
                        default=int(os.environ.get("JOBY_API_PORT", "8000")))
    common.add_argument("--web-port", type=int,
                        default=int(os.environ.get("JOBY_WEB_PORT", "3000")))
    common.add_argument("--host", default="127.0.0.1")

    p = argparse.ArgumentParser(
        prog="joby",
        description="Joby - local-first universal job search.",
        parents=[common],
    )

    sub = p.add_subparsers(dest="command")

    s_up = sub.add_parser("up", parents=[common],
                          help="start API + web (default)")
    s_up.add_argument("--api-only", action="store_true")
    s_up.set_defaults(func=cmd_up)

    sub.add_parser("api", parents=[common], help="start the API only") \
        .set_defaults(func=cmd_api)
    sub.add_parser("web", parents=[common], help="start the web UI only") \
        .set_defaults(func=cmd_web)

    s_inst = sub.add_parser("install", parents=[common],
                            help="first-time setup")
    s_inst.add_argument("--no-scrapers", action="store_true",
                        help="skip python-jobspy (pandas-heavy) extras")
    s_inst.add_argument("--skip-h1b", action="store_true",
                        help="skip USCIS CSV download")
    s_inst.add_argument("--build-web", action="store_true",
                        help="run `npm run build` for a production bundle")
    s_inst.set_defaults(func=cmd_install)

    sub.add_parser("scrape", parents=[common],
                   help="trigger a one-off pipeline run") \
        .set_defaults(func=cmd_scrape)
    sub.add_parser("doctor", parents=[common],
                   help="environment diagnostics") \
        .set_defaults(func=cmd_doctor)
    sub.add_parser("version", parents=[common], help="print version") \
        .set_defaults(func=cmd_version)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        # Default: `joby` with no args == `joby up`.
        args.api_only = False
        return cmd_up(args)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
