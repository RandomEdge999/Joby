from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from ..services.runner import start_run


router = APIRouter(prefix="/api/search", tags=["search"])


class SearchRunRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    intent: Literal["explore", "match", "strict"] = "match"
    locations: list[str] = Field(default_factory=lambda: ["United States"], min_length=1, max_length=4)
    sources: list[Literal["jobspy", "ats", "workday"]] = Field(
        default_factory=lambda: ["jobspy"], min_length=1, max_length=3
    )
    results_per_source: int = Field(200, ge=1, le=1000)
    posted_within_days: int | None = Field(None, ge=1, le=365)
    use_cache: bool = True

    @field_validator("query")
    @classmethod
    def _clean_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("query cannot be blank")
        return cleaned

    @field_validator("locations")
    @classmethod
    def _clean_locations(cls, value: list[str]) -> list[str]:
        cleaned = []
        for item in value:
            text = str(item).strip()
            if text and text not in cleaned:
                cleaned.append(text)
        if not cleaned:
            raise ValueError("at least one location is required")
        return cleaned

    @field_validator("sources")
    @classmethod
    def _dedupe_sources(cls, value: list[str]) -> list[str]:
        cleaned = []
        for item in value:
            if item not in cleaned:
                cleaned.append(item)
        return cleaned


@router.post("/run")
def start_search_run(payload: SearchRunRequest):
    search = payload.model_dump()
    run_id = start_run(trigger_type="search", search=search)
    return {"run_id": run_id, "status": "pending", "search": search}