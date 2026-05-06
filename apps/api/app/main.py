from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import Base, engine
from . import models  # noqa: F401 - register models
from .routers import (
    health, profile, jobs, runs, companies, watches, applications,
    dashboard, backfill, notes, contacts, cold_email, export, sources, search,
)
from .services import scheduler as sched_mod
from .services import runner as runner_mod


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def _ensure_default_profile() -> None:
    """No-blocker bootstrap: on first run create a blank-but-valid profile so
    every endpoint works immediately. Users customize it via /api/profile."""
    try:
        from .db import SessionLocal
        from .models import UserProfile
        from .profile.presets import get_preset
        with SessionLocal() as db:
            has_any = db.query(UserProfile).first() is not None
            if has_any:
                return
            blank = get_preset("custom")
            db.add(UserProfile(name="default", is_active=True,
                               profile_json=blank.model_dump()))
            db.commit()
    except Exception:
        logging.getLogger("joby").exception("default profile bootstrap failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_default_profile()
    try:
        runner_mod.reconcile_incomplete_runs()
    except Exception:
        logging.getLogger("joby").exception("stale run cleanup failed")
    try:
        sched_mod.start()
    except Exception:
        logging.getLogger("joby").exception("scheduler failed to start")
    try:
        yield
    finally:
        try:
            sched_mod.shutdown()
        except Exception:
            pass


app = FastAPI(title="Joby API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(health.router)
app.include_router(profile.router)
app.include_router(jobs.router)
app.include_router(runs.router)
app.include_router(companies.router)
app.include_router(watches.router)
app.include_router(applications.router)
app.include_router(dashboard.router)
app.include_router(backfill.router)
app.include_router(notes.router)
app.include_router(contacts.router)
app.include_router(cold_email.router)
app.include_router(export.router)
app.include_router(sources.router)
app.include_router(search.router)


@app.get("/")
def root():
    return {"name": "joby-api", "version": "0.1.0"}
