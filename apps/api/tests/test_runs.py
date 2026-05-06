from datetime import datetime

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import ScrapeRun


client = TestClient(app)


def test_runs_list_exposes_search_source_diagnostics():
    db = SessionLocal()
    try:
        run = ScrapeRun(
            trigger_type="search",
            status="completed",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            stats_json={
                "events": [],
                "search": {
                    "query": "Data Analyst",
                    "locations": ["United States"],
                    "sources": ["jobspy"],
                    "results_per_source": 200,
                    "use_cache": False,
                },
                "totals": {"persisted": 332, "ranked": 332},
            },
            source_summary_json={
                "details": {
                    "jobspy:Data Analyst@United States": {
                        "key": "jobspy:Data Analyst@United States",
                        "type": "jobspy",
                        "label": "Data Analyst@United States",
                        "status": "ok",
                        "count": 332,
                        "duration_ms": 93000,
                        "cache": {"status": "bypassed", "age_seconds": None},
                    }
                },
                "cache": {
                    "used_cache": False,
                    "total_queries": 1,
                    "hit": 0,
                    "miss": 0,
                    "stale": 0,
                    "bypassed": 1,
                },
            },
            error_json={"errors": [{"source": "jobspy", "error": "ziprecruiter 403"}]},
        )
        db.add(run)
        db.commit()
    finally:
        db.close()

    r = client.get("/api/runs", params={"limit": 1})
    assert r.status_code == 200, r.text
    data = r.json()["items"][0]
    assert data["search"]["query"] == "Data Analyst"
    assert data["totals"]["persisted"] == 332
    assert data["source_summary"]["details"]["jobspy:Data Analyst@United States"]["count"] == 332
    assert data["source_summary"]["cache"]["bypassed"] == 1
    assert data["error"]["errors"][0]["error"] == "ziprecruiter 403"