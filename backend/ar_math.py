"""Pure AR level math and digital-tape vs twin matching — no I/O, no Mongo."""
import math
from typing import Any, Dict, Iterable, List, Optional

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
