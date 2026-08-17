"""Strand roll mill-tag capture, confirmation, bed assignment, and tensioning gate."""
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from auth import get_current_user
from db import db
from models import (
    LOW_CONFIDENCE, StrandRoll, StrandRollAssignInput, StrandRollAssignment,
    StrandRollConfirm, StrandRollPhoto, now_iso,
)
from storage import ROLL_ALLOWED_EXT, file_response, roll_photo_path, save_roll_photo
from strand_gate import GATE_MESSAGE, gate_ok, matching_assignments
from strand_ocr import extract_roll

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["strand-rolls"])


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _photo_url(roll_id: str, filename: str) -> str:
    return f"/api/strand-rolls/{roll_id}/photos/{filename}"


async def _rolls_by_ids(ids: List[str]) -> dict:
    if not ids:
        return {}
    rows = await db.strand_rolls.find({"id": {"$in": ids}}, {"_id": 0}).to_list(500)
    return {row["id"]: row for row in rows}


async def bed_tension_gate(bed_id: str, pour_id: Optional[str] = None) -> dict:
    assignments = await db.strand_roll_assignments.find({"bed_id": bed_id}, {"_id": 0}).to_list(200)
    rolls = await _rolls_by_ids([a.get("roll_id") for a in assignments if a.get("roll_id")])
    matched = matching_assignments(assignments, pour_id)
    ready = []
    for rec in matched:
        roll = rolls.get(rec.get("roll_id"))
        if roll and (roll.get("heat_number") or "").strip() and roll.get("status") in ("confirmed", "assigned", "depleted"):
            ready.append({
                "assignment_id": rec.get("id"),
                "roll_id": roll.get("id"),
                "heat_number": roll.get("heat_number"),
                "reel_number": roll.get("reel_number"),
                "nominal_diameter": roll.get("nominal_diameter"),
                "status": roll.get("status"),
                "beam_ids": rec.get("beam_ids") or [],
            })
    ok = gate_ok(assignments, rolls, pour_id)
    return {
        "ok": ok,
        "bed_id": bed_id,
        "pour_id": pour_id,
        "message": "" if ok else GATE_MESSAGE,
        "rolls": ready,
    }


from audit import override_active


async def assert_tension_allowed(bed_id: Optional[str], pour_id: Optional[str] = None):
    if not bed_id:
        raise HTTPException(status_code=409, detail=GATE_MESSAGE)
    gate = await bed_tension_gate(bed_id, pour_id)
    if gate["ok"]:
        return
    if await override_active("strand_tension", bed_id):
        logger.warning("tension gate overridden bed=%s", bed_id)
        return
    logger.warning("tension gate blocked bed=%s pour=%s", bed_id, pour_id)
    raise HTTPException(status_code=409, detail=GATE_MESSAGE)


async def _enrich_roll(roll: dict) -> dict:
    assignments = await db.strand_roll_assignments.find({"roll_id": roll["id"]}, {"_id": 0}).to_list(50)
    beds = {b["id"]: b for b in await db.beds.find({}, {"_id": 0}).to_list(50)}
    pours = {p["id"]: p for p in await db.pours.find({}, {"_id": 0}).to_list(500)}
    beams = {b["id"]: b for b in await db.beams.find({}, {"_id": 0}).to_list(2000)}
    linked = []
    for rec in assignments:
        bed = beds.get(rec.get("bed_id") or "")
        pour = pours.get(rec.get("pour_id") or "")
        marks = [beams[i]["mark"] for i in (rec.get("beam_ids") or []) if i in beams]
        linked.append({
            **rec,
            "bed_number": (bed or {}).get("bed_number"),
            "bed_name": (bed or {}).get("name"),
            "pour_number": (pour or {}).get("pour_number"),
            "beam_marks": marks,
        })
    roll["assignments"] = linked
    roll["low_confidence_fields"] = [
        key for key, score in (roll.get("field_confidence") or {}).items()
        if float(score or 0) < LOW_CONFIDENCE
    ]
    return roll


