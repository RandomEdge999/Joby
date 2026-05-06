from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..enrichment import visa as visa_mod
from ..models import Job, JobRanking, Screening, UserProfile
from ..profile.schema import Profile
from ..ranking import engine as rank_engine
from ..screener import prefilter as pf


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _job_dict(job: Job) -> dict:
    return {
        "title": job.title,
        "location_raw": job.location_raw,
        "city": job.city,
        "state": job.state,
        "country": job.country,
        "remote_type": job.remote_type,
        "employment_type": job.employment_type,
        "level_guess": job.level_guess,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "description_text": job.description_text,
        "posted_at": job.posted_at,
        "recruiter_blob_json": job.recruiter_blob_json,
    }


def rerank_jobs_for_profile(
    db: Session,
    profile_row: UserProfile,
    profile: Profile | None = None,
) -> int:
    profile = profile or Profile.model_validate(profile_row.profile_json)

    reranked = 0
    for job in db.query(Job).all():
        job_dict = _job_dict(job)
        passed, reasons, signals = pf.evaluate(job_dict, profile)
        visa_tier, evidence = visa_mod.resolve(
            job_dict,
            profile,
            db=db,
            company_id=job.company_id,
        )
        signals["visa_tier"] = visa_tier
        signals["visa_evidence"] = evidence

        screening = db.query(Screening).filter(
            Screening.job_id == job.id,
            Screening.profile_id == profile_row.id,
        ).first()
        screening_fields = {
            "prefilter_passed": passed,
            "prefilter_reasons_json": {"reasons": reasons, "signals": signals},
        }
        if screening:
            for key, value in screening_fields.items():
                setattr(screening, key, value)
        else:
            screening = Screening(
                job_id=job.id,
                profile_id=profile_row.id,
                llm_status="skipped",
                **screening_fields,
            )
            db.add(screening)

        company_tier = (job.company.company_tier if job.company else None) or "unknown"
        ranking_data = rank_engine.rank(job_dict, profile, signals, visa_tier, company_tier)
        ranking = db.query(JobRanking).filter(
            JobRanking.job_id == job.id,
            JobRanking.profile_id == profile_row.id,
        ).first()
        if ranking:
            ranking.fit_score = ranking_data["fit_score"]
            ranking.opportunity_score = ranking_data["opportunity_score"]
            ranking.urgency_score = ranking_data["urgency_score"]
            ranking.composite_score = ranking_data["composite_score"]
            ranking.reason_json = ranking_data["reason_json"]
            ranking.ranking_version = ranking_data["ranking_version"]
            ranking.ranked_at = _utcnow_naive()
        else:
            db.add(JobRanking(job_id=job.id, profile_id=profile_row.id, **ranking_data))
        reranked += 1

    return reranked