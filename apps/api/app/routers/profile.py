from __future__ import annotations

import yaml
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import UserProfile
from ..profile.schema import Profile
from ..profile.presets import list_presets, get_preset, PRESETS
from ..services.rerank import rerank_jobs_for_profile

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _get_active(db: Session) -> UserProfile | None:
    return db.query(UserProfile).filter(UserProfile.is_active == True).first()  # noqa: E712


def _ensure_active_exists(db: Session) -> UserProfile:
    active = _get_active(db)
    if active:
        return active
    default = get_preset("us-new-grad")
    row = UserProfile(
        name=default.profile_name,
        preset=default.preset,
        profile_json=default.model_dump(),
        profile_yaml=yaml.safe_dump(default.model_dump(), sort_keys=False),
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/presets")
def presets():
    return {"presets": list_presets()}


@router.get("/presets/{key}")
def preset_detail(key: str):
    if key not in PRESETS:
        raise HTTPException(status_code=404, detail="preset not found")
    p = get_preset(key)
    return p.model_dump()


@router.get("")
def get_profile(db: Session = Depends(get_db)):
    row = _ensure_active_exists(db)
    return {
        "id": row.id,
        "name": row.name,
        "preset": row.preset,
        "profile": row.profile_json,
    }


@router.put("")
def put_profile(payload: Profile, db: Session = Depends(get_db)):
    # Deactivate any existing active profiles, then upsert a new active one.
    existing = _get_active(db)
    profile_dict = payload.model_dump()
    if existing:
        existing.name = payload.profile_name
        existing.preset = payload.preset
        existing.profile_json = profile_dict
        existing.profile_yaml = yaml.safe_dump(profile_dict, sort_keys=False)
        existing.is_active = True
        row = existing
    else:
        row = UserProfile(
            name=payload.profile_name,
            preset=payload.preset,
            profile_json=profile_dict,
            profile_yaml=yaml.safe_dump(profile_dict, sort_keys=False),
            is_active=True,
        )
        db.add(row)
    db.flush()
    reranked_jobs = rerank_jobs_for_profile(db, row, payload)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "name": row.name,
        "preset": row.preset,
        "profile": row.profile_json,
        "reranked_jobs": reranked_jobs,
    }
