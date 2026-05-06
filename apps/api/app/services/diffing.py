"""Job event diffing per IMPLEMENTATION_PLAN sections 12 & 15.5.

Compares a set of "previously seen" job ids (snapshot from the prior watch run or the
whole DB at run start) against the ids seen in the current run. Emits:
  - new:             first time this dedupe_key has appeared
  - reappeared:      previously inactive/closed job is back
  - disappeared:     previously active job was not in the current run
  - material_change: active job re-observed with a meaningful field change
    (title, location, employment_type, salary range)

Keep this explainable; do not gold-plate.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Dict, Any, List

from sqlalchemy.orm import Session

from ..models import Job, JobEvent


_MATERIAL_FIELDS = ("title", "location_raw", "employment_type",
                    "salary_min", "salary_max", "remote_type")


def snapshot_active(db: Session) -> Dict[int, Dict[str, Any]]:
    """Return {job_id: {field: value}} for currently-active jobs."""
    rows = db.query(Job).filter(Job.is_active == True).all()  # noqa: E712
    return {j.id: {f: getattr(j, f) for f in _MATERIAL_FIELDS} for j in rows}


def emit_events(db: Session, watch_id: int | None,
                before: Dict[int, Dict[str, Any]],
                after_jobs: Iterable[Job],
                first_seen_this_run: set[int]) -> List[JobEvent]:
    """Emit job_events by diffing `before` vs the set of jobs observed in the run.

    `after_jobs` is the list of Job rows persisted/updated by the run.
    `first_seen_this_run` is the subset of job ids whose first_seen_at == last_seen_at
    of this run (i.e. newly inserted rows).
    """
    now = datetime.utcnow()
    events: List[JobEvent] = []
    after_ids = {j.id for j in after_jobs}

    # New
    for jid in first_seen_this_run:
        events.append(JobEvent(
            watch_id=watch_id, job_id=jid, event_type="new",
            event_payload_json={"at": now.isoformat()},
        ))

    # Reappeared / material_change
    for j in after_jobs:
        if j.id in first_seen_this_run:
            continue
        prev = before.get(j.id)
        if prev is None:
            # Wasn't active before this run but existed (was stale/closed)
            events.append(JobEvent(
                watch_id=watch_id, job_id=j.id, event_type="reappeared",
                event_payload_json={"at": now.isoformat()},
            ))
            continue
        diff = {}
        for f in _MATERIAL_FIELDS:
            old = prev.get(f)
            new = getattr(j, f)
            if old != new:
                diff[f] = {"from": old, "to": new}
        if diff:
            events.append(JobEvent(
                watch_id=watch_id, job_id=j.id, event_type="material_change",
                event_payload_json={"changes": diff},
            ))

    # Disappeared: was active before, not in this run
    disappeared_ids = set(before.keys()) - after_ids
    for jid in disappeared_ids:
        events.append(JobEvent(
            watch_id=watch_id, job_id=jid, event_type="disappeared",
            event_payload_json={"at": now.isoformat()},
        ))

    for ev in events:
        db.add(ev)
    db.commit()
    return events