async def _beams_on_bed(bed_id: str, pour_id: Optional[str]) -> List[str]:
    today = _today()
    from bed_layout import covers
    recs = await db.bed_assignments.find({"bed_id": bed_id}, {"_id": 0}).to_list(200)
    ids = []
    for rec in recs:
        if pour_id and rec.get("pour_id") and rec.get("pour_id") != pour_id:
            continue
        if rec.get("scheduled_date") and not covers(rec, today):
            continue
        if rec.get("beam_id"):
            ids.append(rec["beam_id"])
    if ids:
        return ids
    beams = await db.beams.find({"bed_id": bed_id}, {"_id": 0}).to_list(200)
    if pour_id:
        beams = [b for b in beams if not b.get("pour_id") or b.get("pour_id") == pour_id]
    return [b["id"] for b in beams]


async def _stamp_strands(beam_ids: List[str], roll: dict, user: dict):
    if not beam_ids:
        return
    stamp = now_iso()
    for beam_id in beam_ids:
        spec = None
        beam = await db.beams.find_one({"id": beam_id}, {"_id": 0})
        if not beam:
            continue
        if beam.get("spec_id"):
            spec = await db.beam_specs.find_one({"id": beam["spec_id"]}, {"_id": 0})
        if not spec:
            latest = await db.beam_specs.find({"beam_id": beam_id}, {"_id": 0}).sort("created_at", -1).to_list(1)
            spec = latest[0] if latest else None
        if not spec:
            continue
        strands = spec.get("strands") or []
        changed = False
        for strand in strands:
            if strand.get("roll_id"):
                continue
            strand["roll_id"] = roll.get("id")
            strand["heat_number"] = roll.get("heat_number") or ""
            strand["reel_number"] = roll.get("reel_number") or ""
            changed = True
        if changed:
            await db.beam_specs.update_one(
                {"id": spec["id"]},
                {"$set": {"strands": strands, "updated_at": stamp}},
            )
            logger.info(
                "strands linked to roll spec=%s roll=%s heat=%s by=%s",
                spec["id"], roll.get("id"), bool(roll.get("heat_number")), user.get("email"),
            )


@router.get("/strand-rolls")
async def list_strand_rolls(bed_id: str = None, user=Depends(get_current_user)):
    try:
        if bed_id:
            recs = await db.strand_roll_assignments.find({"bed_id": bed_id}, {"_id": 0}).to_list(200)
            ids = [r.get("roll_id") for r in recs if r.get("roll_id")]
            rows = await db.strand_rolls.find({"id": {"$in": ids}}, {"_id": 0}).sort("logged_at", -1).to_list(200) if ids else []
        else:
            rows = await db.strand_rolls.find({}, {"_id": 0}).sort("logged_at", -1).to_list(500)
        out = []
        for row in rows:
            out.append(await _enrich_roll(row))
        return out
    except Exception:
        logger.exception("list_strand_rolls failed")
        raise HTTPException(status_code=500, detail="Failed to list strand rolls")


@router.get("/strand-rolls/gate/{bed_id}")
async def get_strand_gate(bed_id: str, pour_id: str = None, user=Depends(get_current_user)):
    try:
        bed = await db.beds.find_one({"id": bed_id}, {"_id": 0})
        if not bed:
            raise HTTPException(status_code=404, detail="Bed not found")
        return await bed_tension_gate(bed_id, pour_id or bed.get("current_pour_id"))
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_strand_gate failed bed=%s", bed_id)
        raise HTTPException(status_code=500, detail="Failed to load strand gate")


@router.get("/strand-rolls/{roll_id}")
async def get_strand_roll(roll_id: str, user=Depends(get_current_user)):
    try:
        roll = await db.strand_rolls.find_one({"id": roll_id}, {"_id": 0})
        if not roll:
            raise HTTPException(status_code=404, detail="Strand roll not found")
        return await _enrich_roll(roll)
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_strand_roll failed id=%s", roll_id)
        raise HTTPException(status_code=500, detail="Failed to load strand roll")


