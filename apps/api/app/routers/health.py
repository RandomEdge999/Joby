from __future__ import annotations

from fastapi import APIRouter
from ..screener.lmstudio import lmstudio

router = APIRouter()


@router.get("/api/health")
async def health():
    return {"status": "ok"}


@router.get("/api/llm/health")
async def llm_health():
    return await lmstudio.health()
