"""Per-strand and hold-down tension twin APIs. Capture is allowed on locked specs."""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
from beam_spec import (
    BeamSpec, HoldDownCapture, StrandTensionCapture,
    ensure_tension_geometry, hold_down_done, strand_status_key,
)
from db import db
from models import now_iso
from tension import strand_capture_result

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["tension-twin"])


def _find_strand(spec: dict, strand_id: str) -> Optional[dict]:
    for item in spec.get("strands") or []:
        if item.get("id") == strand_id or item.get("strand_id") == strand_id:
            return item
    return None


def _find_hold_down(spec: dict, hd_id: str) -> Optional[dict]:
    for item in spec.get("hold_downs") or []:
        if item.get("id") == hd_id:
            return item
    return None


async def _load_spec_for_beam(beam: dict) -> Optional[dict]:
    spec = None
    if beam.get("spec_id"):
        spec = await db.beam_specs.find_one({"id": beam["spec_id"]}, {"_id": 0})
    if not spec:
        latest = await db.beam_specs.find({"beam_id": beam["id"]}, {"_id": 0}).sort("created_at", -1).to_list(1)
        spec = latest[0] if latest else None
    return spec


async def _persist_geometry(spec_doc: dict) -> dict:
    try:
        filled = ensure_tension_geometry(BeamSpec(**spec_doc))
        dumped = filled.model_dump()
        await db.beam_specs.update_one({"id": spec_doc["id"]}, {"$set": {
            "strands": dumped["strands"],
            "hold_downs": dumped["hold_downs"],
        }})
        spec_doc["strands"] = dumped["strands"]
        spec_doc["hold_downs"] = dumped["hold_downs"]
        return spec_doc
    except Exception:
        logger.exception("tension twin backfill failed spec=%s", spec_doc.get("id"))
        return spec_doc


def _enrich_strands(strands: List[dict], bed_length_ft: float) -> List[dict]:
    rows = []
    for raw in strands or []:
        force = float(raw.get("jacking_force") or raw.get("jacking_kip") or 31.0)
        area = float(raw.get("area_in2") or 0.153)
        modulus = float(raw.get("modulus_ksi") or 28500.0)
        computed = strand_capture_result(
            jacking_force_kip=force,
            bed_length_ft=bed_length_ft,
            strand_area_in2=area,
            modulus_ksi=modulus,
            measured_elongation_in=raw.get("measured_elongation"),
            na=bool(raw.get("na")),
        )
        row = {**raw, **computed}
        if raw.get("theoretical_elongation") is not None and raw.get("measured_elongation") is not None:
            row["theoretical_elongation"] = raw["theoretical_elongation"]
            row["variance_pct"] = raw.get("variance_pct")
            row["within_tolerance"] = raw.get("within_tolerance")
            row["status"] = strand_status_key(row)
        else:
            row["status"] = computed["status"]
        rows.append(row)
    return rows


def _summary(strands: List[dict], hold_downs: List[dict]) -> dict:
    strand_done = 0
    for s in strands:
        if s.get("na") or s.get("measured_elongation") is not None:
            strand_done += 1
    hd_done = sum(1 for h in hold_downs if hold_down_done(h))
    hd_issue = sum(1 for h in hold_downs if h.get("status") == "issue")
    return {
        "strands_complete": strand_done,
        "strands_total": len(strands),
        "hold_downs_verified": hd_done,
        "hold_downs_total": len(hold_downs),
        "hold_downs_issue": hd_issue,
    }