@router.post("/strand-rolls/extract")
async def extract_strand_roll(
    photos: List[UploadFile] = File(...),
    kinds: Optional[str] = Form(None),
    extra_text: str = Form(""),
    user=Depends(get_current_user),
):
    try:
        if not photos:
            raise HTTPException(status_code=400, detail="Take at least one tag photo")
        kind_list = [k.strip() or "tag" for k in (kinds or "").split(",")] if kinds else []
        roll = StrandRoll(
            status="draft",
            logged_by=user.get("name") or "",
            received_date=_today(),
        )
        dumped = roll.model_dump()
        await db.strand_rolls.insert_one(dumped)
        saved_paths = []
        photo_docs = []
        for index, upload in enumerate(photos[:8]):
            raw = await upload.read()
            name = upload.filename or f"tag-{index + 1}.jpg"
            ext = Path(name).suffix.lower() or ".jpg"
            if ext not in ROLL_ALLOWED_EXT:
                raise HTTPException(status_code=400, detail="Unsupported photo type")
            stored_name = f"{index + 1:02d}-{uuid.uuid4().hex[:8]}{ext}"
            path = save_roll_photo(roll.id, stored_name, raw)
            saved_paths.append(path)
            kind = kind_list[index] if index < len(kind_list) else ("mtc" if "mtc" in name.lower() else "tag")
            doc = StrandRollPhoto(
                kind=kind,
                filename=stored_name,
                url=_photo_url(roll.id, stored_name),
                content_type=upload.content_type or "image/jpeg",
            )
            photo_docs.append(doc.model_dump())
            if kind == "mtc" and not dumped.get("mtc_url"):
                dumped["mtc_url"] = doc.url
        extracted = extract_roll(saved_paths, extra_text)
        fields = extracted.get("fields") or {}
        updates = {
            "photos": photo_docs,
            "mtc_url": dumped.get("mtc_url") or next((p["url"] for p in photo_docs if p["kind"] == "mtc"), ""),
            "reel_number": fields.get("reel_number") or "",
            "heat_number": fields.get("heat_number") or "",
            "lot_number": fields.get("lot_number") or "",
            "pack_weight": fields.get("pack_weight") or "",
            "pack_length": fields.get("pack_length") or "",
            "astm_standard": fields.get("astm_standard") or "",
            "strand_grade": str(fields.get("strand_grade") or ""),
            "strand_type": fields.get("strand_type") or "Low-Relaxation",
            "nominal_diameter": fields.get("nominal_diameter") or "",
            "area_in2": fields.get("area_in2"),
            "cert_values": fields.get("cert_values") or {},
            "received_date": fields.get("received_date") or dumped.get("received_date") or _today(),
            "status": "extracted",
            "extractor": extracted.get("extractor") or "",
            "extractor_confidence": float(extracted.get("extractor_confidence") or 0),
            "field_confidence": extracted.get("confidence") or {},
            "raw_text": (fields.get("raw_text") or "")[:8000],
            "updated_at": now_iso(),
        }
        await db.strand_rolls.update_one({"id": roll.id}, {"$set": updates})
        saved = await db.strand_rolls.find_one({"id": roll.id}, {"_id": 0})
        logger.info(
            "strand roll extracted id=%s photos=%s heat=%s by=%s",
            roll.id, len(photo_docs), bool(updates.get("heat_number")), user.get("email"),
        )
        return await _enrich_roll(saved)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("extract_strand_roll failed")
        raise HTTPException(status_code=500, detail="Failed to extract mill tag")


