"""Plastic / fresh concrete ticket math — ASTM C1611 spread, C143 slump, C1621 J-ring.

These are delivery-time (plastic) tests, not hardened cylinder breaks.
"""

ALLOWED_TEST_TYPES = ("spread", "slump", "jring")
ALLOWED_GATES = ("pass", "fail", "hold")
ALLOWED_STABILITY = ("stable", "minor_halo", "segregation")

# ASTM C1621 / AASHTO T 345 blocking bands (inches): unconstrained flow − J-ring flow.
BLOCKING_PASS_MAX_IN = 1.0
BLOCKING_BORDERLINE_MAX_IN = 2.0


def _as_float(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def diameter_average(d1, d2):
    """Orthogonal spread / J-ring diameters → live average (in). One reading is enough."""
    vals = [v for v in (_as_float(d1), _as_float(d2)) if v is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 3)


def blocking_delta(unconstrained_avg_in, jring_avg_in):
    """Δ = unconstrained slump-flow − J-ring flow (in). None if either side is missing."""
    unconstrained = _as_float(unconstrained_avg_in)
    jring = _as_float(jring_avg_in)
    if unconstrained is None or jring is None:
        return None
    return round(unconstrained - jring, 3)


def blocking_assessment(delta_in):
    """ASTM C1621 bands in floor language: PASS / BORDERLINE / BLOCKING."""
    delta = _as_float(delta_in)
    if delta is None:
        return None
    if delta <= BLOCKING_PASS_MAX_IN:
        return {
            "code": "pass",
            "label": "PASS",
            "detail": "No visible blocking (0–1 in)",
        }
    if delta <= BLOCKING_BORDERLINE_MAX_IN:
        return {
            "code": "borderline",
            "label": "BORDERLINE",
            "detail": "Minimal to notable blocking (1–2 in)",
        }
    return {
        "code": "blocking",
        "label": "BLOCKING",
        "detail": "Noticeable blocking (>2 in)",
    }


def apply_computed_fields(data: dict) -> dict:
    """Fill live averages and J-ring blocking from the diameters a tech actually writes."""
    out = dict(data or {})
    spread_avg = diameter_average(out.get("spread_d1_in"), out.get("spread_d2_in"))
    out["spread_avg_in"] = spread_avg

    jring_avg = diameter_average(out.get("jring_d1_in"), out.get("jring_d2_in"))
    out["jring_avg_in"] = jring_avg

    unconstrained = _as_float(out.get("unconstrained_avg_in"))
    if unconstrained is None and spread_avg is not None:
        unconstrained = spread_avg
    out["unconstrained_avg_in"] = unconstrained

    delta = blocking_delta(unconstrained, jring_avg)
    out["blocking_delta_in"] = delta
    assess = blocking_assessment(delta)
    out["blocking_assessment"] = (assess or {}).get("code")
    out["blocking_label"] = (assess or {}).get("label")
    out["blocking_detail"] = (assess or {}).get("detail")
    return out


def sanitize_test_types(raw) -> list:
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    cleaned = []
    for item in items:
        key = str(item or "").strip().lower().replace("-", "").replace(" ", "")
        if key in ("jring", "j_ring"):
            key = "jring"
        if key in ALLOWED_TEST_TYPES and key not in cleaned:
            cleaned.append(key)
    if "jring" in cleaned and "spread" not in cleaned:
        cleaned.insert(0, "spread")
    if not cleaned:
        cleaned = ["spread"]
    return cleaned


def sanitize_gate(raw: str) -> str:
    key = str(raw or "").strip().lower()
    return key if key in ALLOWED_GATES else "hold"


def sanitize_stability(raw):
    key = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    if key in ("minorhalo", "halo"):
        key = "minor_halo"
    return key if key in ALLOWED_STABILITY else None
