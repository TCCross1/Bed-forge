"""Ask Expert API — authenticated, read-only live checks, no override power."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List

from auth import get_current_user
from coach import answer_coach
from coach_audit import gather_live_audit, is_audit_ask

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["coach"])


class GroundedNote(BaseModel):
    id: str = ""
    title: str = ""
    tutorial: str = ""
    body: str = ""


class CoachAskInput(BaseModel):
    question: str = Field(min_length=2, max_length=1200)
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
        live = None
        question = payload.question.strip()
        if is_audit_ask(question):
            try:
                live = await gather_live_audit(user, question)
                logger.info(
                    "ask expert live audit by=%s job=%s mark=%s live_ok=%s findings=%s",
                    user.get("email"),
                    (live or {}).get("asked_job"),
                    (live or {}).get("asked_mark"),
                    (live or {}).get("live_ok"),
                    len((live or {}).get("findings") or []),
                )
            except Exception:
                logger.exception("ask expert live audit failed by=%s", user.get("email"))
                live = {"findings": [], "live_ok": False, "errors": ["live audit raised"]}
        result = answer_coach(
            question,
            grounded=grounded,
            route=(payload.route or "/")[:80],
            role=role,
            live=live,
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
        raise HTTPException(status_code=500, detail="Ask Expert could not answer. Use the Tutorial.")
