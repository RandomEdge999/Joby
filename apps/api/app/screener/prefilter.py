"""Profile-driven prefilter gate per IMPLEMENTATION_PLAN section 17."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Tuple, List, Dict, Any

from ..profile.schema import Profile
from ..utils.location_match import job_matches_location_terms, normalize_location_terms


def _role_similarity(title: str, roles: list[str]) -> float:
    if not roles or not title:
        return 0.0
    t = title.lower()
    best = 0.0
    for r in roles:
        r = r.lower().strip()
        if not r:
            continue
        if r in t:
            best = max(best, 1.0)
            continue
        rt = set(r.split())
        tt = set(t.split())
        if rt and tt:
            overlap = len(rt & tt) / max(1, len(rt))
            best = max(best, overlap)
    return best


def _location_match(job: dict, profile: Profile, location_terms: List[str] | None = None) -> bool:
    explicit_terms = normalize_location_terms(location_terms)
    if explicit_terms:
        return job_matches_location_terms(job, explicit_terms)
    if not profile.targeting.target_locations:
        return True
    remote_pref = profile.targeting.remote_preference
    job_remote = (job.get("remote_type") or "unknown").lower()
    remote_ok = any(getattr(target, "remote_ok", False) for target in profile.targeting.target_locations)
    if job_remote == "remote" and (remote_ok or remote_pref in ("remote", "hybrid_or_remote", "any")):
        return True
    if remote_pref == "hybrid" and job_remote in ("hybrid", "remote"):
        return True
    targets = [target.name for target in profile.targeting.target_locations if (target.name or "").strip()]
    return job_matches_location_terms(job, targets)


def evaluate(job: dict, profile: Profile, strict: bool = False,
             location_terms: List[str] | None = None) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Return (passed, reasons, signals). Reasons include pass/fail codes."""
    reasons: List[str] = []
    signals: Dict[str, Any] = {}
    passed = True
    hard_filter = False  # conservative — UI toggles could tighten later

    # Employment type
    emp = job.get("employment_type") or "unknown"
    if profile.targeting.target_employment and emp not in profile.targeting.target_employment \
            and emp != "unknown":
        reasons.append(f"employment_mismatch:{emp}")
        passed = False
    else:
        reasons.append(f"employment_ok:{emp}")

    # Level
    levels = [l.lower() for l in profile.targeting.target_levels]
    lvl = (job.get("level_guess") or "unknown").lower()
    if levels and lvl != "unknown" and lvl not in levels:
        reasons.append(f"level_mismatch:{lvl}")
        if hard_filter or strict:
            passed = False
    else:
        reasons.append(f"level_ok:{lvl}")

    # Role similarity
    sim = _role_similarity(job.get("title") or "", profile.targeting.target_roles)
    signals["role_similarity"] = sim
    if profile.targeting.target_roles and sim < 0.25:
        reasons.append(f"role_weak:{sim:.2f}")
        # Soft — do not fail unless strictly zero and we have targets
        if sim == 0.0 or strict:
            passed = False
    else:
        reasons.append(f"role_ok:{sim:.2f}")

    text = f"{job.get('title') or ''} {job.get('description_text') or ''}".lower()
    must_skills = [skill.lower().strip() for skill in profile.resume.must_have_skills if skill.strip()]
    if must_skills:
        hits = [skill for skill in must_skills if skill in text]
        missing = [skill for skill in must_skills if skill not in text]
        signals["must_skill_hits"] = len(hits)
        signals["must_skill_total"] = len(must_skills)
        reasons.append(f"must_skills:{len(hits)}/{len(must_skills)}")
        if strict and missing:
            for skill in missing[:5]:
                reasons.append(f"must_skill_missing:{skill}")
            passed = False

    # Location
    if _location_match(job, profile, location_terms=location_terms):
        reasons.append("location_ok")
    else:
        reasons.append("location_mismatch")
        passed = False

    # Salary floor
    floor = profile.targeting.salary_floor
    smin = job.get("salary_min")
    if floor and smin is not None and smin < floor:
        reasons.append(f"salary_below_floor:{smin}<{floor}")
        passed = False
    elif floor and smin is not None:
        reasons.append("salary_ok")

    # Recency
    posted = job.get("posted_at")
    if profile.targeting.posted_within_days and posted:
        if isinstance(posted, datetime):
            cutoff = datetime.utcnow() - timedelta(days=profile.targeting.posted_within_days)
            if posted < cutoff:
                reasons.append("stale")
                # Soft unless very stale (> 2x limit)
                if posted < datetime.utcnow() - timedelta(days=profile.targeting.posted_within_days * 2):
                    passed = False
            else:
                reasons.append("fresh")

    # Years of experience — deterministic: look for "X+ years" in description
    desc = (job.get("description_text") or "")[:4000].lower()
    import re
    m = re.search(r"(\d+)\s*\+?\s*(?:-\s*\d+\s*)?years", desc)
    if m:
        req_yoe = int(m.group(1))
        signals["required_yoe"] = req_yoe
        if req_yoe - profile.resume.years_experience > 3:
            reasons.append(f"yoe_high:{req_yoe}vs{profile.resume.years_experience}")
            # soft
        else:
            reasons.append("yoe_ok")

    # Clearance
    if "security clearance" in desc or "us citizen" in desc:
        signals["clearance_mentioned"] = True
        if profile.identity.security_clearance == "none":
            reasons.append("clearance_required_no_clearance")
            # soft — only hard fail if text explicitly requires clearance AND user has none
            if "requires" in desc and "clearance" in desc and profile.identity.security_clearance == "none":
                # Keep soft by default
                pass

    return passed, reasons, signals
