from datetime import datetime

from app.screener.prefilter import evaluate
from app.profile.presets import get_preset


def _job(**kw):
    base = dict(
        title="Backend Engineer", description_text="python, sql, postgres, docker",
        location_raw="San Francisco, CA", city="San Francisco", state="CA",
        remote_type="onsite", employment_type="full_time", level_guess="entry",
        salary_min=130000, posted_at=datetime.utcnow(),
    )
    base.update(kw)
    return base


def test_pass_for_matching_job():
    p = get_preset("international-student-opt")
    passed, reasons, _ = evaluate(_job(), p)
    assert passed, reasons


def test_fail_for_below_salary_floor():
    p = get_preset("international-student-opt")
    passed, reasons, _ = evaluate(_job(salary_min=50000), p)
    assert not passed
    assert any("salary" in r for r in reasons)


def test_fail_for_location_mismatch():
    p = get_preset("international-student-opt")
    passed, reasons, _ = evaluate(_job(location_raw="Tokyo, Japan", city="Tokyo", state=None,
                                        remote_type="onsite"), p)
    assert not passed


def test_remote_matches_hybrid_or_remote_pref():
    p = get_preset("international-student-opt")
    passed, _, _ = evaluate(_job(location_raw="Remote, US", city=None, state=None,
                                  remote_type="remote"), p)
    assert passed


def test_strict_prefilter_requires_must_have_skills():
    p = get_preset("international-student-opt")
    job = _job(description_text="python, docker, backend services")

    loose_passed, loose_reasons, _ = evaluate(job, p)
    strict_passed, strict_reasons, signals = evaluate(job, p, strict=True)

    assert loose_passed, loose_reasons
    assert not strict_passed
    assert signals["must_skill_hits"] == 1
    assert signals["must_skill_total"] == 2
    assert "must_skill_missing:sql" in strict_reasons


def test_explicit_search_location_terms_override_saved_profile_locations():
    p = get_preset("international-student-opt")

    passed, reasons, _ = evaluate(
        _job(location_raw="New York, NY", city="New York", state="NY", remote_type="onsite"),
        p,
        location_terms=["United States"],
    )

    assert passed, reasons


def test_explicit_remote_search_location_accepts_remote_jobs():
    p = get_preset("international-student-opt")

    passed, reasons, _ = evaluate(
        _job(location_raw="Remote, Germany", city=None, state=None, country="Germany", remote_type="remote"),
        p,
        location_terms=["Remote"],
    )

    assert passed, reasons
