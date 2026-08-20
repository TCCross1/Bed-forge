"""Batch Intelligence — full QC lab suite scoring for mix recommendations.

Append-only vault math lives here (no I/O). Recommendations never invent
admixture doses. AI still cannot write mix (see batch_plant.AI_CAN_WRITE_MIX).
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

INSUFFICIENT = "insufficient_lab_history"
INSUFFICIENT_MESSAGE = "insufficient lab history"

TEST_TYPES = ("release", "7d", "28d", "other")
CONCRETE_NCR_CATEGORIES = ("material", "batch")
CONCRETE_NCR_SOURCES = ("fresh", "cylinder", "batch", "batch_record")

DEFAULT_AIR_TOLERANCE_PCT = 1.0
DEFAULT_SLUMP_TOLERANCE_IN = 1.5
ENV_TEMP_WINDOW_F = 5.0
ENV_RH_WINDOW_PCT = 10.0
MIN_WINNERS = 3
TOP_COMPARABLES = 8

EVENT_LAB = "lab_save"
EVENT_BATCH = "batch_ticket"
EVENT_RECOMMEND = "recommend"
EVENT_ACCEPT = "accept"
EVENT_EXPORT = "export"


def _num(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _text(value) -> str:
    return str(value or "").strip()


def _median(values: Sequence[float]) -> Optional[float]:
    nums = sorted(float(v) for v in values if v is not None)
    n = len(nums)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return round(nums[mid], 4)
    return round((nums[mid - 1] + nums[mid]) / 2.0, 4)


def classify_test_type(age_hours=None, explicit=None, crush_age_days=None) -> str:
    tag = _text(explicit).lower()
    if tag in TEST_TYPES:
        return tag
    hours = _num(age_hours)
    if hours is None:
        days = _num(crush_age_days)
        hours = None if days is None else days * 24.0
    if hours is None:
        return "other"
    if hours <= 36:
        return "release"
    if 5.5 * 24 <= hours <= 9 * 24:
        return "7d"
    if 24 * 24 <= hours <= 32 * 24:
        return "28d"
    return "other"


def classify_pass_fail(psi=None, required_psi=None, explicit=None, release_ok=None) -> Optional[str]:
    tag = _text(explicit).lower()
    if tag in ("pass", "fail"):
        return tag
    if release_ok is True:
        return "pass"
    if release_ok is False:
        return "fail"
    strength = _num(psi)
    required = _num(required_psi)
    if strength is None or required is None:
        return None
    return "pass" if strength >= required else "fail"


def normalize_compressive(row: Optional[dict], required_psi=None) -> Optional[dict]:
    src = dict(row or {})
    psi = _num(src.get("psi") if src.get("psi") is not None else src.get("crush_psi") or src.get("strength_psi"))
    age_hours = _num(src.get("age_hours") if src.get("age_hours") is not None else src.get("age_hr"))
    if age_hours is None and src.get("crush_age_days") is not None:
        days = _num(src.get("crush_age_days"))
        age_hours = None if days is None else round(days * 24.0, 3)
    if psi is None and age_hours is None and not src.get("test_type"):
        return None
    test_type = classify_test_type(age_hours, src.get("test_type"), src.get("crush_age_days"))
    required = _num(src.get("required_psi") if src.get("required_psi") is not None else required_psi)
    pass_fail = classify_pass_fail(psi, required, src.get("pass_fail"), src.get("release_ok"))
    return {
        "age_hours": age_hours,
        "psi": psi,
        "break_load": _num(src.get("break_load") if src.get("break_load") is not None else src.get("crush_load")),
        "pass_fail": pass_fail,
        "test_type": test_type,
        "required_psi": required,
        "source_id": _text(src.get("source_id") or src.get("id")),
    }


def empty_qc_results() -> dict:
    return {
        "compressive": [],
        "air_content_pct": None,
        "slump_in": None,
        "concrete_temp_f": None,
        "unit_weight_pcf": None,
        "retest_of": None,
        "ncr_ids": [],
        "time_to_release_hours": None,
    }


def normalize_qc_results(raw: Optional[dict], required_psi=None) -> dict:
    """Accept the full lab suite when present. Missing tests stay None — never invented."""
    src = dict(raw or {})
    out = empty_qc_results()
    compressive = src.get("compressive") or src.get("cylinders") or []
    if isinstance(compressive, dict):
        compressive = [compressive]
    cleaned = []
    for row in compressive:
        item = normalize_compressive(row, required_psi=required_psi)
        if item:
            cleaned.append(item)
    out["compressive"] = cleaned
    out["air_content_pct"] = _num(src.get("air_content_pct"))
    out["slump_in"] = _num(src.get("slump_in"))
    out["concrete_temp_f"] = _num(
        src.get("concrete_temp_f") if src.get("concrete_temp_f") is not None else src.get("placement_temp_f")
    )
    out["unit_weight_pcf"] = _num(src.get("unit_weight_pcf"))
    out["retest_of"] = _text(src.get("retest_of")) or None
    ncr_ids = src.get("ncr_ids") or []
    if isinstance(ncr_ids, str):
        ncr_ids = [ncr_ids]
    out["ncr_ids"] = [str(x) for x in ncr_ids if x]
    release_hours = _num(src.get("time_to_release_hours"))
    if release_hours is None:
        for row in cleaned:
            if row.get("test_type") == "release" and row.get("age_hours") is not None:
                release_hours = row["age_hours"]
                break
    out["time_to_release_hours"] = release_hours
    return out


def lab_completeness(qc: Optional[dict]) -> float:
    """Prefer complete lab records over sparse PSI-only tickets."""
    rec = qc or {}
    score = 0.0
    comps = rec.get("compressive") or []
    types = {str(row.get("test_type") or "") for row in comps if _num(row.get("psi")) is not None}
    if "release" in types:
        score += 2.0
    if "7d" in types or "28d" in types:
        score += 1.5
    if comps and score == 0:
        score += 0.5
    if rec.get("air_content_pct") is not None:
        score += 1.0
    if rec.get("slump_in") is not None:
        score += 1.0
    if rec.get("concrete_temp_f") is not None:
        score += 1.0
    if rec.get("unit_weight_pcf") is not None:
        score += 0.5
    if rec.get("time_to_release_hours") is not None:
        score += 0.5
    return round(score, 2)


def qc_fingerprint(qc: Optional[dict]) -> str:
    rec = normalize_qc_results(qc)
    comps = [
        f"{row.get('test_type')}:{row.get('age_hours')}:{row.get('psi')}:{row.get('break_load')}"
        for row in rec.get("compressive") or []
    ]
    raw = "|".join(
        comps
        + [
            str(rec.get("air_content_pct")),
            str(rec.get("slump_in")),
            str(rec.get("concrete_temp_f")),
            str(rec.get("unit_weight_pcf")),
            str(rec.get("retest_of") or ""),
            ",".join(rec.get("ncr_ids") or []),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _breaks_of(qc: dict, test_type: str) -> List[dict]:
    return [row for row in (qc.get("compressive") or []) if row.get("test_type") == test_type]


def _met_target(breaks: List[dict], required: Optional[float]) -> Optional[bool]:
    if not breaks:
        return None
    req = _num(required)
    outcomes = []
    for row in breaks:
        if row.get("pass_fail") == "pass":
            outcomes.append(True)
        elif row.get("pass_fail") == "fail":
            outcomes.append(False)
        elif req is not None and _num(row.get("psi")) is not None:
            outcomes.append(_num(row.get("psi")) >= req)
    if not outcomes:
        return None
    return any(outcomes)


def in_band(actual, target, tolerance) -> Optional[bool]:
    value = _num(actual)
    center = _num(target)
    window = _num(tolerance)
    if value is None or center is None or window is None:
        return None
    return abs(value - center) <= window


def env_similar(
    snapshot_env: Optional[dict],
    query_ambient,
    query_rh,
    temp_window: float = ENV_TEMP_WINDOW_F,
    rh_window: float = ENV_RH_WINDOW_PCT,
) -> Optional[bool]:
    env = snapshot_env or {}
    snap_temp = _num(env.get("ambient_f") if env.get("ambient_f") is not None else env.get("ambient_temp_f"))
    snap_rh = _num(env.get("rh_pct") if env.get("rh_pct") is not None else env.get("humidity_pct"))
    q_temp = _num(query_ambient)
    q_rh = _num(query_rh)
    if q_temp is None or snap_temp is None:
        return None
    if abs(snap_temp - q_temp) > temp_window:
        return False
    if q_rh is not None and snap_rh is not None and abs(snap_rh - q_rh) > rh_window:
        return False
    return True


def is_concrete_ncr(row: Optional[dict]) -> bool:
    rec = row or {}
    category = _text(rec.get("category")).lower()
    if category in CONCRETE_NCR_CATEGORIES:
        return True
    source = _text(rec.get("source_type") or (rec.get("ncr_prompt") or {}).get("source_type")).lower()
    if source in CONCRETE_NCR_SOURCES:
        return True
    if rec.get("batch_record_id") or rec.get("batch_id"):
        return True
    title = _text(rec.get("title")).lower()
    needles = ("cylinder", "fresh", "air content", "slump", "mix", "batch", "compressive", "concrete")
    return any(word in title for word in needles)


def is_open_ncr(row: Optional[dict]) -> bool:
    status = _text((row or {}).get("status")).lower()
    return status in ("open", "investigating", "investigation", "corrective_action", "verification")


def snapshot_has_open_concrete_ncr(snapshot: dict, ncrs: Optional[Iterable[dict]] = None) -> Tuple[bool, List[str]]:
    linked_ids = {str(x) for x in ((snapshot.get("qc_results") or {}).get("ncr_ids") or []) if x}
    live: List[str] = []
    pour_id = _text(snapshot.get("pour_id"))
    batch_id = _text(snapshot.get("batch_id"))
    for rec in ncrs or []:
        if not is_concrete_ncr(rec) or not is_open_ncr(rec):
            continue
        rec_id = _text(rec.get("id") or rec.get("code"))
        rec_pour = _text(rec.get("pour_id"))
        rec_batch = _text(rec.get("batch_id") or rec.get("batch_record_id"))
        linked = (
            (rec_id and rec_id in linked_ids)
            or (pour_id and rec_pour == pour_id)
            or (batch_id and rec_batch and rec_batch == batch_id)
        )
        if linked:
            live.append(rec_id)
    return bool(live), list(dict.fromkeys(live))


def score_snapshot(snapshot: dict, query: dict, ncrs: Optional[List[dict]] = None) -> dict:
    """Score one historical batch against the current pour window.

    Hard misses (failed release, air/slump out of band when recorded, open
    concrete NCR, environment outside ±5°F / ±10% RH when both sides have env)
    disqualify a winner. Sparse missing tests do not invent values and do not
    disqualify — they just lower completeness.
    """
    qc = normalize_qc_results((snapshot or {}).get("qc_results"))
    factors: List[str] = []
    notes: List[str] = []
    score = 0.0
    eligible = True

    required_release = _num(query.get("required_release_psi"))
    required_7d = _num(query.get("required_7d_psi"))
    required_28d = _num(query.get("required_28d_psi"))
    target_air = _num(query.get("target_air_pct") if query.get("target_air_pct") is not None else snapshot.get("target_air_pct"))
    target_slump = _num(query.get("target_slump_in") if query.get("target_slump_in") is not None else snapshot.get("target_slump_in"))
    air_tol = _num(query.get("air_tolerance_pct")) or DEFAULT_AIR_TOLERANCE_PCT
    slump_tol = _num(query.get("slump_tolerance_in")) or DEFAULT_SLUMP_TOLERANCE_IN
    temp_window = _num(query.get("env_temp_window_f")) or ENV_TEMP_WINDOW_F
    rh_window = _num(query.get("env_rh_window_pct")) or ENV_RH_WINDOW_PCT

    release_met = _met_target(_breaks_of(qc, "release"), required_release)
    late_7 = _met_target(_breaks_of(qc, "7d"), required_7d)
    late_28 = _met_target(_breaks_of(qc, "28d"), required_28d)

    if required_release is not None:
        if release_met is True:
            score += 40
            factors.append("strength_curve")
        elif release_met is False:
            eligible = False
            notes.append("release PSI missed")
        else:
            eligible = False
            notes.append("no release PSI on record")
    elif release_met is True:
        score += 30
        factors.append("strength_curve")
    elif release_met is False:
        eligible = False
        notes.append("release PSI failed")

    for label, met, required in (("7d", late_7, required_7d), ("28d", late_28, required_28d)):
        if met is True:
            score += 12
            if "strength_curve" not in factors:
                factors.append("strength_curve")
        elif met is False:
            eligible = False
            notes.append(f"{label} PSI missed")
        elif required is not None:
            notes.append(f"no {label} break recorded")

    air_ok = in_band(qc.get("air_content_pct"), target_air, air_tol)
    if air_ok is True:
        score += 15
        factors.append("air")
    elif air_ok is False:
        eligible = False
        notes.append("air outside plant tolerance")
    elif qc.get("air_content_pct") is not None:
        score += 4
        factors.append("air")

    slump_ok = in_band(qc.get("slump_in"), target_slump, slump_tol)
    if slump_ok is True:
        score += 15
        factors.append("slump")
    elif slump_ok is False:
        eligible = False
        notes.append("slump outside plant tolerance")
    elif qc.get("slump_in") is not None:
        score += 4
        factors.append("slump")

    open_ncr, ncr_ids = snapshot_has_open_concrete_ncr({**snapshot, "qc_results": qc}, ncrs)
    if open_ncr:
        eligible = False
        notes.append("open concrete NCR")
        qc["ncr_ids"] = ncr_ids
    else:
        score += 10
        factors.append("ncr_clear")

    similar = env_similar(
        snapshot.get("environment") or {},
        query.get("ambient_f"),
        query.get("rh_pct"),
        temp_window=temp_window,
        rh_window=rh_window,
    )
    if similar is True:
        score += 10
        factors.append("environment")
    elif similar is False:
        eligible = False
        notes.append("environment outside ±5°F / ±10% RH")

    completeness = lab_completeness(qc)
    score += completeness * 3.0
    if completeness >= 4:
        factors.append("completeness")

    return {
        "batch_id": snapshot.get("batch_id") or snapshot.get("id"),
        "pour_id": snapshot.get("pour_id"),
        "mix_code": snapshot.get("mix_code") or snapshot.get("mix_design"),
        "ticket_number": snapshot.get("ticket_number"),
        "score": round(score, 2),
        "eligible": eligible,
        "factors": factors,
        "notes": notes,
        "completeness": completeness,
        "qc_results": qc,
        "environment": snapshot.get("environment") or {},
        "ingredients": snapshot.get("ingredients") or [],
        "admixtures": snapshot.get("admixtures") or [],
        "lab_snapshot": {
            "compressive": qc.get("compressive") or [],
            "air_content_pct": qc.get("air_content_pct"),
            "slump_in": qc.get("slump_in"),
            "concrete_temp_f": qc.get("concrete_temp_f"),
            "unit_weight_pcf": qc.get("unit_weight_pcf"),
            "retest_of": qc.get("retest_of"),
            "ncr_ids": qc.get("ncr_ids") or [],
            "time_to_release_hours": qc.get("time_to_release_hours"),
        },
    }


def _ingredient_key(item: dict) -> str:
    kind = _text(item.get("kind")).lower() or "ingredient"
    name = _text(item.get("name")).lower()
    return f"{kind}::{name}" if name else ""


def _ingredient_amount(item: dict) -> Tuple[Optional[float], str]:
    for key, unit in (
        ("actual_lb", "lb"),
        ("weight_lb", "lb"),
        ("target_lb", "lb"),
        ("dosage", _text(item.get("dosage_unit")) or "oz/cwt"),
        ("dosage_oz", "oz"),
    ):
        value = _num(item.get(key))
        if value is not None:
            return value, unit
    return None, ""


def mix_envelope(winners: Sequence[dict]) -> Optional[dict]:
    """Min / median / max from recorded winner chemistry only. Never invents doses."""
    if not winners:
        return None
    buckets: Dict[str, dict] = {}
    for row in winners:
        items = list(row.get("ingredients") or []) + [
            {**item, "kind": item.get("kind") or "admixture"} for item in (row.get("admixtures") or [])
        ]
        for item in items:
            key = _ingredient_key(item)
            amount, unit = _ingredient_amount(item)
            if not key or amount is None:
                continue
            bucket = buckets.setdefault(
                key,
                {
                    "name": _text(item.get("name")),
                    "kind": _text(item.get("kind")) or "ingredient",
                    "unit": unit,
                    "values": [],
                },
            )
            bucket["values"].append(amount)
            if unit and not bucket.get("unit"):
                bucket["unit"] = unit
    materials = []
    for bucket in buckets.values():
        values = bucket["values"]
        materials.append(
            {
                "name": bucket["name"],
                "kind": bucket["kind"],
                "unit": bucket["unit"],
                "min": round(min(values), 4),
                "median": _median(values),
                "max": round(max(values), 4),
                "sample_size": len(values),
            }
        )
    materials.sort(key=lambda row: (row.get("kind") or "", row.get("name") or ""))
    if not materials:
        return {
            "materials": [],
            "winner_count": len(winners),
            "note": "Winners have lab history but no recorded ingredient / admixture doses — will not invent chemistry.",
        }
    return {"materials": materials, "winner_count": len(winners)}


def confidence_from_sample(winner_count: int, scanned: int) -> dict:
    if winner_count < MIN_WINNERS:
        level = "none"
    elif winner_count < 6:
        level = "low"
    elif winner_count < 15:
        level = "moderate"
    else:
        level = "high"
    return {
        "level": level,
        "sample_size": int(scanned),
        "winner_count": int(winner_count),
        "min_winners": MIN_WINNERS,
    }


def _driver_payload(winners: Sequence[dict], query: dict) -> dict:
    used = {}
    for row in winners:
        for factor in row.get("factors") or []:
            used[factor] = used.get(factor, 0) + 1
    n = max(len(winners), 1)
    air_tol = _num(query.get("air_tolerance_pct")) or DEFAULT_AIR_TOLERANCE_PCT
    slump_tol = _num(query.get("slump_tolerance_in")) or DEFAULT_SLUMP_TOLERANCE_IN
    catalog = [
        ("strength_curve", "Strength curve", "Release PSI and any later-age breaks that were on record."),
        ("air", "Air content", f"Plant air band ±{air_tol}% when air was recorded."),
        ("slump", "Slump", f"Plant slump band ±{slump_tol} in when slump was recorded."),
        ("environment", "Environment", "Similar ambient window ±5°F and ±10% RH."),
        ("ncr_clear", "No open concrete NCR", "Winners have no open material / batch NCR."),
        ("completeness", "Complete lab record", "Full suite preferred over cylinder PSI alone."),
    ]
    return {
        key: {
            "id": key,
            "label": label,
            "used": used.get(key, 0) > 0,
            "winner_share": round(used.get(key, 0) / n, 3),
            "detail": detail,
        }
        for key, label, detail in catalog
    }


def recommend_from_history(
    history: Sequence[dict],
    query: Optional[dict] = None,
    ncrs: Optional[Sequence[dict]] = None,
) -> dict:
    """Pure scorer. Thin history returns insufficient lab history — no invented doses."""
    q = dict(query or {})
    ncr_rows = list(ncrs or [])
    mix = _text(q.get("mix_code") or q.get("mix_design"))
    scanned = []
    for row in history or []:
        snap = dict(row or {})
        snap["qc_results"] = normalize_qc_results(snap.get("qc_results"))
        row_mix = _text(snap.get("mix_code") or snap.get("mix_design"))
        if mix and row_mix and row_mix.lower() != mix.lower():
            continue
        scanned.append(score_snapshot(snap, q, ncr_rows))

    winners = [row for row in scanned if row.get("eligible")]
    winners.sort(key=lambda row: (-row.get("score", 0), -row.get("completeness", 0)))
    confidence = confidence_from_sample(len(winners), len(scanned))

    payload = {
        "status": "ok",
        "message": "",
        "ai_writes_mix": False,
        "confidence": confidence,
        "drivers": _driver_payload(winners, q),
        "mix_envelope": None,
        "comparables": [],
        "scanned_count": len(scanned),
        "winner_count": len(winners),
        "query": {
            "mix_code": mix,
            "required_release_psi": _num(q.get("required_release_psi")),
            "required_7d_psi": _num(q.get("required_7d_psi")),
            "required_28d_psi": _num(q.get("required_28d_psi")),
            "target_air_pct": _num(q.get("target_air_pct")),
            "target_slump_in": _num(q.get("target_slump_in")),
            "ambient_f": _num(q.get("ambient_f")),
            "rh_pct": _num(q.get("rh_pct")),
            "air_tolerance_pct": _num(q.get("air_tolerance_pct")) or DEFAULT_AIR_TOLERANCE_PCT,
            "slump_tolerance_in": _num(q.get("slump_tolerance_in")) or DEFAULT_SLUMP_TOLERANCE_IN,
        },
    }

    if len(winners) < MIN_WINNERS:
        logger.info(
            "batch intelligence insufficient winners=%s scanned=%s mix=%s",
            len(winners),
            len(scanned),
            bool(mix),
        )
        payload["status"] = INSUFFICIENT
        payload["message"] = INSUFFICIENT_MESSAGE
        payload["mix_envelope"] = None
        payload["comparables"] = []
        return payload

    envelope = mix_envelope(winners)
    payload["mix_envelope"] = envelope
    payload["comparables"] = [
        {
            "batch_id": row.get("batch_id"),
            "pour_id": row.get("pour_id"),
            "mix_code": row.get("mix_code"),
            "ticket_number": row.get("ticket_number"),
            "score": row.get("score"),
            "factors": row.get("factors"),
            "completeness": row.get("completeness"),
            "lab_snapshot": row.get("lab_snapshot"),
            "environment": row.get("environment"),
        }
        for row in winners[:TOP_COMPARABLES]
    ]
    logger.info(
        "batch intelligence recommend winners=%s scanned=%s envelope_keys=%s",
        len(winners),
        len(scanned),
        len((envelope or {}).get("materials") or []),
    )
    return payload


def envelope_to_ticket_fields(envelope: Optional[dict]) -> Tuple[List[dict], List[dict]]:
    """Map recorded envelope medians onto a batch ticket. Empty if nothing was recorded."""
    ingredients: List[dict] = []
    admixtures: List[dict] = []
    for row in (envelope or {}).get("materials") or []:
        median = _num(row.get("median"))
        if median is None:
            continue
        kind = _text(row.get("kind")).lower()
        name = _text(row.get("name"))
        if not name:
            continue
        if kind == "admixture" or _text(row.get("unit")).startswith("oz"):
            admixtures.append({"name": name, "dosage_oz": median, "kind": "admixture", "dosage": median, "dosage_unit": row.get("unit") or "oz"})
        else:
            ingredients.append(
                {
                    "name": name,
                    "kind": kind if kind and kind != "ingredient" else "",
                    "target_lb": median,
                    "actual_lb": median,
                    "weight_lb": median,
                }
            )
    return ingredients, admixtures


def qc_from_cylinder(doc: Optional[dict]) -> dict:
    rec = doc or {}
    age_days = _num(rec.get("crush_age_days"))
    item = normalize_compressive(
        {
            "psi": rec.get("crush_psi"),
            "crush_psi": rec.get("crush_psi"),
            "break_load": rec.get("break_load") or rec.get("crush_load"),
            "crush_age_days": age_days,
            "age_hours": rec.get("age_hours"),
            "test_type": rec.get("test_type"),
            "pass_fail": rec.get("pass_fail"),
            "release_ok": rec.get("release_ok"),
            "required_psi": rec.get("required_psi"),
            "id": rec.get("id"),
        },
        required_psi=rec.get("required_psi"),
    )
    qc = empty_qc_results()
    if item:
        qc["compressive"] = [item]
        if item.get("test_type") == "release":
            qc["time_to_release_hours"] = item.get("age_hours")
    qc["retest_of"] = _text(rec.get("retest_of")) or None
    qc["ncr_ids"] = [str(x) for x in (rec.get("ncr_ids") or []) if x]
    return qc


def qc_from_fresh(doc: Optional[dict]) -> dict:
    rec = doc or {}
    qc = empty_qc_results()
    qc["air_content_pct"] = _num(rec.get("air_content_pct"))
    qc["slump_in"] = _num(rec.get("slump_in"))
    qc["concrete_temp_f"] = _num(rec.get("concrete_temp_f"))
    qc["unit_weight_pcf"] = _num(rec.get("unit_weight_pcf"))
    qc["retest_of"] = _text(rec.get("retest_of")) or None
    qc["ncr_ids"] = [str(x) for x in (rec.get("ncr_ids") or []) if x]
    return qc


def qc_from_batch_record(doc: Optional[dict]) -> dict:
    rec = doc or {}
    qc = empty_qc_results()
    compressive = []
    for row in rec.get("cylinders") or []:
        item = normalize_compressive(row)
        if item:
            compressive.append(item)
    qc["compressive"] = compressive
    qc["concrete_temp_f"] = _num(rec.get("concrete_temp_f"))
    linked_fresh = rec.get("linked_fresh") or []
    if linked_fresh:
        fresh = qc_from_fresh(linked_fresh[0])
        for key in ("air_content_pct", "slump_in", "concrete_temp_f", "unit_weight_pcf"):
            if qc.get(key) is None:
                qc[key] = fresh.get(key)
    qc["air_content_pct"] = _num(rec.get("air_content_pct") if rec.get("air_content_pct") is not None else qc.get("air_content_pct"))
    qc["slump_in"] = _num(rec.get("slump_in") if rec.get("slump_in") is not None else qc.get("slump_in"))
    qc["unit_weight_pcf"] = _num(rec.get("unit_weight_pcf"))
    qc["retest_of"] = _text(rec.get("retest_of")) or None
    qc["ncr_ids"] = [str(x) for x in (rec.get("ncr_ids") or []) if x]
    if rec.get("qc_results"):
        qc = normalize_qc_results({**qc, **rec.get("qc_results")})
    return qc


def merge_qc(base: Optional[dict], incoming: Optional[dict]) -> dict:
    out = normalize_qc_results(base)
    add = normalize_qc_results(incoming)
    seen = {
        (row.get("source_id"), row.get("test_type"), row.get("age_hours"), row.get("psi"))
        for row in out["compressive"]
    }
    for row in add["compressive"]:
        key = (row.get("source_id"), row.get("test_type"), row.get("age_hours"), row.get("psi"))
        if key not in seen:
            out["compressive"].append(row)
            seen.add(key)
    for key in ("air_content_pct", "slump_in", "concrete_temp_f", "unit_weight_pcf", "retest_of", "time_to_release_hours"):
        if add.get(key) is not None:
            out[key] = add.get(key)
    out["ncr_ids"] = list(dict.fromkeys((out.get("ncr_ids") or []) + (add.get("ncr_ids") or [])))
    return out


def snapshot_key(row: dict) -> str:
    batch_id = _text(row.get("batch_id") or (row.get("id") if row.get("ticket_number") else ""))
    if batch_id:
        return f"batch:{batch_id}"
    pour_id = _text(row.get("pour_id"))
    mix = _text(row.get("mix_code") or row.get("mix_design"))
    if pour_id:
        return f"pour:{pour_id}:mix:{mix or 'unknown'}"
    return f"event:{_text(row.get('id')) or 'anon'}"


def merge_history_rows(rows: Sequence[dict]) -> List[dict]:
    grouped: Dict[str, dict] = {}
    for raw in rows or []:
        row = dict(raw or {})
        key = snapshot_key(row)
        current = grouped.get(key)
        if not current:
            grouped[key] = {
                "id": row.get("id") or row.get("batch_id"),
                "batch_id": row.get("batch_id") or row.get("id"),
                "pour_id": row.get("pour_id"),
                "job_id": row.get("job_id"),
                "mix_code": row.get("mix_code") or row.get("mix_design"),
                "mix_design": row.get("mix_design") or row.get("mix_code"),
                "ticket_number": row.get("ticket_number"),
                "target_air_pct": row.get("target_air_pct"),
                "target_slump_in": row.get("target_slump_in"),
                "environment": dict(row.get("environment") or {}),
                "ingredients": list(row.get("ingredients") or []),
                "admixtures": list(row.get("admixtures") or []),
                "qc_results": normalize_qc_results(row.get("qc_results")),
            }
            continue
        current["qc_results"] = merge_qc(current.get("qc_results"), row.get("qc_results"))
        if row.get("ingredients") and not current.get("ingredients"):
            current["ingredients"] = list(row.get("ingredients") or [])
        if row.get("admixtures") and not current.get("admixtures"):
            current["admixtures"] = list(row.get("admixtures") or [])
        env = dict(row.get("environment") or {})
        for field, value in env.items():
            if current["environment"].get(field) in (None, "") and value not in (None, ""):
                current["environment"][field] = value
        for field in ("mix_code", "mix_design", "ticket_number", "pour_id", "job_id", "batch_id"):
            if not current.get(field) and row.get(field):
                current[field] = row.get(field)
    return list(grouped.values())
