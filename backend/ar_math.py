"""Pure AR level math, digital-tape vs twin matching, and daily calibration — no I/O, no Mongo."""
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from models import LEVEL_TOLERANCE_IN

STATION_MATCH_WINDOW_FT = 3.0
DEFAULT_STATION_TOLERANCE_IN = 0.5


def meters_to_in(m: float) -> float:
    return float(m) * 39.37007874


def meters_to_ft(m: float) -> float:
    return float(m) * 3.280839895


def evaluate_level(delta_height_in: float, tolerance_in: float = LEVEL_TOLERANCE_IN) -> bool:
    return abs(float(delta_height_in)) <= float(tolerance_in)


def derive_metrics(point_a: dict, point_b: dict):
    ax, ay, az = float(point_a.get("x") or 0), float(point_a.get("y") or 0), float(point_a.get("z") or 0)
    bx, by, bz = float(point_b.get("x") or 0), float(point_b.get("y") or 0), float(point_b.get("z") or 0)
    dist_m = math.sqrt((bx - ax) ** 2 + (by - ay) ** 2 + (bz - az) ** 2)
    delta_in = meters_to_in(by - ay)
    return round(meters_to_ft(dist_m), 4), round(delta_in, 3), evaluate_level(delta_in)


def design_stations_from_spec(spec: Optional[dict], default_tol_in: float = DEFAULT_STATION_TOLERANCE_IN) -> List[Dict[str, Any]]:
    """Hardware + hold-downs as stations from the marked end (blueprint / twin)."""
    if not spec:
        return []
    tols = spec.get("tolerances") or {}
    out: List[Dict[str, Any]] = []
    for item in spec.get("hardware") or []:
        pos = item.get("position") or {}
        kind = item.get("kind") or "insert"
        try:
            tol = float(item.get("tolerance_in") or tols.get(kind) or default_tol_in)
        except (TypeError, ValueError):
            tol = float(default_tol_in)
        try:
            station = float(pos.get("station_ft") or 0)
        except (TypeError, ValueError):
            station = 0.0
        out.append({
            "id": item.get("id") or "",
            "name": item.get("name") or kind,
            "kind": kind,
            "station_ft": station,
            "tolerance_in": tol,
            "source": "hardware",
        })
    for item in spec.get("hold_downs") or []:
        try:
            station = float(item.get("station_from_marked_end") or 0)
        except (TypeError, ValueError):
            station = 0.0
        try:
            tol = float(tols.get("hold_down") or 1.0)
        except (TypeError, ValueError):
            tol = 1.0
        out.append({
            "id": item.get("id") or "",
            "name": item.get("type_spec") or "Hold-down",
            "kind": "hold_down",
            "station_ft": station,
            "tolerance_in": tol,
            "source": "hold_down",
        })
    return [row for row in out if row.get("id")]


def _nearest_unused(station_ft: float, design_points: Iterable[dict], used_ids: set) -> Optional[dict]:
    best = None
    best_delta = None
    for el in design_points:
        eid = el.get("id")
        if not eid or eid in used_ids:
            continue
        try:
            design_ft = float(el.get("station_ft") or 0)
        except (TypeError, ValueError):
            continue
        delta = abs(float(station_ft) - design_ft)
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best = el
    if best is None or best_delta is None or best_delta > STATION_MATCH_WINDOW_FT:
        return None
    return {**best, "_delta_ft": best_delta}


