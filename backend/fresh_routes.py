"""Plant-floor fresh (plastic) concrete tests — spread, slump, J-ring at delivery."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import get_current_user
from db import db
from fresh_concrete import apply_computed_fields, sanitize_gate, sanitize_stability, sanitize_test_types
from models import FreshConcreteTest, FreshConcreteTestCreate, now_iso

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["fresh-concrete"])


def _public(doc: dict) -> dict:
    out = dict(doc or {})
    out.pop("_id", None)
    return out


def _list_query(job_id: Optional[str], pour_id: Optional[str], beam_id: Optional[str]) -> dict:
    q = {}
    if job_id:
        q["job_id"] = str(job_id)
    if pour_id:
        q["pour_id"] = str(pour_id)
    if beam_id:
        q["beam_ids"] = str(beam_id)
    return q


@router.get("/fresh-tests")
async def list_fresh_tests(
    job_id: Optional[str] = Query(None),
    pour_id: Optional[str] = Query(None),
    beam_id: Optional[str] = Query(None),
    user=Depends(get_current_user),
):
    try:
        q = _list_query(job_id, pour_id, beam_id)
        rows = await db.fresh_concrete_tests.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
        logger.info(
            "fresh tests listed count=%s job=%s pour=%s beam=%s by=%s",
            len(rows),
            bool(job_id),
            bool(pour_id),
            bool(beam_id),
            user.get("email"),
        )
        return rows
    except Exception:
        logger.exception("list_fresh_tests failed")
        raise HTTPException(status_code=500, detail="Failed to list fresh concrete tests")


@router.post("/fresh-tests")
async def create_fresh_test(payload: FreshConcreteTestCreate, user=Depends(get_current_user)):
    try:
        data = payload.model_dump()
        if not data.get("job_id") or not data.get("pour_id"):
            raise HTTPException(status_code=400, detail="Pick the job and pour before saving")
        job = await db.jobs.find_one({"id": data["job_id"]}, {"_id": 0})
        pour = await db.pours.find_one({"id": data["pour_id"]}, {"_id": 0})
        if not job:
            raise HTTPException(status_code=400, detail="Job not found")
        if not pour:
            raise HTTPException(status_code=400, detail="Pour not found")
        if pour.get("job_id") and pour["job_id"] != data["job_id"]:
            raise HTTPException(status_code=400, detail="Pour does not belong to that job")

        data["test_types"] = sanitize_test_types(data.get("test_types"))
        data["gate"] = sanitize_gate(data.get("gate"))
        data["visual_stability"] = sanitize_stability(data.get("visual_stability"))
        data["jring_note"] = (data.get("jring_note") or "standard J-ring").strip() or "standard J-ring"
        data["beam_ids"] = [str(b) for b in (data.get("beam_ids") or []) if b]
        data["time_sampled"] = data.get("time_sampled") or now_iso()
        data = apply_computed_fields(data)
        rec = FreshConcreteTest(**data, inspector=user.get("name") or "")
        stored = rec.model_dump()
        await db.fresh_concrete_tests.insert_one(stored)
        logger.info(
            "fresh test saved id=%s pour=%s types=%s gate=%s by=%s",
            rec.id,
            rec.pour_id,
            ",".join(rec.test_types),
            rec.gate,
            user.get("email"),
        )
        if rec.gate == "fail" or rec.blocking_assessment == "blocking":
            from ncr import attach_prompt, build_prompt
            stored = attach_prompt(stored, build_prompt(
                source_type="fresh",
                source_id=rec.id,
                title="Fresh test fail / J-ring blocking — file an NCR",
                category="material",
                severity="major",
                description=f"gate={rec.gate} blocking={rec.blocking_assessment}",
                beam_id=(rec.beam_ids or [""])[0],
                pour_id=rec.pour_id,
                job_id=rec.job_id,
            ))
        return _public(stored)
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_fresh_test failed")
        raise HTTPException(status_code=500, detail="Failed to save fresh concrete test")
