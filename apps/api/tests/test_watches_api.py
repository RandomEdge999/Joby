from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_watches_crud_roundtrip():
    # Create
    r = client.post("/api/watches", json={
        "name": "Nightly scrape",
        "cadence_minutes": 360,
        "enabled": True,
        "query_json": {"keywords": ["engineer"]},
    })
    assert r.status_code == 200, r.text
    w = r.json()
    wid = w["id"]
    assert w["name"] == "Nightly scrape"
    assert w["cadence_minutes"] == 360

    # List
    r = client.get("/api/watches")
    assert r.status_code == 200
    assert any(x["id"] == wid for x in r.json()["items"])

    # Update
    r = client.patch(f"/api/watches/{wid}", json={"cadence_minutes": 720, "enabled": False})
    assert r.status_code == 200
    assert r.json()["cadence_minutes"] == 720
    assert r.json()["enabled"] is False

    # Events endpoint for this watch exists (empty)
    r = client.get(f"/api/watches/{wid}/events")
    assert r.status_code == 200
    assert r.json()["items"] == []

    # Recent global
    r = client.get("/api/watches/events/recent")
    assert r.status_code == 200

    # Delete
    r = client.delete(f"/api/watches/{wid}")
    assert r.status_code == 200


def test_watches_cadence_min():
    r = client.post("/api/watches", json={
        "name": "Too fast", "cadence_minutes": 1,
    })
    assert r.status_code == 422
