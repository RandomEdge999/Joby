from datetime import datetime, timedelta

from app.enrichment.visa import resolve
from app.profile.presets import get_preset


def _job(desc: str = "", title: str = "Software Engineer") -> dict:
    return {"title": title, "description_text": desc, "posted_at": datetime.utcnow()}


def test_skip_when_no_sponsorship_needed():
    p = get_preset("us-new-grad")
    tier, _ = resolve(_job("We offer visa sponsorship"), p)
    assert tier == "not_applicable"


def test_unlikely_for_us_citizens_only():
    p = get_preset("international-student-opt")
    tier, ev = resolve(_job("This role requires US citizenship. US citizens only."), p)
    assert tier == "unlikely"


def test_likely_for_explicit_sponsorship_text():
    p = get_preset("international-student-opt")
    tier, _ = resolve(_job("We provide H-1B sponsorship for qualified candidates."), p)
    assert tier == "likely"


def test_likely_for_opt_and_cpt_friendly_language():
    p = get_preset("international-student-opt")

    tier, evidence = resolve(_job(
        "We are an OPT-friendly employer and accept CPT for qualified internship candidates.",
        title="Data Analyst Intern",
    ), p)

    assert tier == "likely"
    assert any("opt" in item.lower() or "cpt" in item.lower() for item in evidence)


def test_unlikely_when_posting_says_not_eligible_for_visa_sponsorship():
    p = get_preset("international-student-opt")

    tier, evidence = resolve(_job("This role is not eligible for visa sponsorship."), p)

    assert tier == "unlikely"
    assert "jd_excludes_sponsorship" in evidence


def test_unknown_when_no_signal():
    p = get_preset("international-student-opt")
    tier, _ = resolve(_job("Come join a great team."), p)
    assert tier == "unknown"
