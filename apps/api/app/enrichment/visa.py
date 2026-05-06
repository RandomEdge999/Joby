"""Visa tier resolver per IMPLEMENTATION_PLAN section 18."""
from __future__ import annotations

import re
from typing import Tuple, List, Optional

from sqlalchemy.orm import Session

from ..models import CompanyH1B
from ..profile.schema import Profile


_NEGATIVE = [
    re.compile(r"\bno\s+visa\s+sponsor(ship)?\b", re.I),
    re.compile(r"\bno\s+sponsor(ship)?\b", re.I),
    re.compile(r"\bnot\s+(?:able\s+to|provide|offer)\s+sponsor", re.I),
    re.compile(r"\bnot\s+eligible\s+for\s+(?:visa\s+)?sponsor(ship)?\b", re.I),
    re.compile(r"\b(?:visa\s+)?sponsor(ship)?\s+(?:is\s+)?not\s+(?:available|offered|provided)\b", re.I),
    re.compile(r"\b(?:do|does|will)\s+not\s+(?:provide|offer|sponsor)\b", re.I),
    re.compile(r"\bcan(?:not|'t)\s+sponsor\b", re.I),
    re.compile(r"\bunable\s+to\s+sponsor", re.I),
    re.compile(r"\bwithout\s+sponsor(ship)?\b", re.I),
    re.compile(r"\bmust\s+be\s+(?:authorized|eligible)\s+to\s+work\b", re.I),
    re.compile(r"\bus\s+citizens\s+only\b", re.I),
    re.compile(r"\bmust\s+be\s+a\s+us\s+citizen\b", re.I),
]
_POSITIVE = [
    re.compile(r"\bvisa\s+sponsorship\b", re.I),
    re.compile(r"\bh[-\s]?1b\s+sponsorship\b", re.I),
    re.compile(r"\bwill\s+sponsor\b", re.I),
    re.compile(r"\bsponsor\s+work\s+authorization\b", re.I),
    re.compile(r"\bopt[\s-]?friendly\b", re.I),
    re.compile(r"\bcpt[\s-]?available\b", re.I),
    re.compile(r"\baccepts?\s+(?:opt|cpt)\b", re.I),
    re.compile(r"\b(?:opt|cpt)\s+(?:work\s+authorization|support|available)\b", re.I),
]


def _matches(patterns: list[re.Pattern], text: str) -> list[str]:
    found: list[str] = []
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            found.append(match.group(0))
    return found


def resolve(job: dict, profile: Profile, db: Optional[Session] = None,
            company_id: Optional[int] = None) -> Tuple[str, List[str]]:
    """Return (tier, evidence). Tiers: not_applicable, likely, possible, unlikely, unknown."""
    if not profile.identity.needs_sponsorship_now and not profile.identity.needs_sponsorship_future:
        return "not_applicable", ["profile_does_not_need_sponsorship"]

    evidence: List[str] = []
    text = ((job.get("description_text") or "") + " " + (job.get("title") or ""))[:6000]

    negative_matches = _matches(_NEGATIVE, text)
    positive_matches = _matches(_POSITIVE, text)

    h1b_total = 0
    if db is not None and company_id is not None:
        rows = db.query(CompanyH1B).filter(CompanyH1B.company_id == company_id).all()
        h1b_total = sum((r.approvals_count or 0) + (r.filings_count or 0) for r in rows)
        if h1b_total:
            evidence.append(f"h1b_history:{h1b_total}")

    if negative_matches:
        evidence.extend(f"phrase:{value}" for value in negative_matches[:3])
        evidence.append("jd_excludes_sponsorship")
        return "unlikely", evidence
    if positive_matches:
        evidence.extend(f"phrase:{value}" for value in positive_matches[:3])
        evidence.append("jd_mentions_sponsorship")
        return "likely", evidence
    if h1b_total >= 50:
        return "likely", evidence
    if h1b_total >= 5:
        return "possible", evidence
    return "unknown", evidence or ["no_signal"]
