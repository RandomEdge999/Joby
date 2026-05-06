"""ATS scrapers using public JSON APIs.

Supported source types (the ``type`` field in ``config/sources.yaml``):

- ``greenhouse``     (boards-api.greenhouse.io)
- ``lever``          (api.lever.co)
- ``ashby``          (api.ashbyhq.com/posting-api)
- ``workday``        (myworkdayjobs.com cxs endpoint)
- ``smartrecruiters``(api.smartrecruiters.com)
- ``workable``       ({slug}.workable.com/spi/v3/jobs)
- ``recruitee``      ({slug}.recruitee.com/api/offers)

All scrapers return a list of :class:`NormalizedJob` dicts with the fields the
pipeline expects. Each scraper is defensive: network errors raise, but missing
fields never do.
"""
from __future__ import annotations

import copy
import httpx
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from ..utils.normalize import (
    strip_html, parse_iso_datetime, parse_salary, guess_employment_type,
    guess_level, guess_remote_type, parse_location, normalize_title,
    url_hash, normalize_company_name, dedupe_key,
)


_UA = "Joby/0.1 (+https://github.com/RandomEdge999/Joby)"


@dataclass
class _CacheEntry:
    fetched_at: float
    payload: List[dict]


@dataclass
class _CacheState:
    ttl_seconds: int = 1800
    cache: dict[tuple[str, str, str, str], _CacheEntry] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock)


_cache_state = _CacheState()


class NormalizedJob(dict):
    """Typed dict-like normalized record passed between scraper -> pipeline."""


def configure_cache(ttl_seconds: Optional[int] = None) -> None:
    if ttl_seconds is not None:
        _cache_state.ttl_seconds = int(ttl_seconds)


def clear_cache() -> None:
    with _cache_state.lock:
        _cache_state.cache.clear()


def _cache_key(type_: str, slug: str, *, site: Optional[str] = None,
               tenant: Optional[str] = None) -> tuple[str, str, str, str]:
    return (
        str(type_ or "").lower().strip(),
        str(slug or "").lower().strip(),
        str(site or "").lower().strip(),
        str(tenant or "").lower().strip(),
    )


def cache_status(type_: str, slug: str, *, use_cache: bool = True,
                 site: Optional[str] = None, tenant: Optional[str] = None) -> dict:
    if not use_cache:
        return {"status": "bypassed", "age_seconds": None}
    key = _cache_key(type_, slug, site=site, tenant=tenant)
    with _cache_state.lock:
        entry = _cache_state.cache.get(key)
        if not entry:
            return {"status": "miss", "age_seconds": None}
        age = max(0, int(time.time() - entry.fetched_at))
        if age < _cache_state.ttl_seconds:
            return {"status": "hit", "age_seconds": age}
        return {"status": "stale", "age_seconds": age}


def _build(
    *, source: str, company: str, external_id: str, title: str, url: str,
    description_html: Optional[str] = None, description_text: Optional[str] = None,
    location_raw: str = "", posted_at=None, recruiter=None, extra: Optional[dict] = None,
    employment_hint: Optional[str] = None,
) -> NormalizedJob:
    text = description_text or strip_html(description_html or "")
    city, state, country = parse_location(location_raw)
    sal_min, sal_max, currency = parse_salary(text[:4000]) if text else (None, None, None)
    title_norm = normalize_title(title)
    company_norm = normalize_company_name(company)
    dk = dedupe_key(company_norm, title_norm, location_raw or "")
    return NormalizedJob(
        source=source,
        external_job_id=str(external_id),
        canonical_url=url,
        url_hash=url_hash(url) if url else None,
        title=title,
        normalized_title=title_norm,
        company_name_raw=company,
        company_normalized=company_norm,
        location_raw=location_raw,
        city=city, state=state, country=country,
        remote_type=guess_remote_type(location_raw, text),
        employment_type=guess_employment_type(title, text, employment_hint),
        level_guess=guess_level(title, text),
        salary_min=sal_min, salary_max=sal_max, salary_currency=currency,
        description_html=description_html,
        description_text=text,
        posted_at=parse_iso_datetime(posted_at),
        recruiter_blob_json=recruiter,
        source_metadata_json=extra or {},
        dedupe_key=dk,
    )


