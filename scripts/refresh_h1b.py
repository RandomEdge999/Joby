"""Refresh H-1B employer evidence from USCIS public data.

The USCIS H-1B Employer Data Hub publishes per-employer approval/denial
counts per fiscal year as CSV at settings.uscis_h1b_csv_url. This script
streams that CSV, aggregates by (employer, fiscal_year), normalizes the
employer name, and upserts company_h1b rows.

Columns expected (USCIS Employer Data Hub standard):
  Fiscal Year, Employer (Petitioner) Name, Tax ID, Industry (NAICS) Code,
  Petitioner City, Petitioner State, Petitioner Zip Code,
  Initial Approval, Initial Denial, Continuing Approval, Continuing Denial

Usage:  python scripts/refresh_h1b.py
        python scripts/refresh_h1b.py --file path/to/local.csv
        python scripts/refresh_h1b.py --year 2024
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from collections import defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.config import settings
from app.db import SessionLocal, Base, engine
from app.models import Company, CompanyH1B
from app.utils.normalize import normalize_company_name


def _norm_header(h: str) -> str:
    return h.strip().lower().replace("(", "").replace(")", "").replace("  ", " ")


def _find_col(headers: list[str], *needles: str) -> int | None:
    low = [_norm_header(h) for h in headers]
    for i, h in enumerate(low):
        if all(n in h for n in needles):
            return i
    return None


def _parse_int(v: str) -> int:
    if v is None:
        return 0
    v = v.strip().replace(",", "")
    if not v or v == "-":
        return 0
    try:
        return int(float(v))
    except ValueError:
        return 0


def _iter_rows(source: str | Path):
    """Yield dict rows from either a URL (streaming) or a local path."""
    if isinstance(source, Path) or not str(source).startswith(("http://", "https://")):
        with open(source, "r", encoding="utf-8-sig", newline="") as f:
            yield from csv.reader(f)
        return
    with httpx.stream("GET", str(source), timeout=120.0,
                      follow_redirects=True) as resp:
        resp.raise_for_status()
        buf = io.StringIO()
        for chunk in resp.iter_text():
            buf.write(chunk)
        buf.seek(0)
        yield from csv.reader(buf)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="local CSV (skips download)")
    ap.add_argument("--year", type=int, default=None,
                    help="filter to a single fiscal year")
    args = ap.parse_args()

    source: str | Path = args.file or settings.uscis_h1b_csv_url
    if not source:
        print("ERROR: uscis_h1b_csv_url not set and --file not given",
              file=sys.stderr)
        return 2
    print(f"Reading H-1B data from: {source}")

    rows_iter = _iter_rows(source)
    try:
        headers = next(rows_iter)
    except StopIteration:
        print("ERROR: empty CSV", file=sys.stderr)
        return 2

    col_year = _find_col(headers, "fiscal", "year")
    col_emp = _find_col(headers, "employer") or _find_col(headers, "petitioner", "name")
    col_ia = _find_col(headers, "initial", "approval")
    col_id_ = _find_col(headers, "initial", "denial")
    col_ca = _find_col(headers, "continuing", "approval")
    col_cd = _find_col(headers, "continuing", "denial")

    if col_emp is None or col_year is None:
        print(f"ERROR: cannot find required columns in headers: {headers}",
              file=sys.stderr)
        return 2

    # (employer_norm, fy) -> {raw_name, approvals, denials}
    agg: dict[tuple[str, int], dict] = defaultdict(
        lambda: {"raw": "", "approvals": 0, "denials": 0}
    )
    n_rows = 0
    for row in rows_iter:
        if not row or len(row) <= max(col_year, col_emp):
            continue
        try:
            fy = int(str(row[col_year]).strip())
        except (ValueError, IndexError):
            continue
        if args.year and fy != args.year:
            continue
        raw = (row[col_emp] or "").strip()
        if not raw:
            continue
        norm = normalize_company_name(raw)
        if not norm:
            continue
        approvals = (_parse_int(row[col_ia]) if col_ia is not None else 0) + \
                    (_parse_int(row[col_ca]) if col_ca is not None else 0)
        denials = (_parse_int(row[col_id_]) if col_id_ is not None else 0) + \
                  (_parse_int(row[col_cd]) if col_cd is not None else 0)
        bucket = agg[(norm, fy)]
        bucket["raw"] = bucket["raw"] or raw
        bucket["approvals"] += approvals
        bucket["denials"] += denials
        n_rows += 1

    print(f"Parsed {n_rows} rows into {len(agg)} (employer, year) buckets")

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    inserted = updated = 0
    try:
        for (norm, fy), data in agg.items():
            approvals = data["approvals"]
            denials = data["denials"]
            filings = approvals + denials
            if filings == 0:
                continue
            company = db.query(Company).filter(Company.normalized_name == norm).first()
            if not company:
                company = Company(name=data["raw"], normalized_name=norm)
                db.add(company)
                db.commit()
                db.refresh(company)
            existing = db.query(CompanyH1B).filter(
                CompanyH1B.company_id == company.id,
                CompanyH1B.fiscal_year == fy,
            ).first()
            evidence = min(1.0, approvals / 5000.0)
            if existing:
                existing.filings_count = filings
                existing.approvals_count = approvals
                existing.denials_count = denials
                existing.evidence_score = evidence
                existing.source_name = "uscis-employer-data-hub"
                updated += 1
            else:
                db.add(CompanyH1B(
                    company_id=company.id, fiscal_year=fy,
                    filings_count=filings, approvals_count=approvals,
                    denials_count=denials, evidence_score=evidence,
                    source_name="uscis-employer-data-hub",
                ))
                inserted += 1
        db.commit()
    finally:
        db.close()
    print(f"H-1B refresh done: inserted={inserted} updated={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
