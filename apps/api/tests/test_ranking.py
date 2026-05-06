from datetime import datetime

from app.ranking.engine import rank
from app.profile.presets import get_preset


def _job(**kw):
    base = dict(
        title="Backend Engineer", description_text="python fastapi sql docker",
        location_raw="Remote, US", remote_type="remote", employment_type="full_time",
        level_guess="entry", salary_min=120000, salary_max=160000,
        posted_at=datetime.utcnow(),
    )
    base.update(kw)
    return base


def test_rank_produces_all_scores():
    p = get_preset("international-student-opt")
    r = rank(_job(), p, signals={"role_similarity": 0.8, "required_yoe": 2},
             visa_tier="likely", company_tier="top")
    assert 0.0 <= r["fit_score"] <= 1.0
    assert 0.0 <= r["opportunity_score"] <= 1.0
    assert 0.0 <= r["urgency_score"] <= 1.0
    assert 0.0 <= r["composite_score"] <= 1.0
    assert "reason_json" in r


def test_visa_hard_filter_zeroes_composite():
    p = get_preset("international-student-opt")
    p.scoring.visa_hard_filter = True
    r = rank(_job(), p, signals={"role_similarity": 0.9}, visa_tier="unlikely")
    assert r["composite_score"] == 0.0


def test_weights_change_ranking():
    p = get_preset("international-student-opt")
    signals = {"role_similarity": 0.9}

    p.scoring.w_fit = 0.9
    p.scoring.w_opportunity = 0.05
    p.scoring.w_urgency = 0.05
    high_fit = rank(_job(), p, signals, visa_tier="unknown")

    p.scoring.w_fit = 0.05
    p.scoring.w_opportunity = 0.9
    p.scoring.w_urgency = 0.05
    low_fit = rank(_job(), p, signals, visa_tier="unknown")

    # Changing weights must change composite
    assert abs(high_fit["composite_score"] - low_fit["composite_score"]) > 1e-6