# ---------------------------------------------------------------------------
# Greenhouse
# ---------------------------------------------------------------------------

def fetch_greenhouse(slug: str, *, company_name: Optional[str] = None,
                     timeout: float = 15.0) -> List[NormalizedJob]:
    """Greenhouse public board: boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    company = company_name or slug
    with httpx.Client(timeout=timeout, headers={"User-Agent": _UA}) as client:
        r = client.get(url)
        r.raise_for_status()
        payload = r.json()
    jobs = []
    for j in payload.get("jobs", []):
        recruiter = None
        if j.get("metadata"):
            recruiter = {"metadata": j["metadata"]}
        jobs.append(_build(
            source="greenhouse",
            company=company,
            external_id=j.get("id"),
            title=j.get("title") or "",
            url=j.get("absolute_url") or "",
            description_html=j.get("content") or "",
            location_raw=(j.get("location") or {}).get("name", ""),
            posted_at=j.get("updated_at") or j.get("first_published"),
            recruiter=recruiter,
            extra={"departments": [d.get("name") for d in j.get("departments", [])],
                   "offices": [o.get("name") for o in j.get("offices", [])]},
        ))
    return jobs


# ---------------------------------------------------------------------------
# Lever
# ---------------------------------------------------------------------------

def fetch_lever(slug: str, *, company_name: Optional[str] = None,
                timeout: float = 15.0) -> List[NormalizedJob]:
    """Lever public postings API: api.lever.co/v0/postings/{slug}?mode=json"""
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    company = company_name or slug
    with httpx.Client(timeout=timeout, headers={"User-Agent": _UA}) as client:
        r = client.get(url)
        r.raise_for_status()
        payload = r.json()
    jobs = []
    for j in payload:
        cats = j.get("categories") or {}
        desc_html = j.get("descriptionPlain") or j.get("description") or ""
        lists = j.get("lists") or []
        if lists:
            desc_html += "\n" + "\n".join(
                f"<h3>{i.get('text','')}</h3>{i.get('content','')}" for i in lists
            )
        additional = j.get("additionalPlain") or ""
        text_blob = (j.get("descriptionPlain") or "") + "\n" + additional
        jobs.append(_build(
            source="lever",
            company=company,
            external_id=j.get("id"),
            title=j.get("text") or "",
            url=j.get("hostedUrl") or j.get("applyUrl") or "",
            description_html=desc_html,
            description_text=text_blob if text_blob.strip() else None,
            location_raw=cats.get("location") or "",
            posted_at=j.get("createdAt"),
            employment_hint=cats.get("commitment"),
            extra={"team": cats.get("team"), "department": cats.get("department"),
                   "tags": j.get("tags", [])},
        ))
    return jobs


# ---------------------------------------------------------------------------
# Ashby — uses the REST posting-api which returns descriptions in one call.
# The older ``non-user-graphql`` endpoint omits descriptions; do not use it.
# ---------------------------------------------------------------------------

def fetch_ashby(slug: str, *, company_name: Optional[str] = None,
                timeout: float = 20.0) -> List[NormalizedJob]:
    """Ashby public REST: ``/posting-api/job-board/{slug}?includeCompensation=true``.

    Returns a single JSON payload with full ``descriptionHtml`` per posting, so
    no per-job follow-up request is required.
    """
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
    company = company_name or slug
    with httpx.Client(timeout=timeout, headers={"User-Agent": _UA}) as client:
        r = client.get(url)
        r.raise_for_status()
        payload = r.json()

    jobs: List[NormalizedJob] = []
    for j in payload.get("jobs", []) or []:
        if j.get("isListed") is False:
            continue
        # Prefer plain-text description when Ashby exposes it; fall back to HTML.
        desc_html = j.get("descriptionHtml") or ""
        desc_text = j.get("descriptionPlain") or None
        address = j.get("address") or {}
        loc_parts = [
            address.get("postalAddress", {}).get("addressLocality"),
            address.get("postalAddress", {}).get("addressRegion"),
            address.get("postalAddress", {}).get("addressCountry"),
        ]
        location_raw = j.get("location") or ", ".join([p for p in loc_parts if p])
        job_url = j.get("jobUrl") or j.get("applyUrl") or f"https://jobs.ashbyhq.com/{slug}/{j.get('id')}"
        jobs.append(_build(
            source="ashby",
            company=company,
            external_id=j.get("id"),
            title=j.get("title") or "",
            url=job_url,
            description_html=desc_html,
            description_text=desc_text,
            location_raw=location_raw or "",
            posted_at=j.get("publishedAt") or j.get("updatedAt"),
            employment_hint=j.get("employmentType"),
            extra={
                "team": j.get("team"),
                "department": j.get("department"),
                "compensation": j.get("compensation"),
                "is_remote": j.get("isRemote"),
                "secondary_locations": j.get("secondaryLocations") or [],
                "apply_url": j.get("applyUrl"),
            },
        ))
    return jobs


# ---------------------------------------------------------------------------
# Workday — public cxs endpoint
# ---------------------------------------------------------------------------

def fetch_workday(tenant: str, site: str, *, company_name: Optional[str] = None,
                  max_pages: int = 10, timeout: float = 20.0) -> List[NormalizedJob]:
    """Workday public CXS API.

    ``tenant`` is the subdomain (e.g. ``nvidia``) and ``site`` is the site id
    (e.g. ``NVIDIAExternalCareerSite``). The listing endpoint is POST
    ``https://{tenant}.wd1.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs``
    with an empty ``searchText``. Each page returns 20 postings plus pagination
    metadata; we follow the ``externalPath`` to fetch descriptions.

    Workday tenants live on one of a handful of region domains (wd1, wd3, wd5,
    wd103 …). We try each until one responds 200.
    """
    company = company_name or tenant
    subdomains = ["wd1", "wd3", "wd5", "wd103", "wd12", "wd102"]
    base: Optional[str] = None
    headers = {"User-Agent": _UA, "Accept": "application/json",
               "Content-Type": "application/json"}
    jobs: List[NormalizedJob] = []
    with httpx.Client(timeout=timeout, headers=headers) as client:
        for sub in subdomains:
            candidate = f"https://{tenant}.{sub}.myworkdayjobs.com/wday/cxs/{tenant}/{site}"
            try:
                r = client.post(f"{candidate}/jobs",
                                json={"appliedFacets": {}, "limit": 20,
                                      "offset": 0, "searchText": ""})
                if r.status_code == 200:
                    base = candidate
                    break
            except Exception:
                continue
        if not base:
            return []

        offset = 0
        for _ in range(max_pages):
            r = client.post(f"{base}/jobs",
                            json={"appliedFacets": {}, "limit": 20,
                                  "offset": offset, "searchText": ""})
            if r.status_code != 200:
                break
            data = r.json()
            postings = data.get("jobPostings") or []
            if not postings:
                break
            for p in postings:
                external_path = p.get("externalPath") or ""
                detail_url = f"{base}{external_path}" if external_path else ""
                detail = {}
                if detail_url:
                    try:
                        dr = client.get(detail_url)
                        if dr.status_code == 200:
                            detail = dr.json().get("jobPostingInfo") or {}
                    except Exception:
                        detail = {}
                external_id = p.get("bulletFields", [None])[0] or p.get("title") or external_path
                public_url = detail.get("externalUrl") or (
                    f"https://{tenant}.{base.split('//')[1].split('.')[1]}.myworkdayjobs.com"
                    f"/{site}{external_path}" if external_path else ""
                )
                jobs.append(_build(
                    source="workday",
                    company=company,
                    external_id=str(external_id),
                    title=p.get("title") or detail.get("title") or "",
                    url=public_url or detail_url,
                    description_html=detail.get("jobDescription") or "",
                    location_raw=p.get("locationsText") or detail.get("location") or "",
                    posted_at=detail.get("postedOn") or detail.get("startDate"),
                    employment_hint=detail.get("timeType"),
                    extra={"job_req_id": detail.get("jobReqId"),
                           "site": site, "tenant": tenant},
                ))
            total = data.get("total") or 0
            offset += 20
            if offset >= total:
                break
    return jobs


# ---------------------------------------------------------------------------
# SmartRecruiters
# ---------------------------------------------------------------------------

def fetch_smartrecruiters(slug: str, *, company_name: Optional[str] = None,
                          timeout: float = 15.0) -> List[NormalizedJob]:
    """SmartRecruiters public postings: ``api.smartrecruiters.com/v1/companies/{slug}/postings``."""
    company = company_name or slug
    list_url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    headers = {"User-Agent": _UA, "Accept": "application/json"}
    jobs: List[NormalizedJob] = []
    with httpx.Client(timeout=timeout, headers=headers) as client:
        offset = 0
        for _ in range(20):  # hard cap: 2000 postings per company
            r = client.get(list_url, params={"limit": 100, "offset": offset})
            if r.status_code != 200:
                break
            data = r.json()
            items = data.get("content") or []
            if not items:
                break
            for item in items:
                pid = item.get("id")
                detail = {}
                try:
                    dr = client.get(f"{list_url}/{pid}")
                    if dr.status_code == 200:
                        detail = dr.json()
                except Exception:
                    detail = {}
                sections = (detail.get("jobAd") or {}).get("sections") or {}

                def _sec(key: str) -> str:
                    part = sections.get(key) or {}
                    return part.get("text") or ""

                desc_html = "\n".join(filter(None, [
                    _sec("companyDescription"),
                    _sec("jobDescription"),
                    _sec("qualifications"),
                    _sec("additionalInformation"),
                ]))
                loc = item.get("location") or {}
                loc_str = ", ".join(filter(None, [loc.get("city"), loc.get("region"),
                                                  loc.get("country")]))
                jobs.append(_build(
                    source="smartrecruiters",
                    company=company,
                    external_id=pid or item.get("uuid") or item.get("name"),
                    title=item.get("name") or "",
                    url=(item.get("ref") or "").replace("api.smartrecruiters.com/v1/",
                                                         "careers.smartrecruiters.com/")
                        or f"https://jobs.smartrecruiters.com/{slug}/{pid}",
                    description_html=desc_html,
                    location_raw=loc_str,
                    posted_at=item.get("releasedDate") or item.get("createdOn"),
                    employment_hint=(item.get("typeOfEmployment") or {}).get("id"),
                    extra={"industry": item.get("industry"),
                           "department": item.get("department")},
                ))
            total = data.get("totalFound") or 0
            offset += 100
            if offset >= total:
                break
    return jobs


# ---------------------------------------------------------------------------
# Workable
# ---------------------------------------------------------------------------

def fetch_workable(slug: str, *, company_name: Optional[str] = None,
                   timeout: float = 15.0) -> List[NormalizedJob]:
    """Workable public API: ``{slug}.workable.com/spi/v3/jobs`` (list), then per-job detail."""
    company = company_name or slug
    base = f"https://{slug}.workable.com"
    headers = {"User-Agent": _UA, "Accept": "application/json"}
    jobs: List[NormalizedJob] = []
    with httpx.Client(timeout=timeout, headers=headers) as client:
        r = client.get(f"{base}/spi/v3/jobs", params={"details": "true"})
        if r.status_code != 200:
            return []
        data = r.json()
        for j in data.get("jobs", []) or []:
            shortcode = j.get("shortcode") or j.get("id")
            desc_html = j.get("description") or ""
            requirements = j.get("requirements") or ""
            benefits = j.get("benefits") or ""
            combined = "\n".join(filter(None, [desc_html, requirements, benefits]))
            loc = j.get("location") or {}
            loc_str = ", ".join(filter(None, [loc.get("city"), loc.get("region"),
                                              loc.get("country")]))
            jobs.append(_build(
                source="workable",
                company=company,
                external_id=shortcode,
                title=j.get("title") or "",
                url=j.get("url") or f"{base}/j/{shortcode}",
                description_html=combined,
                location_raw=loc_str,
                posted_at=j.get("published_on") or j.get("created_at"),
                employment_hint=j.get("employment_type"),
                extra={"department": j.get("department"),
                       "telecommuting": j.get("telecommuting")},
            ))
    return jobs


# ---------------------------------------------------------------------------
# Recruitee
# ---------------------------------------------------------------------------

def fetch_recruitee(slug: str, *, company_name: Optional[str] = None,
                    timeout: float = 15.0) -> List[NormalizedJob]:
    """Recruitee public offers: ``{slug}.recruitee.com/api/offers/``."""
    company = company_name or slug
    url = f"https://{slug}.recruitee.com/api/offers/"
    headers = {"User-Agent": _UA, "Accept": "application/json"}
    jobs: List[NormalizedJob] = []
    with httpx.Client(timeout=timeout, headers=headers) as client:
        r = client.get(url)
        if r.status_code != 200:
            return []
        data = r.json()
        for o in data.get("offers", []) or []:
            desc_html = (o.get("description") or "") + "\n" + (o.get("requirements") or "")
            loc_str = ", ".join(filter(None, [o.get("city"), o.get("state_code") or o.get("state"),
                                              o.get("country_code") or o.get("country")]))
            jobs.append(_build(
                source="recruitee",
                company=company,
                external_id=o.get("id"),
                title=o.get("title") or "",
                url=o.get("careers_url") or o.get("url") or "",
                description_html=desc_html,
                location_raw=loc_str,
                posted_at=o.get("published_at") or o.get("created_at"),
                employment_hint=o.get("employment_type_code") or o.get("employment_type"),
                extra={"department": o.get("department"),
                       "remote": o.get("remote")},
            ))
    return jobs


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def fetch_source(type_: str, slug: str, company_name: Optional[str] = None,
                 **kwargs) -> List[NormalizedJob]:
    use_cache = kwargs.pop("use_cache", True)
    site = kwargs.get("site")
    tenant = kwargs.get("tenant")
    key = _cache_key(type_, slug, site=site, tenant=tenant)
    if use_cache:
        with _cache_state.lock:
            entry = _cache_state.cache.get(key)
            if entry and (time.time() - entry.fetched_at) < _cache_state.ttl_seconds:
                return copy.deepcopy(entry.payload)

    if type_ == "greenhouse":
        records = fetch_greenhouse(slug, company_name=company_name)
    elif type_ == "lever":
        records = fetch_lever(slug, company_name=company_name)
    elif type_ == "ashby":
        records = fetch_ashby(slug, company_name=company_name)
    elif type_ == "workday":
        site = kwargs.get("site") or slug
        tenant = kwargs.get("tenant") or slug
        records = fetch_workday(tenant, site, company_name=company_name)
    elif type_ == "smartrecruiters":
        records = fetch_smartrecruiters(slug, company_name=company_name)
    elif type_ == "workable":
        records = fetch_workable(slug, company_name=company_name)
    elif type_ == "recruitee":
        records = fetch_recruitee(slug, company_name=company_name)
    else:
        raise ValueError(f"Unsupported ATS type: {type_}")

    with _cache_state.lock:
        _cache_state.cache[key] = _CacheEntry(time.time(), copy.deepcopy(list(records)))
    return records
