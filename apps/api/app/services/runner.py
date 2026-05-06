"""End-to-end run pipeline: scrape -> normalize -> persist -> tier -> contacts ->
prefilter -> visa -> LLM -> rank -> diff events.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import traceback
from datetime import datetime
from typing import List, Dict, Any

from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import (
    Job, Company, ScrapeRun, ScrapeRunJob, UserProfile, Screening, JobRanking,
)
from ..profile.schema import Profile
from ..scrapers import ats as ats_scraper
from ..scrapers import jobspy_daemon
from ..services.sources import (
    enabled_ats_sources, enabled_workday_sources, jobspy_config,
)
from ..screener import prefilter as pf
from ..screener.lmstudio import lmstudio
from ..enrichment import visa as visa_mod
from ..enrichment import tier as tier_mod
from ..enrichment import contacts as contacts_mod
from ..ranking import engine as rank_engine
from ..services.diffing import snapshot_active, emit_events
from ..services import run_lock
from ..utils.normalize import normalize_company_name
from ..utils.location_match import job_matches_location_terms, normalize_location_terms


log = logging.getLogger("joby.runner")
MAX_CONTACT_DISCOVERY_JOBS = 250


def reconcile_incomplete_runs() -> int:
    db = SessionLocal()
    try:
        rows = db.query(ScrapeRun).filter(ScrapeRun.status.in_(["pending", "running"])).all()
        if not rows:
            return 0
        now = datetime.utcnow()
        for row in rows:
            row.status = "failed"
            row.finished_at = now
            row.error_json = {"error": "run interrupted by process restart"}
        db.commit()
        return len(rows)
    finally:
        db.close()


def _push_event(db: Session, run: ScrapeRun, stage: str, message: str = "",
                extra: Dict[str, Any] | None = None) -> None:
    stats = dict(run.stats_json or {})
    events = list(stats.get("events", []))
    events.append({
        "t": datetime.utcnow().isoformat(),
        "stage": stage,
        "message": message,
        **(extra or {}),
    })
    stats["events"] = events
    run.stats_json = stats
    db.commit()


def _upsert_company(db: Session, name: str) -> Company:
    norm = normalize_company_name(name)
    row = db.query(Company).filter(Company.normalized_name == norm).first()
    if row:
        return row
    row = Company(name=name, normalized_name=norm)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _upsert_job(db: Session, nj: dict, now: datetime) -> tuple[Job, bool]:
    q = db.query(Job)
    row = None
    if nj.get("external_job_id"):
        row = q.filter(Job.source == nj["source"],
                       Job.external_job_id == nj["external_job_id"]).first()
    if not row and nj.get("url_hash"):
        row = q.filter(Job.url_hash == nj["url_hash"]).first()
    if not row and nj.get("dedupe_key"):
        row = q.filter(Job.dedupe_key == nj["dedupe_key"]).first()

    company = _upsert_company(
        db, nj.get("company_name_raw") or nj.get("company_normalized") or "Unknown")

    fields = dict(
        source=nj["source"],
        external_job_id=nj.get("external_job_id"),
        canonical_url=nj.get("canonical_url"),
        url_hash=nj.get("url_hash"),
        title=nj.get("title") or "",
        normalized_title=nj.get("normalized_title"),
        company_id=company.id,
        company_name_raw=nj.get("company_name_raw"),
        location_raw=nj.get("location_raw"),
        city=nj.get("city"), state=nj.get("state"), country=nj.get("country"),
        remote_type=nj.get("remote_type"),
        employment_type=nj.get("employment_type"),
        level_guess=nj.get("level_guess"),
        salary_min=nj.get("salary_min"),
        salary_max=nj.get("salary_max"),
        salary_currency=nj.get("salary_currency"),
        description_html=nj.get("description_html"),
        description_text=nj.get("description_text"),
        posted_at=nj.get("posted_at"),
        recruiter_blob_json=nj.get("recruiter_blob_json"),
        source_metadata_json=nj.get("source_metadata_json"),
        dedupe_key=nj.get("dedupe_key"),
        last_seen_at=now,
        is_active=True,
    )
    is_new = row is None
    if row:
        for k, v in fields.items():
            setattr(row, k, v)
        if row.closed_at is not None or row.is_active is False:
            row.closed_at = None
            row.is_active = True
    else:
        row = Job(**fields, first_seen_at=now)
        db.add(row)
    db.commit()
    db.refresh(row)
    return row, is_new


def _record_run_jobs(db: Session, run_id: int, jobs: List[Job], newly_inserted: set[int]) -> int:
    if not jobs:
        return 0
    job_ids = [job.id for job in jobs]
    existing = {
        row[0]
        for row in db.query(ScrapeRunJob.job_id)
        .filter(ScrapeRunJob.run_id == run_id, ScrapeRunJob.job_id.in_(job_ids))
        .all()
    }
    created = 0
    for job in jobs:
        if job.id in existing:
            continue
        db.add(ScrapeRunJob(
            run_id=run_id,
            job_id=job.id,
            source=job.source,
            is_new=job.id in newly_inserted,
        ))
        created += 1
    if created:
        db.commit()
    return created


def _active_profile(db: Session) -> tuple[UserProfile, Profile]:
    """Return the active profile, auto-creating a sensible default if the
    user hasn't saved one yet. No-blocker principle: the pipeline must always
    be runnable, even on a brand-new install.
    """
    up = db.query(UserProfile).filter(UserProfile.is_active == True).first()  # noqa: E712
    if up:
        return up, Profile.model_validate(up.profile_json)
    from ..profile.presets import get_preset
    default = get_preset("custom")  # blank-but-valid profile
    up = UserProfile(name="default", is_active=True,
                     profile_json=default.model_dump())
    db.add(up)
    db.commit()
    db.refresh(up)
    return up, default


def _llm_system_user(job: Job, profile: Profile) -> tuple[str, str]:
    system = (
        "You are a job-screening assistant. Output ONLY JSON matching this schema: "
        "{overall_recommendation: one of [strong_yes, yes, maybe, no], "
        "fit_summary: string, must_have_matches: [string], must_have_gaps: [string], "
        "nice_to_have_matches: [string], yoe_assessment: string, location_assessment: string, "
        "employment_type_assessment: string, major_relevance: string, visa_text_signal: one of "
        "[supports, excludes, silent], confidence: number in [0,1], reasons: [string]}."
    )
    user = (
        f"PROFILE:\n"
        f"roles={profile.targeting.target_roles}; levels={profile.targeting.target_levels}; "
        f"must={profile.resume.must_have_skills}; nice={profile.resume.nice_to_have_skills}; "
        f"yoe={profile.resume.years_experience}; remote_pref={profile.targeting.remote_preference}; "
        f"locations={[l.name for l in profile.targeting.target_locations]}.\n\n"
        f"JOB:\nTitle: {job.title}\nCompany: {job.company_name_raw}\n"
        f"Location: {job.location_raw}\nEmployment: {job.employment_type}\n"
        f"Level: {job.level_guess}\n"
        f"Description:\n{(job.description_text or '')[:4500]}"
    )
    return system, user


def _profile_with_search_overrides(profile: Profile, search: dict | None) -> Profile:
    if not search:
        return profile

    data = profile.model_dump()
    intent = _search_intent(search)
    _apply_search_intent(data, intent)

    targeting = data.setdefault("targeting", {})
    sources_cfg = data.setdefault("sources", {})

    query = str(search.get("query") or "").strip()
    if query:
        targeting["target_roles"] = [query]
        sources_cfg["jobspy_search_terms"] = [query]

    locations = [str(v).strip() for v in (search.get("locations") or []) if str(v).strip()]
    if locations:
        sources_cfg["jobspy_locations"] = locations
        targeting["target_locations"] = [
            {"name": location, "remote_ok": location.lower() == "remote"}
            for location in locations
        ]

    if search.get("results_per_source") is not None:
        sources_cfg["jobspy_results_per_term"] = int(search["results_per_source"])

    if "posted_within_days" in search:
        posted_within_days = search.get("posted_within_days")
        targeting["posted_within_days"] = int(posted_within_days) if posted_within_days is not None else None

    selected_sources = set(search.get("sources") or [])
    if selected_sources:
        sources_cfg["enable_jobspy"] = True
        sources_cfg["enable_ats"] = False
        sources_cfg["enable_workday"] = False

    return Profile.model_validate(data)


def _filter_search_results_by_location(jobs: List[dict], search_request: Dict[str, Any] | None) -> tuple[List[dict], int]:
    location_terms = normalize_location_terms((search_request or {}).get("locations") or [])
    if not location_terms:
        return jobs, 0
    filtered = [job for job in jobs if job_matches_location_terms(job, location_terms)]
    return filtered, max(0, len(jobs) - len(filtered))


def _search_intent(search: dict | None) -> str:
    intent = str((search or {}).get("intent") or "match")
    return intent if intent in {"explore", "match", "strict"} else "match"


def _apply_search_intent(profile_data: dict, intent: str) -> None:
    scoring = profile_data.setdefault("scoring", {})
    resume = profile_data.setdefault("resume", {})
    if intent == "explore":
        resume["must_have_skills"] = []
        resume["nice_to_have_skills"] = []
        scoring["w_fit"] = 0.35
        scoring["w_opportunity"] = 0.35
        scoring["w_urgency"] = 0.30
        scoring["visa_hard_filter"] = False
    elif intent == "strict":
        scoring["w_fit"] = 0.65
        scoring["w_opportunity"] = 0.25
        scoring["w_urgency"] = 0.10


def _source_detail(key: str, type_: str, label: str, *, status: str = "ok",
                   count: int | None = None, duration_ms: int | None = None,
                   cache: dict | None = None, error: str | None = None) -> dict:
    detail = {
        "key": key,
        "type": type_,
        "label": label,
        "status": status,
        "count": count,
        "duration_ms": duration_ms,
    }
    if cache:
        detail["cache"] = cache
    if error:
        detail["error"] = error
    return detail


def _note_cache(cache_summary: Dict[str, Any], cache: dict | None) -> None:
    if not cache:
        return
    cache_summary["total_queries"] += 1
    status = str(cache.get("status") or "").lower()
    if status in ("hit", "miss", "stale", "bypassed"):
        cache_summary[status] += 1


def _jobspy_site_counts(jobs: List[dict], sites: List[str]) -> Dict[str, int]:
    counts = {site: 0 for site in sites}
    for job in jobs:
        source = str(job.get("source") or "")
        if not source.startswith("jobspy:"):
            continue
        site = source.split(":", 1)[1]
        counts[site] = counts.get(site, 0) + 1
    return counts


async def _llm_screen_batch(jobs: List[Job], profile: Profile,
                            model_name: str | None, concurrency: int) -> List[Dict[str, Any]]:
    """Run LLM screening concurrently with a semaphore. Preserves input order."""
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _one(job: Job) -> Dict[str, Any]:
        async with sem:
            system, user = _llm_system_user(job, profile)
            try:
                result = await lmstudio.chat_json(system=system, user=user, max_tokens=700)
            except Exception as e:
                return {"llm_status": "error", "llm_model_name": model_name,
                        "screening_json": None, "error": str(e)}
            if result is None:
                return {"llm_status": "error", "llm_model_name": model_name,
                        "screening_json": None}
            return {"llm_status": "ok", "llm_model_name": model_name,
                    "screening_json": result}

    return await asyncio.gather(*[_one(j) for j in jobs])


def _scrape_all(db: Session, run: ScrapeRun, profile: Profile,
                search_request: Dict[str, Any] | None = None
                ) -> tuple[List[dict], Dict[str, int], Dict[str, dict], Dict[str, Any], List[Dict[str, Any]]]:
    """Run every enabled source and return normalized jobs, counts, metadata, and errors."""
    search_request = search_request or {}
    all_normalized: List[dict] = []
    per_source_counts: Dict[str, int] = {}
    per_source_details: Dict[str, dict] = {}
    cache_summary: Dict[str, Any] = {
        "total_queries": 0,
        "hit": 0,
        "miss": 0,
        "stale": 0,
        "bypassed": 0,
    }
    errors: List[Dict[str, Any]] = []

    # --- ATS scrapers ---------------------------------------------------------
    if profile.sources.enable_ats:
        for s in enabled_ats_sources():
            stype = s.get("type")
            slug = s.get("slug") or s.get("company", "").lower()
            company_name = s.get("company")
            key = f"{stype}:{company_name}"
            use_source_cache = search_request.get("use_cache") is not False
            cache = ats_scraper.cache_status(stype, slug, use_cache=use_source_cache)
            _note_cache(cache_summary, cache)
            started = time.perf_counter()
            _push_event(db, run, "scraping", f"{stype}:{company_name}",
                        extra={"source": stype, "company": company_name,
                               "cache": cache})
            try:
                jobs = ats_scraper.fetch_source(
                    stype, slug, company_name=company_name,
                    use_cache=use_source_cache,
                )
                duration_ms = int((time.perf_counter() - started) * 1000)
                per_source_counts[key] = len(jobs)
                per_source_details[key] = _source_detail(
                    key, stype or "ats", company_name or slug or "unknown",
                    count=len(jobs), duration_ms=duration_ms, cache=cache,
                )
                all_normalized.extend(jobs)
            except Exception as e:
                duration_ms = int((time.perf_counter() - started) * 1000)
                msg = str(e)
                per_source_details[key] = _source_detail(
                    key, stype or "ats", company_name or slug or "unknown",
                    status="error", count=0, duration_ms=duration_ms, error=msg,
                )
                errors.append({"source": stype, "company": company_name, "error": msg})
                _push_event(db, run, "scrape_error", str(e),
                            extra={"source": stype, "company": company_name})

    # --- Workday --------------------------------------------------------------
    if profile.sources.enable_workday:
        for org in enabled_workday_sources():
            tenant = org.get("tenant") or org.get("slug")
            site = org.get("site") or tenant
            company_name = org.get("company") or tenant
            if not tenant or not site:
                continue
            key = f"workday:{company_name}"
            use_source_cache = search_request.get("use_cache") is not False
            cache = ats_scraper.cache_status("workday", tenant, use_cache=use_source_cache,
                                             site=site, tenant=tenant)
            _note_cache(cache_summary, cache)
            started = time.perf_counter()
            _push_event(db, run, "scraping", f"workday:{company_name}",
                        extra={"source": "workday", "company": company_name,
                               "cache": cache})
            try:
                jobs = ats_scraper.fetch_source(
                    "workday", tenant, company_name=company_name,
                    site=site, tenant=tenant, use_cache=use_source_cache,
                )
                duration_ms = int((time.perf_counter() - started) * 1000)
                per_source_counts[key] = len(jobs)
                per_source_details[key] = _source_detail(
                    key, "workday", company_name,
                    count=len(jobs), duration_ms=duration_ms, cache=cache,
                )
                all_normalized.extend(jobs)
            except Exception as e:
                duration_ms = int((time.perf_counter() - started) * 1000)
                msg = str(e)
                per_source_details[key] = _source_detail(
                    key, "workday", company_name,
                    status="error", count=0, duration_ms=duration_ms, error=msg,
                )
                errors.append({"source": "workday", "company": company_name, "error": msg})
                _push_event(db, run, "scrape_error", str(e),
                            extra={"source": "workday", "company": company_name})

    # --- JobSpy daemon (LinkedIn/Indeed/Glassdoor/ZipRecruiter/Google) -------
    if profile.sources.enable_jobspy:
        cfg = jobspy_config()
        sites = [s for s in jobspy_daemon.SUPPORTED_SITES
                 if cfg.get(s if s != "zip_recruiter" else "ziprecruiter", True)]
        terms = profile.sources.jobspy_search_terms or profile.targeting.target_roles or ["software engineer"]
        locations = profile.sources.jobspy_locations or ["United States"]
        results_per = max(5, int(profile.sources.jobspy_results_per_term or 30))
        hours_old = None if profile.targeting.posted_within_days is None else max(1, profile.targeting.posted_within_days * 24)
        use_jobspy_cache = search_request.get("use_cache") is not False
        for term in terms[:8]:  # hard cap to keep runs bounded
            for loc in locations[:4]:
                key = f"jobspy:{term}@{loc}"
                cache = (
                    jobspy_daemon.cache_status(sites, term, loc)
                    if use_jobspy_cache
                    else {"status": "bypassed", "age_seconds": None}
                )
                _note_cache(cache_summary, cache)
                started = time.perf_counter()
                _push_event(db, run, "scraping", f"jobspy:{term}@{loc}",
                            extra={"source": "jobspy", "term": term,
                                   "location": loc, "cache": cache})
                try:
                    jobs = jobspy_daemon.fetch_jobspy(
                        sites=sites, search_term=term, location=loc,
                        results_wanted=results_per, hours_old=hours_old,
                    )
                    duration_ms = int((time.perf_counter() - started) * 1000)
                    per_source_counts[key] = len(jobs)
                    per_source_details[key] = _source_detail(
                        key, "jobspy", f"{term}@{loc}",
                        count=len(jobs), duration_ms=duration_ms, cache=cache,
                    )
                    per_source_details[key]["type"] = "jobspy_bundle"
                    for site, count in _jobspy_site_counts(jobs, sites).items():
                        site_key = f"jobspy:{site}:{term}@{loc}"
                        per_source_counts[site_key] = count
                        per_source_details[site_key] = _source_detail(
                            site_key, "jobspy_site", f"{site.replace('_', ' ')}: {term}@{loc}",
                            status="ok" if count else "empty",
                            count=count, duration_ms=duration_ms, cache=cache,
                        )
                    all_normalized.extend(jobs)
                except jobspy_daemon.JobSpyUnavailable as e:
                    duration_ms = int((time.perf_counter() - started) * 1000)
                    msg = str(e)
                    per_source_details[key] = _source_detail(
                        key, "jobspy", f"{term}@{loc}",
                        status="error", count=0, duration_ms=duration_ms,
                        cache=cache, error=msg,
                    )
                    errors.append({"source": "jobspy", "error": msg})
                    _push_event(db, run, "scrape_error", str(e),
                                extra={"source": "jobspy"})
                    break  # stop looping; install jobspy first
                except Exception as e:
                    duration_ms = int((time.perf_counter() - started) * 1000)
                    msg = str(e)
                    per_source_details[key] = _source_detail(
                        key, "jobspy", f"{term}@{loc}",
                        status="error", count=0, duration_ms=duration_ms,
                        cache=cache, error=msg,
                    )
                    errors.append({"source": "jobspy", "term": term,
                                   "location": loc, "error": msg})

    return all_normalized, per_source_counts, per_source_details, cache_summary, errors


def _run_pipeline(run_id: int, watch_id: int | None = None) -> None:
    if not run_lock.try_acquire():
        # Another pipeline is already running — mark this run as skipped.
        db = SessionLocal()
        try:
            run = db.get(ScrapeRun, run_id)
            if run:
                run.status = "skipped"
                run.finished_at = datetime.utcnow()
                run.error_json = {"error": "another pipeline is already running"}
                db.commit()
        finally:
            db.close()
        return

    db = SessionLocal()
    try:
        run = db.get(ScrapeRun, run_id)
        if not run:
            return
        run.status = "running"
        db.commit()

        search_request = dict((run.stats_json or {}).get("search") or {})
        search_intent = _search_intent(search_request)

        _push_event(db, run, "loading_profile")
        up, profile = _active_profile(db)
        if search_request:
            profile = _profile_with_search_overrides(profile, search_request)
            if search_request.get("use_cache") is False:
                jobspy_daemon.clear_cache()
            _push_event(db, run, "search_config", search_request.get("query", ""),
                        extra={"search": search_request})
            selected_sources = set(search_request.get("sources") or [])
            skipped_sources = sorted(selected_sources.intersection({"ats", "workday"}))
            if skipped_sources:
                _push_event(
                    db, run, "search_scope",
                    "Query search uses web search; tracked boards refresh separately.",
                    extra={"skipped_sources": skipped_sources},
                )

        pre_snapshot = snapshot_active(db)

        _push_event(db, run, "loading_sources")
        all_normalized, per_source_counts, per_source_details, cache_summary, errors = _scrape_all(
            db, run, profile, search_request
        )

        cache_summary["used_cache"] = search_request.get("use_cache") is not False
        cache_summary["freshness_window_hours"] = (
            None if profile.targeting.posted_within_days is None
            else max(1, profile.targeting.posted_within_days * 24)
        )

        run.source_summary_json = {
            "per_source": per_source_counts,
            "details": per_source_details,
            "cache": cache_summary,
        }
        db.commit()

        _push_event(db, run, "normalizing", f"{len(all_normalized)} raw jobs")

        seen = set()
        deduped = []
        for j in all_normalized:
            k1 = (j.get("source"), j.get("external_job_id"))
            k2 = j.get("dedupe_key")
            if k1 in seen or (k2 and k2 in seen):
                continue
            if k1[1]:
                seen.add(k1)
            if k2:
                seen.add(k2)
            deduped.append(j)

        _push_event(db, run, "deduplicating", f"{len(deduped)} after dedupe")

        deduped, location_filtered_out = _filter_search_results_by_location(deduped, search_request)
        if location_filtered_out:
            _push_event(
                db, run, "normalizing",
                f"{len(deduped)} after location gate",
                extra={"location_filtered_out": location_filtered_out},
            )
        else:
            location_filtered_out = 0

        now = datetime.utcnow()
        persisted: List[Job] = []
        newly_inserted: set[int] = set()
        for nj in deduped:
            try:
                row, is_new = _upsert_job(db, nj, now)
                persisted.append(row)
                if is_new:
                    newly_inserted.add(row.id)
            except Exception as e:
                db.rollback()
                errors.append({"stage": "persist", "error": str(e)})

        linked = _record_run_jobs(db, run.id, persisted, newly_inserted)
        _push_event(db, run, "persisted", f"{len(persisted)} jobs upserted", extra={"run_jobs": linked})

        _push_event(db, run, "tier_classifying")
        try:
            company_ids = {j.company_id for j in persisted if j.company_id}
            if company_ids:
                for c in db.query(Company).filter(Company.id.in_(company_ids)).all():
                    t, src = tier_mod.classify(c, db=db)
                    if c.company_tier != t or c.tier_source != src:
                        c.company_tier = t
                        c.tier_source = src
                db.commit()
        except Exception as e:
            errors.append({"stage": "tier", "error": str(e)})

        _push_event(db, run, "contact_discovery")
        try:
            contact_jobs = persisted
            if len(contact_jobs) > MAX_CONTACT_DISCOVERY_JOBS:
                _push_event(
                    db, run, "contact_discovery_limited",
                    f"processing first {MAX_CONTACT_DISCOVERY_JOBS} of {len(contact_jobs)} jobs",
                )
                contact_jobs = contact_jobs[:MAX_CONTACT_DISCOVERY_JOBS]
            for j in contact_jobs:
                contacts_mod.discover_for_job(db, j)
        except Exception as e:
            errors.append({"stage": "contacts", "error": str(e)})

        # ----- screening + ranking ------------------------------------------
        mode = profile.screening.mode
        concurrency = max(1, int(profile.screening.llm_concurrency))
        per_run_cap = max(0, int(profile.screening.llm_per_run_cap))

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        llm_available = False
        llm_model: str | None = None
        if mode != "heuristic":
            try:
                h = loop.run_until_complete(lmstudio.health())
                llm_available = bool(h.get("available"))
                llm_model = h.get("model")
            except Exception:
                llm_available = False
        use_llm = (mode == "llm") or (mode == "auto" and llm_available)
        if mode == "llm" and not llm_available:
            _push_event(db, run, "llm_unavailable",
                        "screening_mode=llm but LM Studio is unreachable; jobs will be marked error")

        _push_event(db, run, "screening",
                    f"mode={mode} llm_available={llm_available} use_llm={use_llm}")

        # Step 1: deterministic prefilter + visa + signals for every persisted job.
        per_job_signals: Dict[int, Dict[str, Any]] = {}
        prefilter_eligible: List[Job] = []
        for job in persisted:
            job_dict = {
                "title": job.title, "location_raw": job.location_raw,
                "city": job.city, "state": job.state, "country": job.country,
                "remote_type": job.remote_type, "employment_type": job.employment_type,
                "level_guess": job.level_guess, "salary_min": job.salary_min,
                "salary_max": job.salary_max, "description_text": job.description_text,
                "posted_at": job.posted_at, "recruiter_blob_json": job.recruiter_blob_json,
            }
            passed, reasons, signals = pf.evaluate(
                job_dict,
                profile,
                strict=search_intent == "strict",
                location_terms=normalize_location_terms(search_request.get("locations") or []),
            )
            signals["search_intent"] = search_intent
            visa_tier, visa_evidence = visa_mod.resolve(
                job_dict, profile, db=db, company_id=job.company_id)
            signals["visa_tier"] = visa_tier
            signals["visa_evidence"] = visa_evidence
            per_job_signals[job.id] = {"passed": passed, "reasons": reasons,
                                       "signals": signals, "job_dict": job_dict}
            if passed and use_llm:
                prefilter_eligible.append(job)

        # Step 2: concurrent LLM screening for eligible jobs.
        llm_results: Dict[int, Dict[str, Any]] = {}
        if use_llm and prefilter_eligible:
            batch = prefilter_eligible if per_run_cap == 0 else prefilter_eligible[:per_run_cap]
            try:
                results = loop.run_until_complete(
                    _llm_screen_batch(batch, profile, llm_model, concurrency)
                )
                for job, res in zip(batch, results):
                    llm_results[job.id] = res
            except Exception as e:
                errors.append({"stage": "llm_batch", "error": str(e)})

        # Step 3: write screening + ranking rows.
        screened = ranked = 0
        for job in persisted:
            ps = per_job_signals[job.id]
            passed: bool = ps["passed"]
            reasons: List[str] = ps["reasons"]
            signals: Dict[str, Any] = ps["signals"]
            job_dict = ps["job_dict"]

            if not use_llm:
                llm_payload = {"llm_status": "disabled" if mode == "heuristic" else "unavailable",
                               "llm_model_name": None, "screening_json": None}
            elif job.id in llm_results:
                llm_payload = llm_results[job.id]
            elif not passed:
                llm_payload = {"llm_status": "skipped", "llm_model_name": None,
                               "screening_json": None}
            else:
                # Eligible but not run because of per_run_cap.
                llm_payload = {"llm_status": "capped", "llm_model_name": llm_model,
                               "screening_json": None}

            fields = dict(
                prefilter_passed=passed,
                prefilter_reasons_json={"reasons": reasons, "signals": signals},
                llm_status=llm_payload["llm_status"],
                llm_model_name=llm_payload.get("llm_model_name"),
                screening_json=llm_payload.get("screening_json"),
            )
            screening = db.query(Screening).filter(
                Screening.job_id == job.id, Screening.profile_id == up.id
            ).first()
            if screening:
                for k, v in fields.items():
                    setattr(screening, k, v)
            else:
                screening = Screening(job_id=job.id, profile_id=up.id, **fields)
                db.add(screening)
            screened += 1

            company_tier = (job.company.company_tier if job.company else None) or "unknown"
            r = rank_engine.rank(job_dict, profile, signals, signals["visa_tier"], company_tier)
            r["reason_json"]["search_intent"] = search_intent
            ranking = db.query(JobRanking).filter(
                JobRanking.job_id == job.id, JobRanking.profile_id == up.id
            ).first()
            if ranking:
                ranking.fit_score = r["fit_score"]
                ranking.opportunity_score = r["opportunity_score"]
                ranking.urgency_score = r["urgency_score"]
                ranking.composite_score = r["composite_score"]
                ranking.reason_json = r["reason_json"]
                ranking.ranking_version = r["ranking_version"]
                ranking.ranked_at = datetime.utcnow()
            else:
                db.add(JobRanking(job_id=job.id, profile_id=up.id, **r))
            ranked += 1

            if ranked % 50 == 0:
                db.commit()
                _push_event(db, run, "ranking_progress", f"{ranked}/{len(persisted)}")

        db.commit()
        loop.close()

        try:
            events = emit_events(db, watch_id, pre_snapshot, persisted, newly_inserted)
            _push_event(db, run, "diffing", f"{len(events)} job_events")
        except Exception as e:
            errors.append({"stage": "diffing", "error": str(e)})

        _push_event(db, run, "completed",
                    f"persisted={len(persisted)} screened={screened} ranked={ranked}",
                  extra={"per_source": per_source_counts, "cache": cache_summary,
                      "errors": errors})
        run.status = "completed"
        run.finished_at = datetime.utcnow()
        stats = dict(run.stats_json or {})
        stats["totals"] = {"persisted": len(persisted), "screened": screened,
                           "ranked": ranked,
                           "llm_calls": len(llm_results),
                           "mode": mode,
                           "location_filtered_out": location_filtered_out,
                           "intent": search_intent}
        stats["per_source"] = per_source_counts
        stats["cache"] = cache_summary
        if errors:
            run.error_json = {"errors": errors}
        run.stats_json = stats
        db.commit()

    except Exception as e:
        log.exception("pipeline failed")
        try:
            run = db.get(ScrapeRun, run_id)
            if run:
                run.status = "failed"
                run.finished_at = datetime.utcnow()
                run.error_json = {"error": str(e), "trace": traceback.format_exc()[-2000:]}
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
        run_lock.release()


def start_run(trigger_type: str = "manual", watch_id: int | None = None,
              search: dict | None = None) -> int:
    db = SessionLocal()
    try:
        stats = {"events": []}
        if search:
            stats["search"] = search
        run = ScrapeRun(trigger_type=trigger_type, status="pending",
                        stats_json=stats)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
    finally:
        db.close()

    t = threading.Thread(target=_run_pipeline, args=(run_id, watch_id), daemon=True)
    t.start()
    return run_id


def run_pipeline_sync(watch_id: int | None = None, trigger_type: str = "watch",
                      search: dict | None = None) -> int:
    """Blocking variant for schedulers/backfill. Returns run_id."""
    db = SessionLocal()
    try:
        stats = {"events": []}
        if search:
            stats["search"] = search
        run = ScrapeRun(trigger_type=trigger_type, status="pending",
                        stats_json=stats)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
    finally:
        db.close()
    _run_pipeline(run_id, watch_id=watch_id)
    return run_id
