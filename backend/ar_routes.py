"""AR level measurements, device registration, and real-time sync feed."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
from ar_math import derive_metrics
from db import db
from models import (
    ARMeasurement, ARMeasurementCreate, DeviceRegistration, DeviceRegistrationCreate,
    LEVEL_TOLERANCE_IN, new_id, now_iso,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["ar-sync"])
MAX_PHOTO_CHARS = 400_000


async def emit_sync_event(event_type: str, title: str, user: dict, **extra):
    rec = {
        "id": new_id(),
        "type": event_type,
        "title": title,
        "created_by": (user or {}).get("name") or "",
        "created_at": now_iso(),
        **extra,
    }
    await db.sync_events.insert_one(rec)
    return rec


@router.post("/ar-measurements")
async def create_ar_measurement(payload: ARMeasurementCreate, user=Depends(get_current_user)):
    try:
        if payload.photo_data and len(payload.photo_data) > MAX_PHOTO_CHARS:
            raise HTTPException(status_code=400, detail="Photo is too large")
        if payload.beam_id:
            beam = await db.beams.find_one({"id": payload.beam_id}, {"_id": 0})
            if not beam:
                raise HTTPException(status_code=404, detail="Beam not found")
        dist, delta, level = derive_metrics(payload.point_a, payload.point_b)
        rec = ARMeasurement(
            beam_id=payload.beam_id,
            bed_id=payload.bed_id,
            purpose=payload.purpose or "level",
            point_a=payload.point_a,
            point_b=payload.point_b,
            distance_ft=payload.distance_ft if payload.distance_ft is not None else dist,
            delta_height_in=payload.delta_height_in if payload.delta_height_in is not None else delta,
            level=payload.level if payload.level is not None else level,
            forced=bool(payload.forced),
            confidence=max(0.0, min(1.0, float(payload.confidence or 0))),
            sample_count=int(payload.sample_count or 12),
            lidar=bool(payload.lidar),
            engine=payload.engine or "web",
            device_class=payload.device_class or "field",
            device_model=(payload.device_model or "")[:80],
            warning=payload.warning or ("Force-snapped off-level" if payload.forced and not level else ""),
            note=(payload.note or "")[:2000],
            photo_data=payload.photo_data or "",
            element_id=payload.element_id,
            created_by=user.get("name") or "",
        )
        dumped = rec.model_dump()
        await db.ar_measurements.insert_one(dumped)
        if rec.element_id and rec.beam_id:
            beam = await db.beams.find_one({"id": rec.beam_id}, {"_id": 0}) or {}
            spec_id = beam.get("spec_id")
            if spec_id:
                await db.spec_measurements.insert_one({
                    "id": new_id(),
                    "spec_id": spec_id,
                    "beam_id": rec.beam_id,
                    "element_id": rec.element_id,
                    "element_kind": "ar_level",
                    "element_name": "AR level",
                    "design_station_ft": rec.distance_ft,
                    "measured_station_ft": rec.distance_ft,
                    "delta_in": abs(rec.delta_height_in),
                    "tolerance_in": LEVEL_TOLERANCE_IN,
                    "within_tolerance": rec.level,
                    "inspector": rec.created_by,
                    "notes": rec.note or rec.warning,
                    "created_at": rec.created_at,
                })
        await emit_sync_event(
            "ar_measurement",
            f"AR {rec.purpose} · {rec.distance_ft} ft · {'LEVEL' if rec.level else 'OFF LEVEL'}",
            user,
            beam_id=rec.beam_id,
            bed_id=rec.bed_id,
            measurement_id=rec.id,
            level=rec.level,
            forced=rec.forced,
        )
        logger.info(
            "ar measurement saved id=%s beam=%s level=%s engine=%s by=%s",
            rec.id, rec.beam_id, rec.level, rec.engine, user.get("email"),
        )
        safe = {k: v for k, v in dumped.items() if k != "photo_data"}
        return safe
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_ar_measurement failed")
        raise HTTPException(status_code=500, detail="Failed to save AR measurement")


@router.get("/ar-measurements")
async def list_ar_measurements(
    beam_id: Optional[str] = None,
    bed_id: Optional[str] = None,
    since: Optional[str] = None,
    user=Depends(get_current_user),
):
    try:
        q = {}
        if beam_id:
            q["beam_id"] = beam_id
        if bed_id:
            q["bed_id"] = bed_id
        if since:
            q["created_at"] = {"$gt": since}
        rows = await db.ar_measurements.find(q, {"_id": 0, "photo_data": 0}).sort("created_at", -1).to_list(200)
        return rows
    except Exception:
        logger.exception("list_ar_measurements failed")
        raise HTTPException(status_code=500, detail="Failed to list AR measurements")


@router.get("/sync/feed")
async def sync_feed(since: Optional[str] = None, user=Depends(get_current_user)):
    try:
        q = {"created_at": {"$gt": since}} if since else {}
        events = await db.sync_events.find(q, {"_id": 0}).sort("created_at", -1).to_list(100)
        measurements = await db.ar_measurements.find(q if since else {}, {"_id": 0, "photo_data": 0}).sort("created_at", -1).to_list(40)
        return {
            "server_time": now_iso(),
            "events": list(reversed(events)),
            "ar_measurements": list(reversed(measurements)),
        }
    except Exception:
        logger.exception("sync_feed failed")
        raise HTTPException(status_code=500, detail="Failed to load live sync feed")


@router.post("/devices")
async def register_device(payload: DeviceRegistrationCreate, user=Depends(get_current_user)):
    try:
        rec = DeviceRegistration(
            platform=payload.platform or "web",
            device_class=payload.device_class or "field",
            push_token=(payload.push_token or "")[:200],
            model=(payload.model or "")[:80],
            user_id=user.get("id") or "",
        )
        dumped = rec.model_dump()
        dumped["updated_at"] = now_iso()
        query = {"user_id": rec.user_id, "platform": rec.platform, "device_class": rec.device_class}
        if rec.push_token:
            query = {"push_token": rec.push_token, "user_id": rec.user_id}
        existing = await db.devices.find_one(query, {"_id": 0})
        if existing:
            patch = {k: v for k, v in dumped.items() if k not in ("id", "created_at")}
            await db.devices.update_one({"id": existing["id"]}, {"$set": patch})
            logger.info("device registered platform=%s class=%s by=%s", rec.platform, rec.device_class, user.get("email"))
            return {"ok": True, "id": existing["id"]}
        await db.devices.insert_one(dumped)
        logger.info("device registered platform=%s class=%s by=%s", rec.platform, rec.device_class, user.get("email"))
        return {"ok": True, "id": rec.id}
    except Exception:
        logger.exception("register_device failed")
        raise HTTPException(status_code=500, detail="Failed to register device")
