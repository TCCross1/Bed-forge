"""Forge Coach API — authenticated, no DB lookups, no override power."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List

from auth import get_current_user
from coach import answer_coach

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["coach"])


class GroundedNote(BaseModel):
    id: str = ""
    title: str = ""
    tutorial: str = ""
    body: str = ""


class CoachAskInput(BaseModel):
    question: str = Field(min_length=2, max_length=800)
    route: str = "/"
    role: str = ""
    grounded: List[GroundedNote] = []


@router.post("/coach/ask")
async def coach_ask(payload: CoachAskInput, user=Depends(get_current_user)):
    try:
        role = payload.role or user.get("role") or "qc_tech"
        grounded = [n.model_dump() for n in (payload.grounded or [])[:8]]
        for row in grounded:
            row["body"] = str(row.get("body") or "")[:1200]
        result = answer_coach(
            payload.question.strip(),
            grounded=grounded,
            route=(payload.route or "/")[:80],
            role=role,
        )
        logger.info(
            "coach ask by=%s role=%s route=%s source=%s",
            user.get("email"),
            role,
            payload.route,
            result.get("source"),
        )
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("coach_ask failed")
        raise HTTPException(status_code=500, detail="Forge Coach could not answer. Use the Tutorial.")
