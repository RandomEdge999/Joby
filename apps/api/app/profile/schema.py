from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator


class MajorFamily(BaseModel):
    primary: Optional[str] = None
    related: List[str] = Field(default_factory=list)


class Identity(BaseModel):
    citizenship_status: Literal[
        "us_citizen", "permanent_resident", "international_student",
        "h1b_holder", "other", "unknown",
    ] = "unknown"
    needs_sponsorship_now: bool = False
    needs_sponsorship_future: bool = False
    security_clearance: Literal["none", "secret", "top_secret", "ts_sci"] = "none"
    major_family: MajorFamily = Field(default_factory=MajorFamily)


class TargetLocation(BaseModel):
    name: str
    radius_miles: Optional[int] = 35
    remote_ok: bool = True


class Targeting(BaseModel):
    target_employment: List[Literal["full_time", "internship", "co_op", "contract"]] = Field(
        default_factory=lambda: ["full_time"]
    )
    target_levels: List[str] = Field(default_factory=list)
    target_roles: List[str] = Field(default_factory=list)
    target_locations: List[TargetLocation] = Field(default_factory=list)
    remote_preference: Literal["onsite", "hybrid", "remote", "hybrid_or_remote", "any"] = "any"
    relocation_ok: bool = True
    salary_floor: Optional[int] = None
    salary_ceiling: Optional[int] = None
    posted_within_days: Optional[int] = 30
    industry_allow: List[str] = Field(default_factory=list)
    industry_block: List[str] = Field(default_factory=list)
    company_tier_preference: List[Literal["top", "strong", "standard", "unknown"]] = Field(
        default_factory=list
    )


class Resume(BaseModel):
    resume_path: Optional[str] = None
    resume_summary: Optional[str] = ""
    must_have_skills: List[str] = Field(default_factory=list)
    nice_to_have_skills: List[str] = Field(default_factory=list)
    years_experience: int = 0


class Scoring(BaseModel):
    w_fit: float = 0.5
    w_opportunity: float = 0.3
    w_urgency: float = 0.2
    visa_hard_filter: bool = False

    def normalized(self) -> "Scoring":
        total = self.w_fit + self.w_opportunity + self.w_urgency
        if total <= 0:
            return Scoring(w_fit=1/3, w_opportunity=1/3, w_urgency=1/3,
                           visa_hard_filter=self.visa_hard_filter)
        return Scoring(
            w_fit=self.w_fit / total,
            w_opportunity=self.w_opportunity / total,
            w_urgency=self.w_urgency / total,
            visa_hard_filter=self.visa_hard_filter,
        )


class Screening(BaseModel):
    """Controls whether the LLM is used for screening.

    - ``auto``: use LM Studio when reachable, otherwise skip silently (default).
    - ``llm``: require LM Studio; mark jobs as ``error`` if unreachable.
    - ``heuristic``: deterministic-only; never call the LLM.
    """
    mode: Literal["auto", "llm", "heuristic"] = "auto"
    # Max concurrent in-flight LLM requests when mode != heuristic.
    llm_concurrency: int = 4
    # Cap on LLM-screened jobs per run (0 = no cap). Keeps runs bounded when the
    # catalog grows to tens of thousands of postings.
    llm_per_run_cap: int = 0


class Sources(BaseModel):
    # JobSpy is the "thousands of companies" source (LinkedIn/Indeed/Glassdoor/
    # ZipRecruiter/Google Jobs). Enabled by default so a fresh install sees
    # real postings immediately; silently no-ops if python-jobspy isn't
    # installed (the daemon lazy-imports it).
    enable_jobspy: bool = True
    enable_ats: bool = True
    enable_workday: bool = False
    enable_smartrecruiters: bool = True
    enable_workable: bool = True
    enable_recruitee: bool = True
    # JobSpy search terms fed to the daemon when enable_jobspy is true.
    jobspy_search_terms: List[str] = Field(default_factory=list)
    jobspy_locations: List[str] = Field(default_factory=lambda: ["United States"])
    jobspy_results_per_term: int = 30
    watch_default_cadence_hours: int = 6


class Profile(BaseModel):
    profile_name: str = "default"
    preset: Optional[str] = None
    identity: Identity = Field(default_factory=Identity)
    targeting: Targeting = Field(default_factory=Targeting)
    resume: Resume = Field(default_factory=Resume)
    scoring: Scoring = Field(default_factory=Scoring)
    screening: Screening = Field(default_factory=Screening)
    sources: Sources = Field(default_factory=Sources)

    @field_validator("scoring")
    @classmethod
    def _validate_scoring(cls, v: Scoring) -> Scoring:
        # Allow any non-negative weights; normalization happens on use.
        if v.w_fit < 0 or v.w_opportunity < 0 or v.w_urgency < 0:
            raise ValueError("ranking weights must be non-negative")
        return v
