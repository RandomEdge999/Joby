from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Note

router = APIRouter(prefix="/api/notes", tags=["notes"])


class NoteIn(BaseModel):
    job_id: Optional[int] = None
    company_id: Optional[int] = None
    body: str = Field(min_length=1, max_length=20000)


class NoteOut(BaseModel):
    id: int
    job_id: Optional[int]
    company_id: Optional[int]
    body: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[NoteOut])
def list_notes(
    db: Session = Depends(get_db),
    job_id: Optional[int] = None,
    company_id: Optional[int] = None,
):
    q = db.query(Note)
    if job_id is not None:
        q = q.filter(Note.job_id == job_id)
    if company_id is not None:
        q = q.filter(Note.company_id == company_id)
    return q.order_by(Note.created_at.desc()).limit(500).all()


@router.post("", response_model=NoteOut, status_code=201)
def create_note(payload: NoteIn, db: Session = Depends(get_db)):
    if payload.job_id is None and payload.company_id is None:
        raise HTTPException(400, "either job_id or company_id is required")
    row = Note(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{note_id}", response_model=NoteOut)
def update_note(note_id: int, payload: NoteIn, db: Session = Depends(get_db)):
    row = db.get(Note, note_id)
    if not row:
        raise HTTPException(404, "note not found")
    row.body = payload.body
    if payload.job_id is not None:
        row.job_id = payload.job_id
    if payload.company_id is not None:
        row.company_id = payload.company_id
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{note_id}", status_code=204)
def delete_note(note_id: int, db: Session = Depends(get_db)):
    row = db.get(Note, note_id)
    if not row:
        raise HTTPException(404, "note not found")
    db.delete(row)
    db.commit()
    return None
