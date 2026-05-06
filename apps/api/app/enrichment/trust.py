from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from ..models import Company, Job


_KNOWN_SOURCE_PREFIXES = (
    "greenhouse", "lever", "ashby", "smartrecruiters", "workable",
    "recruitee", "workday", "jobspy",
)
_KNOWN_ATS_VENDORS = {
    "greenhouse.io": "greenhouse",
    "lever.co": "lever",
    "ashbyhq.com": "ashby",
    "smartrecruiters.com": "smartrecruiters",
    "workable.com": "workable",
    "recruitee.com": "recruitee",
    "myworkdayjobs.com": "workday",
    "workdayjobs.com": "workday",
}
_PERSONAL_EMAIL_RE = re.compile(r"\b[\w.+-]+@(gmail|yahoo|outlook|hotmail|protonmail)\.com\b", re.I)
_SENSITIVE_REQUESTS = [
    re.compile(r"\b(social security number|ssn|bank account|routing number)\b", re.I),
    re.compile(r"\b(gift card|crypto|bitcoin|telegram|whatsapp only)\b", re.I),
    re.compile(r"\b(pay.*application fee|application fee.*pay)\b", re.I),
]


def _host(url: str | None) -> str:
    if not url:
        return ""
    try:
        return (urlparse(url).netloc or "").lower().removeprefix("www.")
    except Exception:
        return ""


def _known_ats_vendor(host: str) -> str | None:
    for domain, vendor in _KNOWN_ATS_VENDORS.items():
        if host == domain or host.endswith(f".{domain}"):
            return vendor
    return None


def assess(job: Job, company: Company | None) -> dict[str, Any]:
    evidence: list[str] = []
    warnings: list[str] = []
    source = (job.source or "").lower()
    source_known = source.startswith(_KNOWN_SOURCE_PREFIXES)
    host = _host(job.canonical_url)
    ats_vendor = _known_ats_vendor(host) if host else None
    company_domain = ((company.domain if company else None) or "").lower().removeprefix("www.")
    text = " ".join(filter(None, [job.title, job.description_text]))[:8000]

    if source_known:
        evidence.append(f"known_source:{job.source}")
    else:
        warnings.append("unknown_source")

    if host:
        evidence.append(f"posting_host:{host}")
        if ats_vendor:
            evidence.append(f"known_ats_vendor:{ats_vendor}")
    else:
        warnings.append("missing_original_url")

    if company_domain and host and company_domain not in host and not source.startswith("jobspy") and not ats_vendor:
        warnings.append("company_domain_mismatch")

    if _PERSONAL_EMAIL_RE.search(text):
        warnings.append("personal_email_in_posting")

    for pattern in _SENSITIVE_REQUESTS:
        match = pattern.search(text)
        if match:
            warnings.append(f"sensitive_request:{match.group(0).lower()}")

    if len((job.description_text or "").strip()) < 120 and (not source_known or not host):
        warnings.append("very_short_description")

    if job.salary_min and job.salary_min > 400000:
        warnings.append("unusually_high_salary")

    if any(item.startswith("sensitive_request:") for item in warnings) or len(warnings) >= 3:
        label = "suspicious_signals"
        summary = "Review carefully before sharing personal information."
    elif warnings:
        label = "review_recommended"
        summary = "Some source or posting details need review."
    elif source_known and (host or ats_vendor):
        label = "verified_source"
        summary = "Known source and posting URL are present."
    elif source_known:
        label = "low_risk"
        summary = "Known source with no suspicious text signals."
    else:
        label = "unknown_source"
        summary = "Source could not be verified from available data."

    score = max(0.0, min(1.0, 1.0 - 0.22 * len(warnings)))
    return {
        "label": label,
        "score": round(score, 2),
        "summary": summary,
        "evidence": evidence or ["no_positive_source_evidence"],
        "warnings": warnings,
    }