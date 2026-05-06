"""Watches CRUD and APScheduler integration.

Watches are stored scrape definitions that run on a cadence. For v1 we keep the
query shape free-form (`query_json`) — the scrape pipeline ignores per-watch
query filters today; they are stored for future use and UI display.

The scheduler runs inside the API process using APScheduler's BackgroundScheduler.
On startup we re-read enabled watches. On CRUD we update schedule entries.
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Watch


_scheduler: BackgroundScheduler | None = None
_lock = threading.Lock()


def _job_id(watch_id: int) -> str:
    return f"watch_{watch_id}"


def _run_watch(watch_id: int) -> None:
    # Local import to avoid circular dependency with services.runner.
    from ..services.runner import run_pipeline_sync
    from ..services.freshness import sweep

    db = SessionLocal()
    try:
        w = db.get(Watch, watch_id)
        if not w or not w.enabled:
            return
        w.last_run_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()

    run_pipeline_sync(watch_id=watch_id, trigger_type="watch")

    # Freshness sweep after each watch run so stale/closed transitions accumulate.
    db = SessionLocal()
    try:
        sweep(db)
    finally:
        db.close()


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    with _lock:
        if _scheduler is None:
            _scheduler = BackgroundScheduler(daemon=True)
        return _scheduler


def start() -> None:
    """Start scheduler and register all enabled watches. Idempotent."""
    sched = get_scheduler()
    if not sched.running:
        sched.start()
    reconcile_all()


def shutdown() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None


def reconcile_all() -> None:
    """Sync scheduled jobs with DB state."""
    sched = get_scheduler()
    db = SessionLocal()
    try:
        watches = db.query(Watch).all()
        existing_ids = {j.id for j in sched.get_jobs()}
        desired_ids = set()
        for w in watches:
            jid = _job_id(w.id)
            if w.enabled:
                desired_ids.add(jid)
                schedule_one(w, sched=sched, replace=True)
        for jid in existing_ids - desired_ids:
            try:
                sched.remove_job(jid)
            except Exception:
                pass
    finally:
        db.close()


def schedule_one(watch: Watch, sched: Optional[BackgroundScheduler] = None,
                 replace: bool = True) -> None:
    sched = sched or get_scheduler()
    jid = _job_id(watch.id)
    minutes = max(1, int(watch.cadence_minutes or 360))
    trigger = IntervalTrigger(minutes=minutes)
    if replace and jid in {j.id for j in sched.get_jobs()}:
        job = sched.reschedule_job(jid, trigger=trigger)
    else:
        job = sched.add_job(_run_watch, trigger=trigger, args=[watch.id],
                            id=jid, replace_existing=True, max_instances=1,
                            coalesce=True)
    # Propagate the scheduler-computed next fire time back to the DB so the UI
    # can display an accurate countdown without polling APScheduler directly.
    try:
        if job and getattr(job, "next_run_time", None):
            db = SessionLocal()
            try:
                w = db.get(Watch, watch.id)
                if w:
                    w.next_run_at = job.next_run_time.replace(tzinfo=None)
                    db.commit()
            finally:
                db.close()
    except Exception:
        pass


def unschedule(watch_id: int) -> None:
    sched = get_scheduler()
    try:
        sched.remove_job(_job_id(watch_id))
    except Exception:
        pass


def run_now(watch_id: int) -> None:
    """Synchronous trigger; used by the /run endpoint."""
    _run_watch(watch_id)
