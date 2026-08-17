"""Bed layout, assignment, calendar, and twin payload APIs."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user, require_roles
from bed_layout import (
    GAP_FT, HEADER_SETBACK_FT, MAX_BEAMS_TYPICAL, covers, end_day, fallback_spec,
    find_conflicts, map_production_status, pack_stations, parse_day, remaining_ft,
)
from db import db
from models import (
    BedAssignment, BedAssignmentCreate, BedAssignmentUpdate, BedReorder, now_iso,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["beds"])
MUTATE = require_roles("admin", "qc_supervisor", "production")


async def _bed(bed_id: str) -> dict:
    bed = await db.beds.find_one({"id": bed_id}, {"_id": 0})
    if not bed:
        raise HTTPException(status_code=404, detail="Bed not found")
    return bed


async def _beam(beam_id: str) -> dict:
    beam = await db.beams.find_one({"id": beam_id}, {"_id": 0})
    if not beam:
        raise HTTPException(status_code=404, detail="Beam not found")
    return beam


async def _spec_for_beam(beam: dict) -> Optional[dict]:
    if beam.get("spec_id"):
        spec = await db.beam_specs.find_one({"id": beam["spec_id"]}, {"_id": 0})
        if spec:
            return spec
    specs = await db.beam_specs.find({"beam_id": beam["id"]}, {"_id": 0}).sort("created_at", -1).to_list(1)
    return specs[0] if specs else None


async def _layout_payload(bed: dict, day: str) -> dict:
    assignments = await db.bed_assignments.find({"bed_id": bed["id"]}, {"_id": 0}).to_list(200)
    on_day = [a for a in assignments if covers(a, day)]
    on_day.sort(key=lambda a: (a.get("position_on_bed") or 0, a.get("station_ft") or 0))
    rows = []
    lengths = []
    for rec in on_day:
        beam = await db.beams.find_one({"id": rec["beam_id"]}, {"_id": 0}) or {}
        spec = await _spec_for_beam(beam) if beam else None
        if not spec and beam:
            spec = fallback_spec(beam)
        length = float((spec or {}).get("geometry", {}).get("length_ft") or beam.get("length_ft") or 0)
        lengths.append(length)
        job_id = rec.get("job_id") or beam.get("job_id")
        pour_id = rec.get("pour_id") or beam.get("pour_id")
        job = await db.jobs.find_one({"id": job_id}, {"_id": 0}) if job_id else None
        pour = await db.pours.find_one({"id": pour_id}, {"_id": 0}) if pour_id else None
        rows.append({
            **rec,
            "beam": beam,
            "spec": spec,
            "length_ft": length,
            "job_number": (job or {}).get("job_number"),
            "pour_number": (pour or {}).get("pour_number"),
        })
    try:
        stations = pack_stations(bed.get("length_ft") or 300, lengths) if lengths else []
    except ValueError:
        stations = [r.get("station_ft") or 0 for r in rows]
    for i, row in enumerate(rows):
        start = stations[i] if i < len(stations) else row.get("station_ft") or 0
        row["station_ft"] = start
        row["end_station_ft"] = round(start + row["length_ft"], 3)
        row["gap_after_ft"] = GAP_FT if i < len(rows) - 1 else 0
        row["position_on_bed"] = i + 1
    return {
        "bed": bed,
        "date": day,
        "header_setback_ft": HEADER_SETBACK_FT,
        "gap_ft": GAP_FT,
        "remaining_ft": remaining_ft(bed.get("length_ft") or 300, lengths),
        "over_typical": len(rows) > MAX_BEAMS_TYPICAL,
        "assignments": rows,
        "active_beam_id": bed.get("active_beam_id"),
    }


async def _repack_bed_day(bed_id: str, day: str) -> None:
    bed = await _bed(bed_id)
    payload = await _layout_payload(bed, day)
    for rec in payload["assignments"]:
        await db.bed_assignments.update_one({"id": rec["id"]}, {"$set": {
            "station_ft": rec["station_ft"],
            "position_on_bed": rec["position_on_bed"],
            "updated_at": now_iso(),
        }})
        await db.beams.update_one({"id": rec["beam_id"]}, {"$set": {
            "bed_id": bed_id,
            "position_on_bed": rec["position_on_bed"],
        }})


@router.get("/beds/{bed_id}/layout")
async def get_layout(bed_id: str, date: Optional[str] = None, user=Depends(get_current_user)):
    try:
        bed = await _bed(bed_id)
        day = parse_day(date) if date else datetime.now(timezone.utc).date().isoformat()
        return await _layout_payload(bed, day)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("get_layout failed bed=%s", bed_id)
        raise HTTPException(status_code=500, detail="Failed to load bed layout")


@router.get("/beds/plant-layout")
async def plant_layout(date: Optional[str] = None, user=Depends(get_current_user)):
    try:
        day = parse_day(date) if date else datetime.now(timezone.utc).date().isoformat()
        beds = await db.beds.find({}, {"_id": 0}).sort("bed_number", 1).to_list(20)
        layouts = []
        for bed in beds:
            layouts.append(await _layout_payload(bed, day))
        return {"date": day, "beds": layouts}
    except Exception:
        logger.exception("plant_layout failed")
        raise HTTPException(status_code=500, detail="Failed to load plant bed twins")


@router.get("/beds/calendar")
async def bed_calendar(start: Optional[str] = None, days: int = 7, user=Depends(get_current_user)):
    try:
        start_day = parse_day(start) if start else datetime.now(timezone.utc).date().isoformat()
        start_dt = datetime.fromisoformat(start_day)
        span = max(1, min(int(days or 7), 21))
        dates = [(start_dt + timedelta(days=i)).date().isoformat() for i in range(span)]
        beds = await db.beds.find({}, {"_id": 0}).sort("bed_number", 1).to_list(20)
        assignments = await db.bed_assignments.find({}, {"_id": 0}).to_list(2000)
        beams = {b["id"]: b for b in await db.beams.find({}, {"_id": 0}).to_list(2000)}
        cells = []
        for bed in beds:
            for day in dates:
                on = [a for a in assignments if a.get("bed_id") == bed["id"] and covers(a, day)]
                on.sort(key=lambda a: a.get("position_on_bed") or 0)
                cells.append({
                    "bed_id": bed["id"],
                    "bed_number": bed["bed_number"],
                    "date": day,
                    "count": len(on),
                    "marks": [beams.get(a["beam_id"], {}).get("mark", "?") for a in on],
                    "statuses": [a.get("production_status") for a in on],
                    "assignment_ids": [a["id"] for a in on],
                })
        return {"start": start_day, "dates": dates, "beds": beds, "cells": cells}
    except Exception:
        logger.exception("bed_calendar failed")
        raise HTTPException(status_code=500, detail="Failed to load bed calendar")


@router.get("/planner/pool")
async def planner_pool(date: Optional[str] = None, job_id: Optional[str] = None, user=Depends(get_current_user)):
    try:
        day = parse_day(date) if date else datetime.now(timezone.utc).date().isoformat()
        jobs = await db.jobs.find({"id": job_id} if job_id else {}, {"_id": 0}).to_list(200)
        pours = {p["id"]: p for p in await db.pours.find({}, {"_id": 0}).to_list(500)}
        assignments = await db.bed_assignments.find({}, {"_id": 0}).to_list(2000)
        beds = {b["id"]: b for b in await db.beds.find({}, {"_id": 0}).to_list(50)}
        beams = await db.beams.find({"job_id": job_id} if job_id else {}, {"_id": 0}).to_list(2000)
        rows = []
        for beam in beams:
            hits = [a for a in assignments if a.get("beam_id") == beam["id"] and covers(a, day)]
            rec = hits[0] if hits else None
            bed = beds.get((rec or {}).get("bed_id") or beam.get("bed_id") or "")
            pour = pours.get(beam.get("pour_id") or "")
            rows.append({
                **beam,
                "assigned": bool(rec),
                "assignment_id": (rec or {}).get("id"),
                "bed_id": (rec or {}).get("bed_id") or beam.get("bed_id"),
                "bed_number": (bed or {}).get("bed_number"),
                "position_on_bed": (rec or {}).get("position_on_bed") or beam.get("position_on_bed"),
                "production_status": (rec or {}).get("production_status") or beam.get("production_status") or "planned",
                "pour_number": (pour or {}).get("pour_number"),
            })
        return {"date": day, "jobs": jobs, "beams": rows}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("planner_pool failed")
        raise HTTPException(status_code=500, detail="Failed to load planner beam pool")


@router.get("/bed-assignments")
async def list_assignments(bed_id: Optional[str] = None, beam_id: Optional[str] = None, user=Depends(get_current_user)):
    try:
        q = {}
        if bed_id:
            q["bed_id"] = bed_id
        if beam_id:
            q["beam_id"] = beam_id
        return await db.bed_assignments.find(q, {"_id": 0}).sort("scheduled_date", 1).to_list(1000)
    except Exception:
        logger.exception("list_assignments failed")
        raise HTTPException(status_code=500, detail="Failed to list bed assignments")


@router.post("/bed-assignments")
async def create_assignment(payload: BedAssignmentCreate, user=Depends(MUTATE)):
    try:
        bed = await _bed(payload.bed_id)
        beam = await _beam(payload.beam_id)
        start = parse_day(payload.scheduled_date)
        end = end_day(start, payload.scheduled_end_date)
        existing = await db.bed_assignments.find({}, {"_id": 0}).to_list(2000)
        _, beam_hits = find_conflicts(
            existing, bed_id=payload.bed_id, beam_id=payload.beam_id, start=start, end=end,
        )
        if beam_hits:
            raise HTTPException(status_code=409, detail="Beam is already assigned to a bed on overlapping dates")
        if payload.marked_end_toward not in ("header", "bulkhead"):
            raise HTTPException(status_code=400, detail="marked_end_toward must be header or bulkhead")
        on_day = [a for a in existing if a.get("bed_id") == payload.bed_id and covers(a, start)]
        on_day.sort(key=lambda a: a.get("position_on_bed") or 0)
        position = payload.position_on_bed or (len(on_day) + 1)
        if any(a.get("position_on_bed") == position for a in on_day):
            position = len(on_day) + 1
        lengths = []
        for rec in on_day:
            other = await _beam(rec["beam_id"])
            lengths.append(float(other.get("length_ft") or 0))
        lengths.insert(max(position - 1, 0), float(beam.get("length_ft") or 0))
        stations = pack_stations(bed.get("length_ft") or 300, lengths)
        station = stations[min(max(position - 1, 0), len(stations) - 1)]
        rec = BedAssignment(
            bed_id=payload.bed_id,
            beam_id=payload.beam_id,
            job_id=payload.job_id or beam.get("job_id"),
            pour_id=payload.pour_id or beam.get("pour_id"),
            position_on_bed=position,
            station_ft=station,
            marked_end_toward=payload.marked_end_toward or "header",
            scheduled_date=start,
            scheduled_end_date=end,
            production_status=payload.production_status or map_production_status(beam.get("status"), beam.get("qc_state")),
            notes=payload.notes or "",
            created_by=user.get("name") or "",
        )
        dumped = rec.model_dump()
        await db.bed_assignments.insert_one(dumped)
        await db.beams.update_one({"id": beam["id"]}, {"$set": {
            "bed_id": payload.bed_id,
            "position_on_bed": position,
            "production_status": rec.production_status,
            "job_id": rec.job_id,
            "pour_id": rec.pour_id,
        }})
        await db.beds.update_one({"id": payload.bed_id}, {"$set": {
            "current_pour_id": rec.pour_id,
            "updated_at": now_iso(),
            "status": "setup" if bed.get("status") == "idle" else bed.get("status"),
        }})
        await _repack_bed_day(payload.bed_id, start)
        logger.info("bed assignment created id=%s bed=%s beam=%s by=%s", rec.id, payload.bed_id, payload.beam_id, user.get("email"))
        return await db.bed_assignments.find_one({"id": rec.id}, {"_id": 0})
    except HTTPException:
        raise
    except ValueError as exc:
        logger.warning("bed assignment rejected: %s", exc)
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception:
        logger.exception("create_assignment failed")
        raise HTTPException(status_code=500, detail="Failed to assign beam to bed")


@router.patch("/bed-assignments/{assignment_id}")
async def update_assignment(assignment_id: str, payload: BedAssignmentUpdate, user=Depends(MUTATE)):
    try:
        rec = await db.bed_assignments.find_one({"id": assignment_id}, {"_id": 0})
        if not rec:
            raise HTTPException(status_code=404, detail="Assignment not found")
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        if "scheduled_date" in updates:
            updates["scheduled_date"] = parse_day(updates["scheduled_date"])
        if "scheduled_end_date" in updates:
            updates["scheduled_end_date"] = parse_day(updates["scheduled_end_date"])
        start = updates.get("scheduled_date") or rec["scheduled_date"]
        end = updates.get("scheduled_end_date") or rec.get("scheduled_end_date") or start
        bed_id = updates.get("bed_id") or rec["bed_id"]
        existing = await db.bed_assignments.find({}, {"_id": 0}).to_list(2000)
        _, beam_hits = find_conflicts(
            existing, bed_id=bed_id, beam_id=rec["beam_id"], start=start, end=end, ignore_id=assignment_id,
        )
        if beam_hits:
            raise HTTPException(status_code=409, detail="Beam is already assigned on overlapping dates")
        if updates.get("production_status") == "stressed":
            from strand_roll_routes import assert_tension_allowed
            beam_doc = await db.beams.find_one({"id": rec["beam_id"]}, {"_id": 0}) or {}
            await assert_tension_allowed(bed_id, rec.get("pour_id") or beam_doc.get("pour_id"))
        updates["updated_at"] = now_iso()
        await db.bed_assignments.update_one({"id": assignment_id}, {"$set": updates})
        if updates.get("production_status"):
            await db.beams.update_one({"id": rec["beam_id"]}, {"$set": {"production_status": updates["production_status"]}})
        await _repack_bed_day(bed_id, start)
        if rec.get("bed_id") and rec["bed_id"] != bed_id:
            await _repack_bed_day(rec["bed_id"], rec.get("scheduled_date") or start)
        logger.info("bed assignment updated id=%s by=%s", assignment_id, user.get("email"))
        return await db.bed_assignments.find_one({"id": assignment_id}, {"_id": 0})
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception:
        logger.exception("update_assignment failed id=%s", assignment_id)
        raise HTTPException(status_code=500, detail="Failed to update assignment")


@router.delete("/bed-assignments/{assignment_id}")
async def delete_assignment(assignment_id: str, user=Depends(MUTATE)):
    try:
        rec = await db.bed_assignments.find_one({"id": assignment_id}, {"_id": 0})
        if not rec:
            raise HTTPException(status_code=404, detail="Assignment not found")
        await db.bed_assignments.delete_one({"id": assignment_id})
        leftover = await db.bed_assignments.find({"beam_id": rec["beam_id"]}, {"_id": 0}).to_list(20)
        if leftover:
            leftover.sort(key=lambda a: a.get("scheduled_date") or "")
            latest = leftover[-1]
            await db.beams.update_one({"id": rec["beam_id"]}, {"$set": {
                "bed_id": latest.get("bed_id") or "",
                "position_on_bed": latest.get("position_on_bed") or 0,
            }})
        else:
            await db.beams.update_one({"id": rec["beam_id"]}, {"$set": {"bed_id": "", "position_on_bed": 0}})
        await _repack_bed_day(rec["bed_id"], rec["scheduled_date"])
        logger.info("bed assignment deleted id=%s by=%s", assignment_id, user.get("email"))
        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        logger.exception("delete_assignment failed id=%s", assignment_id)
        raise HTTPException(status_code=500, detail="Failed to remove assignment")


@router.post("/beds/{bed_id}/reorder")
async def reorder_bed(bed_id: str, payload: BedReorder, user=Depends(MUTATE)):
    try:
        await _bed(bed_id)
        day = parse_day(payload.date)
        for index, assignment_id in enumerate(payload.assignment_ids, start=1):
            rec = await db.bed_assignments.find_one({"id": assignment_id}, {"_id": 0})
            if not rec or rec.get("bed_id") != bed_id:
                raise HTTPException(status_code=400, detail="Assignment does not belong to this bed")
            await db.bed_assignments.update_one({"id": assignment_id}, {"$set": {
                "position_on_bed": index,
                "updated_at": now_iso(),
            }})
        await _repack_bed_day(bed_id, day)
        logger.info("bed reordered id=%s n=%s by=%s", bed_id, len(payload.assignment_ids), user.get("email"))
        return await _layout_payload(await _bed(bed_id), day)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception:
        logger.exception("reorder_bed failed id=%s", bed_id)
        raise HTTPException(status_code=500, detail="Failed to reorder bed")


@router.post("/beams/{beam_id}/assign-to-bed")
async def assign_to_bed(
    beam_id: str,
    bed_id: str,
    scheduled_date: Optional[str] = None,
    position_on_bed: Optional[int] = None,
    marked_end_toward: str = "header",
    user=Depends(MUTATE),
):
    payload = BedAssignmentCreate(
        bed_id=bed_id,
        beam_id=beam_id,
        scheduled_date=scheduled_date or datetime.now(timezone.utc).date().isoformat(),
        position_on_bed=position_on_bed,
        marked_end_toward=marked_end_toward,
    )
    return await create_assignment(payload, user)


@router.post("/beds/{bed_id}/active-beam")
async def set_active_beam(bed_id: str, beam_id: Optional[str] = None, user=Depends(MUTATE)):
    try:
        bed = await _bed(bed_id)
        if beam_id:
            await _beam(beam_id)
        await db.beds.update_one({"id": bed_id}, {"$set": {"active_beam_id": beam_id, "updated_at": now_iso()}})
        logger.info("active beam set bed=%s beam=%s by=%s", bed_id, beam_id, user.get("email"))
        return {**bed, "active_beam_id": beam_id}
    except HTTPException:
        raise
    except Exception:
        logger.exception("set_active_beam failed")
        raise HTTPException(status_code=500, detail="Failed to set active beam")
