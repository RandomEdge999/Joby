from __future__ import annotations

import re
from typing import Any

from ..models import Company, Job, Screening
from ..profile.schema import Profile


_CLEARANCE_RE = re.compile(r"\b(security clearance|secret clearance|top secret|ts/sci|ts sci)\b", re.I)
_CITIZEN_RE = re.compile(r"\b(us citizens only|u\.s\. citizens only|must be a us citizen|must be a u\.s\. citizen)\b", re.I)


def _signals(screening: Screening | None) -> dict[str, Any]:
    return ((screening.prefilter_reasons_json or {}).get("signals") or {}) if screening else {}


def _visa_summary(tier: str) -> tuple[str, str]:
    if tier == "likely":
        return "explicitly_positive", "Sponsorship signal is positive."
    if tier == "possible":
        return "possible", "Sponsorship signal is possible but not definitive."
    if tier == "unlikely":
        return "explicitly_negative", "Posting or evidence suggests sponsorship may be blocked."
    if tier == "not_applicable":
        return "not_applicable", "Your active profile does not require sponsorship."
    return "silent_unknown", "No clear sponsorship signal found."


def _location_status(job: Job, profile: Profile | None) -> str:
    if profile is None or not profile.targeting.target_locations:
        return "not_checked"
    remote_type = (job.remote_type or "unknown").lower()
    remote_pref = profile.targeting.remote_preference
    if remote_type == "remote" and remote_pref in ("remote", "hybrid_or_remote", "any"):
        return "compatible"
    location_blob = " ".join(filter(None, [job.location_raw, job.city, job.state, job.country])).lower()
    for target in profile.targeting.target_locations:
        name = (target.name or "").lower()
        if name and name in location_blob:
            return "compatible"
    return "review_required"


def summarize(job: Job, company: Company | None, screening: Screening | None,
              profile: Profile | None) -> dict[str, Any]:
    signals = _signals(screening)
    visa_tier = str(signals.get("visa_tier") or "unknown")
    visa_signal, visa_text = _visa_summary(visa_tier)
    evidence = list(signals.get("visa_evidence") or [])

    description = job.description_text or ""
    clearance_required = bool(_CLEARANCE_RE.search(description))
    citizenship_only = bool(_CITIZEN_RE.search(description))

    clearance_status = "not_mentioned"
    if clearance_required:
        has_clearance = bool(profile and profile.identity.security_clearance != "none")
        clearance_status = "compatible" if has_clearance else "review_required"
        evidence.append("clearance_language_detected")

    citizenship_status = "not_mentioned"
    if citizenship_only:
        is_citizen = bool(profile and profile.identity.citizenship_status == "us_citizen")
        citizenship_status = "compatible" if is_citizen else "likely_blocked"
        evidence.append("citizenship_requirement_detected")

    employment_status = "not_checked"
    if profile and profile.targeting.target_employment:
        employment_status = "compatible" if job.employment_type in profile.targeting.target_employment else "review_required"

    level_status = "not_checked"
    if profile and profile.targeting.target_levels and (job.level_guess or "unknown") != "unknown":
        level_status = "compatible" if job.level_guess in profile.targeting.target_levels else "review_required"

    location_status = _location_status(job, profile)

    blockers = visa_tier == "unlikely" or citizenship_status == "likely_blocked"
    review = any(value == "review_required" for value in (
        clearance_status, employment_status, level_status, location_status,
    ))

    if blockers:
        label = "likely_blocked"
        summary = "Review before applying; one or more eligibility signals may block this role."
    elif review:
        label = "review_required"
        summary = "Some eligibility signals need review before applying."
    elif visa_tier in ("likely", "not_applicable"):
        label = "compatible"
        summary = "No obvious eligibility blocker found."
    else:
        label = "uncertain"
        summary = "Eligibility is uncertain because key signals are silent or incomplete."

    return {
        "label": label,
        "summary": summary,
        "visa_tier": visa_tier,
        "sponsorship_signal": visa_signal,
        "sponsorship_summary": visa_text,
        "clearance_status": clearance_status,
        "citizenship_status": citizenship_status,
        "employment_status": employment_status,
        "level_status": level_status,
        "location_status": location_status,
        "company_tier": company.company_tier if company else None,
        "evidence": evidence or ["no_explicit_evidence"],
    }