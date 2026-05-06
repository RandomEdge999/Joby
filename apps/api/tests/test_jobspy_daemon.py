from math import nan

from app.scrapers.jobspy_daemon import _normalize_one


def test_jobspy_normalize_handles_nan_company_and_location():
    row = {
        "title": "Data Analyst",
        "company": nan,
        "description": nan,
        "job_url": "https://example.com/job/1",
        "location": nan,
        "id": "job-1",
        "site": "indeed",
    }

    normalized = _normalize_one("indeed", row)

    assert normalized["company_name_raw"] == "Unknown"
    assert normalized["title"] == "Data Analyst"
    assert normalized["location_raw"] == ""