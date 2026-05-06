"""Company / ATS auto-discovery.

Given a company name or website, probe the major ATS endpoints to find
where that company actually lists jobs. Returns the first slug that
responds with a non-empty job board. No hardcoded mappings; no blockers.

Used by:
    POST /api/sources/discover   -> {company, website?} -> {matches: [...]}
    POST /api/sources/add        -> persist a discovered source to an
                                    overlay YAML (config/sources.user.yaml)
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Iterable, List, Optional

import httpx
import yaml

from ..config import settings


_UA = "Joby/0.1 (+https://github.com/RandomEdge999/Joby)"
_TIMEOUT = httpx.Timeout(8.0, connect=4.0)


def _slug_candidates(company: str, website: Optional[str] = None) -> List[str]:
    """Generate ATS-slug candidates from a company name + optional domain."""
    seen: list[str] = []
    def add(s: str) -> None:
        s = s.strip().lower()
        if s and s not in seen:
            seen.append(s)

    # From the company name.
    name = company.strip()
    add(re.sub(r"[^a-z0-9]", "", name.lower()))
    add(re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"))
    add(re.sub(r"[^a-z0-9]+", "", name.lower().split()[0] if name else ""))
    # Short forms: drop common suffixes.
    stripped = re.sub(r"\b(inc|llc|ltd|co|corp|corporation|gmbh|ag|sa|plc)\b",
                      "", name.lower())
    add(re.sub(r"[^a-z0-9]", "", stripped))

    # From a website domain.
    if website:
        m = re.search(r"https?://(?:www\.)?([^/]+)", website)
        host = (m.group(1) if m else website).lower()
        root = host.split(".")[0]
        add(root)
        add(re.sub(r"[^a-z0-9]", "", root))

    return [s for s in seen if s and len(s) >= 2]


async def _try_greenhouse(client: httpx.AsyncClient, slug: str) -> Optional[int]:
    """Return job count if Greenhouse board exists and is non-empty."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    try:
        r = await client.get(url)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("jobs") or []
            return len(jobs)
    except Exception:
        return None
    return None


async def _try_lever(client: httpx.AsyncClient, slug: str) -> Optional[int]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = await client.get(url)
        if r.status_code == 200:
            data = r.json()
            return len(data) if isinstance(data, list) else 0
    except Exception:
        return None
    return None


async def _try_ashby(client: httpx.AsyncClient, slug: str) -> Optional[int]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        r = await client.get(url)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("jobs") or []
            return len(jobs)
    except Exception:
        return None
    return None


async def _try_smartrecruiters(client: httpx.AsyncClient, slug: str) -> Optional[int]:
    url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1"
    try:
        r = await client.get(url)
        if r.status_code == 200:
            data = r.json()
            return int(data.get("totalFound") or 0)
    except Exception:
        return None
    return None


async def _try_workable(client: httpx.AsyncClient, slug: str) -> Optional[int]:
    url = f"https://{slug}.workable.com/spi/v3/jobs?limit=1"
    try:
        r = await client.get(url)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("jobs") or data.get("results") or []
            return len(jobs) if jobs else (1 if data.get("total") else 0)
    except Exception:
        return None
    return None


async def _try_recruitee(client: httpx.AsyncClient, slug: str) -> Optional[int]:
    url = f"https://{slug}.recruitee.com/api/offers/"
    try:
        r = await client.get(url)
        if r.status_code == 200:
            data = r.json()
            offers = data.get("offers") or []
            return len(offers)
    except Exception:
        return None
    return None


_PROBES = [
    ("greenhouse", _try_greenhouse),
    ("lever", _try_lever),
    ("ashby", _try_ashby),
    ("smartrecruiters", _try_smartrecruiters),
    ("workable", _try_workable),
    ("recruitee", _try_recruitee),
]


async def discover_async(company: str, website: Optional[str] = None,
                         max_candidates: int = 4) -> List[dict]:
    """Probe ATS endpoints for a company. Returns the sorted list of hits.

    Each hit: {type, slug, job_count}.
    """
    slugs = _slug_candidates(company, website)[:max_candidates]
    if not slugs:
        return []
    headers = {"User-Agent": _UA, "Accept": "application/json"}
    async with httpx.AsyncClient(headers=headers, timeout=_TIMEOUT,
                                 follow_redirects=True) as client:
        tasks = []
        meta: list[tuple[str, str]] = []
        for slug in slugs:
            for ats_type, probe in _PROBES:
                tasks.append(probe(client, slug))
                meta.append((ats_type, slug))
        results = await asyncio.gather(*tasks, return_exceptions=True)

    hits: list[dict] = []
    for (ats_type, slug), res in zip(meta, results):
        if isinstance(res, Exception) or res is None or res == 0:
            continue
        hits.append({"type": ats_type, "slug": slug, "job_count": int(res)})
    # Higher job_count first, then alphabetical for stability.
    hits.sort(key=lambda h: (-h["job_count"], h["type"]))
    return hits


def discover(company: str, website: Optional[str] = None) -> List[dict]:
    """Sync wrapper for the router."""
    return asyncio.run(discover_async(company, website))


# --- persistence: user-added sources live in sources.user.yaml ------------

def _user_yaml_path() -> Path:
    return settings.resolved_config_dir() / "sources.user.yaml"


def load_user_sources() -> list[dict]:
    p = _user_yaml_path()
    if not p.exists():
        return []
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    rows = data.get("ats_sources") or []
    return [r for r in rows if isinstance(r, dict)]


def write_user_sources(rows: list[dict]) -> None:
    p = _user_yaml_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    cleaned = [r for r in rows if isinstance(r, dict)]
    if not cleaned:
        if p.exists():
            p.unlink()
        return
    p.write_text(
        yaml.safe_dump({"ats_sources": cleaned}, sort_keys=False,
                       allow_unicode=True),
        encoding="utf-8",
    )


def add_user_source(company: str, type_: str, slug: str,
                    enabled: bool = True) -> dict:
    """Append (or overwrite) an entry in sources.user.yaml. Idempotent."""
    existing = load_user_sources()
    key = (type_.lower(), slug.lower())
    out = [r for r in existing
           if (str(r.get("type", "")).lower(),
               str(r.get("slug", "")).lower()) != key]
    row = {"company": company, "type": type_, "slug": slug, "enabled": enabled}
    out.append(row)
    write_user_sources(out)
    return row


def remove_user_source(type_: str, slug: str) -> bool:
    existing = load_user_sources()
    key = (type_.lower(), slug.lower())
    out = [r for r in existing
           if (str(r.get("type", "")).lower(),
               str(r.get("slug", "")).lower()) != key]
    if len(out) == len(existing):
        return False
    write_user_sources(out)
    return True
