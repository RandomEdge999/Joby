from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, or_, false
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Job, Company, JobRanking, Screening, UserProfile, Contact, ScrapeRun, ScrapeRunJob
from ..services.freshness import sweep as freshness_sweep
from ..profile.schema import Profile
from ..enrichment import eligibility as eligibility_mod
from ..enrichment import trust as trust_mod
from ..utils.location_match import US_LOCATION_TERMS, US_STATE_CODES

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

REMOTE_TYPE_PATTERN = "^(remote|hybrid|onsite|unknown)$"
EMPLOYMENT_TYPE_PATTERN = "^(full_time|internship|co_op|contract)$"
LEVEL_PATTERN = "^(intern|new_grad|entry|mid|senior|lead|unknown)$"
COMPANY_TIER_PATTERN = "^(top|strong|standard|unknown)$"
VISA_TIER_PATTERN = "^(not_applicable|likely|possible|unlikely|unknown)$"

def _location_conditions(location: str):
    terms = [item.strip().lower() for item in location.split(",") if item.strip()]
    conditions = []
    for term in terms:
        if term in US_LOCATION_TERMS:
            conditions.append(or_(
                func.lower(Job.country).in_(["us", "usa", "united states"]),
                func.lower(Job.location_raw).like("%united states%"),
                func.lower(Job.location_raw).like("% usa%"),
                func.lower(Job.location_raw).like("% us%"),
                func.upper(Job.state).in_(US_STATE_CODES),
            ))
        elif term == "remote":
            conditions.append(or_(
                Job.remote_type == "remote",
                func.lower(Job.location_raw).like("%remote%"),
            ))
        else:
            like = f"%{term}%"
            conditions.append(or_(
                func.lower(Job.location_raw).like(like),
                func.lower(Job.city).like(like),
                func.lower(Job.state).like(like),
                func.lower(Job.country).like(like),
            ))
    return conditions


@router.post("/freshness/sweep")
def freshness_sweep_endpoint(db: Session = Depends(get_db)):
    return freshness_sweep(db)

def _profile_from_row(profile: Optional[UserProfile]) -> Optional[Profile]:
    if not profile:
        return None
    try:
        return Profile.model_validate(profile.profile_json)
    except Exception:
        return None


def _serialize(job: Job, ranking: Optional[JobRanking], screening: Optional[Screening],
               company: Optional[Company], profile: Optional[Profile] = None) -> dict:
    return {
        "id": job.id,
        "source": job.source,
        "external_job_id": job.external_job_id,
        "url": job.canonical_url,
        "title": job.title,
        "company": {
            "id": company.id if company else None,
            "name": company.name if company else job.company_name_raw,
            "tier": company.company_tier if company else None,
        } if (company or job.company_name_raw) else None,
        "location": {
            "raw": job.location_raw, "city": job.city, "state": job.state, "country": job.country,
            "remote_type": job.remote_type,
        },
        "employment_type": job.employment_type,
        "level_guess": job.level_guess,
        "salary": {"min": job.salary_min, "max": job.salary_max, "currency": job.salary_currency},
        "posted_at": job.posted_at.isoformat() if job.posted_at else None,
        "first_seen_at": job.first_seen_at.isoformat() if job.first_seen_at else None,
        "last_seen_at": job.last_seen_at.isoformat() if job.last_seen_at else None,
        "is_active": job.is_active,
        "description_text": (job.description_text or "")[:1200],
        "ranking": {
            "fit": ranking.fit_score, "opportunity": ranking.opportunity_score,
            "urgency": ranking.urgency_score, "composite": ranking.composite_score,
            "reason_json": ranking.reason_json,
            "version": ranking.ranking_version,
        } if ranking else None,
        "screening": {
            "prefilter_passed": screening.prefilter_passed,
            "prefilter_reasons": screening.prefilter_reasons_json,
            "llm_status": screening.llm_status,
            "llm_model": screening.llm_model_name,
            "screening_json": screening.screening_json,
        } if screening else None,
        "eligibility": eligibility_mod.summarize(job, company, screening, profile),
        "trust": trust_mod.assess(job, company),
    }


