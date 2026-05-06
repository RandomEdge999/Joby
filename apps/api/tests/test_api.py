from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import Company, Job, JobRanking, UserProfile

from datetime import UTC, datetime

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_llm_health_shape():
    r = client.get("/api/llm/health")
    assert r.status_code == 200
    data = r.json()
    assert "available" in data
    assert "base_url" in data


def test_presets_list():
    r = client.get("/api/profile/presets")
    assert r.status_code == 200
    assert len(r.json()["presets"]) == 6


def test_profile_default_and_put():
    r = client.get("/api/profile")
    assert r.status_code == 200
    assert r.json()["profile"] is not None

    new_profile = {
        "profile_name": "Test Profile",
        "preset": "us-new-grad",
        "identity": {"citizenship_status": "us_citizen",
                     "needs_sponsorship_now": False, "needs_sponsorship_future": False,
                     "security_clearance": "none",
                     "major_family": {"primary": "cs", "related": []}},
        "targeting": {"target_employment": ["full_time"], "target_levels": ["entry"],
                      "target_roles": ["software engineer"], "target_locations": [],
                      "remote_preference": "any", "relocation_ok": True,
                      "posted_within_days": 30, "industry_allow": [], "industry_block": [],
                      "company_tier_preference": []},
        "resume": {"must_have_skills": ["python"], "nice_to_have_skills": [],
                   "years_experience": 0},
        "scoring": {"w_fit": 0.5, "w_opportunity": 0.3, "w_urgency": 0.2,
                    "visa_hard_filter": False},
        "sources": {"enable_jobspy": False, "enable_ats": True, "enable_workday": False,
                    "watch_default_cadence_hours": 6},
    }
    r = client.put("/api/profile", json=new_profile)
    assert r.status_code == 200, r.text
    r = client.get("/api/profile")
    assert r.json()["name"] == "Test Profile"


def test_jobs_empty_returns_items():
    r = client.get("/api/jobs")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data


def test_profile_put_reranks_existing_jobs():
    client.get("/api/profile")

    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        active = db.query(UserProfile).filter(UserProfile.is_active == True).first()  # noqa: E712
        company = Company(name="Ranking Labs", normalized_name="ranking labs")
        db.add(company)
        db.flush()
        job = Job(
            source="greenhouse",
            external_job_id="profile-rerank-001",
            canonical_url="https://rankinglabs.example/jobs/platform-engineer",
            url_hash="profile-rerank-001",
            title="Platform Engineer",
            normalized_title="platform engineer",
            company_id=company.id,
            company_name_raw=company.name,
            location_raw="Remote, United States",
            country="US",
            remote_type="remote",
            employment_type="full_time",
            level_guess="entry",
            salary_min=120000,
            salary_max=150000,
            salary_currency="USD",
            description_text="python fastapi sql backend platform engineer",
            posted_at=now,
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
            dedupe_key="profile-rerank-001",
        )
        db.add(job)
        db.flush()
        db.add(JobRanking(
            job_id=job.id,
            profile_id=active.id,
            fit_score=0.01,
            opportunity_score=0.01,
            urgency_score=0.01,
            composite_score=0.01,
            reason_json={"weights": {"fit": 0.5, "opportunity": 0.3, "urgency": 0.2}},
            ranking_version="v1",
        ))
        db.commit()
        job_id = job.id

    profile = client.get("/api/profile").json()["profile"]
    profile["scoring"]["w_fit"] = 0
    profile["scoring"]["w_opportunity"] = 0
    profile["scoring"]["w_urgency"] = 1

    r = client.put("/api/profile", json=profile)
    assert r.status_code == 200, r.text
    assert r.json()["reranked_jobs"] >= 1

    with SessionLocal() as db:
        ranking = db.query(JobRanking).filter(JobRanking.job_id == job_id).first()
        assert ranking is not None
        assert ranking.composite_score > 0.5
        assert ranking.reason_json["weights"]["fit"] == 0.0
        assert ranking.reason_json["weights"]["urgency"] == 1.0
