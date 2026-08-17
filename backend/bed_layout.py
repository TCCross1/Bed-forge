"""Bed layout packing and conflict checks. Stations are feet from the header."""
from datetime import datetime
from typing import List, Optional, Tuple

HEADER_SETBACK_FT = 8.0
BULKHEAD_SETBACK_FT = 8.0
GAP_FT = 2.5
MAX_BEAMS_TYPICAL = 4


def parse_day(value: str) -> str:
    if not value:
        raise ValueError("scheduled_date is required")
    return str(value)[:10]


def end_day(start: str, end: Optional[str]) -> str:
    return parse_day(end) if end else parse_day(start)


def ranges_overlap(a0: str, a1: str, b0: str, b1: str) -> bool:
    return parse_day(a0) <= parse_day(b1) and parse_day(b0) <= parse_day(a1)


def covers(rec: dict, day: str) -> bool:
    start = rec.get("scheduled_date")
    if not start:
        return False
    return parse_day(start) <= parse_day(day) <= end_day(start, rec.get("scheduled_end_date"))


def pack_stations(bed_length_ft: float, lengths: List[float]) -> List[float]:
    """Return start station for each beam from the header, or raise ValueError."""
    if not lengths:
        return []
    usable = float(bed_length_ft) - HEADER_SETBACK_FT - BULKHEAD_SETBACK_FT
    if usable <= 0:
        raise ValueError("Bed length is too short for header and bulkhead setbacks")
    needed = sum(lengths) + GAP_FT * max(len(lengths) - 1, 0)
    if needed > usable + 0.01:
        raise ValueError(
            f"Beams need {needed:.1f} ft plus setbacks; bed has {bed_length_ft:.1f} ft "
            f"({usable:.1f} ft usable)"
        )
    stations = []
    cursor = HEADER_SETBACK_FT
    for length in lengths:
        stations.append(round(cursor, 3))
        cursor += length + GAP_FT
    return stations


def remaining_ft(bed_length_ft: float, lengths: List[float]) -> float:
    usable = float(bed_length_ft) - HEADER_SETBACK_FT - BULKHEAD_SETBACK_FT
    used = sum(lengths) + GAP_FT * max(len(lengths) - 1, 0)
    return round(usable - used, 2)


def map_production_status(beam_status: str, qc_state: str) -> str:
    if qc_state == "shipped" or beam_status == "complete":
        return "released"
    mapping = {
        "idle": "planned",
        "setup": "forming",
        "tensioning": "stressed",
        "casting": "poured",
        "curing": "cured",
        "stripping": "cured",
        "complete": "released",
        "planned": "planned",
        "forming": "forming",
        "stressed": "stressed",
        "poured": "poured",
        "cured": "cured",
        "released": "released",
    }
    return mapping.get(beam_status, "planned")


def find_conflicts(
    existing: List[dict],
    *,
    bed_id: str,
    beam_id: str,
    start: str,
    end: str,
    ignore_id: Optional[str] = None,
) -> Tuple[List[str], List[str]]:
    """Return (bed_conflicts, beam_conflicts) assignment ids."""
    bed_hits = []
    beam_hits = []
    s0, s1 = parse_day(start), end_day(start, end)
    for rec in existing:
        if ignore_id and rec.get("id") == ignore_id:
            continue
        r0 = rec.get("scheduled_date")
        r1 = rec.get("scheduled_end_date") or r0
        if not r0 or not ranges_overlap(s0, s1, r0, r1):
            continue
        if rec.get("beam_id") == beam_id:
            beam_hits.append(rec["id"])
        if rec.get("bed_id") == bed_id:
            bed_hits.append(rec["id"])
    return bed_hits, beam_hits


def fallback_spec(beam: dict) -> dict:
    """Minimal BeamSpec-shaped payload so a bed twin can render without a locked drawing."""
    length = float(beam.get("length_ft") or 90)
    twin = beam.get("twin_type") or "i_beam"
    box = twin == "box_beam"
    depth = 27.0 if box else 45.0
    width = 48.0 if box else 16.0
    return {
        "id": f"fallback-{beam.get('id') or 'beam'}",
        "status": "draft",
        "marked_end_id": "ME",
        "unmarked_end_id": "UE",
        "product_name": beam.get("mark") or "Beam",
        "geometry": {
            "twin_type": twin,
            "length_ft": length,
            "depth_in": depth,
            "width_in": width,
            "top_flange_width_in": 16.0 if not box else width,
            "top_flange_thick_in": 7.0,
            "bot_flange_width_in": 18.0 if not box else width,
            "bot_flange_thick_in": 7.0,
            "web_thick_in": 6.0,
        },
        "strands": [],
        "stirrup_zones": [],
        "hardware": [
            {"id": "ll-me", "kind": "lift_loop", "name": "Lift loop ME", "position": {"station_ft": round(length * 0.2, 2), "offset_in": 0, "height_from_soffit_in": depth}},
            {"id": "ll-ue", "kind": "lift_loop", "name": "Lift loop UE", "position": {"station_ft": round(length * 0.8, 2), "offset_in": 0, "height_from_soffit_in": depth}},
            {"id": "brg-me", "kind": "bearing_plate", "name": "Bearing ME", "position": {"station_ft": 0.75, "offset_in": 0, "height_from_soffit_in": 0}},
            {"id": "brg-ue", "kind": "bearing_plate", "name": "Bearing UE", "position": {"station_ft": round(length - 0.75, 2), "offset_in": 0, "height_from_soffit_in": 0}},
        ],
    }
