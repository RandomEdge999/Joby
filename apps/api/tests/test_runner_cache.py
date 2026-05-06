from app.db import SessionLocal
from app.models import ScrapeRun
from app.profile.schema import Profile
from app.services import runner


def test_scrape_all_passes_search_cache_policy_to_direct_sources(monkeypatch):
    captured = {}

    def fake_enabled_ats_sources():
        return [{"type": "greenhouse", "slug": "figma", "company": "Figma"}]

    def fake_cache_status(source_type, slug, **kwargs):
        captured["cache_kwargs"] = kwargs
        return {"status": "bypassed" if kwargs.get("use_cache") is False else "miss"}

    def fake_fetch_source(source_type, slug, **kwargs):
        captured["fetch_kwargs"] = kwargs
        return [{"source": source_type, "external_job_id": "job-1", "company_name_raw": "Figma"}]

    monkeypatch.setattr(runner, "enabled_ats_sources", fake_enabled_ats_sources)
    monkeypatch.setattr(runner.ats_scraper, "cache_status", fake_cache_status)
    monkeypatch.setattr(runner.ats_scraper, "fetch_source", fake_fetch_source)

    profile = Profile()
    profile.sources.enable_ats = True
    profile.sources.enable_workday = False
    profile.sources.enable_jobspy = False

    db = SessionLocal()
    try:
        run = ScrapeRun(trigger_type="search", status="running", stats_json={})
        db.add(run)
        db.commit()
        db.refresh(run)

        jobs, _, _, cache_summary, errors = runner._scrape_all(
            db, run, profile, {"use_cache": False}
        )
    finally:
        db.close()

    assert errors == []
    assert jobs[0]["external_job_id"] == "job-1"
    assert captured["cache_kwargs"]["use_cache"] is False
    assert captured["fetch_kwargs"]["use_cache"] is False
    assert cache_summary["bypassed"] == 1


def test_scrape_all_reports_jobspy_cache_bypass(monkeypatch):
    def fake_jobspy_config():
        return {}

    def fake_cache_status(*args, **kwargs):
        raise AssertionError("cache_status should not be called when cache is bypassed")

    def fake_fetch_jobspy(**kwargs):
        return [{"source": "jobspy:indeed", "external_job_id": "job-1", "company_name_raw": "Acme"}]

    monkeypatch.setattr(runner, "jobspy_config", fake_jobspy_config)
    monkeypatch.setattr(runner.jobspy_daemon, "cache_status", fake_cache_status)
    monkeypatch.setattr(runner.jobspy_daemon, "fetch_jobspy", fake_fetch_jobspy)

    profile = Profile()
    profile.sources.enable_ats = False
    profile.sources.enable_workday = False
    profile.sources.enable_jobspy = True
    profile.sources.jobspy_search_terms = ["Data Analyst"]
    profile.sources.jobspy_locations = ["United States"]

    db = SessionLocal()
    try:
        run = ScrapeRun(trigger_type="search", status="running", stats_json={})
        db.add(run)
        db.commit()
        db.refresh(run)

        jobs, _, details, cache_summary, errors = runner._scrape_all(
            db, run, profile, {"use_cache": False}
        )
    finally:
        db.close()

    assert errors == []
    assert jobs[0]["external_job_id"] == "job-1"
    assert cache_summary["bypassed"] == 1
    assert details["jobspy:Data Analyst@United States"]["cache"]["status"] == "bypassed"
    assert details["jobspy:Data Analyst@United States"]["type"] == "jobspy_bundle"
    assert details["jobspy:indeed:Data Analyst@United States"]["count"] == 1
    assert details["jobspy:linkedin:Data Analyst@United States"]["status"] == "empty"


def test_post_fetch_location_gate_keeps_remote_jobs_for_remote_search():
    jobs = [
        {"title": "Remote role", "location_raw": "Berlin, Germany", "country": "Germany", "remote_type": "remote"},
        {"title": "Onsite role", "location_raw": "Berlin, Germany", "country": "Germany", "remote_type": "onsite"},
    ]

    filtered, removed = runner._filter_search_results_by_location(jobs, {"locations": ["Remote"]})

    assert [job["title"] for job in filtered] == ["Remote role"]
    assert removed == 1