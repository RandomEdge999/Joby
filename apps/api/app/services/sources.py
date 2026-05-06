"""Source configuration loading for config/sources.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any
import yaml

from ..config import settings


def load_sources() -> Dict[str, Any]:
    """Merge the curated config/sources.yaml with the user overlay
    config/sources.user.yaml (created by the company-discovery flow).
    User entries take precedence on (type, slug) collisions.
    """
    path = settings.resolved_config_dir() / "sources.yaml"
    base: Dict[str, Any] = {"ats_sources": [],
                            "jobspy": {"enabled": False},
                            "workday": {"enabled": False, "organizations": []}}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            base = yaml.safe_load(f) or base

    overlay = settings.resolved_config_dir() / "sources.user.yaml"
    if overlay.exists():
        try:
            with open(overlay, "r", encoding="utf-8") as f:
                user = yaml.safe_load(f) or {}
            user_rows = user.get("ats_sources") or []
            seen = {(str(r.get("type", "")).lower(),
                     str(r.get("slug", "")).lower())
                    for r in user_rows if isinstance(r, dict)}
            merged = [r for r in base.get("ats_sources", [])
                      if (str(r.get("type", "")).lower(),
                          str(r.get("slug", "")).lower()) not in seen]
            merged.extend(r for r in user_rows if isinstance(r, dict))
            base["ats_sources"] = merged
        except Exception:
            pass
    return base


def enabled_ats_sources() -> List[Dict[str, Any]]:
    """ATS sources only (Greenhouse/Lever/Ashby/SmartRecruiters/Workable/Recruitee).

    Workday is handled separately by :func:`enabled_workday_sources` because its
    config shape includes ``tenant`` and ``site`` identifiers.
    """
    data = load_sources()
    ats_types = {"greenhouse", "lever", "ashby", "smartrecruiters",
                 "workable", "recruitee"}
    return [s for s in data.get("ats_sources", [])
            if s.get("enabled", True) and s.get("type") in ats_types]


def enabled_workday_sources() -> List[Dict[str, Any]]:
    data = load_sources()
    wd = data.get("workday") or {}
    if not wd.get("enabled"):
        return []
    return [o for o in wd.get("organizations", []) if o.get("enabled", True)]


def jobspy_config() -> Dict[str, Any]:
    data = load_sources()
    return data.get("jobspy") or {"enabled": False}
