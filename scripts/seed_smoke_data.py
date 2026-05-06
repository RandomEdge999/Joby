from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import os
import sys


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))


def _reset_sqlite_file(url: str) -> None:
    if not url.startswith("sqlite:///"):
        return
    path = Path(url.replace("sqlite:///", "", 1))
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    for suffix in ("", "-wal", "-shm"):
        target = Path(f"{path}{suffix}")
        if target.exists():
            target.unlink()


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "sqlite:///./data/joby_smoke.db")
    _reset_sqlite_file(database_url)

    from app.db import Base, engine, SessionLocal
    from app.models import Company, Contact, Job, JobRanking, Screening, UserProfile
    from app.profile.presets import get_preset

    Base.metadata.create_all(bind=engine)

    now = datetime.now(UTC).replace(tzinfo=None)
    profile = get_preset("us-new-grad").model_dump()

    with SessionLocal() as db:
        db.add(UserProfile(name="Smoke Profile", preset="us-new-grad", profile_json=profile, is_active=True))
        db.flush()

        company = Company(
            name="Northstar Labs",
            normalized_name="northstar labs",
            domain="northstarlabs.example",
            website_url="https://northstarlabs.example",
            careers_url="https://northstarlabs.example/careers",
            industry="software",
            headquarters="Remote",
            company_tier="strong",
            tier_source="smoke",
        )
        db.add(company)
        db.flush()

        primary_job = Job(
            source="greenhouse",
            external_job_id="smoke-ml-001",
            canonical_url="https://northstarlabs.example/jobs/platform-ml-engineer",
            url_hash="smoke-ml-001",
            title="Platform Machine Learning Engineer",
            normalized_title="platform machine learning engineer",
            company_id=company.id,
            company_name_raw=company.name,
            location_raw="Remote, United States",
            city=None,
            state=None,
            country="US",
            remote_type="remote",
            employment_type="full_time",
            level_guess="entry",
            salary_min=125000,
            salary_max=150000,
            salary_currency="USD",
            description_text=(
                "Build internal machine learning platform services, production APIs, and ranking tools. "
                "This deterministic record exists for the local smoke suite."
            ),
            posted_at=now - timedelta(days=2),
            first_seen_at=now - timedelta(days=2),
            last_seen_at=now - timedelta(hours=1),
            is_active=True,
            dedupe_key="smoke-platform-ml-engineer",
            source_metadata_json={"seed": "smoke"},
        )
        secondary_job = Job(
            source="lever",
            external_job_id="smoke-finops-002",
            canonical_url="https://northstarlabs.example/jobs/finance-operations-analyst",
            url_hash="smoke-finops-002",
            title="Finance Operations Analyst",
            normalized_title="finance operations analyst",
            company_id=company.id,
            company_name_raw=company.name,
            location_raw="Austin, Texas",
            city="Austin",
            state="Texas",
            country="US",
            remote_type="onsite",
            employment_type="full_time",
            level_guess="entry",
            salary_min=80000,
            salary_max=95000,
            salary_currency="USD",
            description_text="Own reporting workflows and finance operations for the business systems team.",
            posted_at=now - timedelta(days=5),
            first_seen_at=now - timedelta(days=5),
            last_seen_at=now - timedelta(days=1),
            is_active=True,
            dedupe_key="smoke-finance-operations-analyst",
            source_metadata_json={"seed": "smoke"},
        )
        db.add_all([primary_job, secondary_job])
        db.flush()

        active_profile = db.query(UserProfile).filter(UserProfile.is_active == True).first()  # noqa: E712
        profile_id = active_profile.id

        db.add_all([
            JobRanking(
                job_id=primary_job.id,
                profile_id=profile_id,
                fit_score=0.94,
                opportunity_score=0.88,
                urgency_score=0.71,
                composite_score=0.87,
                reason_json={"summary": "Matches backend, API, and ranking work."},
                ranking_version="smoke",
            ),
            JobRanking(
                job_id=secondary_job.id,
                profile_id=profile_id,
                fit_score=0.31,
                opportunity_score=0.45,
                urgency_score=0.52,
                composite_score=0.39,
                reason_json={"summary": "Lower fit for the active profile."},
                ranking_version="smoke",
            ),
            Screening(
                job_id=primary_job.id,
                profile_id=profile_id,
                prefilter_passed=True,
                prefilter_reasons_json={"signals": {"visa_tier": "not_applicable"}},
                llm_status="skipped",
                screening_json={"summary": "Local smoke fixture."},
            ),
            Screening(
                job_id=secondary_job.id,
                profile_id=profile_id,
                prefilter_passed=True,
                prefilter_reasons_json={"signals": {"visa_tier": "not_applicable"}},
                llm_status="skipped",
                screening_json={"summary": "Local smoke fixture."},
            ),
            Contact(
                job_id=primary_job.id,
                company_id=company.id,
                name="Jordan Lee",
                title="Engineering Recruiter",
                email="jordan.lee@northstarlabs.example",
                source="smoke",
                confidence_score=0.9,
                evidence_json={"seed": "smoke"},
            ),
        ])

        db.commit()

    print(f"Seeded smoke database at {database_url}")


if __name__ == "__main__":
    main()