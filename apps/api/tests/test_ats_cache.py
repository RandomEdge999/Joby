from app.scrapers import ats


def setup_function():
    ats.clear_cache()
    ats.configure_cache(ttl_seconds=3600)


def test_fetch_source_reuses_cached_direct_board(monkeypatch):
    calls = {"count": 0}

    def fake_fetch(slug, *, company_name=None, timeout=15.0):
        calls["count"] += 1
        return [{"source": "greenhouse", "external_job_id": f"{slug}-{calls['count']}"}]

    monkeypatch.setattr(ats, "fetch_greenhouse", fake_fetch)

    first = ats.fetch_source("greenhouse", "figma", company_name="Figma")
    second = ats.fetch_source("greenhouse", "figma", company_name="Figma")

    assert calls["count"] == 1
    assert first == second
    assert ats.cache_status("greenhouse", "figma")["status"] == "hit"


def test_fetch_source_bypasses_cache_when_requested(monkeypatch):
    calls = {"count": 0}

    def fake_fetch(slug, *, company_name=None, timeout=15.0):
        calls["count"] += 1
        return [{"source": "greenhouse", "external_job_id": f"{slug}-{calls['count']}"}]

    monkeypatch.setattr(ats, "fetch_greenhouse", fake_fetch)

    first = ats.fetch_source("greenhouse", "figma", company_name="Figma", use_cache=False)
    second = ats.fetch_source("greenhouse", "figma", company_name="Figma", use_cache=False)

    assert calls["count"] == 2
    assert first != second
    assert ats.cache_status("greenhouse", "figma", use_cache=False)["status"] == "bypassed"


def test_workday_cache_key_includes_site_and_tenant(monkeypatch):
    calls = {"count": 0}

    def fake_fetch(tenant, site, *, company_name=None, max_pages=10, timeout=20.0):
        calls["count"] += 1
        return [{"source": "workday", "external_job_id": f"{tenant}-{site}-{calls['count']}"}]

    monkeypatch.setattr(ats, "fetch_workday", fake_fetch)

    first = ats.fetch_source("workday", "tenant-a", company_name="Acme", tenant="tenant-a", site="site-a")
    second = ats.fetch_source("workday", "tenant-a", company_name="Acme", tenant="tenant-a", site="site-a")
    third = ats.fetch_source("workday", "tenant-a", company_name="Acme", tenant="tenant-a", site="site-b")

    assert calls["count"] == 2
    assert first == second
    assert third != first