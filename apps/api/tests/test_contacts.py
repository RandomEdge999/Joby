from datetime import datetime

from app.db import SessionLocal
from app.models import Company, Job, Contact
from app.enrichment import contacts as contacts_mod


def _make_job(db, **overrides):
    c = Company(name="Acme", normalized_name=f"acme-contacts-{overrides.get('tag','x')}",
                domain="acme.example")
    db.add(c); db.commit(); db.refresh(c)
    job = Job(
        source=overrides.get("source", "greenhouse"),
        external_job_id=overrides.get("external_job_id", f"j-{overrides.get('tag','x')}"),
        title="SWE", company_id=c.id, company_name_raw="Acme",
        last_seen_at=datetime.utcnow(), first_seen_at=datetime.utcnow(),
        description_text=overrides.get("description_text"),
        recruiter_blob_json=overrides.get("recruiter_blob_json"),
        source_metadata_json=overrides.get("source_metadata_json"),
    )
    db.add(job); db.commit(); db.refresh(job)
    return c, job


def test_greenhouse_metadata_email():
    db = SessionLocal()
    try:
        _, job = _make_job(db, tag="gh",
            recruiter_blob_json={"metadata": [
                {"name": "Recruiter email", "value": "jane@acme.example"}
            ]})
        created = contacts_mod.discover_for_job(db, job)
        emails = {c.email for c in created}
        assert "jane@acme.example" in emails
        gh = db.query(Contact).filter(Contact.email == "jane@acme.example").first()
        assert gh.source == "ats_greenhouse_metadata"
        assert gh.confidence_score >= 0.8
    finally:
        db.close()


def test_jd_email_scan():
    db = SessionLocal()
    try:
        _, job = _make_job(db, tag="jd",
            description_text="Apply or reach out to hiring@acme.example for questions.")
        created = contacts_mod.discover_for_job(db, job)
        emails = {c.email for c in created}
        assert "hiring@acme.example" in emails
    finally:
        db.close()


def test_pattern_inference_when_domain_known():
    db = SessionLocal()
    try:
        _, job = _make_job(db, tag="pattern")
        contacts_mod.discover_for_job(db, job)
        pat = db.query(Contact).filter(
            Contact.email == "recruiting@acme.example",
            Contact.source == "pattern_inference",
        ).first()
        assert pat is not None
        assert pat.confidence_score == 0.25
    finally:
        db.close()
