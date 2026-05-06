from datetime import datetime

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import ScrapeRun


client = TestClient(app)


def test_sources_health_shape_includes_recent_run_data():
    db = SessionLocal()
    try:
        run = ScrapeRun(
            trigger_type="search",
            status="completed",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            source_summary_json={
                "per_source": {
                    "greenhouse:Health Test Co": 3,
                    "jobspy:AI engineer@United States": 8,
                },
                "details": {
                    "greenhouse:Health Test Co": {
                        "key": "greenhouse:Health Test Co",
                        "type": "greenhouse",
                        "label": "Health Test Co",
                        "status": "ok",
                        "count": 3,
                        "duration_ms": 220,
                    },
                    "jobspy:AI engineer@United States": {
                        "key": "jobspy:AI engineer@United States",
                        "type": "jobspy",
                        "label": "AI engineer@United States",
                        "status": "ok",
                        "count": 8,
                        "duration_ms": 95,
                        "cache": {"status": "hit", "age_seconds": 40},
                    },
                },
                "cache": {
                    "used_cache": True,
                    "freshness_window_hours": 336,
                    "total_queries": 1,
                    "hit": 1,
                    "miss": 0,
                    "stale": 0,
                    "bypassed": 0,
                },
            },
            stats_json={"events": []},
            error_json={"errors": [
                {"source": "lever", "company": "Broken Co", "error": "timeout"},
            ]},
        )
        db.add(run)
        db.commit()
    finally:
        db.close()

    r = client.get("/api/sources/health")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "jobspy" in data
    assert "search_cache" in data
    assert "sources" in data
    assert "recent_errors" in data

    by_key = {row["key"]: row for row in data["sources"]}
    assert by_key["greenhouse:Health Test Co"]["last_status"] == "ok"
    assert by_key["greenhouse:Health Test Co"]["last_count"] == 3
    assert by_key["greenhouse:Health Test Co"]["last_duration_ms"] == 220
    assert by_key["jobspy:AI engineer@United States"]["last_cache_status"] == "hit"
    assert by_key["lever:Broken Co"]["last_status"] == "error"
    assert data["search_cache"]["hit"] == 1
    assert any(item["error"] == "timeout" for item in data["recent_errors"])


def test_sources_health_tracks_recent_history_and_latest_error():
    db = SessionLocal()
    try:
        older = ScrapeRun(
            trigger_type="search",
            status="completed",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            source_summary_json={
                "per_source": {"greenhouse:History Co": 4},
                "details": {
                    "greenhouse:History Co": {
                        "key": "greenhouse:History Co",
                        "type": "greenhouse",
                        "label": "History Co",
                        "status": "ok",
                        "count": 4,
                        "duration_ms": 140,
                    },
                },
            },
            stats_json={"events": []},
        )
        newer = ScrapeRun(
            trigger_type="search",
            status="completed",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            source_summary_json={
                "details": {
                    "greenhouse:History Co": {
                        "key": "greenhouse:History Co",
                        "type": "greenhouse",
                        "label": "History Co",
                        "status": "error",
                        "count": 0,
                        "duration_ms": 50,
                        "error": "rate limit",
                    },
                },
            },
            stats_json={"events": []},
            error_json={"errors": [
                {"source": "greenhouse", "company": "History Co", "error": "rate limit"},
            ]},
        )
        db.add(older)
        db.add(newer)
        db.commit()
    finally:
        db.close()

    r = client.get("/api/sources/health")
    assert r.status_code == 200, r.text
    row = next(item for item in r.json()["sources"] if item["key"] == "greenhouse:History Co")
    assert row["last_status"] == "error"
    assert row["last_error"] == "rate limit"
    assert row["last_success_at"] is not None
    assert len(row["recent_history"]) >= 2
    assert row["recent_history"][0]["status"] == "error"