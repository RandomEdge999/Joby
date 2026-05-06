from datetime import datetime

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Company, CompanyH1B, Job, Screening, UserProfile
from app.profile.presets import get_preset


client = TestClient(app)


def test_job_detail_exposes_eligibility_explanation():
    db = SessionLocal()
    try:
        db.query(UserProfile).update({UserProfile.is_active: False})
        profile = get_preset("international-student-opt")
        row = UserProfile(
            name="Eligibility Profile",
            profile_json=profile.model_dump(),
            is_active=True,
        )
        company = Company(name="Eligibility Co", normalized_name="eligibility-co")
        db.add_all([row, company])
        db.commit()
        db.refresh(row)
        db.refresh(company)
        db.add(CompanyH1B(company_id=company.id, fiscal_year=2024,
                          filings_count=40, approvals_count=20))
        job = Job(
            source="greenhouse",
            external_job_id="eligibility-detail",
            canonical_url="https://boards.greenhouse.io/eligibility/jobs/1",
            title="Software Engineer",
            company_id=company.id,
            company_name_raw=company.name,
            location_raw="Remote, US",
            remote_type="remote",
            employment_type="full_time",
            level_guess="entry",
            description_text="We provide H-1B sponsorship for qualified candidates.",
            posted_at=datetime.utcnow(),
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        db.add(Screening(
            job_id=job.id,
            profile_id=row.id,
            prefilter_passed=True,
            prefilter_reasons_json={"signals": {
                "visa_tier": "likely",
                "visa_evidence": ["h1b_history:60", "phrase:H-1B sponsorship"],
            }},
        ))
        db.commit()
        job_id = job.id
    finally:
        db.close()

    r = client.get(f"/api/jobs/{job_id}")
    assert r.status_code == 200, r.text
    eligibility = r.json()["eligibility"]
    assert eligibility["label"] == "compatible"
    assert eligibility["sponsorship_signal"] == "explicitly_positive"
    assert "phrase:H-1B sponsorship" in eligibility["evidence"]


def test_job_detail_marks_citizenship_and_sponsorship_blockers():
    db = SessionLocal()
    try:
        db.query(UserProfile).update({UserProfile.is_active: False})
        profile = get_preset("international-student-opt")
        row = UserProfile(name="Blocked Profile", profile_json=profile.model_dump(), is_active=True)
        company = Company(name="Blocked Co", normalized_name="blocked-co")
        db.add_all([row, company])
        db.commit()
        db.refresh(row)
        db.refresh(company)
        job = Job(
            source="lever",
            external_job_id="eligibility-blocked",
            canonical_url="https://jobs.lever.co/blocked/1",
            title="Backend Engineer",
            company_id=company.id,
            company_name_raw=company.name,
            location_raw="Washington, DC",
            remote_type="onsite",
            employment_type="full_time",
            level_guess="entry",
            description_text="US citizens only. We are unable to sponsor visas for this role.",
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        db.add(Screening(
            job_id=job.id,
            profile_id=row.id,
            prefilter_passed=True,
            prefilter_reasons_json={"signals": {
                "visa_tier": "unlikely",
                "visa_evidence": ["phrase:unable to sponsor", "jd_excludes_sponsorship"],
            }},
        ))
        db.commit()
        job_id = job.id
    finally:
        db.close()

    r = client.get(f"/api/jobs/{job_id}")
    assert r.status_code == 200, r.text
    eligibility = r.json()["eligibility"]
    assert eligibility["label"] == "likely_blocked"
    assert eligibility["sponsorship_signal"] == "explicitly_negative"
    assert eligibility["citizenship_status"] == "likely_blocked"