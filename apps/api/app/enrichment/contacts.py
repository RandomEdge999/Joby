"""Contact discovery pipeline per IMPLEMENTATION_PLAN section 21.

Public, ToS-aware, deterministic-first. Descending confidence:
  1. ATS recruiter/poster block (Greenhouse metadata, Lever hiring manager)
  2. Company domain-based email pattern inference (first.last@domain)
  3. LLM fallback is intentionally omitted from v1 — it is easy to add later
     behind a flag; silent failure modes are worse than an honest gap.

Persists Contact rows with source, confidence_score, evidence_json.
"""
from __future__ import annotations

import re
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from ..models import Job, Company, Contact


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _extract_emails(text: str) -> List[str]:
    if not text:
        return []
    return list({m.group(0) for m in _EMAIL_RE.finditer(text)})


def _from_greenhouse(job: Job) -> List[Dict[str, Any]]:
    """Greenhouse job metadata occasionally carries recruiter info in metadata array."""
    out: List[Dict[str, Any]] = []
    blob = job.recruiter_blob_json or {}
    metadata = blob.get("metadata") if isinstance(blob, dict) else None
    if not isinstance(metadata, list):
        return out
    for m in metadata:
        if not isinstance(m, dict):
            continue
        name = m.get("name") or ""
        value = m.get("value")
        if isinstance(value, str) and _EMAIL_RE.match(value.strip()):
            out.append({
                "name": None, "title": name or "Recruiter",
                "email": value.strip().lower(),
                "source": "ats_greenhouse_metadata",
                "confidence": 0.85,
                "evidence": {"field": name, "raw": value},
            })
    return out


def _from_lever(job: Job) -> List[Dict[str, Any]]:
    """Lever sometimes exposes hiringManager in categories; rare in public API."""
    out: List[Dict[str, Any]] = []
    meta = job.source_metadata_json or {}
    hm = meta.get("hiring_manager") if isinstance(meta, dict) else None
    if isinstance(hm, dict) and hm.get("email"):
        out.append({
            "name": hm.get("name"), "title": hm.get("title") or "Hiring manager",
            "email": hm["email"].lower(),
            "source": "ats_lever_hiring_manager", "confidence": 0.85,
            "evidence": hm,
        })
    return out


def _from_description(job: Job) -> List[Dict[str, Any]]:
    emails = _extract_emails(job.description_text or "")
    return [{
        "name": None, "title": "Listed in JD",
        "email": e.lower(),
        "source": "jd_email_scan", "confidence": 0.6,
        "evidence": {"match": e},
    } for e in emails]


def _infer_pattern(company: Company) -> Optional[Dict[str, Any]]:
    """If we have a company domain, we can advertise a safe recruiting alias.
    We do NOT fabricate individual emails — only well-known role aliases.
    """
    if not company or not company.domain:
        return None
    return {
        "name": None, "title": "Recruiting (pattern)",
        "email": f"recruiting@{company.domain.lower()}",
        "source": "pattern_inference", "confidence": 0.25,
        "evidence": {"pattern": "recruiting@<domain>"},
    }


def _upsert(db: Session, job: Job, row: Dict[str, Any]) -> Optional[Contact]:
    if not row.get("email"):
        return None
    existing = db.query(Contact).filter(
        Contact.email == row["email"],
        Contact.company_id == job.company_id,
    ).first()
    if existing:
        # Keep whichever has higher confidence
        if (existing.confidence_score or 0.0) < row["confidence"]:
            existing.title = row.get("title") or existing.title
            existing.source = row.get("source") or existing.source
            existing.confidence_score = row["confidence"]
            existing.evidence_json = row.get("evidence")
        return existing
    c = Contact(
        job_id=job.id, company_id=job.company_id,
        name=row.get("name"), title=row.get("title"),
        email=row["email"], source=row.get("source"),
        confidence_score=row["confidence"], evidence_json=row.get("evidence"),
    )
    db.add(c)
    return c


def discover_for_job(db: Session, job: Job) -> List[Contact]:
    """Run the contact discovery pipeline for a single job. Returns persisted contacts."""
    rows: List[Dict[str, Any]] = []
    if job.source == "greenhouse":
        rows.extend(_from_greenhouse(job))
    if job.source == "lever":
        rows.extend(_from_lever(job))
    rows.extend(_from_description(job))
    pattern = _infer_pattern(job.company) if job.company else None
    if pattern:
        rows.append(pattern)

    created: List[Contact] = []
    for r in rows:
        c = _upsert(db, job, r)
        if c:
            created.append(c)
    db.commit()
    return created


def discover_for_all(db: Session, limit: Optional[int] = None) -> int:
    """Run discovery across every job. Returns number of jobs processed."""
    q = db.query(Job)
    if limit:
        q = q.limit(limit)
    count = 0
    for job in q.all():
        discover_for_job(db, job)
        count += 1
    return count
