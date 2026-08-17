"""AR level measurements, digital tape runs vs twin, daily calibration, device registration, and live sync."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from ar_math import (
    CAL_LOCK_HOURS,
    CAL_NO_DEVICE_DETAIL,
    CAL_TOLERANCE_PCT,
    apply_device_scale,
    cal_expires_at,
    cal_lock_status,
    compare_tape_shots,
    derive_metrics,
    design_stations_from_spec,
    evaluate_calibration,
    measure_block,
    public_cal_audit,
    sanitize_engine,
    utc_now,
)
from audit import write_audit
from auth import get_current_user
from db import db
from models import (
    ARMeasurement, ARMeasurementCreate, DeviceRegistration, DeviceRegistrationCreate,
    LEVEL_TOLERANCE_IN, TapeCalibrationCreate, TapeRunCreate, TapeRunPreview, TapeShotIn, new_id, now_iso,
)
from tape_ai import ai_tape_review

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["ar-sync"])
MAX_PHOTO_CHARS = 400_000
MAX_TAPE_SHOTS = 80


def resolve_device_id(payload_id: Optional[str], request: Request) -> str:
    body = str(payload_id or "").strip()[:80]
    header = str(request.headers.get("x-device-id") or "").strip()[:80]
    return body or header


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


async def _spec_for_beam_id(beam_id: Optional[str]):
    if not beam_id:
        return None, None
    beam = await db.beams.find_one({"id": beam_id}, {"_id": 0})
    if not beam:
        return None, None
    spec = None
    if beam.get("spec_id"):
        spec = await db.beam_specs.find_one({"id": beam["spec_id"]}, {"_id": 0})
    if not spec:
        latest = await db.beam_specs.find({"beam_id": beam_id}, {"_id": 0}).sort("created_at", -1).to_list(1)
        spec = latest[0] if latest else None
    return beam, spec


async def _default_length_tol() -> float:
    try:
        doc = await db.company_settings.find_one({"id": "plant"}, {"_id": 0}) or {}
        return float(doc.get("length_tolerance_in") or 0.5)
    except (TypeError, ValueError):
        return 0.5


def _shot_metrics(origin: dict, shot: TapeShotIn, scale_factor: Optional[float] = None):
    point_b = shot.point_b or {"x": 0.0, "y": 0.0, "z": 0.0}
    dist, delta, level = derive_metrics(origin, point_b)
    station = shot.station_ft if shot.station_ft is not None else shot.distance_ft
    if station is None:
        station = dist
    station = apply_device_scale(station, scale_factor)
    return {
        "point_b": point_b,
        "distance_ft": float(station),
        "station_ft": float(station),
        "delta_height_in": float(shot.delta_height_in if shot.delta_height_in is not None else delta),
        "level": bool(shot.level if shot.level is not None else level),
        "forced": bool(shot.forced),
        "confidence": max(0.0, min(1.0, float(shot.confidence or 0))),
        "sample_count": int(shot.sample_count or 12),
        "note": (shot.note or "")[:2000],
        "element_id": None,
        "warning": (shot.warning or "")[:500],
        "station_index": int(shot.station_index or 1),
    }


async def _build_compare(beam_id: Optional[str], shots: list) -> dict:
    _beam, spec = await _spec_for_beam_id(beam_id)
    default_tol = await _default_length_tol()
    if spec and spec.get("tolerances", {}).get("length") is not None:
        try:
            default_tol = float(spec["tolerances"]["length"])
        except (TypeError, ValueError):
            pass
    design = design_stations_from_spec(spec, default_tol)
    compare = compare_tape_shots(shots, design, default_tol)
    review = ai_tape_review(compare)
    compare["ai"] = review
    compare["spec_id"] = (spec or {}).get("id")
    compare["beam_mark"] = (_beam or {}).get("mark")
    compare["default_tolerance_in"] = default_tol
    return compare


async def _write_spec_rows(run_id: str, beam: dict, spec: dict, matches: list, inspector: str):
    if not spec or not beam:
        return
    for row in matches:
        if not row.get("element_id"):
            continue
        await db.spec_measurements.insert_one({
            "id": new_id(),
            "spec_id": spec.get("id"),
            "beam_id": beam.get("id"),
            "element_id": row.get("element_id"),
            "element_kind": row.get("element_kind") or "tape",
            "element_name": row.get("element_name") or "Digital tape",
            "design_station_ft": row.get("design_station_ft"),
            "measured_station_ft": row.get("measured_station_ft"),
            "delta_in": row.get("delta_in"),
            "tolerance_in": row.get("tolerance_in") or LEVEL_TOLERANCE_IN,
            "within_tolerance": bool(row.get("within_tolerance")) and not row.get("rescan"),
            "inspector": inspector,
            "notes": f"tape run {run_id} · {row.get('flag')}",
            "created_at": now_iso(),
        })


async def _latest_passing_cal(device_id: str) -> Optional[dict]:
    rows = await db.tape_calibrations.find(
        {"device_id": device_id, "passed": True},
        {"_id": 0},
    ).sort("calibrated_at", -1).to_list(1)
    return rows[0] if rows else None


async def _require_device_cal(device_id: str) -> dict:
    if not device_id:
        logger.info("tape measure blocked reason=no_device")
        raise HTTPException(status_code=400, detail=CAL_NO_DEVICE_DETAIL)
    rec = await _latest_passing_cal(device_id)
    status = cal_lock_status(rec)
    blocked = measure_block(status)
    if blocked:
        code, detail = blocked
        logger.info("tape measure blocked device=%s reason=%s", device_id, status.get("reason"))
        raise HTTPException(status_code=code, detail=detail)
    return status


def _status_payload(device_id: str, status: dict, honesty: Optional[dict] = None) -> dict:
    out = {
        **status,
        "device_id": device_id or status.get("device_id"),
        "lock_hours": CAL_LOCK_HOURS,
        "tolerance_pct": CAL_TOLERANCE_PCT,
    }
    if honesty:
        out["honesty"] = honesty
    return out


@router.get("/tape-calibration")
async def get_tape_calibration(
    request: Request,
    device_id: Optional[str] = None,
    user=Depends(get_current_user),
):
    try:
        did = resolve_device_id(device_id, request)
        if not did:
            raise HTTPException(status_code=400, detail=CAL_NO_DEVICE_DETAIL)
        rec = await _latest_passing_cal(did)
        status = cal_lock_status(rec)
        honesty = sanitize_engine((rec or {}).get("engine") or "web", bool((rec or {}).get("lidar")))
        logger.info(
            "tape cal status device=%s allowed=%s remaining=%s by=%s",
            did, status.get("allowed"), status.get("remaining_seconds"), user.get("email"),
        )
        return _status_payload(did, status, honesty)
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_tape_calibration failed")
        raise HTTPException(status_code=500, detail="Failed to load tape calibration")


@router.get("/tape-calibration/history")
async def list_tape_calibrations(
    request: Request,
    device_id: Optional[str] = None,
    user=Depends(get_current_user),
):
    try:
        did = resolve_device_id(device_id, request)
        if not did:
            raise HTTPException(status_code=400, detail=CAL_NO_DEVICE_DETAIL)
        rows = await db.tape_calibrations.find(
            {"device_id": did},
            {"_id": 0, "photo_data": 0, "gps": 0, "latitude": 0, "longitude": 0},
        ).sort("calibrated_at", -1).to_list(20)
        return [public_cal_audit(row) for row in rows]
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_tape_calibrations failed")
        raise HTTPException(status_code=500, detail="Failed to list tape calibrations")


@router.post("/tape-calibration")
async def create_tape_calibration(
    payload: TapeCalibrationCreate,
    request: Request,
    user=Depends(get_current_user),
):
    try:
        did = resolve_device_id(payload.device_id, request)
        if not did:
            raise HTTPException(status_code=400, detail=CAL_NO_DEVICE_DETAIL)
        result = evaluate_calibration(payload.known_length_ft, payload.measured_length_ft)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("detail") or "Invalid calibration lengths")
        honesty = sanitize_engine(payload.engine, payload.lidar)
        stamp = utc_now()
        expires = cal_expires_at(stamp) if result["passed"] else None
        rec = {
            "id": new_id(),
            "device_id": did,
            "device_model": (payload.device_model or "")[:80],
            "device_class": (payload.device_class or "field")[:20],
            "known_length_ft": result["known_length_ft"],
            "measured_length_ft": result["measured_length_ft"],
            "scale_factor": result["scale_factor"] if result["passed"] else None,
            "error_pct": result["error_pct"],
            "tolerance_pct": result["tolerance_pct"],
            "passed": bool(result["passed"]),
            "engine": honesty["engine"],
            "lidar": bool(honesty["lidar"]),
            "honesty_label": honesty["honesty_label"],
            "honesty_code": honesty["honesty_code"],
            "note": (payload.note or "")[:500],
            "calibrated_by": (user.get("name") or "")[:80],
            "calibrated_by_email": (user.get("email") or "")[:120],
            "calibrated_by_role": (user.get("role") or "")[:40],
            "calibrated_at": stamp.isoformat(),
            "expires_at": expires.isoformat() if expires else None,
            "lock_hours": CAL_LOCK_HOURS,
        }
        await db.tape_calibrations.insert_one(rec)
        live = await _latest_passing_cal(did)
        status = cal_lock_status(live)
        await write_audit(
            action="tape.calibrate",
            user=user,
            request=request,
            entity_type="tape_calibration",
            entity_id=rec["id"],
            ok=bool(result["passed"]),
            extra={
                "device_id": did,
                "known_length_ft": result["known_length_ft"],
                "measured_length_ft": result["measured_length_ft"],
                "scale_factor": rec["scale_factor"],
                "error_pct": result["error_pct"],
                "passed": bool(result["passed"]),
                "engine": honesty["engine"],
            },
        )
        logger.info(
            "tape cal saved id=%s device=%s passed=%s error_pct=%s engine=%s by=%s",
            rec["id"], did, result["passed"], result["error_pct"], honesty["engine"], user.get("email"),
        )
        return {
            "calibration": public_cal_audit(rec),
            "status": _status_payload(did, status, honesty),
            "passed": bool(result["passed"]),
            "detail": result.get("detail"),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_tape_calibration failed")
        raise HTTPException(status_code=500, detail="Failed to save tape calibration")


@router.post("/ar-measurements")
async def create_ar_measurement(payload: ARMeasurementCreate, request: Request, user=Depends(get_current_user)):
    try:
        did = resolve_device_id(payload.device_id, request)
        cal = await _require_device_cal(did)
        if payload.photo_data and len(payload.photo_data) > MAX_PHOTO_CHARS:
            raise HTTPException(status_code=400, detail="Photo is too large")
        if payload.beam_id:
            beam = await db.beams.find_one({"id": payload.beam_id}, {"_id": 0})
            if not beam:
                raise HTTPException(status_code=404, detail="Beam not found")
        honesty = sanitize_engine(payload.engine, payload.lidar)
        dist, delta, level = derive_metrics(payload.point_a, payload.point_b)
        raw_dist = payload.distance_ft if payload.distance_ft is not None else dist
        scaled = apply_device_scale(raw_dist, cal.get("scale_factor"))
        rec = ARMeasurement(
            beam_id=payload.beam_id,
            bed_id=payload.bed_id,
            purpose=payload.purpose or "level",
            point_a=payload.point_a,
            point_b=payload.point_b,
            distance_ft=scaled,
            delta_height_in=payload.delta_height_in if payload.delta_height_in is not None else delta,
            level=payload.level if payload.level is not None else level,
            forced=bool(payload.forced),
            confidence=max(0.0, min(1.0, float(payload.confidence or 0))),
            sample_count=int(payload.sample_count or 12),
            lidar=bool(honesty["lidar"]),
            engine=honesty["engine"],
            device_class=payload.device_class or "field",
            device_model=(payload.device_model or "")[:80],
            warning=payload.warning or ("Force-snapped off-level" if payload.forced and not level else ""),
            note=(payload.note or "")[:2000],
            photo_data=payload.photo_data or "",
            element_id=payload.element_id,
            run_id=payload.run_id,
            station_index=payload.station_index,
            origin_label=(payload.origin_label or "")[:40],
            device_id=did,
            scale_factor=cal.get("scale_factor"),
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
            "ar measurement saved id=%s beam=%s level=%s engine=%s device=%s by=%s",
            rec.id, rec.beam_id, rec.level, rec.engine, did, user.get("email"),
        )
        safe = {k: v for k, v in dumped.items() if k != "photo_data"}
        safe["honesty_label"] = honesty["honesty_label"]
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


@router.post("/ar-tape-runs/preview")
async def preview_tape_run(payload: TapeRunPreview, user=Depends(get_current_user)):
    try:
        if payload.beam_id:
            beam = await db.beams.find_one({"id": payload.beam_id}, {"_id": 0})
            if not beam:
                raise HTTPException(status_code=404, detail="Beam not found")
        if len(payload.shots or []) > MAX_TAPE_SHOTS:
            raise HTTPException(status_code=400, detail="Too many stations in one run")
        origin = {"x": 0.0, "y": 0.0, "z": 0.0}
        shots = [_shot_metrics(origin, s) for s in (payload.shots or [])]
        compare = await _build_compare(payload.beam_id, shots)
        logger.info(
            "tape preview beam=%s shots=%s rescan=%s by=%s",
            payload.beam_id, len(shots), compare.get("rescan_count"), user.get("email"),
        )
        return compare
    except HTTPException:
        raise
    except Exception:
        logger.exception("preview_tape_run failed")
        raise HTTPException(status_code=500, detail="Failed to compare tape run to twin")


@router.post("/ar-tape-runs")
async def create_tape_run(payload: TapeRunCreate, request: Request, user=Depends(get_current_user)):
    try:
        did = resolve_device_id(payload.device_id, request)
        cal = await _require_device_cal(did)
        if not payload.shots:
            raise HTTPException(status_code=400, detail="Snap at least one station after the origin")
        if len(payload.shots) > MAX_TAPE_SHOTS:
            raise HTTPException(status_code=400, detail="Too many stations in one run")
        beam = None
        if payload.beam_id:
            beam = await db.beams.find_one({"id": payload.beam_id}, {"_id": 0})
            if not beam:
                raise HTTPException(status_code=404, detail="Beam not found")
        honesty = sanitize_engine(payload.engine, payload.lidar)
        origin = payload.point_a or {"x": 0.0, "y": 0.0, "z": 0.0}
        packed = [_shot_metrics(origin, s, cal.get("scale_factor")) for s in payload.shots]
        compare = await _build_compare(payload.beam_id, packed)
        by_index = {m.get("station_index"): m for m in (compare.get("matches") or [])}
        for row in packed:
            hit = by_index.get(row["station_index"])
            if hit and hit.get("element_id"):
                row["element_id"] = hit["element_id"]
        run_id = new_id()
        inspector = user.get("name") or ""
        shot_ids = []
        for row in packed:
            rec = ARMeasurement(
                beam_id=payload.beam_id,
                bed_id=payload.bed_id,
                purpose=payload.purpose or "tape",
                point_a=origin,
                point_b=row["point_b"],
                distance_ft=row["distance_ft"],
                delta_height_in=row["delta_height_in"],
                level=row["level"],
                forced=row["forced"],
                confidence=row["confidence"],
                sample_count=row["sample_count"],
                lidar=bool(honesty["lidar"]),
                engine=honesty["engine"],
                device_class=payload.device_class or "field",
                device_model=(payload.device_model or "")[:80],
                warning=row["warning"] or ("Force-snapped off-level" if row["forced"] and not row["level"] else ""),
                note=row["note"] or (payload.note or "")[:2000],
                element_id=row.get("element_id"),
                run_id=run_id,
                station_index=row["station_index"],
                origin_label=(payload.origin_label or "header")[:40],
                device_id=did,
                scale_factor=cal.get("scale_factor"),
                created_by=inspector,
            )
            dumped = rec.model_dump()
            await db.ar_measurements.insert_one(dumped)
            shot_ids.append(rec.id)
        _beam, spec = await _spec_for_beam_id(payload.beam_id)
        await _write_spec_rows(run_id, _beam or beam or {}, spec or {}, compare.get("matches") or [], inspector)
        run = {
            "id": run_id,
            "beam_id": payload.beam_id,
            "bed_id": payload.bed_id,
            "purpose": payload.purpose or "tape",
            "origin_label": (payload.origin_label or "header")[:40],
            "point_a": origin,
            "shot_ids": shot_ids,
            "shot_count": len(shot_ids),
            "compare": compare,
            "engine": honesty["engine"],
            "honesty_label": honesty["honesty_label"],
            "device_class": payload.device_class or "field",
            "device_model": (payload.device_model or "")[:80],
            "device_id": did,
            "scale_factor": cal.get("scale_factor"),
            "lidar": bool(honesty["lidar"]),
            "note": (payload.note or "")[:2000],
            "created_by": inspector,
            "created_at": now_iso(),
        }
        await db.ar_tape_runs.insert_one(run)
        await emit_sync_event(
            "ar_tape_run",
            f"Digital tape · {len(shot_ids)} pts · {compare.get('rescan_count') or 0} rescan",
            user,
            beam_id=payload.beam_id,
            bed_id=payload.bed_id,
            run_id=run_id,
            rescan_count=compare.get("rescan_count"),
        )
        logger.info(
            "tape run saved id=%s beam=%s shots=%s rescan=%s engine=%s device=%s by=%s",
            run_id, payload.beam_id, len(shot_ids), compare.get("rescan_count"), honesty["engine"], did, user.get("email"),
        )
        return {k: v for k, v in run.items() if k != "_id"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_tape_run failed")
        raise HTTPException(status_code=500, detail="Failed to save digital tape run")


@router.get("/ar-tape-runs")
async def list_tape_runs(beam_id: Optional[str] = None, user=Depends(get_current_user)):
    try:
        q = {"beam_id": beam_id} if beam_id else {}
        rows = await db.ar_tape_runs.find(q, {"_id": 0}).sort("created_at", -1).to_list(50)
        return rows
    except Exception:
        logger.exception("list_tape_runs failed")
        raise HTTPException(status_code=500, detail="Failed to list tape runs")


@router.get("/ar-tape-runs/{run_id}")
async def get_tape_run(run_id: str, user=Depends(get_current_user)):
    try:
        rec = await db.ar_tape_runs.find_one({"id": run_id}, {"_id": 0})
        if not rec:
            raise HTTPException(status_code=404, detail="Tape run not found")
        shots = await db.ar_measurements.find({"run_id": run_id}, {"_id": 0, "photo_data": 0}).sort("station_index", 1).to_list(MAX_TAPE_SHOTS)
        rec["shots"] = shots
        return rec
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_tape_run failed id=%s", run_id)
        raise HTTPException(status_code=500, detail="Failed to load tape run")


@router.post("/ar-tape-runs/{run_id}/compare")
async def recompare_tape_run(run_id: str, user=Depends(get_current_user)):
    try:
        rec = await db.ar_tape_runs.find_one({"id": run_id}, {"_id": 0})
        if not rec:
            raise HTTPException(status_code=404, detail="Tape run not found")
        shots = await db.ar_measurements.find({"run_id": run_id}, {"_id": 0, "photo_data": 0}).sort("station_index", 1).to_list(MAX_TAPE_SHOTS)
        packed = [{
            "station_index": s.get("station_index"),
            "station_ft": s.get("distance_ft"),
            "distance_ft": s.get("distance_ft"),
            "delta_height_in": s.get("delta_height_in"),
            "level": s.get("level"),
            "forced": s.get("forced"),
        } for s in shots]
        compare = await _build_compare(rec.get("beam_id"), packed)
        await db.ar_tape_runs.update_one({"id": run_id}, {"$set": {"compare": compare}})
        logger.info("tape recompare id=%s rescan=%s by=%s", run_id, compare.get("rescan_count"), user.get("email"))
        return compare
    except HTTPException:
        raise
    except Exception:
        logger.exception("recompare_tape_run failed id=%s", run_id)
        raise HTTPException(status_code=500, detail="Failed to recompare tape run")


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
