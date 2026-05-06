"""JobSpy daemon: in-process singleton that calls ``python-jobspy`` with caching.

JobSpy (``pip install python-jobspy``) aggregates LinkedIn, Indeed, Glassdoor,
ZipRecruiter, and Google Jobs behind one Python API. We wrap it in a process-
wide singleton that:

- Lazily imports the library so the rest of the app works without it installed.
- Serializes calls behind a lock so overlapping pipeline runs don't double-hit
  LinkedIn (which quickly rate-limits).
- Caches results per ``(site, search_term, location)`` tuple for a configurable
  window (default 30 min). Cache hits are free; misses are network-bound.
- Normalizes every hit into the :class:`NormalizedJob` shape the pipeline
  already consumes.

This is called a "daemon" because it outlives any single pipeline run within
the FastAPI process and manages its own cache lifecycle. If the package is not
installed, :func:`fetch_jobspy` raises ``JobSpyUnavailable`` and the pipeline
simply records the error and continues.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..utils.normalize import (
    strip_html, parse_iso_datetime, parse_salary, guess_employment_type,
    guess_level, guess_remote_type, parse_location, normalize_title,
    url_hash, normalize_company_name, dedupe_key,
)
from .ats import NormalizedJob, _build  # reuse build helper

log = logging.getLogger("joby.jobspy")


class JobSpyUnavailable(RuntimeError):
    """Raised when python-jobspy is not installed."""


@dataclass
class _CacheEntry:
    fetched_at: float
    records: List[NormalizedJob]


@dataclass
class _DaemonState:
    cache: Dict[Tuple[str, str, str], _CacheEntry] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    ttl_seconds: int = 1800  # 30 minutes
    total_calls: int = 0
    total_hits: int = 0
    last_error: Optional[str] = None


_state = _DaemonState()


SUPPORTED_SITES = ("linkedin", "indeed", "glassdoor", "zip_recruiter", "google")


def _safe_text(value, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    text = str(value).strip()
    return text or default


def _cache_key(sites: List[str], search_term: str, location: str) -> Tuple[str, str, str]:
    sites = [s for s in sites if s in SUPPORTED_SITES] or list(SUPPORTED_SITES)
    return (
        ",".join(sorted(sites)),
        (search_term or "").lower().strip(),
        (location or "").lower().strip(),
    )


def health() -> dict:
    """Report daemon status + cache stats. Used by ``/api/llm/health`` UI area."""
    try:
        import jobspy  # noqa: F401
        available = True
        version = getattr(__import__("jobspy"), "__version__", "unknown")
    except Exception as e:
        available = False
        version = None
        _state.last_error = str(e)
    return {
        "available": available,
        "version": version,
        "cached_queries": len(_state.cache),
        "total_calls": _state.total_calls,
        "total_hits": _state.total_hits,
        "ttl_seconds": _state.ttl_seconds,
        "last_error": _state.last_error,
    }


def configure(ttl_seconds: Optional[int] = None) -> None:
    if ttl_seconds is not None:
        _state.ttl_seconds = int(ttl_seconds)


def clear_cache() -> None:
    with _state.lock:
        _state.cache.clear()


def cache_status(sites: List[str], search_term: str, location: str) -> dict:
    key = _cache_key(sites, search_term, location)
    with _state.lock:
        entry = _state.cache.get(key)
        if not entry:
            return {"status": "miss", "age_seconds": None}
        age = max(0, int(time.time() - entry.fetched_at))
        if age < _state.ttl_seconds:
            return {"status": "hit", "age_seconds": age}
        return {"status": "stale", "age_seconds": age}


def _normalize_one(site: str, record: dict) -> NormalizedJob:
    title = _safe_text(record.get("title"))
    company = _safe_text(record.get("company"), "Unknown")
    desc = _safe_text(record.get("description"))
    url = _safe_text(record.get("job_url") or record.get("job_url_direct"))
    location_raw = _safe_text(record.get("location"))
    posted = record.get("date_posted")
    # jobspy returns a datetime.date for date_posted; parse_iso accepts strings
    if hasattr(posted, "isoformat"):
        posted = posted.isoformat()
    nj = _build(
        source=f"jobspy:{site}",
        company=company,
        external_id=str(record.get("id") or url or f"{company}:{title}:{location_raw}"),
        title=title,
        url=url,
        description_html=None,
        description_text=desc,
        location_raw=location_raw,
        posted_at=posted,
        employment_hint=record.get("job_type") or record.get("employment_type"),
        extra={
            "compensation": record.get("compensation"),
            "is_remote": record.get("is_remote"),
            "salary_interval": record.get("interval"),
            "min_amount": record.get("min_amount"),
            "max_amount": record.get("max_amount"),
            "currency": record.get("currency"),
            "job_level": record.get("job_level"),
            "company_industry": record.get("company_industry"),
        },
    )
    # jobspy exposes salary numbers cleanly — prefer them when our parser missed.
    if nj.get("salary_min") is None and record.get("min_amount"):
        try:
            nj["salary_min"] = float(record["min_amount"])
        except Exception:
            pass
    if nj.get("salary_max") is None and record.get("max_amount"):
        try:
            nj["salary_max"] = float(record["max_amount"])
        except Exception:
            pass
    if not nj.get("salary_currency") and record.get("currency"):
        nj["salary_currency"] = record["currency"]
    return nj


def fetch_jobspy(
    sites: List[str],
    search_term: str,
    location: str,
    *,
    results_wanted: int = 30,
    hours_old: Optional[int] = None,
    country_indeed: str = "USA",
) -> List[NormalizedJob]:
    """Call JobSpy for one (sites, term, location) bundle. Cached per query."""
    try:
        from jobspy import scrape_jobs  # type: ignore
    except Exception as e:
        _state.last_error = str(e)
        raise JobSpyUnavailable(
            "python-jobspy is not installed. Run `pip install python-jobspy` "
            "inside apps/api to enable LinkedIn/Indeed/Glassdoor/ZipRecruiter/Google Jobs."
        ) from e

    sites = [s for s in sites if s in SUPPORTED_SITES] or list(SUPPORTED_SITES)
    cache_key = _cache_key(sites, search_term, location)
    with _state.lock:
        _state.total_calls += 1
        entry = _state.cache.get(cache_key)
        if entry and (time.time() - entry.fetched_at) < _state.ttl_seconds:
            _state.total_hits += 1
            return list(entry.records)

    try:
        df = scrape_jobs(
            site_name=sites,
            search_term=search_term,
            location=location,
            results_wanted=results_wanted,
            hours_old=hours_old,
            country_indeed=country_indeed,
            verbose=0,
        )
    except Exception as e:
        _state.last_error = str(e)
        log.warning("jobspy scrape failed for %s/%s: %s", search_term, location, e)
        with _state.lock:
            _state.cache[cache_key] = _CacheEntry(time.time(), [])
        return []

    records: List[NormalizedJob] = []
    if df is not None and len(df) > 0:
        for row in df.to_dict(orient="records"):
            try:
                site = row.get("site") or sites[0]
                records.append(_normalize_one(str(site), row))
            except Exception as e:
                log.warning("jobspy normalize failed: %s", e)
                continue

    with _state.lock:
        _state.cache[cache_key] = _CacheEntry(time.time(), list(records))
    return records
