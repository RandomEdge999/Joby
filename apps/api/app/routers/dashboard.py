"""Dashboard summary + chart endpoints."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Job, Application, JobRanking, UserProfile, Company, Screening


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    active_total = db.query(func.count(Job.id)).filter(Job.is_active == True).scalar() or 0  # noqa: E712
    total_total = db.query(func.count(Job.id)).scalar() or 0

    # Newly discovered: first_seen_at within last 7 days
    cutoff_7 = datetime.utcnow() - timedelta(days=7)
    new_7 = db.query(func.count(Job.id)).filter(Job.first_seen_at >= cutoff_7).scalar() or 0

    # High-ranked: composite >= 0.7
    profile = db.query(UserProfile).filter(UserProfile.is_active == True).first()  # noqa: E712
    high_ranked = 0
    if profile:
        high_ranked = (db.query(func.count(JobRanking.id))
                       .filter(JobRanking.profile_id == profile.id,
                               JobRanking.composite_score >= 0.7).scalar() or 0)

    apps_by_status = dict(db.query(Application.status,
                                   func.count(Application.id))
                          .group_by(Application.status).all())

    return {
        "active_jobs": active_total,
        "total_jobs": total_total,
        "new_last_7d": new_7,
        "high_ranked": high_ranked,
        "applications_by_status": apps_by_status,
        "companies_total": db.query(func.count(Company.id)).scalar() or 0,
    }


@router.get("/charts")
def charts(db: Session = Depends(get_db)):
    # Jobs over time: first_seen_at per day for last 14 days
    cutoff = datetime.utcnow() - timedelta(days=14)
    rows = db.query(Job.first_seen_at).filter(Job.first_seen_at >= cutoff).all()
    buckets: Counter = Counter()
    for (ts,) in rows:
        if ts is None:
            continue
        key = ts.date().isoformat()
        buckets[key] += 1
    # Build contiguous last-14-day series
    today = datetime.utcnow().date()
    series = []
    for i in range(13, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        series.append({"date": d, "count": buckets.get(d, 0)})

    # Source mix
    sources = dict(db.query(Job.source, func.count(Job.id))
                   .filter(Job.is_active == True)  # noqa: E712
                   .group_by(Job.source).all())

    # Score distribution (bucketed 0.0..1.0 step 0.1)
    profile = db.query(UserProfile).filter(UserProfile.is_active == True).first()  # noqa: E712
    buckets_score = [0] * 10
    if profile:
        for (score,) in db.query(JobRanking.composite_score).filter(
            JobRanking.profile_id == profile.id
        ).all():
            if score is None:
                continue
            i = min(9, max(0, int(score * 10)))
            buckets_score[i] += 1

    return {
        "jobs_over_time": series,
        "sources": sources,
        "score_distribution": [
            {"range": f"{i/10:.1f}-{(i+1)/10:.1f}", "count": c}
            for i, c in enumerate(buckets_score)
        ],
    }
