from datetime import datetime

from app.db import SessionLocal
from app.models import Company, CompanyH1B
from app.enrichment import tier as tier_mod


def test_curated_top():
    db = SessionLocal()
    try:
        c = Company(name="OpenAI", normalized_name="openai")
        db.add(c); db.commit(); db.refresh(c)
        t, src = tier_mod.classify(c, db=db)
        assert t == "top"
        assert src == "curated"
    finally:
        db.close()


def test_curated_strong():
    db = SessionLocal()
    try:
        c = Company(name="Vercel", normalized_name="vercel")
        db.add(c); db.commit(); db.refresh(c)
        t, src = tier_mod.classify(c, db=db)
        assert t == "strong"
        assert src == "curated"
    finally:
        db.close()


def test_h1b_fallback_top():
    db = SessionLocal()
    try:
        c = Company(name="BigConsultCo", normalized_name="bigconsultco-h1b")
        db.add(c); db.commit(); db.refresh(c)
        db.add(CompanyH1B(company_id=c.id, fiscal_year=2024,
                          approvals_count=250, filings_count=0,
                          loaded_at=datetime.utcnow()))
        db.commit()
        t, src = tier_mod.classify(c, db=db)
        assert t == "top"
        assert src == "h1b_history"
    finally:
        db.close()


def test_unknown_when_no_signals():
    db = SessionLocal()
    try:
        c = Company(name="Obscure LLC", normalized_name="obscure-llc-tier")
        db.add(c); db.commit(); db.refresh(c)
        t, src = tier_mod.classify(c, db=db)
        assert t == "unknown"
        assert src == "default"
    finally:
        db.close()
