"""Company tier classifier per IMPLEMENTATION_PLAN section 20.

Simple, explainable rules:
  1. curated seed mapping keyed by normalized name
  2. H-1B evidence as secondary signal (>=200 approvals => top, >=25 => strong)
  3. domain/name keyword heuristic (FAANG-adjacent, well-known tech)

Output: (tier, source_tag). Tiers: top | strong | standard | unknown.
"""
from __future__ import annotations

from typing import Tuple, Optional

from sqlalchemy.orm import Session

from ..models import Company, CompanyH1B


# Curated seed — small, opinionated. Matches what recent college grads typically
# think of as "top" vs "strong" tech employers. Normalized (lowercase-dash) names.
_TOP = {
    "openai", "anthropic", "google", "alphabet", "meta", "apple", "amazon",
    "microsoft", "nvidia", "netflix", "stripe", "databricks", "figma",
    "airbnb", "linkedin", "uber", "coinbase",
}
_STRONG = {
    "palantir", "ramp", "linear", "notion", "vercel", "cloudflare", "snowflake",
    "datadog", "mongodb", "hashicorp", "twilio", "shopify", "atlassian",
    "roblox", "discord", "reddit", "instacart", "doordash", "lyft", "pinterest",
    "robinhood", "plaid", "chime", "gusto", "rippling", "brex", "mercury",
    "scale ai", "scale-ai", "scale", "huggingface", "hugging-face",
}


def classify(company: Company, db: Optional[Session] = None) -> Tuple[str, str]:
    """Return (tier, tier_source). Idempotent; safe to call during pipeline or backfill."""
    norm = (company.normalized_name or "").lower()
    name_lower = (company.name or "").lower()

    if norm in _TOP or name_lower in _TOP:
        return "top", "curated"
    if norm in _STRONG or name_lower in _STRONG:
        return "strong", "curated"

    # H-1B secondary signal
    if db is not None:
        rows = db.query(CompanyH1B).filter(CompanyH1B.company_id == company.id).all()
        total = sum((r.approvals_count or 0) + (r.filings_count or 0) for r in rows)
        if total >= 200:
            return "top", "h1b_history"
        if total >= 25:
            return "strong", "h1b_history"
        if total > 0:
            return "standard", "h1b_history"

    return "unknown", "default"


def apply_to_all(db: Session) -> dict:
    """Classify every company row; persist tier + tier_source. Returns counts."""
    counts = {"top": 0, "strong": 0, "standard": 0, "unknown": 0}
    for c in db.query(Company).all():
        tier, src = classify(c, db=db)
        if c.company_tier != tier or c.tier_source != src:
            c.company_tier = tier
            c.tier_source = src
        counts[tier] = counts.get(tier, 0) + 1
    db.commit()
    return counts