@router.post("/strand-rolls/{roll_id}/photos")
async def add_strand_roll_photos(
    roll_id: str,
    photos: List[UploadFile] = File(...),
    kinds: Optional[str] = Form(None),
    user=Depends(get_current_user),
):
    try:
        roll = await db.strand_rolls.find_one({"id": roll_id}, {"_id": 0})
        if not roll:
            raise HTTPException(status_code=404, detail="Strand roll not found")
        kind_list = [k.strip() or "tag" for k in (kinds or "").split(",")] if kinds else []
        existing = list(roll.get("photos") or [])
        start = len(existing)
        saved_paths = []
        for index, upload in enumerate(photos[:8]):
            raw = await upload.read()
            name = upload.filename or f"tag-{start + index + 1}.jpg"
            ext = Path(name).suffix.lower() or ".jpg"
            stored_name = f"{start + index + 1:02d}-{uuid.uuid4().hex[:8]}{ext}"
            path = save_roll_photo(roll_id, stored_name, raw)
            saved_paths.append(path)
            kind = kind_list[index] if index < len(kind_list) else ("mtc" if "mtc" in name.lower() else "tag")
            doc = StrandRollPhoto(
                kind=kind,
                filename=stored_name,
                url=_photo_url(roll_id, stored_name),
                content_type=upload.content_type or "image/jpeg",
            ).model_dump()
            existing.append(doc)
        extracted = extract_roll(saved_paths, roll.get("raw_text") or "")
        fields = extracted.get("fields") or {}
        updates = {
            "photos": existing,
            "updated_at": now_iso(),
            "extractor": extracted.get("extractor") or roll.get("extractor"),
            "extractor_confidence": float(extracted.get("extractor_confidence") or roll.get("extractor_confidence") or 0),
            "field_confidence": extracted.get("confidence") or roll.get("field_confidence") or {},
        }
        if fields.get("heat_number") and not roll.get("heat_number"):
            updates["heat_number"] = fields["heat_number"]
        for key in ("reel_number", "lot_number", "pack_weight", "pack_length", "astm_standard", "strand_grade", "strand_type", "nominal_diameter"):
            if fields.get(key) and not roll.get(key):
                updates[key] = fields[key]
        if fields.get("area_in2") and roll.get("area_in2") is None:
            updates["area_in2"] = fields["area_in2"]
        mtc = next((p["url"] for p in existing if p.get("kind") == "mtc"), roll.get("mtc_url") or "")
        updates["mtc_url"] = mtc
        await db.strand_rolls.update_one({"id": roll_id}, {"$set": updates})
        saved = await db.strand_rolls.find_one({"id": roll_id}, {"_id": 0})
        logger.info("strand roll photos added id=%s count=%s by=%s", roll_id, len(photos), user.get("email"))
        return await _enrich_roll(saved)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("add_strand_roll_photos failed id=%s", roll_id)
        raise HTTPException(status_code=500, detail="Failed to add mill-tag photos")


@router.get("/strand-rolls/{roll_id}/photos/{filename}")
async def get_strand_roll_photo(roll_id: str, filename: str, user=Depends(get_current_user)):
    try:
        roll = await db.strand_rolls.find_one({"id": roll_id}, {"_id": 0})
        if not roll:
            raise HTTPException(status_code=404, detail="Strand roll not found")
        path = roll_photo_path(roll_id, filename)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Photo not found")
        return file_response(path, filename, "image/jpeg")
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid photo path")
    except Exception:
        logger.exception("get_strand_roll_photo failed id=%s", roll_id)
        raise HTTPException(status_code=500, detail="Failed to load photo")


@router.patch("/strand-rolls/{roll_id}")
async def patch_strand_roll(roll_id: str, payload: StrandRollConfirm, user=Depends(get_current_user)):
    try:
        roll = await db.strand_rolls.find_one({"id": roll_id}, {"_id": 0})
        if not roll:
            raise HTTPException(status_code=404, detail="Strand roll not found")
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        updates["updated_at"] = now_iso()
        await db.strand_rolls.update_one({"id": roll_id}, {"$set": updates})
        saved = await db.strand_rolls.find_one({"id": roll_id}, {"_id": 0})
        logger.info("strand roll patched id=%s by=%s fields=%s", roll_id, user.get("email"), list(updates.keys()))
        return await _enrich_roll(saved)
    except HTTPException:
        raise
    except Exception:
        logger.exception("patch_strand_roll failed id=%s", roll_id)
        raise HTTPException(status_code=500, detail="Failed to update strand roll")


@router.post("/strand-rolls/{roll_id}/confirm")
async def confirm_strand_roll(roll_id: str, payload: StrandRollConfirm, user=Depends(get_current_user)):
    try:
        roll = await db.strand_rolls.find_one({"id": roll_id}, {"_id": 0})
        if not roll:
            raise HTTPException(status_code=404, detail="Strand roll not found")
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        heat = (updates.get("heat_number") if "heat_number" in updates else roll.get("heat_number") or "").strip()
        if not heat:
            raise HTTPException(status_code=400, detail="Heat number is required before confirming a roll")
        updates["heat_number"] = heat
        updates["status"] = "confirmed"
        updates["confirmed_by"] = user.get("name") or ""
        updates["confirmed_at"] = now_iso()
        updates["updated_at"] = now_iso()
        await db.strand_rolls.update_one({"id": roll_id}, {"$set": updates})
        saved = await db.strand_rolls.find_one({"id": roll_id}, {"_id": 0})
        logger.info("strand roll confirmed id=%s heat=%s by=%s", roll_id, bool(heat), user.get("email"))
        return await _enrich_roll(saved)
    except HTTPException:
        raise
    except Exception:
        logger.exception("confirm_strand_roll failed id=%s", roll_id)
        raise HTTPException(status_code=500, detail="Failed to confirm strand roll")


