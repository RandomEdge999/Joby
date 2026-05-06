"""Watches router: CRUD + manual trigger + event inspection."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Watch, JobEvent, Job
from ..services import scheduler as sched_mod


router = APIRouter(prefix="/api/watches", tags=["watches"])


class WatchCreate(BaseModel):
    name: str
    cadence_minutes: int = Field(360, ge=5)
    enabled: bool = True
    query_json: Optional[dict] = None


class WatchUpdate(BaseModel):
    name: Optional[str] = None
    cadence_minutes: Optional[int] = Field(None, ge=5)
    enabled: Optional[bool] = None
    query_json: Optional[dict] = None


def _serialize(w: Watch) -> dict:
    return {
        "id": w.id, "name": w.name, "cadence_minutes": w.cadence_minutes,
        "enabled": w.enabled, "query_json": w.query_json,
        "last_run_at": w.last_run_at.isoformat() if w.last_run_at else None,
        "next_run_at": w.next_run_at.isoformat() if w.next_run_at else None,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


@router.get("")
def list_watches(db: Session = Depends(get_db)):
    rows = db.query(Watch).order_by(Watch.id.desc()).all()
    return {"items": [_serialize(w) for w in rows]}


@router.post("")
def create_watch(payload: WatchCreate, db: Session = Depends(get_db)):
    w = Watch(
        name=payload.name, cadence_minutes=payload.cadence_minutes,
        enabled=payload.enabled, query_json=payload.query_json,
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    if w.enabled:
        try:
            sched_mod.schedule_one(w)
        except Exception:
            pass
    return _serialize(w)


@router.patch("/{watch_id}")
def update_watch(watch_id: int, payload: WatchUpdate, db: Session = Depends(get_db)):
    w = db.get(Watch, watch_id)
    if not w:
        raise HTTPException(404, "watch not found")
    if payload.name is not None:
        w.name = payload.name
    if payload.cadence_minutes is not None:
        w.cadence_minutes = payload.cadence_minutes
    if payload.enabled is not None:
        w.enabled = payload.enabled
    if payload.query_json is not None:
        w.query_json = payload.query_json
    db.commit()
    db.refresh(w)
    try:
        if w.enabled:
            sched_mod.schedule_one(w)
        else:
            sched_mod.unschedule(w.id)
    except Exception:
        pass
    return _serialize(w)


@router.delete("/{watch_id}")
def delete_watch(watch_id: int, db: Session = Depends(get_db)):
    w = db.get(Watch, watch_id)
    if not w:
        raise HTTPException(404, "watch not found")
    db.delete(w)
    db.commit()
    try:
        sched_mod.unschedule(watch_id)
    except Exception:
        pass
    return {"ok": True}


@router.post("/{watch_id}/run")
def run_watch_now(watch_id: int, background: BackgroundTasks,
                  db: Session = Depends(get_db)):
    w = db.get(Watch, watch_id)
    if not w:
        raise HTTPException(404, "watch not found")
    background.add_task(sched_mod.run_now, watch_id)
    return {"ok": True, "watch_id": watch_id, "queued": True}


@router.get("/{watch_id}/events")
def watch_events(watch_id: int, db: Session = Depends(get_db), limit: int = 100):
    rows = (db.query(JobEvent, Job)
            .join(Job, Job.id == JobEvent.job_id)
            .filter(JobEvent.watch_id == watch_id)
            .order_by(JobEvent.id.desc()).limit(limit).all())
    return {"items": [{
        "id": ev.id, "event_type": ev.event_type,
        "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else None,
        "payload": ev.event_payload_json,
        "job": {"id": j.id, "title": j.title, "company": j.company_name_raw,
                "url": j.canonical_url},
    } for ev, j in rows]}


@router.get("/events/recent")
def recent_events(db: Session = Depends(get_db), limit: int = 25):
    """Cross-watch recent events for the dashboard card."""
    rows = (db.query(JobEvent, Job)
            .join(Job, Job.id == JobEvent.job_id)
            .order_by(JobEvent.id.desc()).limit(limit).all())
    return {"items": [{
        "id": ev.id, "event_type": ev.event_type, "watch_id": ev.watch_id,
        "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else None,
        "job": {"id": j.id, "title": j.title, "company": j.company_name_raw},
    } for ev, j in rows]}
