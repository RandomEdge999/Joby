from fastapi.testclient import TestClient

from app.main import app
from app.profile.schema import Profile
from app.profile.presets import get_preset
from app.routers import search as search_router
from app.services.runner import _filter_search_results_by_location, _profile_with_search_overrides


client = TestClient(app)


def test_search_run_endpoint_records_query_metadata(monkeypatch):
    captured = {}

    def fake_start_run(trigger_type="manual", watch_id=None, search=None):
        captured["trigger_type"] = trigger_type
        captured["watch_id"] = watch_id
        captured["search"] = search
        return 123

    monkeypatch.setattr(search_router, "start_run", fake_start_run)

    r = client.post("/api/search/run", json={
        "query": "  AI engineer  ",
        "intent": "strict",
        "locations": ["United States", "Remote", "Remote"],
        "sources": ["jobspy", "ats"],
        "results_per_source": 12,
        "posted_within_days": 14,
        "use_cache": False,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["run_id"] == 123
    assert data["search"]["query"] == "AI engineer"
    assert data["search"]["intent"] == "strict"
    assert data["search"]["locations"] == ["United States", "Remote"]
    assert captured["trigger_type"] == "search"
    assert captured["search"] == data["search"]


def test_search_run_rejects_invalid_source():
    r = client.post("/api/search/run", json={
        "query": "AI engineer",
        "sources": ["private_portal"],
    })
    assert r.status_code == 422


def test_search_run_rejects_invalid_intent():
    r = client.post("/api/search/run", json={
        "query": "AI engineer",
        "intent": "autopilot",
    })
    assert r.status_code == 422


def test_search_run_defaults_to_query_driven_web_search(monkeypatch):
    captured = {}

    def fake_start_run(trigger_type="manual", watch_id=None, search=None):
        captured["search"] = search
        return 124

    monkeypatch.setattr(search_router, "start_run", fake_start_run)

    r = client.post("/api/search/run", json={"query": "AI engineer"})
    assert r.status_code == 200, r.text
    assert r.json()["search"]["sources"] == ["jobspy"]
    assert r.json()["search"]["intent"] == "match"
    assert captured["search"]["sources"] == ["jobspy"]


def test_search_overrides_profile_without_persisting_it():
    profile = Profile()
    updated = _profile_with_search_overrides(profile, {
        "query": "AI engineer",
        "locations": ["Remote"],
        "sources": ["jobspy"],
        "results_per_source": 15,
        "posted_within_days": 7,
    })

    assert updated.targeting.target_roles == ["AI engineer"]
    assert updated.targeting.posted_within_days == 7
    assert updated.sources.jobspy_search_terms == ["AI engineer"]
    assert updated.sources.jobspy_locations == ["Remote"]
    assert updated.sources.jobspy_results_per_term == 15
    assert updated.sources.enable_jobspy is True
    assert updated.sources.enable_ats is False
    assert updated.sources.enable_workday is False
    assert profile.targeting.target_roles == []


def test_search_without_posted_filter_disables_profile_recency_cap():
    profile = Profile()
    assert profile.targeting.posted_within_days == 30

    updated = _profile_with_search_overrides(profile, {
        "query": "Data Analyst",
        "locations": ["United States"],
        "sources": ["jobspy"],
        "posted_within_days": None,
    })

    assert updated.targeting.posted_within_days is None
    assert profile.targeting.posted_within_days == 30


def test_explore_intent_relaxes_resume_skills_without_persisting_profile():
    profile = get_preset("international-student-opt")

    updated = _profile_with_search_overrides(profile, {
        "query": "AI engineer",
        "locations": ["United States"],
        "sources": ["jobspy"],
        "intent": "explore",
    })

    assert updated.resume.must_have_skills == []
    assert updated.resume.nice_to_have_skills == []
    assert updated.scoring.w_fit == 0.35
    assert updated.scoring.w_opportunity == 0.35
    assert updated.scoring.w_urgency == 0.30
    assert profile.resume.must_have_skills == ["python", "sql"]


def test_strict_intent_reweights_toward_profile_fit():
    profile = get_preset("international-student-opt")

    updated = _profile_with_search_overrides(profile, {
        "query": "AI engineer",
        "locations": ["United States"],
        "sources": ["jobspy"],
        "intent": "strict",
    })

    assert updated.resume.must_have_skills == ["python", "sql"]
    assert updated.scoring.w_fit == 0.65
    assert updated.scoring.w_opportunity == 0.25
    assert updated.scoring.w_urgency == 0.10


def test_search_locations_override_profile_target_locations_temporarily():
    profile = get_preset("international-student-opt")

    updated = _profile_with_search_overrides(profile, {
        "query": "Data Analyst",
        "locations": ["United States", "Remote"],
        "sources": ["jobspy"],
    })

    assert [item.name for item in updated.targeting.target_locations] == ["United States", "Remote"]
    assert [item.name for item in profile.targeting.target_locations] == ["san_francisco_bay_area"]


def test_post_fetch_location_gate_filters_out_off_target_jobs():
    jobs = [
        {"title": "US role", "location_raw": "Austin, TX", "city": "Austin", "state": "TX", "country": "US"},
        {"title": "Spain role", "location_raw": "Madrid, Spain", "city": "Madrid", "state": None, "country": "Spain"},
    ]

    filtered, removed = _filter_search_results_by_location(jobs, {"locations": ["United States"]})

    assert len(filtered) == 1
    assert filtered[0]["title"] == "US role"
    assert removed == 1


def test_search_overrides_ignore_tracked_board_sources_for_query_runs():
    profile = Profile()

    updated = _profile_with_search_overrides(profile, {
        "query": "Data Analyst",
        "locations": ["United States"],
        "sources": ["jobspy", "ats", "workday"],
    })

    assert updated.sources.enable_jobspy is True
    assert updated.sources.enable_ats is False
    assert updated.sources.enable_workday is False