@router.post("/strand-rolls/{roll_id}/assign")
async def assign_strand_roll(roll_id: str, payload: StrandRollAssignInput, user=Depends(get_current_user)):
    try:
        roll = await db.strand_rolls.find_one({"id": roll_id}, {"_id": 0})
        if not roll:
            raise HTTPException(status_code=404, detail="Strand roll not found")
        if roll.get("status") not in ("confirmed", "assigned"):
            raise HTTPException(status_code=409, detail="Confirm the mill tag before assigning this roll to a bed")
        bed = await db.beds.find_one({"id": payload.bed_id}, {"_id": 0})
        if not bed:
            raise HTTPException(status_code=404, detail="Bed not found")
        pour_id = payload.pour_id or bed.get("current_pour_id")
        beam_ids = payload.beam_ids if payload.beam_ids is not None else await _beams_on_bed(payload.bed_id, pour_id)
        rec = StrandRollAssignment(
            roll_id=roll_id,
            bed_id=payload.bed_id,
            pour_id=pour_id,
            beam_ids=beam_ids,
            allocated_length=payload.allocated_length,
            logged_by=user.get("name") or "",
        )
        await db.strand_roll_assignments.insert_one(rec.model_dump())
        await db.strand_rolls.update_one({"id": roll_id}, {"$set": {"status": "assigned", "updated_at": now_iso()}})
        await _stamp_strands(beam_ids, {**roll, "status": "assigned"}, user)
        saved = await db.strand_rolls.find_one({"id": roll_id}, {"_id": 0})
        logger.info(
            "strand roll assigned id=%s bed=%s beams=%s by=%s",
            roll_id, payload.bed_id, len(beam_ids), user.get("email"),
        )
        return {"roll": await _enrich_roll(saved), "assignment": rec.model_dump()}
    except HTTPException:
        raise
    except Exception:
        logger.exception("assign_strand_roll failed id=%s", roll_id)
        raise HTTPException(status_code=500, detail="Failed to assign strand roll")


@router.get("/beams/{beam_id}/strand-traceability")
async def beam_strand_traceability(beam_id: str, user=Depends(get_current_user)):
    try:
        beam = await db.beams.find_one({"id": beam_id}, {"_id": 0})
        if not beam:
            raise HTTPException(status_code=404, detail="Beam not found")
        recs = await db.strand_roll_assignments.find({"beam_ids": beam_id}, {"_id": 0}).to_list(50)
        if not recs and beam.get("bed_id"):
            recs = await db.strand_roll_assignments.find({"bed_id": beam["bed_id"]}, {"_id": 0}).to_list(50)
            recs = [r for r in recs if not r.get("pour_id") or r.get("pour_id") == beam.get("pour_id")]
        rolls = await _rolls_by_ids([r.get("roll_id") for r in recs if r.get("roll_id")])
        chain = []
        for rec in recs:
            roll = rolls.get(rec.get("roll_id")) or {}
            chain.append({
                "beam_id": beam_id,
                "beam_mark": beam.get("mark"),
                "roll_id": roll.get("id"),
                "reel_number": roll.get("reel_number"),
                "heat_number": roll.get("heat_number"),
                "lot_number": roll.get("lot_number"),
                "astm_standard": roll.get("astm_standard"),
                "strand_grade": roll.get("strand_grade"),
                "nominal_diameter": roll.get("nominal_diameter"),
                "mtc_url": roll.get("mtc_url"),
                "photos": roll.get("photos") or [],
                "assignment_id": rec.get("id"),
                "bed_id": rec.get("bed_id"),
                "pour_id": rec.get("pour_id"),
            })
        return {"beam": beam, "chain": chain, "rolls": list(rolls.values())}
    except HTTPException:
        raise
    except Exception:
        logger.exception("beam_strand_traceability failed beam=%s", beam_id)
        raise HTTPException(status_code=500, detail="Failed to load strand traceability")