@router.get("")
def list_jobs(
    db: Session = Depends(get_db),
    q: Optional[str] = None,
    role: Optional[str] = None,
    company: Optional[str] = None,
    location: Optional[str] = None,
    remote_type: Optional[str] = Query(None, pattern=REMOTE_TYPE_PATTERN),
    employment_type: Optional[str] = Query(None, pattern=EMPLOYMENT_TYPE_PATTERN),
    level: Optional[str] = Query(None, pattern=LEVEL_PATTERN),
    company_tier: Optional[str] = Query(None, pattern=COMPANY_TIER_PATTERN),
    visa_tier: Optional[str] = Query(None, pattern=VISA_TIER_PATTERN),
    salary_floor: Optional[int] = None,
    posted_within_days: Optional[int] = None,
    active_only: bool = True,
    has_contacts: Optional[bool] = None,
    run_id: Optional[int] = Query(None, ge=1),
    sort: str = Query("composite", pattern="^(composite|posted|fit|urgency)$"),
    page: int = 1,
    page_size: int = Query(50, ge=1, le=200),
):
    profile = db.query(UserProfile).filter(UserProfile.is_active == True).first()  # noqa: E712
    profile_model = _profile_from_row(profile)
    stmt = select(Job).options(selectinload(Job.company))
    strict_run_scope = False
    screening_joined = False
    if run_id is not None:
        run = db.get(ScrapeRun, run_id)
        if not run:
            raise HTTPException(404, "run not found")
        search = dict((run.stats_json or {}).get("search") or {})
        strict_run_scope = search.get("intent") == "strict"
        stmt = stmt.join(ScrapeRunJob, ScrapeRunJob.job_id == Job.id).where(ScrapeRunJob.run_id == run_id)
    if strict_run_scope:
        if profile:
            stmt = stmt.join(
                Screening,
                and_(Screening.job_id == Job.id, Screening.profile_id == profile.id),
            ).where(Screening.prefilter_passed == True)  # noqa: E712
            screening_joined = True
        else:
            stmt = stmt.where(false())
    if active_only:
        stmt = stmt.where(Job.is_active == True)  # noqa: E712
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(
            func.lower(Job.title).like(like),
            func.lower(Job.company_name_raw).like(like),
            func.lower(Job.description_text).like(like),
        ))
    if role:
        stmt = stmt.where(func.lower(Job.title).like(f"%{role.lower()}%"))
    if company or company_tier:
        stmt = stmt.join(Company, Job.company_id == Company.id, isouter=True)
    if company:
        like = f"%{company.lower()}%"
        stmt = stmt.where(
            or_(func.lower(Company.name).like(like),
                func.lower(Job.company_name_raw).like(like))
        )
    if location:
        conditions = _location_conditions(location)
        if conditions:
            stmt = stmt.where(or_(*conditions))
    if remote_type:
        stmt = stmt.where(Job.remote_type == remote_type)
    if employment_type:
        stmt = stmt.where(Job.employment_type == employment_type)
    if level:
        if level == "entry":
            stmt = stmt.where(Job.level_guess.in_(["entry", "new_grad", "unknown"]))
        elif level in {"intern", "new_grad", "mid"}:
            stmt = stmt.where(Job.level_guess.in_([level, "unknown"]))
        else:
            stmt = stmt.where(Job.level_guess == level)
    if company_tier:
        stmt = stmt.where(Company.company_tier == company_tier)
    if visa_tier:
        if profile:
            if not screening_joined:
                stmt = stmt.join(
                    Screening,
                    and_(Screening.job_id == Job.id,
                         Screening.profile_id == profile.id),
                )
                screening_joined = True
            stmt = stmt.where(
                Screening.prefilter_reasons_json["signals"]["visa_tier"].as_string() == visa_tier
            )
        else:
            stmt = stmt.where(false())
    if salary_floor:
        stmt = stmt.where(Job.salary_min >= salary_floor)
    if posted_within_days:
        cutoff = datetime.utcnow() - timedelta(days=posted_within_days)
        stmt = stmt.where(or_(Job.posted_at >= cutoff, Job.posted_at.is_(None)))
    if has_contacts is not None:
        contact_exists = select(Contact.id).where(or_(
            Contact.job_id == Job.id,
            and_(Job.company_id.is_not(None), Contact.company_id == Job.company_id),
        )).exists()
        stmt = stmt.where(contact_exists if has_contacts else ~contact_exists)

    # SQL-level sort via outerjoin on JobRanking for the active profile.
    if sort == "posted":
        order_stmt = stmt.order_by(Job.posted_at.desc().nullslast(),
                                    Job.first_seen_at.desc().nullslast())
    else:
        score_col = {
            "composite": JobRanking.composite_score,
            "fit": JobRanking.fit_score,
            "urgency": JobRanking.urgency_score,
        }[sort]
        if profile:
            order_stmt = stmt.outerjoin(
                JobRanking,
                and_(JobRanking.job_id == Job.id,
                     JobRanking.profile_id == profile.id),
            ).order_by(score_col.desc().nullslast(),
                        Job.first_seen_at.desc().nullslast())
        else:
            order_stmt = stmt.order_by(Job.first_seen_at.desc().nullslast())

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    results = db.scalars(
        order_stmt.offset((page - 1) * page_size).limit(page_size)
    ).unique().all()

    rankings: dict[int, JobRanking] = {}
    screenings: dict[int, Screening] = {}
    if profile and results:
        ids = [j.id for j in results]
        for r in db.query(JobRanking).filter(
            JobRanking.profile_id == profile.id, JobRanking.job_id.in_(ids)
        ).all():
            rankings[r.job_id] = r
        for s in db.query(Screening).filter(
            Screening.profile_id == profile.id, Screening.job_id.in_(ids)
        ).all():
            screenings[s.job_id] = s

    serialized: list[dict] = []
    for j in results:
        s = screenings.get(j.id)
        r = rankings.get(j.id)
        serialized.append(_serialize(j, r, s, j.company, profile_model))

    return {"total": total, "page": page, "page_size": page_size, "run_id": run_id, "items": serialized}


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    profile = db.query(UserProfile).filter(UserProfile.is_active == True).first()  # noqa: E712
    profile_model = _profile_from_row(profile)
    ranking = screening = None
    if profile:
        ranking = db.query(JobRanking).filter(
            JobRanking.job_id == job.id, JobRanking.profile_id == profile.id
        ).first()
        screening = db.query(Screening).filter(
            Screening.job_id == job.id, Screening.profile_id == profile.id
        ).first()
    out = _serialize(job, ranking, screening, job.company, profile_model)
    # Full description in detail endpoint
    out["description_text"] = job.description_text
    out["description_html"] = job.description_html
    contacts = (db.query(Contact)
                .filter((Contact.job_id == job.id) | (Contact.company_id == job.company_id))
                .order_by(Contact.confidence_score.desc().nullslast()).limit(10).all())
    out["contacts"] = [{
        "id": c.id, "name": c.name, "title": c.title, "email": c.email,
        "linkedin_url": c.linkedin_url, "source": c.source,
        "confidence": c.confidence_score, "evidence": c.evidence_json,
    } for c in contacts]
    return out
