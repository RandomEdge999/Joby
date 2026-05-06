from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Company, Contact, Job, ScrapeRun, ScrapeRunJob, Screening, UserProfile


client = TestClient(app)


SENTINEL = "joby-filter-contract"


def _seed_filter_jobs():
    db = SessionLocal()
    try:
        db.query(UserProfile).update({UserProfile.is_active: False})
        profile = UserProfile(
            name="Filter Contract Profile",
            profile_json={"profile_name": "Filter Contract Profile"},
            is_active=True,
        )
        top_company = Company(
            name="Filter Top Co",
            normalized_name="filter-top-co-contract",
            company_tier="top",
        )
        strong_company = Company(
            name="Filter Strong Co",
            normalized_name="filter-strong-co-contract",
            company_tier="strong",
        )
        standard_company = Company(
            name="Filter Standard Co",
            normalized_name="filter-standard-co-contract",
            company_tier="standard",
        )
        db.add_all([profile, top_company, strong_company, standard_company])
        db.commit()
        db.refresh(profile)
        db.refresh(top_company)
        db.refresh(strong_company)
        db.refresh(standard_company)

        now = datetime.utcnow()
        top_job = Job(
            source="test-filter",
            external_job_id=f"{SENTINEL}-top",
            title=f"{SENTINEL} Software Engineer",
            company_id=top_company.id,
            company_name_raw=top_company.name,
            location_raw="Remote, US",
            remote_type="remote",
            employment_type="full_time",
            level_guess="new_grad",
            salary_min=130000,
            posted_at=now,
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
            description_text="Filter contract role with sponsorship signal.",
        )
        strong_job = Job(
            source="test-filter",
            external_job_id=f"{SENTINEL}-strong",
            title=f"{SENTINEL} Data Analyst Intern",
            company_id=strong_company.id,
            company_name_raw=strong_company.name,
            location_raw="New York, NY",
            remote_type="hybrid",
            employment_type="internship",
            level_guess="intern",
            salary_min=70000,
            posted_at=now - timedelta(days=10),
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
            description_text="Filter contract role with possible sponsorship signal.",
        )
        inactive_job = Job(
            source="test-filter",
            external_job_id=f"{SENTINEL}-inactive",
            title=f"{SENTINEL} Closed Backend Engineer",
            company_id=standard_company.id,
            company_name_raw=standard_company.name,
            location_raw="Austin, TX",
            remote_type="onsite",
            employment_type="contract",
            level_guess="entry",
            salary_min=90000,
            posted_at=now,
            first_seen_at=now,
            last_seen_at=now,
            is_active=False,
            description_text="Filter contract role that is inactive.",
        )
        db.add_all([top_job, strong_job, inactive_job])
        db.commit()
        db.refresh(top_job)
        db.refresh(strong_job)
        db.refresh(inactive_job)

        db.add_all([
            Screening(
                job_id=top_job.id,
                profile_id=profile.id,
                prefilter_passed=True,
                prefilter_reasons_json={"signals": {"visa_tier": "likely"}},
            ),
            Screening(
                job_id=strong_job.id,
                profile_id=profile.id,
                prefilter_passed=True,
                prefilter_reasons_json={"signals": {"visa_tier": "possible"}},
            ),
            Screening(
                job_id=inactive_job.id,
                profile_id=profile.id,
                prefilter_passed=True,
                prefilter_reasons_json={"signals": {"visa_tier": "unlikely"}},
            ),
            Contact(
                job_id=top_job.id,
                name="Recruiter",
                title="Technical Recruiter",
                source="test",
                confidence_score=0.9,
            ),
        ])
        db.commit()
    finally:
        db.close()


def _get(params: dict):
    merged = {"q": SENTINEL, **params}
    r = client.get("/api/jobs", params=merged)
    assert r.status_code == 200, r.text
    return r.json()


def test_jobs_filter_contract_values_and_totals():
    _seed_filter_jobs()

    data = _get({"company_tier": "top"})
    assert data["total"] == 1
    assert data["items"][0]["company"]["tier"] == "top"

    data = _get({"visa_tier": "likely"})
    assert data["total"] == 1
    assert data["items"][0]["screening"]["prefilter_reasons"]["signals"]["visa_tier"] == "likely"

    data = _get({"remote_type": "hybrid", "employment_type": "internship", "level": "intern"})
    assert data["total"] == 1
    assert data["items"][0]["employment_type"] == "internship"

    data = _get({"level": "entry"})
    assert data["total"] == 1
    assert data["items"][0]["level_guess"] == "new_grad"

    data = _get({"salary_floor": 100000})
    assert data["total"] == 1
    assert data["items"][0]["salary"]["min"] == 130000

    data = _get({"posted_within_days": 3})
    assert data["total"] == 1
    assert data["items"][0]["company"]["tier"] == "top"

    data = _get({"has_contacts": "true"})
    assert data["total"] == 1
    assert data["items"][0]["company"]["tier"] == "top"

    data = _get({"has_contacts": "false"})
    assert data["total"] == 1
    assert data["items"][0]["company"]["tier"] == "strong"

    data = _get({"active_only": "false", "company_tier": "standard"})
    assert data["total"] == 1
    assert data["items"][0]["is_active"] is False


