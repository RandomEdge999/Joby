"""Applications router: Kanban-style tracker CRUD."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Application, Job


router = APIRouter(prefix="/api/applications", tags=["applications"])

Status = Literal["saved", "applied", "interviewing", "offer", "rejected", "archived"]


class ApplicationCreate(BaseModel):
    job_id: int
    status: Status = "saved"
    notes_summary: Optional[str] = None
    portal_url: Optional[str] = None


class ApplicationUpdate(BaseModel):
    status: Optional[Status] = None
    notes_summary: Optional[str] = None
    portal_url: Optional[str] = None
    applied_at: Optional[datetime] = None
    next_action_at: Optional[datetime] = None


def _serialize(a: Application, job: Optional[Job] = None) -> dict:
    return {
        "id": a.id, "job_id": a.job_id, "status": a.status,
        "applied_at": a.applied_at.isoformat() if a.applied_at else None,
        "next_action_at": a.next_action_at.isoformat() if a.next_action_at else None,
        "portal_url": a.portal_url, "notes_summary": a.notes_summary,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        "job": {"id": job.id, "title": job.title,
                "company": job.company_name_raw,
                "location": job.location_raw,
                "url": job.canonical_url} if job else None,
    }


@router.get("")
def list_applications(db: Session = Depends(get_db),
                      status: Optional[Status] = None):
    q = db.query(Application)
    if status:
        q = q.filter(Application.status == status)
    rows = q.order_by(Application.updated_at.desc()).all()
    jobs = {j.id: j for j in db.query(Job).filter(
        Job.id.in_([a.job_id for a in rows])
    ).all()}
    return {"items": [_serialize(a, jobs.get(a.job_id)) for a in rows]}


@router.post("")
def create_application(payload: ApplicationCreate, db: Session = Depends(get_db)):
    if not db.get(Job, payload.job_id):
        raise HTTPException(404, "job not found")
    existing = db.query(Application).filter(Application.job_id == payload.job_id).first()
    if existing:
        raise HTTPException(409, "application exists for this job")
    a = Application(
        job_id=payload.job_id, status=payload.status,
        notes_summary=payload.notes_summary, portal_url=payload.portal_url,
        applied_at=datetime.utcnow() if payload.status == "applied" else None,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return _serialize(a, db.get(Job, a.job_id))


@router.patch("/{application_id}")
def update_application(application_id: int, payload: ApplicationUpdate,
                       db: Session = Depends(get_db)):
    a = db.get(Application, application_id)
    if not a:
        raise HTTPException(404, "application not found")
    if payload.status is not None:
        if a.status != "applied" and payload.status == "applied" and not a.applied_at:
            a.applied_at = datetime.utcnow()
        a.status = payload.status
    if payload.notes_summary is not None:
        a.notes_summary = payload.notes_summary
    if payload.portal_url is not None:
        a.portal_url = payload.portal_url
    if payload.applied_at is not None:
        a.applied_at = payload.applied_at
    if payload.next_action_at is not None:
        a.next_action_at = payload.next_action_at
    db.commit()
    db.refresh(a)
    return _serialize(a, db.get(Job, a.job_id))


@router.delete("/{application_id}")
def delete_application(application_id: int, db: Session = Depends(get_db)):
    a = db.get(Application, application_id)
    if not a:
        raise HTTPException(404, "application not found")
    db.delete(a)
    db.commit()
    return {"ok": True}
