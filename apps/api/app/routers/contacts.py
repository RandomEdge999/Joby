from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Contact, Job
from ..enrichment import contacts as contacts_mod

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


class ContactIn(BaseModel):
    job_id: Optional[int] = None
    company_id: Optional[int] = None
    name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[str] = None
    email_status: Optional[str] = None
    linkedin_url: Optional[str] = None
    source: Optional[str] = "manual"
    confidence_score: Optional[float] = None
    evidence_json: Optional[dict] = None


class ContactOut(ContactIn):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[ContactOut])
def list_contacts(
    db: Session = Depends(get_db),
    job_id: Optional[int] = None,
    company_id: Optional[int] = None,
):
    q = db.query(Contact)
    if job_id is not None:
        q = q.filter(Contact.job_id == job_id)
    if company_id is not None:
        q = q.filter(Contact.company_id == company_id)
    return q.order_by(Contact.confidence_score.desc().nullslast()).limit(500).all()


@router.post("", response_model=ContactOut, status_code=201)
def create_contact(payload: ContactIn, db: Session = Depends(get_db)):
    if payload.job_id is None and payload.company_id is None:
        raise HTTPException(400, "either job_id or company_id is required")
    row = Contact(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: int, payload: ContactIn, db: Session = Depends(get_db)):
    row = db.get(Contact, contact_id)
    if not row:
        raise HTTPException(404, "contact not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{contact_id}", status_code=204)
def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    row = db.get(Contact, contact_id)
    if not row:
        raise HTTPException(404, "contact not found")
    db.delete(row)
    db.commit()
    return None


@router.post("/regenerate/{job_id}")
def regenerate_for_job(job_id: int, db: Session = Depends(get_db)):
    """Re-run the deterministic contact-discovery pipeline for one job."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    found = contacts_mod.discover_for_job(db, job)
    return {"job_id": job_id, "contacts_found": len(found)}
