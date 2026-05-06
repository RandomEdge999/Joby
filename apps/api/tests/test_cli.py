from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from app import cli


def _make_repo_root(tmp_path: Path, with_config: bool = True, with_alembic: bool = True) -> Path:
    root = tmp_path / "repo"
    (root / "apps" / "api" / "data").mkdir(parents=True)
    (root / "apps" / "web").mkdir(parents=True)
    if with_config:
        (root / "config").mkdir()
    if with_alembic:
        (root / "apps" / "api" / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    return root


def test_cmd_doctor_reports_structured_checks(monkeypatch, tmp_path, capsys):
    root = _make_repo_root(tmp_path)
    db_path = root / "apps" / "api" / "data" / "joby.db"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/joby.db")
    conn = sqlite3.connect(db_path)
    conn.execute("create table jobs (id integer primary key)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(cli, "_repo_root", lambda: root)
    monkeypatch.setattr(cli, "_command_version", lambda name: {"node": "v20.11.1", "npm": "10.5.0"}.get(name))
    monkeypatch.setattr(cli, "_jobspy_available", lambda: True)
    monkeypatch.setattr(cli, "_http_status", lambda url: (False, "connection refused"))
    monkeypatch.setattr(cli, "_port_open", lambda host, port: False)

    args = SimpleNamespace(api_port=8000, web_port=3000, host="127.0.0.1")
    rc = cli.cmd_doctor(args)

    out = capsys.readouterr().out
    assert rc == 0
    assert "[PASS][required] Python:" in out
    assert "[PASS][required] Database schema: 1 tables present" in out
    assert "[WARN][optional] API health:" in out
    assert "next: Run `joby up` or `joby api` to start the backend." in out
    assert "doctor result: WARN" in out


def test_cmd_doctor_fails_when_required_paths_missing(monkeypatch, tmp_path, capsys):
    root = _make_repo_root(tmp_path, with_config=False, with_alembic=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/joby.db")

    monkeypatch.setattr(cli, "_repo_root", lambda: root)
    monkeypatch.setattr(cli, "_command_version", lambda name: None)
    monkeypatch.setattr(cli, "_jobspy_available", lambda: False)
    monkeypatch.setattr(cli, "_http_status", lambda url: (False, "connection refused"))
    monkeypatch.setattr(cli, "_port_open", lambda host, port: False)

    args = SimpleNamespace(api_port=8000, web_port=3000, host="127.0.0.1")
    rc = cli.cmd_doctor(args)

    out = capsys.readouterr().out
    assert rc == 1
    assert "[FAIL][required] Config dir:" in out
    assert "[FAIL][required] Migrations:" in out
    assert "doctor result: FAIL" in out


def test_cmd_install_reports_follow_up_steps(monkeypatch, tmp_path, capsys):
    root = _make_repo_root(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/joby.db")

    monkeypatch.setattr(cli, "_repo_root", lambda: root)
    monkeypatch.setattr(cli, "_python_exe", lambda: "python")
    monkeypatch.setattr(cli, "_node_available", lambda: False)

    def fake_run(cmd, cwd=None, check=True, env=None):
        if cmd[:4] == ["python", "-m", "pip", "install"] and "-e" in cmd:
            return 0
        if cmd[:3] == ["python", "-m", "alembic"]:
            return 1
        return 0

    monkeypatch.setattr(cli, "_run", fake_run)

    args = SimpleNamespace(no_scrapers=False, skip_h1b=True, build_web=False)
    rc = cli.cmd_install(args)

    out = capsys.readouterr().out
    assert rc == 0
    assert "install finished with follow-up steps:" in out
    assert "Re-run `joby install` after fixing Alembic" in out
    assert "Install it, then re-run `joby install` to enable the web UI" in out