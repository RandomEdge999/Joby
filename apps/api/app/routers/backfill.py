"""Backfill: rerun tier classification, contact discovery, and re-rank existing
jobs without scraping. Useful after scoring logic changes.
"""
from __future__ import annotations

import threading
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..models import Job, JobRanking, Screening, UserProfile
from ..enrichment import tier as tier_mod
from ..enrichment import contacts as contacts_mod
from ..services.freshness import sweep
from ..profile.schema import Profile
from ..services.rerank import rerank_jobs_for_profile


router = APIRouter(prefix="/api/backfill", tags=["backfill"])


def _backfill_run(stats: dict) -> None:
    db = SessionLocal()
    try:
        # 1. Freshness sweep first.
        stats["freshness"] = sweep(db)

        # 2. Tier classifier over all companies.
        stats["tiers"] = tier_mod.apply_to_all(db)

        # 3. Contacts for every job (idempotent upsert).
        stats["contacts_jobs_processed"] = contacts_mod.discover_for_all(db)

        # 4. Re-prefilter + re-visa + re-rank.
        up = db.query(UserProfile).filter(UserProfile.is_active == True).first()  # noqa: E712
        if not up:
            stats["reranked"] = 0
            return
        profile = Profile.model_validate(up.profile_json)

        reranked = rerank_jobs_for_profile(db, up, profile)
        db.commit()
        stats["reranked"] = reranked
        stats["status"] = "completed"
    except Exception as e:
        stats["status"] = "failed"
        stats["error"] = str(e)
    finally:
        db.close()


# A tiny in-process status registry. Fine for local-first v1.
_STATE: dict = {"status": "idle"}


@router.post("/run")
def run_backfill(background: bool = True):
    if _STATE.get("status") == "running":
        return dict(_STATE)
    _STATE.clear()
    _STATE.update({"status": "running", "started_at": datetime.utcnow().isoformat()})
    if background:
        threading.Thread(target=_backfill_run, args=(_STATE,), daemon=True).start()
        return dict(_STATE)
    _backfill_run(_STATE)
    return dict(_STATE)


@router.get("/status")
def backfill_status():
    return dict(_STATE)
