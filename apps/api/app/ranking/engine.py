"""Ranking engine per IMPLEMENTATION_PLAN section 22."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Any, Tuple

from ..profile.schema import Profile


RANKING_VERSION = "v1"


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _fit(job: dict, profile: Profile, signals: Dict[str, Any]) -> Tuple[float, list]:
    reasons = []
    title_sim = float(signals.get("role_similarity", 0.0))

    # Skill overlap
    text = ((job.get("description_text") or "") + " " + (job.get("title") or "")).lower()
    must = [s.lower() for s in profile.resume.must_have_skills]
    nice = [s.lower() for s in profile.resume.nice_to_have_skills]
    must_hits = sum(1 for s in must if s and s in text)
    nice_hits = sum(1 for s in nice if s and s in text)
    must_ratio = must_hits / len(must) if must else 0.5
    nice_ratio = nice_hits / len(nice) if nice else 0.25

    # YOE compatibility
    req_yoe = signals.get("required_yoe")
    if req_yoe is None:
        yoe_score = 0.6
    else:
        gap = req_yoe - profile.resume.years_experience
        yoe_score = _clamp(1.0 - (max(0, gap) / 6.0))

    # Employment match
    emp_ok = 1.0 if (not profile.targeting.target_employment or
                     job.get("employment_type") in profile.targeting.target_employment) else 0.3
    # Level match
    lvl_ok = 1.0
    if profile.targeting.target_levels and (job.get("level_guess") or "unknown") != "unknown":
        lvl_ok = 1.0 if job["level_guess"] in profile.targeting.target_levels else 0.4

    score = (
        0.35 * title_sim +
        0.30 * must_ratio +
        0.10 * nice_ratio +
        0.10 * yoe_score +
        0.10 * emp_ok +
        0.05 * lvl_ok
    )
    reasons.append(f"title_sim={title_sim:.2f}")
    reasons.append(f"must_skills={must_hits}/{len(must)}")
    reasons.append(f"nice_skills={nice_hits}/{len(nice)}")
    reasons.append(f"yoe_score={yoe_score:.2f}")
    return _clamp(score), reasons


def _opportunity(job: dict, profile: Profile, visa_tier: str,
                 company_tier: str = "unknown") -> Tuple[float, list]:
    reasons = []
    # Visa
    visa_map = {"not_applicable": 0.8, "likely": 1.0, "possible": 0.7,
                "unknown": 0.5, "unlikely": 0.1}
    visa_score = visa_map.get(visa_tier, 0.5)
    reasons.append(f"visa={visa_tier}")

    # Company tier alignment
    tier_map = {"top": 1.0, "strong": 0.8, "standard": 0.5, "unknown": 0.5}
    tier_score = tier_map.get(company_tier, 0.5)
    if profile.targeting.company_tier_preference:
        tier_score = 1.0 if company_tier in profile.targeting.company_tier_preference else tier_score * 0.7
    reasons.append(f"tier={company_tier}")

    # Salary quality
    sal_score = 0.5
    if job.get("salary_min") and profile.targeting.salary_floor:
        delta = (job["salary_min"] - profile.targeting.salary_floor) / max(1.0, profile.targeting.salary_floor)
        sal_score = _clamp(0.5 + delta)
    reasons.append(f"salary_score={sal_score:.2f}")

    # Recruiter availability
    recr_score = 0.6 if job.get("recruiter_blob_json") else 0.4

    score = 0.5 * visa_score + 0.25 * tier_score + 0.15 * sal_score + 0.10 * recr_score
    return _clamp(score), reasons


def _urgency(job: dict) -> Tuple[float, list]:
    reasons = []
    posted = job.get("posted_at")
    score = 0.5
    if isinstance(posted, datetime):
        age_days = max(0.0, (datetime.utcnow() - posted).total_seconds() / 86400.0)
        score = _clamp(1.0 - (age_days / 30.0))
        reasons.append(f"age_days={age_days:.1f}")
    else:
        reasons.append("age_unknown")

    text = (job.get("description_text") or "").lower()
    if "apply now" in text or "closing soon" in text or "limited" in text:
        score = _clamp(score + 0.1)
        reasons.append("closing_language")
    return score, reasons


def rank(job: dict, profile: Profile, signals: Dict[str, Any],
         visa_tier: str, company_tier: str = "unknown") -> Dict[str, Any]:
    fit, fit_reasons = _fit(job, profile, signals)
    opp, opp_reasons = _opportunity(job, profile, visa_tier, company_tier)
    urg, urg_reasons = _urgency(job)

    w = profile.scoring.normalized()
    composite = w.w_fit * fit + w.w_opportunity * opp + w.w_urgency * urg

    if profile.scoring.visa_hard_filter and visa_tier == "unlikely":
        composite = 0.0

    reason_json = {
        "fit": {"score": fit, "reasons": fit_reasons},
        "opportunity": {"score": opp, "reasons": opp_reasons, "visa_tier": visa_tier,
                        "company_tier": company_tier},
        "urgency": {"score": urg, "reasons": urg_reasons},
        "weights": {"fit": w.w_fit, "opportunity": w.w_opportunity, "urgency": w.w_urgency},
        "version": RANKING_VERSION,
    }
    return {
        "fit_score": fit,
        "opportunity_score": opp,
        "urgency_score": urg,
        "composite_score": composite,
        "reason_json": reason_json,
        "ranking_version": RANKING_VERSION,
    }