@router.get("/beams/{beam_id}/tension-twin")
async def get_tension_twin(beam_id: str, user=Depends(get_current_user)):
    try:
        beam = await db.beams.find_one({"id": beam_id}, {"_id": 0})
        if not beam:
            raise HTTPException(status_code=404, detail="Beam not found")
        spec = await _load_spec_for_beam(beam)
        if not spec:
            raise HTTPException(status_code=404, detail="No BeamSpec for this beam. Upload and lock a shop drawing first.")
        needs = (not spec.get("hold_downs")) or any(not s.get("row") for s in (spec.get("strands") or []))
        if needs:
            spec = await _persist_geometry(spec)
        bed = await db.beds.find_one({"id": beam.get("bed_id") or ""}, {"_id": 0}) if beam.get("bed_id") else None
        bed_length = float((bed or {}).get("length_ft") or (spec.get("geometry") or {}).get("length_ft") or 0)
        strands = _enrich_strands(spec.get("strands") or [], bed_length)
        hold_downs = spec.get("hold_downs") or []
        return {
            "beam": beam,
            "spec": spec,
            "bed": bed,
            "bed_length_ft": bed_length,
            "strands": strands,
            "hold_downs": hold_downs,
            "summary": _summary(strands, hold_downs),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_tension_twin failed beam=%s", beam_id)
        raise HTTPException(status_code=500, detail="Failed to load tension twin")


@router.post("/beam-specs/{spec_id}/strands/{strand_id}/tension")
async def capture_strand_tension(
    spec_id: str,
    strand_id: str,
    payload: StrandTensionCapture,
    user=Depends(get_current_user),
):
    try:
        spec = await db.beam_specs.find_one({"id": spec_id}, {"_id": 0})
        if not spec:
            raise HTTPException(status_code=404, detail="BeamSpec not found")
        spec = await _persist_geometry(spec)
        strand = _find_strand(spec, strand_id)
        if not strand:
            raise HTTPException(status_code=404, detail="Strand not found on this BeamSpec")
        beam = await db.beams.find_one({"id": spec.get("beam_id") or ""}, {"_id": 0}) if spec.get("beam_id") else None
        bed = await db.beds.find_one({"id": (beam or {}).get("bed_id") or ""}, {"_id": 0}) if beam else None
        bed_length = float(
            payload.bed_length_ft
            or (bed or {}).get("length_ft")
            or (spec.get("geometry") or {}).get("length_ft")
            or 0
        )
        force = float(payload.jacking_force_kip or strand.get("jacking_force") or strand.get("jacking_kip") or 31.0)
        result = strand_capture_result(
            jacking_force_kip=force,
            bed_length_ft=bed_length,
            strand_area_in2=float(strand.get("area_in2") or 0.153),
            modulus_ksi=float(strand.get("modulus_ksi") or 28500.0),
            measured_elongation_in=None if payload.na else payload.measured_elongation_in,
            na=payload.na,
        )
        stamp = now_iso()
        updates: Dict[str, Any] = {
            "strands.$.theoretical_elongation": result["theoretical_elongation"],
            "strands.$.measured_elongation": result["measured_elongation"],
            "strands.$.jacking_force": result["jacking_force"],
            "strands.$.variance_pct": result["variance_pct"],
            "strands.$.within_tolerance": result["within_tolerance"],
            "strands.$.na": result["na"],
            "strands.$.recorded_by": user.get("name") or "",
            "strands.$.recorded_at": stamp,
            "strands.$.notes": payload.notes if payload.notes else strand.get("notes") or "",
            "updated_at": stamp,
        }
        await db.beam_specs.update_one(
            {"id": spec_id, "strands.id": strand.get("id")},
            {"$set": updates},
        )
        logger.info(
            "strand tension captured spec=%s strand=%s status=%s by=%s",
            spec_id, strand.get("id"), result["status"], user.get("email"),
        )
        saved = await db.beam_specs.find_one({"id": spec_id}, {"_id": 0})
        updated = _find_strand(saved, strand.get("id"))
        return {**(updated or {}), **result, "status": result["status"]}
    except HTTPException:
        raise
    except Exception:
        logger.exception("capture_strand_tension failed spec=%s strand=%s", spec_id, strand_id)
        raise HTTPException(status_code=500, detail="Failed to save strand tension")


@router.post("/beam-specs/{spec_id}/hold-downs/{hd_id}/check")
async def capture_hold_down(
    spec_id: str,
    hd_id: str,
    payload: HoldDownCapture,
    user=Depends(get_current_user),
):
    try:
        spec = await db.beam_specs.find_one({"id": spec_id}, {"_id": 0})
        if not spec:
            raise HTTPException(status_code=404, detail="BeamSpec not found")
        spec = await _persist_geometry(spec)
        item = _find_hold_down(spec, hd_id)
        if not item:
            raise HTTPException(status_code=404, detail="Hold-down not found on this BeamSpec")
        status = (payload.status or "pending").lower()
        allowed = {"pending", "installed", "stressed", "released", "inspected", "verified", "issue"}
        if status not in allowed:
            raise HTTPException(status_code=400, detail="Invalid hold-down status")
        stamp = now_iso()
        updates = {
            "hold_downs.$.status": status,
            "hold_downs.$.notes": payload.notes,
            "updated_at": stamp,
        }
        if status in ("verified", "inspected"):
            updates["hold_downs.$.verified_by"] = user.get("name") or ""
            updates["hold_downs.$.verified_at"] = stamp
        await db.beam_specs.update_one({"id": spec_id, "hold_downs.id": hd_id}, {"$set": updates})
        logger.info("hold-down captured spec=%s hd=%s status=%s by=%s", spec_id, hd_id, status, user.get("email"))
        saved = await db.beam_specs.find_one({"id": spec_id}, {"_id": 0})
        return _find_hold_down(saved, hd_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("capture_hold_down failed spec=%s hd=%s", spec_id, hd_id)
        raise HTTPException(status_code=500, detail="Failed to save hold-down check")