def compare_tape_shots(
    shots: List[dict],
    design_points: List[dict],
    default_tol_in: float = DEFAULT_STATION_TOLERANCE_IN,
) -> dict:
    """Match each measured station (feet from origin/header) to the nearest unused design point.

    Rescan when the station is outside that element's tolerance, the shot was off-level,
    or it was force-snapped. Extra shots with no twin match are warnings, not auto-rescan.
    """
    used = set()
    matches = []
    ordered = sorted(
        list(shots or []),
        key=lambda s: (float(s.get("station_ft") or s.get("distance_ft") or 0), int(s.get("station_index") or 0)),
    )
    for shot in ordered:
        try:
            station = float(shot.get("station_ft") if shot.get("station_ft") is not None else shot.get("distance_ft") or 0)
        except (TypeError, ValueError):
            station = 0.0
        level = bool(shot.get("level"))
        forced = bool(shot.get("forced"))
        try:
            delta_height = float(shot.get("delta_height_in") or 0)
        except (TypeError, ValueError):
            delta_height = 0.0
        hit = _nearest_unused(station, design_points, used)
        reasons = []
        if not level:
            reasons.append("off_level")
        if forced:
            reasons.append("forced_snap")
        if hit:
            used.add(hit["id"])
            delta_in = round(float(hit["_delta_ft"]) * 12.0, 3)
            try:
                tol = float(hit.get("tolerance_in") or default_tol_in)
            except (TypeError, ValueError):
                tol = float(default_tol_in)
            within = delta_in <= tol
            if not within:
                reasons.append("station_out_of_tolerance")
            rescan = bool(reasons)
            matches.append({
                "station_index": shot.get("station_index"),
                "measured_station_ft": round(station, 4),
                "delta_height_in": round(delta_height, 3),
                "level": level,
                "forced": forced,
                "element_id": hit.get("id"),
                "element_name": hit.get("name"),
                "element_kind": hit.get("kind"),
                "design_station_ft": round(float(hit.get("station_ft") or 0), 4),
                "delta_in": delta_in,
                "tolerance_in": tol,
                "within_tolerance": within,
                "matched": True,
                "rescan": rescan,
                "flag": reasons[0] if reasons else "pass",
                "reasons": reasons,
            })
        else:
            reasons.append("no_spec_match")
            matches.append({
                "station_index": shot.get("station_index"),
                "measured_station_ft": round(station, 4),
                "delta_height_in": round(delta_height, 3),
                "level": level,
                "forced": forced,
                "element_id": None,
                "element_name": None,
                "element_kind": None,
                "design_station_ft": None,
                "delta_in": None,
                "tolerance_in": float(default_tol_in),
                "within_tolerance": None,
                "matched": False,
                "rescan": (not level) or forced,
                "flag": "no_spec_match",
                "reasons": reasons,
            })

    unshot = []
    for el in design_points or []:
        if el.get("id") in used:
            continue
        unshot.append({
            "id": el.get("id"),
            "name": el.get("name"),
            "kind": el.get("kind"),
            "station_ft": round(float(el.get("station_ft") or 0), 4),
            "tolerance_in": float(el.get("tolerance_in") or default_tol_in),
        })

    rescan_rows = [m for m in matches if m.get("rescan")]
    pass_rows = [m for m in matches if m.get("matched") and not m.get("rescan")]
    return {
        "matches": matches,
        "unshot": unshot,
        "shot_count": len(matches),
        "design_count": len(design_points or []),
        "pass_count": len(pass_rows),
        "rescan_count": len(rescan_rows),
        "unmatched_count": sum(1 for m in matches if not m.get("matched")),
        "unshot_count": len(unshot),
        "needs_rescan": [m for m in rescan_rows],
    }


CAL_TOLERANCE_PCT = 0.15
CAL_LOCK_HOURS = 24
CAL_EXPIRED_DETAIL = "Daily calibration expired — recalibrate this device before measuring"
CAL_MISSING_DETAIL = "Calibrate this device against a known length before measuring (±0.15%, 24-hour lock)."
CAL_FAILED_DETAIL = "Last calibration failed ±0.15% — this device is not unlocked."
CAL_NO_DEVICE_DETAIL = "Device id is required. Scale and calibration lock are per phone, not plant-wide."
WEB_ENGINES = frozenset({"web", "gravity", "camera", "photo", "browser"})
NATIVE_ENGINES = frozenset({"arkit", "arkit-lidar"})
WEB_HONESTY_LABEL = "Camera / gravity tape — not ARKit, not LiDAR"
ARKIT_HONESTY_LABEL = "ARKit world tracking (no LiDAR)"
ARKIT_LIDAR_HONESTY_LABEL = "ARKit with LiDAR"


