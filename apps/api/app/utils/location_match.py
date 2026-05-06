from __future__ import annotations

from collections.abc import Iterable


US_LOCATION_TERMS = {"united states", "usa", "us", "u.s.", "u.s.a."}
US_COUNTRY_TERMS = {"united states", "usa", "us"}
US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS",
    "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY",
    "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
}
_BAY_AREA_TOKENS = (
    "san francisco", "oakland", "san jose", "palo alto",
    "mountain view", "sunnyvale", "berkeley",
)


def normalize_location_terms(values: Iterable[str] | None) -> list[str]:
    if not values:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        cleaned.append(text)
        seen.add(key)
    return cleaned


def job_matches_location_terms(job: dict, location_terms: Iterable[str] | None) -> bool:
    terms = normalize_location_terms(location_terms)
    if not terms:
        return True

    location_raw = str(job.get("location_raw") or "").lower()
    city = str(job.get("city") or "").lower()
    state = str(job.get("state") or "").lower()
    country = str(job.get("country") or "").lower()
    state_code = str(job.get("state") or "").upper()
    remote_type = str(job.get("remote_type") or "unknown").lower()
    has_explicit_location = any([location_raw, city, state, country])

    for term in terms:
        normalized = term.lower().replace("_", " ")
        if normalized == "remote":
            if remote_type == "remote" or "remote" in location_raw:
                return True
            continue

        if normalized in US_LOCATION_TERMS:
            if (
                country in US_COUNTRY_TERMS
                or state_code in US_STATE_CODES
                or "united states" in location_raw
                or ", us" in location_raw
                or ", usa" in location_raw
            ):
                return True
            continue

        if "bay area" in normalized:
            if any(token in location_raw or token in city for token in _BAY_AREA_TOKENS):
                return True
            continue

        if normalized in location_raw or normalized in city or normalized in state or normalized in country:
            return True
        if len(normalized) == 2 and normalized.upper() in US_STATE_CODES and state_code == normalized.upper():
            return True

    return not has_explicit_location