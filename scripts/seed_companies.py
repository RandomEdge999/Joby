"""Seed companies table from config/sources.yaml.

Usage (from apps/api): python -m scripts.seed_companies  (run from repo root)
Or: python scripts/seed_companies.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root: make apps/api importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.db import SessionLocal, Base, engine
from app.models import Company
from app.services.sources import load_sources
from app.utils.normalize import normalize_company_name


def main():
    Base.metadata.create_all(bind=engine)
    data = load_sources()
    db = SessionLocal()
    created = 0
    try:
        for s in data.get("ats_sources", []):
            name = s.get("company")
            if not name:
                continue
            norm = normalize_company_name(name)
            existing = db.query(Company).filter(Company.normalized_name == norm).first()
            if existing:
                # Update careers_url/domain if empty
                if not existing.careers_url and s.get("url"):
                    existing.careers_url = s["url"]
                continue
            db.add(Company(
                name=name, normalized_name=norm,
                careers_url=s.get("url"),
                metadata_json={"ats_type": s.get("type"), "slug": s.get("slug")},
            ))
            created += 1
        db.commit()
    finally:
        db.close()
    print(f"Seeded {created} new companies")


if __name__ == "__main__":
    main()
