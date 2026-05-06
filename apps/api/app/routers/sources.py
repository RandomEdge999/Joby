"""Sources management + auto-discovery.

Lets users:
  - List every configured ATS source (curated + user-added) and its status.
  - Auto-discover a company's ATS just by typing its name.
  - Add/remove custom sources without editing YAML files by hand.

No authentication (single-user local tool), but the discover endpoint is
rate-limited by its upstream calls and returns within ~8s.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ScrapeRun
from ..scrapers import jobspy_daemon
from ..services import discovery
from ..services.sources import (
    enabled_ats_sources, enabled_workday_sources, jobspy_config, load_sources,
)


router = APIRouter(prefix="/api/sources", tags=["sources"])


class DiscoverIn(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    website: Optional[str] = None


class SourceRow(BaseModel):
    company: str
    type: str
    slug: str
    enabled: bool = True


def _run_time(run: ScrapeRun) -> str | None:
    value = run.finished_at or run.started_at
    return value.isoformat() if value else None


def _error_key(error: dict) -> str:
    source = str(error.get("source") or error.get("stage") or "unknown")
    company = error.get("company")
    if company:
        return f"{source}:{company}"
    return source


def _blank_source_row(key: str, type_: str, label: str, enabled: bool = True) -> dict:
    return {
        "key": key,
        "type": type_,
        "label": label,
        "enabled": enabled,
        "last_status": "never_run",
        "last_success_at": None,
        "last_error_at": None,
        "last_error": None,
        "last_count": None,
        "last_duration_ms": None,
        "last_cache_status": None,
        "last_cache_age_seconds": None,
        "recent_history": [],
    }


def _detail_rows(run: ScrapeRun) -> dict[str, dict]:
    summary = run.source_summary_json or {}
    details = summary.get("details") or {}
    if details:
        return details
    per_source = summary.get("per_source") or (run.stats_json or {}).get("per_source") or {}
    rows: dict[str, dict] = {}
    for key, count in per_source.items():
        rows[key] = {
            "key": key,
            "type": str(key).split(":", 1)[0],
            "label": str(key).split(":", 1)[-1],
            "status": "ok",
            "count": count,
        }
    return rows


def _source_health(db: Session) -> dict:
    configured: dict[str, dict] = {}
    for source in enabled_ats_sources():
        source_type = source.get("type") or "ats"
        company = source.get("company") or source.get("slug") or "unknown"
        key = f"{source_type}:{company}"
        configured[key] = _blank_source_row(
            key, source_type, company, bool(source.get("enabled", True))
        )
    for org in enabled_workday_sources():
        company = org.get("company") or org.get("tenant") or org.get("slug") or "unknown"
        key = f"workday:{company}"
        configured[key] = _blank_source_row(
            key, "workday", company, bool(org.get("enabled", True))
        )

    recent_errors: list[dict] = []
    seen_recent_errors: set[tuple[int, str, str]] = set()
    search_cache = {
        "used_cache": None,
        "freshness_window_hours": None,
        "latest_run_at": None,
        "total_queries": 0,
        "hit": 0,
        "miss": 0,
        "stale": 0,
        "bypassed": 0,
    }
    runs = db.query(ScrapeRun).order_by(ScrapeRun.id.desc()).limit(25).all()
    for run in runs:
        when = _run_time(run)
        summary = run.source_summary_json or {}
        summary_cache = summary.get("cache") or {}
        if summary_cache:
            if search_cache["latest_run_at"] is None:
                search_cache["latest_run_at"] = when
                search_cache["used_cache"] = summary_cache.get("used_cache")
                search_cache["freshness_window_hours"] = summary_cache.get("freshness_window_hours")
            for key in ("total_queries", "hit", "miss", "stale", "bypassed"):
                search_cache[key] += int(summary_cache.get(key) or 0)

        for key, detail in _detail_rows(run).items():
            row = configured.setdefault(
                key,
                _blank_source_row(
                    key,
                    str(detail.get("type") or str(key).split(":", 1)[0]),
                    str(detail.get("label") or str(key).split(":", 1)[-1]),
                    True,
                ),
            )
            cache = detail.get("cache") or {}
            history = {
                "at": when,
                "status": str(detail.get("status") or "ok"),
                "count": detail.get("count"),
                "duration_ms": detail.get("duration_ms"),
                "cache_status": cache.get("status"),
            }
            if len(row["recent_history"]) < 5:
                row["recent_history"].append(history)

            if row["last_status"] == "never_run":
                row["last_status"] = history["status"]
                row["last_count"] = detail.get("count")
                row["last_duration_ms"] = detail.get("duration_ms")
                row["last_cache_status"] = cache.get("status")
                row["last_cache_age_seconds"] = cache.get("age_seconds")

            if history["status"] == "ok" and row["last_success_at"] is None:
                row["last_success_at"] = when
                if row["last_count"] is None:
                    row["last_count"] = detail.get("count")

            if history["status"] == "error":
                msg = str(detail.get("error") or "unknown error")
                if row["last_error_at"] is None:
                    row["last_error_at"] = when
                    row["last_error"] = msg
                signature = (run.id, key, msg)
                if signature not in seen_recent_errors:
                    recent_errors.append({"run_id": run.id, "at": when, "key": key,
                                          "error": msg})
                    seen_recent_errors.add(signature)

        for error in (run.error_json or {}).get("errors", []) or []:
            key = _error_key(error)
            row = configured.setdefault(
                key,
                _blank_source_row(
                    key,
                    str(error.get("source") or error.get("stage") or "unknown"),
                    str(error.get("company") or error.get("term") or key),
                    True,
                ),
            )
            if row["last_error_at"] is None:
                if row["last_status"] == "never_run":
                    row["last_status"] = "error"
                row["last_error_at"] = when
                row["last_error"] = str(error.get("error") or error)
            if len(row["recent_history"]) < 5:
                row["recent_history"].append({
                    "at": when,
                    "status": "error",
                    "count": None,
                    "duration_ms": None,
                    "cache_status": None,
                })
            msg = str(error.get("error") or error)
            signature = (run.id, key, msg)
            if signature not in seen_recent_errors:
                recent_errors.append({"run_id": run.id, "at": when, "key": key,
                                      "error": msg})
                seen_recent_errors.add(signature)

    return {
        "jobspy": {"enabled": bool(jobspy_config().get("enabled", False)),
                   **jobspy_daemon.health()},
        "search_cache": search_cache,
        "sources": sorted(configured.values(), key=lambda item: item["key"]),
        "recent_errors": recent_errors[:10],
    }


@router.get("")
def list_all():
    """Full inventory so the UI can render toggles + a user-added list."""
    data = load_sources()
    user_rows = discovery.load_user_sources()
    user_keys = {(str(r.get("type", "")).lower(),
                  str(r.get("slug", "")).lower()) for r in user_rows}
    ats = [dict(r) for r in data.get("ats_sources", [])]
    for r in ats:
        key = (str(r.get("type", "")).lower(),
               str(r.get("slug", "")).lower())
        r["user_added"] = key in user_keys
    return {
        "ats_sources": ats,
        "workday": data.get("workday") or {"enabled": False, "organizations": []},
        "jobspy": data.get("jobspy") or {"enabled": False},
        "counts": {
            "ats_enabled": len(enabled_ats_sources()),
            "workday_enabled": len(enabled_workday_sources()),
            "user_added": len(user_rows),
        },
    }


@router.get("/health")
def source_health(db: Session = Depends(get_db)):
    return _source_health(db)


@router.post("/discover")
def discover_company(payload: DiscoverIn):
    """Probe every known ATS for this company. Returns the candidates ranked
    by job count; the UI then lets the user pick one and add it."""
    hits = discovery.discover(payload.company, payload.website)
    return {"company": payload.company, "matches": hits}


@router.post("/add", status_code=201)
def add_source(payload: SourceRow):
    row = discovery.add_user_source(
        company=payload.company, type_=payload.type,
        slug=payload.slug, enabled=payload.enabled,
    )
    return {"added": row}


@router.delete("/{type_}/{slug}")
def remove_source(type_: str, slug: str):
    ok = discovery.remove_user_source(type_, slug)
    return {"removed": ok, "type": type_, "slug": slug}
