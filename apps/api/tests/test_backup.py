from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.db import SessionLocal
from app.models import (
    Application,
    Company,
    Job,
    JobRanking,
    Note,
    Screening,
    UserProfile,
)
from app.profile.presets import get_preset
from app.services import discovery
from app.config import settings


client = TestClient(app)


def _clear_workspace() -> None:
    with SessionLocal() as db:
        for table in [
            "job_events",
            "notes",
            "contacts",
            "applications",
            "job_rankings",
            "screenings",
            "scrape_runs",
            "watches",
            "jobs",
            "company_h1b",
            "companies",
            "user_profile",
        ]:
            db.execute(text(f"DELETE FROM {table}"))
        db.commit()


def test_workspace_backup_exports_and_restores(monkeypatch, tmp_path):
    _clear_workspace()

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    monkeypatch.setattr(settings, "config_dir", str(config_dir))

    now = datetime.now(UTC).replace(tzinfo=None)
    profile = get_preset("us-new-grad").model_dump()
    with SessionLocal() as db:
        user = UserProfile(name="backup-user", preset="us-new-grad", profile_json=profile, is_active=True)
        db.add(user)
        db.flush()
        company = Company(name="Backup Labs", normalized_name="backup labs")
        db.add(company)
        db.flush()
        job = Job(
            source="greenhouse",
            external_job_id="backup-001",
            canonical_url="https://backuplabs.example/jobs/backend-engineer",
            url_hash="backup-001",
            title="Backend Engineer",
            normalized_title="backend engineer",
            company_id=company.id,
            company_name_raw=company.name,
            location_raw="Remote, United States",
            country="US",
            remote_type="remote",
            employment_type="full_time",
            level_guess="entry",
            description_text="python fastapi sql backend engineer",
            posted_at=now,
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
            dedupe_key="backup-001",
        )
        db.add(job)
        db.flush()
        db.add(Screening(
            job_id=job.id,
            profile_id=user.id,
            prefilter_passed=True,
            prefilter_reasons_json={"signals": {"visa_tier": "not_applicable"}},
            llm_status="skipped",
            screening_json={"summary": "backup"},
        ))
        db.add(JobRanking(
            job_id=job.id,
            profile_id=user.id,
            fit_score=0.8,
            opportunity_score=0.7,
            urgency_score=0.6,
            composite_score=0.74,
            reason_json={"weights": {"fit": 0.5, "opportunity": 0.3, "urgency": 0.2}},
            ranking_version="v1",
        ))
        db.add(Application(job_id=job.id, status="saved", notes_summary="Track this role"))
        db.add(Note(job_id=job.id, body="Backup note"))
        db.commit()

    discovery.write_user_sources([
        {"company": "Backup Labs", "type": "greenhouse", "slug": "backuplabs", "enabled": True}
    ])

    export_response = client.get("/api/backup/export")
    assert export_response.status_code == 200
    bundle = export_response.json()
    assert bundle["schema_version"] == 1
    assert bundle["summary"]["table_counts"]["user_profile"] == 1
    assert bundle["summary"]["table_counts"]["jobs"] == 1
    assert bundle["summary"]["table_counts"]["applications"] == 1
    assert bundle["summary"]["sources_user_count"] == 1

    _clear_workspace()
    discovery.write_user_sources([])
    assert discovery.load_user_sources() == []

    import_response = client.post(
        "/api/backup/import",
        json={"backup": bundle, "confirm_replace": True},
    )
    assert import_response.status_code == 200, import_response.text
    assert import_response.json()["total_rows"] >= 5
    assert import_response.json()["sources_user_count"] == 1

    with SessionLocal() as db:
        assert db.query(UserProfile).count() == 1
        assert db.query(Job).count() == 1
        assert db.query(Application).count() == 1
        assert db.query(Note).count() == 1
    assert discovery.load_user_sources()[0]["slug"] == "backuplabs"


def test_workspace_backup_import_requires_confirmation():
    response = client.post(
        "/api/backup/import",
        json={
            "backup": {
                "schema_version": 1,
                "exported_at": datetime.now(UTC).isoformat(),
                "tables": {},
                "config": {},
                "summary": {},
            },
            "confirm_replace": False,
        },
    )
    assert response.status_code == 400
    assert "confirm_replace=true required" in response.text