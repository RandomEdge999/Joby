from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_db, SessionLocal
from ..models import ScrapeRun
from ..services.runner import start_run

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _serialize_run(r: ScrapeRun) -> dict:
    stats = r.stats_json or {}
    return {
        "id": r.id,
        "trigger_type": r.trigger_type,
        "status": r.status,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "source_summary": r.source_summary_json,
        "stats": stats,
        "search": stats.get("search"),
        "totals": stats.get("totals"),
        "error": r.error_json,
    }


@router.post("/trigger")
def trigger_run():
    run_id = start_run(trigger_type="manual")
    return {"run_id": run_id, "status": "pending"}


@router.get("/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    r = db.get(ScrapeRun, run_id)
    if not r:
        raise HTTPException(404, "run not found")
    return _serialize_run(r)


@router.get("")
def list_runs(db: Session = Depends(get_db), limit: int = 20):
    rows = db.query(ScrapeRun).order_by(ScrapeRun.id.desc()).limit(limit).all()
    return {"items": [_serialize_run(r) for r in rows]}


@router.get("/{run_id}/events")
async def stream_events(run_id: int):
    """SSE stream: polls run state and emits new events until run finishes."""
    async def gen():
        last_idx = 0
        while True:
            db = SessionLocal()
            try:
                r = db.get(ScrapeRun, run_id)
                if not r:
                    yield f"event: error\ndata: {json.dumps({'error':'not_found'})}\n\n"
                    return
                events = (r.stats_json or {}).get("events", []) or []
                for ev in events[last_idx:]:
                    yield f"data: {json.dumps(ev)}\n\n"
                last_idx = len(events)
                if r.status in ("completed", "failed", "skipped"):
                    final = {"terminal": True, "status": r.status,
                             "totals": (r.stats_json or {}).get("totals"),
                             "error": r.error_json}
                    yield f"event: done\ndata: {json.dumps(final)}\n\n"
                    return
            finally:
                db.close()
            await asyncio.sleep(1.0)

    return StreamingResponse(gen(), media_type="text/event-stream")
