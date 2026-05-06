from app.profile.presets import PRESETS, get_preset, list_presets
from app.profile.schema import Profile


def test_six_presets_present():
    expected = {
        "international-student-opt",
        "international-student-pre-opt",
        "us-new-grad",
        "us-clearance",
        "career-switcher",
        "custom",
    }
    assert set(PRESETS.keys()) == expected


def test_us_new_grad_needs_no_sponsorship():
    p = get_preset("us-new-grad")
    assert p.identity.needs_sponsorship_now is False
    assert p.identity.needs_sponsorship_future is False


def test_intl_opt_needs_future_sponsorship():
    p = get_preset("international-student-opt")
    assert p.identity.needs_sponsorship_future is True


def test_scoring_weights_normalize():
    p = Profile()
    n = p.scoring.normalized()
    assert abs(n.w_fit + n.w_opportunity + n.w_urgency - 1.0) < 1e-6


def test_list_presets_returns_six():
    assert len(list_presets()) == 6