def parse_iso(stamp: Optional[str]) -> Optional[datetime]:
    if not stamp:
        return None
    text = str(stamp).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sanitize_engine(engine: Optional[str], lidar: bool = False) -> dict:
    """Web browsers never get an ARKit/LiDAR honesty label, even if the client claims lidar."""
    raw = str(engine or "web").strip().lower() or "web"
    if raw in NATIVE_ENGINES:
        use_lidar = bool(lidar) or raw == "arkit-lidar"
        code = "arkit-lidar" if use_lidar else "arkit"
        return {
            "engine": code,
            "lidar": use_lidar,
            "is_native": True,
            "honesty_code": "arkit_lidar" if use_lidar else "arkit",
            "honesty_label": ARKIT_LIDAR_HONESTY_LABEL if use_lidar else ARKIT_HONESTY_LABEL,
        }
    web_engine = raw if raw in WEB_ENGINES else "web"
    if web_engine == "browser":
        web_engine = "web"
    return {
        "engine": web_engine,
        "lidar": False,
        "is_native": False,
        "honesty_code": "web_camera",
        "honesty_label": WEB_HONESTY_LABEL,
    }


def evaluate_calibration(
    known_length_ft: Any,
    measured_length_ft: Any,
    tolerance_pct: float = CAL_TOLERANCE_PCT,
) -> dict:
    """Pass only when |measured - known| / known * 100 <= ±0.15%. Failed cals do not unlock."""
    try:
        known = float(known_length_ft)
        measured = float(measured_length_ft)
        tol = float(tolerance_pct)
    except (TypeError, ValueError):
        return {
            "ok": False,
            "passed": False,
            "known_length_ft": None,
            "measured_length_ft": None,
            "error_pct": None,
            "scale_factor": None,
            "tolerance_pct": CAL_TOLERANCE_PCT,
            "detail": "Known and measured lengths must be numbers",
        }
    if known <= 0 or measured <= 0:
        return {
            "ok": False,
            "passed": False,
            "known_length_ft": known,
            "measured_length_ft": measured,
            "error_pct": None,
            "scale_factor": None,
            "tolerance_pct": tol,
            "detail": "Known and measured lengths must be greater than zero",
        }
    error_pct = round(abs(measured - known) / known * 100.0, 6)
    passed = error_pct <= tol
    return {
        "ok": True,
        "passed": passed,
        "known_length_ft": round(known, 6),
        "measured_length_ft": round(measured, 6),
        "error_pct": error_pct,
        "scale_factor": round(known / measured, 8),
        "tolerance_pct": tol,
        "detail": None if passed else f"Calibration failed — {error_pct:.4f}% error exceeds ±{tol}%",
    }


def cal_expires_at(calibrated_at: Optional[datetime] = None, lock_hours: int = CAL_LOCK_HOURS) -> datetime:
    start = calibrated_at or utc_now()
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return start + timedelta(hours=int(lock_hours))