def test_jobs_rejects_stale_filter_values():
    r = client.get("/api/jobs", params={"company_tier": "top_tier"})
    assert r.status_code == 422

    r = client.get("/api/jobs", params={"visa_tier": "likely_sponsors"})
    assert r.status_code == 422


def test_jobs_location_filter_handles_us_and_foreign_locations():
    marker = "joby-location-filter-contract"
    db = SessionLocal()
    try:
        db.query(Job).filter(Job.external_job_id.in_([f"{marker}-us", f"{marker}-foreign"])).delete(synchronize_session=False)
        db.query(UserProfile).update({UserProfile.is_active: False})
        profile = UserProfile(name="Location Filter Profile", profile_json={"profile_name": "Location Filter Profile"}, is_active=True)
        us_company = Company(name="Location US Co", normalized_name=f"{marker}-us-co")
        foreign_company = Company(name="Location Foreign Co", normalized_name=f"{marker}-foreign-co")
        db.add_all([profile, us_company, foreign_company])
        db.commit()
        db.refresh(us_company)
        db.refresh(foreign_company)
        now = datetime.utcnow()
        db.add_all([
            Job(
                source="test-location",
                external_job_id=f"{marker}-us",
                title=f"{marker} Engineer",
                company_id=us_company.id,
                company_name_raw=us_company.name,
                location_raw="New York, NY",
                city="New York",
                state="NY",
                country="US",
                remote_type="hybrid",
                employment_type="full_time",
                level_guess="entry",
                posted_at=now,
                first_seen_at=now,
                last_seen_at=now,
                is_active=True,
                description_text="US location filter fixture.",
            ),
            Job(
                source="test-location",
                external_job_id=f"{marker}-foreign",
                title=f"{marker} Engineer",
                company_id=foreign_company.id,
                company_name_raw=foreign_company.name,
                location_raw="Madrid, Spain",
                city="Madrid",
                country="Spain",
                remote_type="onsite",
                employment_type="full_time",
                level_guess="entry",
                posted_at=now,
                first_seen_at=now,
                last_seen_at=now,
                is_active=True,
                description_text="Foreign location filter fixture.",
            ),
        ])
        db.commit()
    finally:
        db.close()

    r = client.get("/api/jobs", params={"q": marker, "location": "United States"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["location"]["country"] == "US"

    r = client.get("/api/jobs", params={"q": marker, "location": "Spain"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["location"]["country"] == "Spain"


def test_entry_level_filter_keeps_unknown_level_rows_visible():
    marker = "joby-entry-unknown-filter"
    db = SessionLocal()
    try:
        db.query(Job).filter(Job.external_job_id == marker).delete(synchronize_session=False)
        db.query(UserProfile).update({UserProfile.is_active: False})
        profile = UserProfile(name="Entry Filter Profile", profile_json={"profile_name": "Entry Filter Profile"}, is_active=True)
        company = Company(name="Entry Unknown Co", normalized_name=f"{marker}-co")
        db.add_all([profile, company])
        db.commit()
        db.refresh(company)
        now = datetime.utcnow()
        db.add(Job(
            source="test-entry",
            external_job_id=marker,
            title="Data Analyst",
            company_id=company.id,
            company_name_raw=company.name,
            location_raw="Remote, United States",
            remote_type="remote",
            employment_type="full_time",
            level_guess="unknown",
            posted_at=now,
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
            description_text="Entry filter should not hide unknown-level analyst roles.",
        ))
        db.commit()
    finally:
        db.close()

    r = client.get("/api/jobs", params={"q": "Data Analyst", "company": "Entry Unknown Co", "level": "entry"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["level_guess"] == "unknown"


def test_jobs_can_be_scoped_to_a_search_run():
    marker = "joby-run-scope-filter"
    db = SessionLocal()
    try:
        db.query(ScrapeRunJob).delete(synchronize_session=False)
        db.query(Job).filter(Job.external_job_id.in_([f"{marker}-one", f"{marker}-two"])).delete(synchronize_session=False)
        db.query(UserProfile).update({UserProfile.is_active: False})
        profile = UserProfile(name="Run Scope Profile", profile_json={"profile_name": "Run Scope Profile"}, is_active=True)
        company = Company(name="Run Scope Co", normalized_name=f"{marker}-co")
        db.add_all([profile, company])
        db.commit()
        db.refresh(company)
        now = datetime.utcnow()
        job_one = Job(
            source="jobspy:indeed",
            external_job_id=f"{marker}-one",
            title=f"{marker} Data Analyst",
            company_id=company.id,
            company_name_raw=company.name,
            location_raw="Remote, United States",
            country="US",
            remote_type="remote",
            employment_type="full_time",
            level_guess="entry",
            posted_at=now,
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
            description_text="Run-scoped result fixture.",
        )
        job_two = Job(
            source="greenhouse",
            external_job_id=f"{marker}-two",
            title=f"{marker} Data Analyst",
            company_id=company.id,
            company_name_raw=company.name,
            location_raw="Remote, United States",
            country="US",
            remote_type="remote",
            employment_type="full_time",
            level_guess="entry",
            posted_at=now,
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
            description_text="Historical local result fixture.",
        )
        run = ScrapeRun(trigger_type="search", status="completed", stats_json={"events": []})
        db.add_all([job_one, job_two, run])
        db.commit()
        db.refresh(job_one)
        db.refresh(run)
        run_id = run.id
        db.add(ScrapeRunJob(run_id=run_id, job_id=job_one.id, source=job_one.source, is_new=True))
        db.commit()
    finally:
        db.close()

    r = client.get("/api/jobs", params={"q": marker, "run_id": run_id})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    assert data["run_id"] == run_id
    assert data["items"][0]["source"] == "jobspy:indeed"


def test_strict_search_run_scope_hides_prefilter_failures():
    marker = "joby-strict-run-scope"
    db = SessionLocal()
    try:
        db.query(Job).filter(Job.external_job_id.in_([f"{marker}-pass", f"{marker}-fail"])).delete(synchronize_session=False)
        db.query(UserProfile).update({UserProfile.is_active: False})
        profile = UserProfile(name="Strict Scope Profile", profile_json={"profile_name": "Strict Scope Profile"}, is_active=True)
        company = Company(name="Strict Scope Co", normalized_name=f"{marker}-co")
        db.add_all([profile, company])
        db.commit()
        db.refresh(profile)
        db.refresh(company)
        now = datetime.utcnow()
        passed_job = Job(
            source="jobspy:indeed",
            external_job_id=f"{marker}-pass",
            title=f"{marker} Passed Backend Engineer",
            company_id=company.id,
            company_name_raw=company.name,
            location_raw="Remote, United States",
            country="US",
            remote_type="remote",
            employment_type="full_time",
            level_guess="entry",
            posted_at=now,
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
            description_text="Passed strict fixture.",
        )
        failed_job = Job(
            source="jobspy:indeed",
            external_job_id=f"{marker}-fail",
            title=f"{marker} Failed Backend Engineer",
            company_id=company.id,
            company_name_raw=company.name,
            location_raw="Remote, United States",
            country="US",
            remote_type="remote",
            employment_type="full_time",
            level_guess="entry",
            posted_at=now,
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
            description_text="Failed strict fixture.",
        )
        run = ScrapeRun(
            trigger_type="search",
            status="completed",
            stats_json={"events": [], "search": {"query": marker, "intent": "strict"}},
        )
        db.add_all([passed_job, failed_job, run])
        db.commit()
        db.refresh(passed_job)
        db.refresh(failed_job)
        db.refresh(run)
        run_id = run.id
        db.add_all([
            ScrapeRunJob(run_id=run_id, job_id=passed_job.id, source=passed_job.source, is_new=True),
            ScrapeRunJob(run_id=run_id, job_id=failed_job.id, source=failed_job.source, is_new=True),
            Screening(job_id=passed_job.id, profile_id=profile.id, prefilter_passed=True, prefilter_reasons_json={"signals": {"visa_tier": "likely"}}),
            Screening(job_id=failed_job.id, profile_id=profile.id, prefilter_passed=False, prefilter_reasons_json={"signals": {"visa_tier": "likely"}}),
        ])
        db.commit()
    finally:
        db.close()

    r = client.get("/api/jobs", params={"q": marker, "run_id": run_id})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    assert "Passed" in data["items"][0]["title"]