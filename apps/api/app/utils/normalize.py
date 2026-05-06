"""Normalization helpers for scraped jobs."""
from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timezone
from typing import Optional


_TITLE_LEVEL_PATTERNS = [
    (re.compile(r"\b(intern|internship)\b", re.I), "intern"),
    (re.compile(r"\b(new ?grad|university grad|entry[- ]?level|associate)\b", re.I), "new_grad"),
    (re.compile(r"\b(jr|junior)\b", re.I), "entry"),
    (re.compile(r"\b(mid[- ]?level|intermediate|level\s*2|level\s*ii|\bii\b)\b", re.I), "mid"),
    (re.compile(r"\b(senior|sr\.|staff|lead|principal)\b", re.I), "senior"),
    (re.compile(r"\b(manager|director|head of)\b", re.I), "lead"),
]

_EMPLOYMENT_PATTERNS = [
    (re.compile(r"\b(intern|internship)\b", re.I), "internship"),
    (re.compile(r"\bco[- ]?op\b", re.I), "co_op"),
    (re.compile(r"\bcontract(or)?\b|\bcontract to hire\b", re.I), "contract"),
    (re.compile(r"\bfull[- ]?time\b|\bpermanent\b", re.I), "full_time"),
]


def _clean_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def normalize_title(title: str) -> str:
    t = _clean_text(title)
    t = re.sub(r"\s+", " ", t)
    return t.lower()


def guess_level(title: str, description_text: str = "") -> str:
    title_text = _clean_text(title)
    description = _clean_text(description_text)
    blob = f"{title_text} {description[:400]}"
    for pat, level in _TITLE_LEVEL_PATTERNS:
        if pat.search(blob):
            return level
    return "unknown"


def guess_employment_type(title: str, description_text: str = "",
                          hint: Optional[str] = None) -> str:
    if hint:
        h = _clean_text(hint).lower().replace("-", "_").replace(" ", "_")
        for allowed in ("full_time", "internship", "co_op", "contract"):
            if allowed in h:
                return allowed
    title_text = _clean_text(title)
    description = _clean_text(description_text)
    blob = f"{title_text} {description[:600]}"
    for pat, emp in _EMPLOYMENT_PATTERNS:
        if pat.search(blob):
            return emp
    return "full_time"  # default assumption


_REMOTE_PAT = re.compile(r"\bremote\b", re.I)
_HYBRID_PAT = re.compile(r"\bhybrid\b", re.I)
_ONSITE_PAT = re.compile(r"\bon[- ]?site\b|\bin[- ]office\b", re.I)


def guess_remote_type(location_raw: str = "", description_text: str = "") -> str:
    location = _clean_text(location_raw)
    description = _clean_text(description_text)
    blob = f"{location} {description[:400]}"
    if _REMOTE_PAT.search(blob) and not _ONSITE_PAT.search(blob):
        return "remote"
    if _HYBRID_PAT.search(blob):
        return "hybrid"
    if _ONSITE_PAT.search(blob):
        return "onsite"
    return "unknown"


_US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA",
    "ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK",
    "OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC",
}


def parse_location(location_raw: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Best-effort parse of 'City, ST' or 'City, Country' into (city, state, country)."""
    s = _clean_text(location_raw)
    if not s:
        return None, None, None
    # Strip leading prefixes like "Remote -", "Remote:"
    s = re.sub(r"^remote\s*[-:\u2013]\s*", "", s, flags=re.I)
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if not parts:
        return None, None, None
    if len(parts) == 1:
        return parts[0], None, None
    city = parts[0]
    second = parts[1]
    if second.upper() in _US_STATES:
        country = parts[2] if len(parts) >= 3 else "US"
        return city, second.upper(), country
    return city, None, second


_SALARY_PAT = re.compile(
    r"\$?\s*([0-9]{2,3}),?([0-9]{3})\s*(?:-|to|\u2013)\s*\$?\s*([0-9]{2,3}),?([0-9]{3})"
)


def parse_salary(text: str) -> tuple[Optional[float], Optional[float], Optional[str]]:
    text = _clean_text(text)
    if not text:
        return None, None, None
    m = _SALARY_PAT.search(text)
    if not m:
        return None, None, None
    lo = float(m.group(1) + m.group(2))
    hi = float(m.group(3) + m.group(4))
    return lo, hi, "USD"


def strip_html(html: str) -> str:
    if not html:
        return ""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(" ", strip=True)


def url_hash(url: str) -> str:
    return hashlib.sha256(_clean_text(url).encode("utf-8")).hexdigest()[:32]


def normalize_company_name(name: str) -> str:
    name = _clean_text(name)
    if not name:
        return ""
    n = name.lower()
    n = re.sub(r"[^a-z0-9]+", "-", n)
    n = re.sub(r"-+", "-", n).strip("-")
    return n


def dedupe_key(company_norm: str, title_norm: str, location_raw: str) -> str:
    basis = f"{company_norm}|{title_norm}|{(location_raw or '').lower().strip()}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


def parse_iso_datetime(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, (int, float)):
        try:
            return datetime.utcfromtimestamp(value / 1000 if value > 10_000_000_000 else value)
        except Exception:
            return None
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            return None
    return None
