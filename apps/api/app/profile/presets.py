"""Six canonical profile presets per IMPLEMENTATION_PLAN section 6."""
from __future__ import annotations

from typing import Dict
from .schema import (
    Profile, Identity, Targeting, TargetLocation, Resume, Scoring, Sources, MajorFamily,
)


def _intl_opt() -> Profile:
    return Profile(
        profile_name="International student on OPT",
        preset="international-student-opt",
        identity=Identity(
            citizenship_status="international_student",
            needs_sponsorship_now=False,
            needs_sponsorship_future=True,
            major_family=MajorFamily(primary="computer_science",
                                     related=["software_engineering", "data_science"]),
        ),
        targeting=Targeting(
            target_employment=["full_time"],
            target_levels=["entry", "new_grad"],
            target_roles=["software engineer", "backend engineer", "data engineer"],
            target_locations=[TargetLocation(name="san_francisco_bay_area", radius_miles=35, remote_ok=True)],
            remote_preference="hybrid_or_remote",
            salary_floor=90000,
            posted_within_days=14,
            company_tier_preference=["top", "strong"],
        ),
        resume=Resume(must_have_skills=["python", "sql"], nice_to_have_skills=["docker", "aws"], years_experience=1),
        scoring=Scoring(w_fit=0.5, w_opportunity=0.3, w_urgency=0.2, visa_hard_filter=False),
    )


def _intl_pre_opt() -> Profile:
    return Profile(
        profile_name="International student (pre-OPT / internship)",
        preset="international-student-pre-opt",
        identity=Identity(
            citizenship_status="international_student",
            needs_sponsorship_now=True,
            needs_sponsorship_future=True,
            major_family=MajorFamily(primary="computer_science"),
        ),
        targeting=Targeting(
            target_employment=["internship", "co_op"],
            target_levels=["intern"],
            target_roles=["software engineering intern", "data science intern"],
            remote_preference="any",
            posted_within_days=21,
        ),
        resume=Resume(years_experience=0),
        scoring=Scoring(w_fit=0.5, w_opportunity=0.3, w_urgency=0.2, visa_hard_filter=False),
    )


def _us_new_grad() -> Profile:
    return Profile(
        profile_name="US new grad (no sponsorship needed)",
        preset="us-new-grad",
        identity=Identity(
            citizenship_status="us_citizen",
            needs_sponsorship_now=False,
            needs_sponsorship_future=False,
        ),
        targeting=Targeting(
            target_employment=["full_time"],
            target_levels=["entry", "new_grad"],
            target_roles=["software engineer"],
            remote_preference="any",
            posted_within_days=21,
            salary_floor=80000,
        ),
        resume=Resume(years_experience=0),
        scoring=Scoring(w_fit=0.6, w_opportunity=0.2, w_urgency=0.2, visa_hard_filter=False),
    )


def _us_clearance() -> Profile:
    return Profile(
        profile_name="US citizen, clearance-eligible",
        preset="us-clearance",
        identity=Identity(
            citizenship_status="us_citizen",
            needs_sponsorship_now=False,
            needs_sponsorship_future=False,
            security_clearance="secret",
        ),
        targeting=Targeting(
            target_employment=["full_time"],
            target_levels=["entry", "mid", "senior"],
            target_roles=["software engineer", "systems engineer"],
            industry_allow=["defense", "aerospace", "government"],
            posted_within_days=30,
        ),
        scoring=Scoring(w_fit=0.5, w_opportunity=0.3, w_urgency=0.2, visa_hard_filter=False),
    )


def _switcher() -> Profile:
    return Profile(
        profile_name="Career switcher",
        preset="career-switcher",
        identity=Identity(citizenship_status="unknown"),
        targeting=Targeting(
            target_employment=["full_time"],
            target_levels=["entry", "mid"],
            target_roles=["software engineer"],
            posted_within_days=30,
        ),
        resume=Resume(years_experience=0),
        scoring=Scoring(w_fit=0.4, w_opportunity=0.4, w_urgency=0.2, visa_hard_filter=False),
    )


def _blank() -> Profile:
    return Profile(profile_name="Custom", preset="custom")


PRESETS: Dict[str, Profile] = {
    "international-student-opt": _intl_opt(),
    "international-student-pre-opt": _intl_pre_opt(),
    "us-new-grad": _us_new_grad(),
    "us-clearance": _us_clearance(),
    "career-switcher": _switcher(),
    "custom": _blank(),
}


def list_presets() -> list[dict]:
    return [
        {"key": k, "name": p.profile_name, "preset": p.preset}
        for k, p in PRESETS.items()
    ]


def get_preset(key: str) -> Profile:
    if key not in PRESETS:
        raise KeyError(key)
    # Return a deep copy via model dump/validate
    return Profile.model_validate(PRESETS[key].model_dump())
