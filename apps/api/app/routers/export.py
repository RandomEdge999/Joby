"""Data export + wipe. Single-user tool so there's no auth layer; the
wipe endpoint requires a confirm=YES query param as a safety interlock.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, text
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    Job, Company, CompanyH1B, Application, Contact, Note, JobEvent, JobRanking,
    Screening, ScrapeRun, Watch, UserProfile,
)
from ..services import discovery


router = APIRouter(tags=["export"])
BACKUP_SCHEMA_VERSION = 1
BACKUP_MODELS = [
    UserProfile,
    Company,
    CompanyH1B,
    Job,
    Watch,
    ScrapeRun,
    Screening,
    JobRanking,
    Application,
    Contact,
    Note,
    JobEvent,
]
BACKUP_MODEL_MAP = {model.__tablename__: model for model in BACKUP_MODELS}


class BackupBundle(BaseModel):
    schema_version: int = BACKUP_SCHEMA_VERSION
    exported_at: str
    tables: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)


class BackupImportPayload(BaseModel):
    backup: BackupBundle
    confirm_replace: bool = False


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialize_table(db: Session, model) -> list[dict[str, Any]]:
    rows = []
    columns = [column.name for column in model.__table__.columns]
    for row in db.query(model).all():
        rows.append({column: _serialize_value(getattr(row, column)) for column in columns})
    return rows


def _deserialize_row(model, raw: dict[str, Any]) -> dict[str, Any]:
    allowed = {column.name: column for column in model.__table__.columns}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        column = allowed.get(key)
        if column is None:
            continue
        if value is not None and isinstance(column.type, DateTime) and isinstance(value, str):
            try:
                out[key] = datetime.fromisoformat(value)
                continue
            except ValueError:
                pass
        out[key] = value
    return out


def _wipe_workspace(db: Session) -> None:
    for model in reversed(BACKUP_MODELS):
        db.execute(text(f"DELETE FROM {model.__tablename__}"))


def _backup_summary(bundle: BackupBundle) -> dict[str, Any]:
    table_counts = {table: len(rows) for table, rows in bundle.tables.items()}
    sources_user_count = len(bundle.config.get("sources_user") or [])
    return {
        "table_counts": table_counts,
        "sources_user_count": sources_user_count,
        "total_rows": sum(table_counts.values()),
    }


@router.get("/api/export")
def export(
    db: Session = Depends(get_db),
    entity: Literal["jobs", "applications", "contacts", "notes"] = "jobs",
    format: Literal["json", "csv"] = "json",
):
    rows: list[dict] = []
    if entity == "jobs":
        q = db.query(Job).limit(20000).all()
        for j in q:
            rows.append({
                "id": j.id,
                "source": j.source,
                "title": j.title,
                "company": j.company_name_raw,
                "url": j.canonical_url,
                "location": j.location_raw,
                "remote_type": j.remote_type,
                "employment_type": j.employment_type,
                "level": j.level_guess,
                "salary_min": j.salary_min,
                "salary_max": j.salary_max,
                "posted_at": j.posted_at.isoformat() if j.posted_at else None,
                "is_active": j.is_active,
            })
    elif entity == "applications":
        for a in db.query(Application).all():
            rows.append({
                "id": a.id, "job_id": a.job_id, "status": a.status,
                "applied_at": a.applied_at.isoformat() if a.applied_at else None,
                "next_action_at": a.next_action_at.isoformat() if a.next_action_at else None,
                "portal_url": a.portal_url, "notes_summary": a.notes_summary,
            })
    elif entity == "contacts":
        for c in db.query(Contact).all():
            rows.append({
                "id": c.id, "job_id": c.job_id, "company_id": c.company_id,
                "name": c.name, "title": c.title, "email": c.email,
                "email_status": c.email_status, "linkedin_url": c.linkedin_url,
                "source": c.source, "confidence": c.confidence_score,
            })
    elif entity == "notes":
        for n in db.query(Note).all():
            rows.append({
                "id": n.id, "job_id": n.job_id, "company_id": n.company_id,
                "body": n.body,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            })

    if format == "json":
        return {"entity": entity, "count": len(rows),
                "exported_at": _utcnow_iso(), "items": rows}

    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{entity}.csv"'})


@router.get("/api/backup/export")
def export_workspace_backup(db: Session = Depends(get_db)):
    bundle = BackupBundle(
        exported_at=_utcnow_iso(),
        tables={model.__tablename__: _serialize_table(db, model) for model in BACKUP_MODELS},
        config={"sources_user": discovery.load_user_sources()},
    )
    bundle.summary = _backup_summary(bundle)
    return bundle.model_dump()


@router.post("/api/backup/import")
def import_workspace_backup(payload: BackupImportPayload, db: Session = Depends(get_db)):
    if not payload.confirm_replace:
        raise HTTPException(400, "confirm_replace=true required to import workspace backup")
    if payload.backup.schema_version != BACKUP_SCHEMA_VERSION:
        raise HTTPException(400, f"unsupported backup schema version: {payload.backup.schema_version}")

    _wipe_workspace(db)
    for model in BACKUP_MODELS:
        rows = payload.backup.tables.get(model.__tablename__) or []
        if rows:
            db.execute(
                model.__table__.insert(),
                [_deserialize_row(model, row) for row in rows if isinstance(row, dict)],
            )

    discovery.write_user_sources(payload.backup.config.get("sources_user") or [])
    db.commit()

    restored = {
        model.__tablename__: len(payload.backup.tables.get(model.__tablename__) or [])
        for model in BACKUP_MODELS
    }
    return {
        "restored": restored,
        "sources_user_count": len(payload.backup.config.get("sources_user") or []),
        "total_rows": sum(restored.values()),
    }


@router.delete("/api/data/wipe")
def wipe(
    db: Session = Depends(get_db),
    confirm: str = Query("", description="must equal 'YES' to proceed"),
    keep_profile: bool = True,
):
    """Delete all scraped data. UserProfile is preserved by default."""
    if confirm != "YES":
        raise HTTPException(400, "confirm=YES required to wipe data")

    # Order matters for FK cascades on SQLite.
    tables = [
        JobEvent.__tablename__,
        JobRanking.__tablename__,
        Screening.__tablename__,
        Application.__tablename__,
        Contact.__tablename__,
        Note.__tablename__,
        Watch.__tablename__,
        ScrapeRun.__tablename__,
        Job.__tablename__,
        Company.__tablename__,
    ]
    counts: dict[str, int] = {}
    for t in tables:
        counts[t] = db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() or 0
        db.execute(text(f"DELETE FROM {t}"))
    db.commit()
    return {"deleted": counts, "profile_kept": keep_profile}
