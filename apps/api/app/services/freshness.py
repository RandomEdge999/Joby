"""Freshness and closing logic per IMPLEMENTATION_PLAN section 16.

Rules:
  - Every successful sighting updates last_seen_at (done in runner._upsert_job).
  - If last_seen_at is older than STALE_DAYS, mark job stale (is_active=False, closed_at=None).
  - If older than CLOSED_DAYS, mark closed (is_active=False, closed_at=now).
  - Reappearance (a stale/closed job seen again) is handled in runner by setting
    is_active=True and clearing closed_at; we additionally emit a job_event.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict

from sqlalchemy.orm import Session

from ..models import Job, JobEvent


STALE_DAYS = 14
CLOSED_DAYS = 30


def sweep(db: Session, now: datetime | None = None) -> Dict[str, int]:
    """Transition jobs to stale/closed based on last_seen_at. Returns counts."""
    now = now or datetime.utcnow()
    stale_cutoff = now - timedelta(days=STALE_DAYS)
    closed_cutoff = now - timedelta(days=CLOSED_DAYS)

    counts = {"stale": 0, "closed": 0}

    # Closed: last_seen older than CLOSED_DAYS — set closed_at, deactivate.
    closed_rows = db.query(Job).filter(
        Job.last_seen_at < closed_cutoff,
        Job.closed_at.is_(None),
    ).all()
    for j in closed_rows:
        j.is_active = False
        j.closed_at = now
        counts["closed"] += 1

    # Stale: active jobs older than STALE_DAYS but newer than CLOSED_DAYS.
    stale_rows = db.query(Job).filter(
        Job.last_seen_at < stale_cutoff,
        Job.last_seen_at >= closed_cutoff,
        Job.is_active == True,  # noqa: E712
    ).all()
    for j in stale_rows:
        j.is_active = False
        counts["stale"] += 1

    db.commit()
    return counts


def record_reappearance(db: Session, job: Job, watch_id: int | None = None) -> None:
    """Emit a reappearance job_event and reactivate the job."""
    job.is_active = True
    job.closed_at = None
    db.add(JobEvent(
        watch_id=watch_id, job_id=job.id, event_type="reappeared",
        event_payload_json={"last_seen_at": job.last_seen_at.isoformat()},
    ))
    db.commit()
