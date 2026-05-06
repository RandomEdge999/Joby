from datetime import datetime

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Company, Job
from app.enrichment.trust import assess


client = TestClient(app)


def test_job_detail_exposes_trust_for_known_source():
    db = SessionLocal()
    try:
        company = Company(name="Trust Co", normalized_name="trust-co", domain="trust.co")
        db.add(company)
        db.commit()
        db.refresh(company)
        job = Job(
            source="greenhouse",
            external_job_id="trust-known-source",
            canonical_url="https://trust.co/careers/jobs/1",
            title="Product Engineer",
            company_id=company.id,
            company_name_raw=company.name,
            location_raw="Remote, US",
            description_text="Build thoughtful products with a small engineering team.",
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    r = client.get(f"/api/jobs/{job_id}")
    assert r.status_code == 200, r.text
    trust = r.json()["trust"]
    assert trust["label"] == "verified_source"
    assert "known_source:greenhouse" in trust["evidence"]


def test_jobs_list_exposes_suspicious_trust_signals():
    db = SessionLocal()
    try:
        company = Company(name="Review Co", normalized_name="review-co", domain="review.co")
        db.add(company)
        db.commit()
        db.refresh(company)
        job = Job(
            source="unknown-board",
            external_job_id="trust-review-source",
            title="Review Safety Engineer",
            company_id=company.id,
            company_name_raw=company.name,
            location_raw="Remote",
            salary_min=650000,
            description_text="Email hiring@gmail.com on Telegram. Do not use the website. Provide SSN after interview.",
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
    finally:
        db.close()

    r = client.get("/api/jobs", params={"q": "Review Safety Engineer"})
    assert r.status_code == 200, r.text
    trust = r.json()["items"][0]["trust"]
    assert trust["label"] == "suspicious_signals"
    assert "personal_email_in_posting" in trust["warnings"]
    assert any(item.startswith("sensitive_request:") for item in trust["warnings"])


def test_trust_recognizes_known_ats_vendor_urls():
    company = Company(name="Acme", normalized_name="acme", domain="acme.com")
    job = Job(
        source="greenhouse",
        external_job_id="trust-known-ats-vendor",
        canonical_url="https://boards.greenhouse.io/acme/jobs/123",
        title="Software Engineer",
        description_text="Build reliable systems on a real engineering team.",
    )

    trust = assess(job, company)

    assert trust["label"] == "verified_source"
    assert "known_ats_vendor:greenhouse" in trust["evidence"]
    assert "company_domain_mismatch" not in trust["warnings"]