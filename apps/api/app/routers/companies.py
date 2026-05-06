from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from ..db import get_db
from ..models import Company, Job

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("")
def list_companies(
    q: Optional[str] = Query(None),
    tier: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Company)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(or_(func.lower(Company.name).like(like),
                                 func.lower(Company.normalized_name).like(like)))
    if tier:
        query = query.filter(Company.company_tier == tier)
    rows = query.order_by(Company.name.asc()).all()
    counts = dict(db.query(Job.company_id, func.count(Job.id))
                    .group_by(Job.company_id).all())
    return {"items": [
        {"id": c.id, "name": c.name, "normalized_name": c.normalized_name,
         "company_tier": c.company_tier, "tier_source": c.tier_source,
         "domain": c.domain, "jobs_count": counts.get(c.id, 0)}
        for c in rows
    ]}


@router.get("/{company_id}")
def get_company(company_id: int, db: Session = Depends(get_db)):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(404, "company not found")
    return {"id": c.id, "name": c.name, "normalized_name": c.normalized_name,
            "tier": c.company_tier, "tier_source": c.tier_source, "domain": c.domain,
            "headquarters": c.headquarters, "careers_url": c.careers_url,
            "metadata": c.metadata_json}