def cal_lock_status(cal_record: Optional[dict], now: Optional[datetime] = None) -> dict:
    """Server-side 24h lock. Only a passing cal on this device unlocks measuring."""
    stamp = now or utc_now()
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    blocked = {
        "allowed": False,
        "http_code": 409,
        "reason": "missing",
        "detail": CAL_MISSING_DETAIL,
        "remaining_seconds": 0,
        "scale_factor": None,
        "expires_at": None,
        "calibrated_at": None,
        "passed": False,
        "device_id": None,
        "calibrated_by": None,
        "known_length_ft": None,
        "measured_length_ft": None,
        "error_pct": None,
        "engine": None,
        "lock_hours": CAL_LOCK_HOURS,
        "tolerance_pct": CAL_TOLERANCE_PCT,
    }
    if not cal_record:
        return blocked
    blocked["device_id"] = cal_record.get("device_id")
    blocked["calibrated_at"] = cal_record.get("calibrated_at")
    blocked["calibrated_by"] = cal_record.get("calibrated_by")
    blocked["known_length_ft"] = cal_record.get("known_length_ft")
    blocked["measured_length_ft"] = cal_record.get("measured_length_ft")
    blocked["error_pct"] = cal_record.get("error_pct")
    blocked["engine"] = cal_record.get("engine")
    blocked["scale_factor"] = cal_record.get("scale_factor")
    if not cal_record.get("passed"):
        blocked["reason"] = "failed"
        blocked["detail"] = CAL_FAILED_DETAIL
        return blocked
    exp = parse_iso(cal_record.get("expires_at") or "")
    cal_at = parse_iso(cal_record.get("calibrated_at") or "")
    if exp is None and cal_at is not None:
        exp = cal_expires_at(cal_at)
    if exp is None:
        return blocked
    remaining = int((exp - stamp).total_seconds())
    if remaining <= 0:
        blocked["reason"] = "expired"
        blocked["detail"] = CAL_EXPIRED_DETAIL
        blocked["expires_at"] = exp.isoformat()
        blocked["passed"] = True
        return blocked
    return {
        "allowed": True,
        "http_code": 200,
        "reason": "ok",
        "detail": None,
        "remaining_seconds": remaining,
        "scale_factor": float(cal_record.get("scale_factor") or 1.0),
        "expires_at": exp.isoformat(),
        "calibrated_at": cal_record.get("calibrated_at"),
        "passed": True,
        "device_id": cal_record.get("device_id"),
        "calibrated_by": cal_record.get("calibrated_by"),
        "known_length_ft": cal_record.get("known_length_ft"),
        "measured_length_ft": cal_record.get("measured_length_ft"),
        "error_pct": cal_record.get("error_pct"),
        "engine": cal_record.get("engine"),
        "lock_hours": CAL_LOCK_HOURS,
        "tolerance_pct": CAL_TOLERANCE_PCT,
    }


def measure_block(status: Optional[dict]) -> Optional[Tuple[int, str]]:
    """None when measuring is allowed; otherwise (http_code, detail) for a 409 gate."""
    rec = status or cal_lock_status(None)
    if rec.get("allowed"):
        return None
    return (int(rec.get("http_code") or 409), str(rec.get("detail") or CAL_MISSING_DETAIL))


def scale_for_device(cal_record: Optional[dict], device_id: str, now: Optional[datetime] = None) -> Optional[float]:
    """Return this device's live scale only. Never fall back to another phone's factor."""
    if not device_id or not cal_record:
        return None
    if str(cal_record.get("device_id") or "") != str(device_id):
        return None
    status = cal_lock_status(cal_record, now=now)
    if not status.get("allowed"):
        return None
    try:
        factor = float(status.get("scale_factor") or 1.0)
    except (TypeError, ValueError):
        return None
    if factor <= 0:
        return None
    return factor


def apply_device_scale(distance_ft: Any, scale_factor: Optional[float]) -> float:
    try:
        dist = float(distance_ft or 0)
    except (TypeError, ValueError):
        dist = 0.0
    try:
        factor = float(scale_factor) if scale_factor is not None else 1.0
    except (TypeError, ValueError):
        factor = 1.0
    if factor <= 0:
        factor = 1.0
    return round(dist * factor, 4)


def public_cal_audit(cal_record: Optional[dict]) -> dict:
    """Who / when / device / lengths / scale / pass — never photo bytes or GPS."""
    rec = cal_record or {}
    return {
        "id": rec.get("id"),
        "device_id": rec.get("device_id"),
        "device_model": rec.get("device_model") or "",
        "device_class": rec.get("device_class") or "",
        "known_length_ft": rec.get("known_length_ft"),
        "measured_length_ft": rec.get("measured_length_ft"),
        "scale_factor": rec.get("scale_factor"),
        "error_pct": rec.get("error_pct"),
        "passed": bool(rec.get("passed")),
        "engine": rec.get("engine"),
        "honesty_label": rec.get("honesty_label") or "",
        "calibrated_by": rec.get("calibrated_by") or "",
        "calibrated_by_email": rec.get("calibrated_by_email") or "",
        "calibrated_at": rec.get("calibrated_at"),
        "expires_at": rec.get("expires_at"),
        "note": rec.get("note") or "",
    }
