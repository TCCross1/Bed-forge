"""Nurse-Saul maturity and release-strength forecast — no I/O."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

DATUM_C = 0.0
REF_C = 20.0
DEFAULT_SU_PSI = 8500.0
DEFAULT_K_HOURS = 18.0
DEFAULT_REQUIRED_PSI = 4000.0
ASSUMED_AMBIENT_F = 70.0
PASS_RATIO = 1.03
BORDER_RATIO = 0.92


def parse_iso(value: str) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        try:
            d = datetime.strptime(text[:10], "%Y-%m-%d")
            return d.replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def f_to_c(temp_f: float) -> float:
    return (float(temp_f) - 32.0) * 5.0 / 9.0


def nurse_saul_increment_c_hours(temp_f: float, hours: float, datum_c: float = DATUM_C) -> float:
    hours = max(0.0, float(hours))
    temp_c = f_to_c(temp_f)
    return max(temp_c - float(datum_c), 0.0) * hours


def equivalent_age_hours(maturity_c_hours: float, datum_c: float = DATUM_C, ref_c: float = REF_C) -> float:
    denom = float(ref_c) - float(datum_c)
    if denom <= 0:
        return 0.0
    return max(0.0, float(maturity_c_hours) / denom)


def predict_strength_psi(eq_age_hours: float, su_psi: float = DEFAULT_SU_PSI, k_hours: float = DEFAULT_K_HOURS) -> float:
    k = max(0.1, float(k_hours))
    te = max(0.0, float(eq_age_hours))
    return round(float(su_psi) * (te / (k + te)), 1)


def classify_release(predicted_psi: float, required_psi: float, crush_psi: Optional[float] = None) -> str:
    if crush_psi is not None:
        try:
            actual = float(crush_psi)
            need = float(required_psi)
            if actual >= need:
                return "confirmed_pass"
            return "confirmed_fail"
        except (TypeError, ValueError):
            pass
    need = float(required_psi or 0)
    if need <= 0:
        return "unknown"
    pred = float(predicted_psi)
    if pred >= need * PASS_RATIO:
        return "expected_pass"
    if pred >= need * BORDER_RATIO:
        return "borderline"
    return "fail_risk"


def status_label(code: str) -> str:
    return {
        "expected_pass": "Expected Pass",
        "borderline": "Borderline",
        "fail_risk": "Fail Risk",
        "confirmed_pass": "Crush Pass",
        "confirmed_fail": "Crush Fail",
        "unknown": "No maturity yet",
    }.get(code, "No maturity yet")


def _sorted_samples(samples: List[dict]) -> List[Tuple[datetime, float]]:
    rows = []
    for rec in samples or []:
        dt = parse_iso(rec.get("recorded_at") or rec.get("created_at") or "")
        try:
            temp = float(rec.get("temp_f"))
        except (TypeError, ValueError):
            continue
        if dt is None:
            continue
        rows.append((dt, temp))
    rows.sort(key=lambda r: r[0])
    return rows


def maturity_from_samples(
    samples: List[dict],
    *,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    datum_c: float = DATUM_C,
    assumed_temp_f: Optional[float] = None,
) -> Dict[str, Any]:
    """Integrate Nurse-Saul from pour start to `end` (default now)."""
    now = end or datetime.now(timezone.utc)
    points = _sorted_samples(samples)
    assumed = False
    if start is None:
        start = points[0][0] if points else now
    if start > now:
        start = now
    if not points:
        assumed = True
        temp = float(assumed_temp_f if assumed_temp_f is not None else ASSUMED_AMBIENT_F)
        hours = max(0.0, (now - start).total_seconds() / 3600.0)
        maturity = nurse_saul_increment_c_hours(temp, hours, datum_c)
        return {
            "maturity_c_hours": round(maturity, 2),
            "equivalent_age_hours": round(equivalent_age_hours(maturity, datum_c), 3),
            "hours_since_pour": round(hours, 2),
            "sample_count": 0,
            "assumed_temp": True,
            "assumed_temp_f": temp,
            "last_temp_f": temp,
        }

    cursor = start
    last_temp = points[0][1]
    maturity = 0.0
    idx = 0
    # Walk sample timeline; hold last known temp between readings.
    while idx < len(points) and points[idx][0] < start:
        last_temp = points[idx][1]
        idx += 1
    while idx < len(points):
        stamp, temp = points[idx]
        if stamp > now:
            break
        if stamp > cursor:
            hours = (stamp - cursor).total_seconds() / 3600.0
            maturity += nurse_saul_increment_c_hours(last_temp, hours, datum_c)
            cursor = stamp
        last_temp = temp
        idx += 1
    if now > cursor:
        hours = (now - cursor).total_seconds() / 3600.0
        maturity += nurse_saul_increment_c_hours(last_temp, hours, datum_c)
    hours_since = max(0.0, (now - start).total_seconds() / 3600.0)
    return {
        "maturity_c_hours": round(maturity, 2),
        "equivalent_age_hours": round(equivalent_age_hours(maturity, datum_c), 3),
        "hours_since_pour": round(hours_since, 2),
        "sample_count": len(points),
        "assumed_temp": assumed,
        "assumed_temp_f": None,
        "last_temp_f": last_temp,
    }


def forecast_release(
    *,
    required_psi: float = DEFAULT_REQUIRED_PSI,
    samples: Optional[List[dict]] = None,
    pour_at: Optional[str] = None,
    as_of: Optional[str] = None,
    pull_at: Optional[str] = None,
    crush_psi: Optional[float] = None,
    crush_id: Optional[str] = None,
    su_psi: float = DEFAULT_SU_PSI,
    k_hours: float = DEFAULT_K_HOURS,
    datum_c: float = DATUM_C,
) -> dict:
    end = parse_iso(as_of) or datetime.now(timezone.utc)
    start = parse_iso(pour_at) or None
    math = maturity_from_samples(samples or [], start=start, end=end, datum_c=datum_c)
    predicted = predict_strength_psi(math["equivalent_age_hours"], su_psi, k_hours)
    code = classify_release(predicted, required_psi, crush_psi)
    morning = parse_iso(pull_at)
    morning_pred = None
    morning_code = None
    if morning and crush_psi is None:
        m2 = maturity_from_samples(samples or [], start=start, end=morning, datum_c=datum_c)
        morning_pred = predict_strength_psi(m2["equivalent_age_hours"], su_psi, k_hours)
        morning_code = classify_release(morning_pred, required_psi, None)
    return {
        **math,
        "required_psi": float(required_psi),
        "predicted_psi": predicted,
        "status": code,
        "label": status_label(code),
        "crush_psi": crush_psi,
        "crush_id": crush_id,
        "morning_predicted_psi": morning_pred,
        "morning_status": morning_code,
        "morning_label": status_label(morning_code) if morning_code else None,
        "pull_at": pull_at,
        "advice": _advice(code, predicted, required_psi, math.get("assumed_temp")),
    }


def _advice(code: str, predicted: float, required: float, assumed: bool) -> str:
    if code == "confirmed_pass":
        return "Morning crush already meets release. Do not hold the bed for strength."
    if code == "confirmed_fail":
        return "Crush is below release. Hold the pull and recast or wait on the next cylinder."
    extra = " Temperature was assumed 70°F — log bed/maturity probes to tighten this." if assumed else ""
    if code == "expected_pass":
        return f"On track for {predicted:.0f} psi vs {required:.0f} required. Plan the pull.{extra}"
    if code == "borderline":
        return f"Close call ({predicted:.0f} vs {required:.0f}). Wait for the crush before an early pull.{extra}"
    if code == "fail_risk":
        return f"Predicted {predicted:.0f} psi is under {required:.0f}. Do not pull early — you will waste the bed-day.{extra}"
    return "Log pour time and a temperature reading to forecast release."


def evaluate_release_gate(
    *,
    required_psi: float = DEFAULT_REQUIRED_PSI,
    crush_psi: Optional[float] = None,
    predicted_psi: Optional[float] = None,
    override_active: bool = False,
) -> Dict[str, Any]:
    """Allow release if crush or predicted meets required. Override is audited. Never auto-pass."""
    if override_active:
        return {
            "allow": True,
            "via": "override",
            "reason": "release_strength override on file",
            "prompt_ncr": False,
            "required_psi": float(required_psi or 0),
            "crush_psi": crush_psi,
            "predicted_psi": predicted_psi,
        }
    req = float(required_psi if required_psi not in (None, "") else DEFAULT_REQUIRED_PSI)
    crush = None
    pred = None
    try:
        if crush_psi is not None:
            crush = float(crush_psi)
    except (TypeError, ValueError):
        crush = None
    try:
        if predicted_psi is not None:
            pred = float(predicted_psi)
    except (TypeError, ValueError):
        pred = None
    if crush is not None and crush >= req:
        return {"allow": True, "via": "crush", "reason": "cylinder crush meets required", "prompt_ncr": False, "required_psi": req, "crush_psi": crush, "predicted_psi": pred}
    if pred is not None and pred >= req:
        return {"allow": True, "via": "predicted", "reason": "predicted strength meets required", "prompt_ncr": False, "required_psi": req, "crush_psi": crush, "predicted_psi": pred}
    return {
        "allow": False,
        "via": "gate",
        "reason": f"Release blocked — crush {crush if crush is not None else 'none'} / predicted {pred if pred is not None else 'none'} vs required {req:.0f} psi",
        "prompt_ncr": True,
        "required_psi": req,
        "crush_psi": crush,
        "predicted_psi": pred,
    }


def next_morning_iso(now: Optional[datetime] = None, hour: int = 6) -> str:
    stamp = now or datetime.now(timezone.utc)
    local = stamp
    candidate = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if candidate <= local:
        candidate = candidate + timedelta(days=1)
    return candidate.isoformat()
