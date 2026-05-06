from math import nan

from app.utils.normalize import (
    normalize_title, guess_level, guess_employment_type, guess_remote_type,
    parse_location, parse_salary, normalize_company_name, dedupe_key, url_hash,
)


def test_normalize_title_basic():
    assert normalize_title("  Senior   Software Engineer  ") == "senior software engineer"


def test_guess_level_intern():
    assert guess_level("Software Engineer Intern, Summer 2025") == "intern"


def test_guess_level_senior():
    assert guess_level("Senior Backend Engineer") == "senior"


def test_guess_level_mid_level():
    assert guess_level("Mid-level Data Analyst") == "mid"


def test_employment_type_intern_from_title():
    assert guess_employment_type("Software Engineering Intern") == "internship"


def test_employment_type_full_time_default():
    assert guess_employment_type("Backend Engineer") == "full_time"


def test_remote_type_detection():
    assert guess_remote_type("Remote, US") == "remote"
    assert guess_remote_type("Hybrid - New York") == "hybrid"
    assert guess_remote_type("San Francisco, CA") == "unknown"


def test_parse_location_us():
    city, state, country = parse_location("San Francisco, CA, United States")
    assert city == "San Francisco"
    assert state == "CA"
    assert country == "United States"


def test_parse_salary_range():
    lo, hi, cur = parse_salary("The base salary range is $120,000 - $180,000 USD")
    assert lo == 120000.0
    assert hi == 180000.0
    assert cur == "USD"


def test_normalize_company_name():
    assert normalize_company_name("OpenAI, Inc.") == "openai-inc"


def test_normalize_helpers_tolerate_nan_values():
    assert normalize_title(nan) == ""
    assert normalize_company_name(nan) == ""
    assert parse_location(nan) == (None, None, None)


def test_dedupe_key_stable():
    a = dedupe_key("stripe", "backend engineer", "San Francisco, CA")
    b = dedupe_key("stripe", "backend engineer", "San Francisco, CA")
    assert a == b


def test_url_hash_diff():
    assert url_hash("a") != url_hash("b")
