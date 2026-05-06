"""Cold-email generator.

Produces copy-paste email subject + body targeting a recruiter/hiring contact
for a specific job. Always emits a deterministic template; if the LLM is
available AND the profile's screening.mode is not 'heuristic', the draft is
refined through LM Studio for tone.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Contact, Job, UserProfile
from ..profile.schema import Profile
from ..screener.lmstudio import lmstudio

router = APIRouter(prefix="/api/cold_email", tags=["cold_email"])


class GenerateIn(BaseModel):
    contact_id: int
    job_id: int
    tone: str = "warm"  # warm | concise | enthusiastic
    refine_with_llm: Optional[bool] = None  # None => use profile.screening.mode


class GenerateOut(BaseModel):
    subject: str
    body: str
    refined: bool
    model: Optional[str] = None


def _template(contact: Contact, job: Job, company_name: str, profile: Profile,
              tone: str) -> tuple[str, str]:
    first_name = (contact.name or "").split(" ")[0] or "there"
    role_title = job.title or "an open role"
    must = ", ".join(profile.resume.must_have_skills[:4]) or "my background"
    yoe = profile.resume.years_experience
    subject = f"Interest in {role_title} @ {company_name}"
    opener = {
        "warm": f"Hi {first_name},",
        "concise": f"Hi {first_name} —",
        "enthusiastic": f"Hi {first_name}!",
    }.get(tone, f"Hi {first_name},")
    body = (
        f"{opener}\n\n"
        f"I came across the {role_title} opening at {company_name} and "
        f"wanted to reach out directly. I have {yoe} years of experience "
        f"with {must}, and the role maps closely to what I've shipped "
        f"recently.\n\n"
        f"If there's a good time this week, I'd love to share a short "
        f"summary of relevant work and learn more about what your team is "
        f"prioritizing.\n\n"
        f"Thanks for your time,\n"
    )
    return subject, body


async def _refine(subject: str, body: str, tone: str) -> Optional[tuple[str, str, str]]:
    health = await lmstudio.health()
    if not health.get("available"):
        return None
    system = (
        "You refine cold outreach emails. Output ONLY JSON: "
        '{"subject": string, "body": string}. Keep it under 130 words, '
        "avoid buzzwords, preserve all facts, match the requested tone, "
        "and keep the exact sign-off line."
    )
    user = f"Tone: {tone}\nSUBJECT: {subject}\nBODY:\n{body}"
    result = await lmstudio.chat_json(system=system, user=user, max_tokens=500)
    if not result:
        return None
    sub = result.get("subject") or subject
    bod = result.get("body") or body
    return sub, bod, health.get("model") or ""


@router.post("/generate", response_model=GenerateOut)
def generate(payload: GenerateIn, db: Session = Depends(get_db)):
    contact = db.get(Contact, payload.contact_id)
    if not contact:
        raise HTTPException(404, "contact not found")
    job = db.get(Job, payload.job_id)
    if not job:
        raise HTTPException(404, "job not found")
    up = db.query(UserProfile).filter(UserProfile.is_active == True).first()  # noqa: E712
    if up:
        profile = Profile.model_validate(up.profile_json)
    else:
        # No-blocker: if the user never saved a profile, use the blank preset
        # so cold-email generation still works end-to-end.
        from ..profile.presets import get_preset
        profile = get_preset("custom")

    company_name = (job.company.name if job.company else None) or job.company_name_raw or "your team"
    subject, body = _template(contact, job, company_name, profile, payload.tone)

    mode = profile.screening.mode
    use_llm = payload.refine_with_llm if payload.refine_with_llm is not None else (mode != "heuristic")

    refined = False
    model: Optional[str] = None
    if use_llm:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                out = loop.run_until_complete(_refine(subject, body, payload.tone))
            finally:
                loop.close()
            if out:
                subject, body, model = out
                refined = True
        except Exception:
            # Never fail the request just because LLM refinement broke.
            pass

    return GenerateOut(subject=subject, body=body, refined=refined, model=model)
