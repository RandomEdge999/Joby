from datetime import datetime, timedelta

from app.db import SessionLocal
from app.models import Company, Job
from app.services import freshness


def _make_job(db, last_seen_days_ago: int, tag: str, closed: bool = False):
    c = Company(name="F", normalized_name=f"freshness-{tag}")
    db.add(c); db.commit(); db.refresh(c)
    now = datetime.utcnow()
    ls = now - timedelta(days=last_seen_days_ago)
    job = Job(source="greenhouse", external_job_id=f"fresh-{tag}",
              title="T", company_id=c.id,
              first_seen_at=ls, last_seen_at=ls, is_active=not closed,
              closed_at=now if closed else None)
    db.add(job); db.commit(); db.refresh(job)
    return job


def test_sweep_marks_stale_but_not_closed():
    db = SessionLocal()
    try:
        job = _make_job(db, last_seen_days_ago=20, tag="stale")
        counts = freshness.sweep(db)
        db.refresh(job)
        assert counts["stale"] >= 1
        assert job.is_active is False
        assert job.closed_at is None
    finally:
        db.close()


def test_sweep_marks_closed_past_30d():
    db = SessionLocal()
    try:
        job = _make_job(db, last_seen_days_ago=45, tag="closed")
        freshness.sweep(db)
        db.refresh(job)
        assert job.is_active is False
        assert job.closed_at is not None
    finally:
        db.close()


def test_sweep_leaves_fresh_alone():
    db = SessionLocal()
    try:
        job = _make_job(db, last_seen_days_ago=3, tag="fresh")
        freshness.sweep(db)
        db.refresh(job)
        assert job.is_active is True
        assert job.closed_at is None
    finally:
        db.close()
