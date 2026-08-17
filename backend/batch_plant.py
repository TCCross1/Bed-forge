"""Batch plant math — w/cm, immutability, weather labels, AI recommendations (never writes mix)."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

AI_CAN_WRITE_MIX = False

CEMENTITIOUS_KINDS = ("cement", "scm")
WATER_KINDS = ("water", "ice")
DRAFT_ROLES = ("production", "admin", "executive")
CONFIRM_ROLES = ("admin", "executive")
MUTABLE_STATUSES = ("draft",)

WMO_WEATHER = {
    0: "sunny",
    1: "mainly sunny",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "fog",
    51: "drizzle",
    53: "drizzle",
    55: "drizzle",
    61: "rain",
    63: "rain",
    65: "rain",
    71: "snow",
    73: "snow",
    75: "snow",
    80: "rain",
    81: "rain",
    82: "rain",
    95: "thunderstorm",
    96: "thunderstorm",
    99: "thunderstorm",
}


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


def ingredient_weight(item: dict) -> float:
    return _num((item or {}).get("weight_lb")) or 0.0


def cementitious_lb(ingredients: Optional[List[dict]]) -> float:
    total = 0.0
    for item in ingredients or []:
        kind = str((item or {}).get("kind") or "").strip().lower()
        if kind in CEMENTITIOUS_KINDS:
            total += ingredient_weight(item)
    return round(total, 3)


def water_lb(ingredients: Optional[List[dict]]) -> float:
    total = 0.0
    for item in ingredients or []:
        kind = str((item or {}).get("kind") or "").strip().lower()
        if kind in WATER_KINDS:
            total += ingredient_weight(item)
    return round(total, 3)


def water_cementitious_ratio(ingredients: Optional[List[dict]]) -> Optional[float]:
    """w/cm = (batch water + ice) / (cement + SCM). None if no cementitious."""
    cem = cementitious_lb(ingredients)
    if cem <= 0:
        return None
    return round(water_lb(ingredients) / cem, 4)


def is_immutable(doc: Optional[dict]) -> bool:
    rec = doc or {}
    return bool(rec.get("immutable")) or str(rec.get("status") or "") == "confirmed"


def confirm_blocker(rec: Optional[dict]) -> Optional[str]:
    """Plant manager cannot freeze a ticket that has no mix identity."""
    mix = str((rec or {}).get("mix_code") or "").strip()
    if not mix:
        return "Mix code is required before confirm"
    return None


def can_draft(role: str) -> bool:
    return (role or "") in DRAFT_ROLES


def can_confirm(role: str) -> bool:
    return (role or "") in CONFIRM_ROLES


def weather_label(code) -> str:
    try:
        return WMO_WEATHER.get(int(code), "overcast")
    except (TypeError, ValueError):
        return "overcast"


def c_to_f(celsius) -> Optional[float]:
    value = _num(celsius)
    if value is None:
        return None
    return round(value * 9.0 / 5.0 + 32.0, 1)


def hpa_to_inhg(hpa) -> Optional[float]:
    value = _num(hpa)
    if value is None:
        return None
    return round(value / 33.8639, 2)


def solar_proxy(hour: Optional[int], weather: str = "") -> str:
    try:
        hr = int(hour)
    except (TypeError, ValueError):
        return "unknown"
    tag = (weather or "").lower()
    if hr < 6 or hr >= 20:
        return "night"
    if "rain" in tag or "storm" in tag or "snow" in tag:
        return "low"
    if 10 <= hr <= 16 and ("sun" in tag or tag in ("sunny", "mainly sunny")):
        return "high"
    if 10 <= hr <= 16:
        return "moderate"
    return "low"


def apply_computed_batch(data: dict) -> dict:
    out = dict(data or {})
    ingredients = out.get("ingredients") or []
    out["cementitious_lb"] = cementitious_lb(ingredients)
    out["water_lb"] = water_lb(ingredients)
    out["w_cm"] = water_cementitious_ratio(ingredients)
    return out


def copy_library_into_batch(data: dict, design: Optional[dict]) -> dict:
    """Fill empty mix fields from a library card. Never overwrites keyed-in weights."""
    out = dict(data or {})
    mix = design or {}
    if not str(out.get("mix_code") or "").strip() and mix.get("mix_code"):
        out["mix_code"] = mix["mix_code"]
    if not out.get("mix_design_id") and mix.get("id"):
        out["mix_design_id"] = mix["id"]
    for key in ("target_strength_psi", "target_air_pct", "target_slump_in", "target_spread_in", "target_temp_f"):
        if out.get(key) in (None, "") and mix.get(key) not in (None, ""):
            out[key] = mix.get(key)
    current = out.get("ingredients") or []
    blank = not current or not any(
        (_num(item.get("weight_lb")) or 0) or (_num(item.get("dosage")) or 0)
        for item in current
    )
    if blank and mix.get("ingredients"):
        out["ingredients"] = [dict(row) for row in mix["ingredients"]]
    return out


def weather_failure_env(manual_override: bool = False) -> dict:
    """Open-Meteo down must never block a mixer. No lat/lon in this payload."""
    return {
        "source": "manual",
        "env_flag": "estimated/manual",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "manual_override": bool(manual_override),
        "ambient_f": None,
        "rh_pct": None,
        "pressure_inhg": None,
        "wind_mph": None,
        "weather": "",
        "solar_proxy": "unknown",
    }


def apply_recommendations_to_batch(_batch: dict, _recs: List[dict]) -> dict:
    """Hard gate: the analyst never writes ingredients, dosages, or targets."""
    raise PermissionError("AI cannot change the mix. Recommendations only — plant manager decides.")


def _admixture_dose(ingredients: List[dict], needle: str) -> Optional[float]:
    needle = needle.lower()
    for item in ingredients or []:
        name = str((item or {}).get("name") or "").lower()
        kind = str((item or {}).get("kind") or "").lower()
        if kind == "admixture" and needle in name:
            return _num(item.get("dosage"))
    return None


def _fresh_air(batch: dict) -> Optional[float]:
    linked = (batch.get("linked_fresh") or [{}])[0]
    return _num(batch.get("actual_air_pct")) or _num(linked.get("air_content_pct"))


def _fresh_spread(batch: dict) -> Optional[float]:
    linked = (batch.get("linked_fresh") or [{}])[0]
    return _num(batch.get("actual_spread_in")) or _num(linked.get("spread_avg_in")) or _num(linked.get("slump_in"))


def _early_psi(batch: dict) -> Optional[float]:
    for cyl in batch.get("linked_cylinders") or []:
        age = _num(cyl.get("crush_age_days"))
        psi = _num(cyl.get("crush_psi"))
        if psi is None:
            continue
        if age is not None and age <= 3:
            return psi
        if age is None:
            return psi
    return None


def _late_psi(batch: dict) -> Optional[float]:
    best = None
    for cyl in batch.get("linked_cylinders") or []:
        age = _num(cyl.get("crush_age_days")) or 0
        psi = _num(cyl.get("crush_psi"))
        if psi is None:
            continue
        if age >= 7 and (best is None or age >= (best[0] or 0)):
            best = (age, psi)
    return None if best is None else best[1]


def build_recommendations(batch: dict, history: List[dict], ncrs: Optional[List[dict]] = None) -> List[dict]:
    """Grounded suggestions from this batch + confirmed history. Never mutates mix."""
    recs: List[dict] = []
    env = batch.get("environment") or {}
    ambient = _num(env.get("ambient_f"))
    rh = _num(env.get("rh_pct"))
    weather = str(env.get("weather") or "")
    air_actual = _fresh_air(batch)
    air_target = _num(batch.get("target_air_pct"))
    ingredients = batch.get("ingredients") or []
    aea = _admixture_dose(ingredients, "aea")
    retarder = _admixture_dose(ingredients, "retard")
    wcm = _num(batch.get("w_cm")) or water_cementitious_ratio(ingredients)
    mix_code = str(batch.get("mix_code") or "")

    similar = [
        row for row in (history or [])
        if row.get("id") != batch.get("id") and str(row.get("status") or "") in ("confirmed", "amended")
    ]
    same_mix = [row for row in similar if mix_code and row.get("mix_code") == mix_code]

    if ambient is not None and ambient >= 85 and (rh is None or rh <= 45):
        cites = [row.get("id") for row in same_mix[:4] if _fresh_air(row) is not None]
        bump = 0.4
        if air_target is not None and air_actual is not None and air_actual < air_target - 0.3:
            bump = round(max(0.4, air_target - air_actual), 2)
        recs.append({
            "id": "hot-dry-air",
            "title": "Hot/dry day — air often runs low",
            "body": (
                f"Ambient {ambient}°F"
                + (f", RH {rh}%" if rh is not None else "")
                + ". Air-entraining dosage often needs a bump on dry, windy days. "
                + (f"This load’s air is {air_actual}% vs target {air_target}%. " if air_actual is not None and air_target is not None else "")
                + f"Consider +{bump} oz/cwt AEA on the next load of this mix — do not change this confirmed ticket automatically."
            ),
            "suggested_aea_delta_oz_cwt": bump,
            "current_aea": aea,
            "cite_batch_ids": cites[:4],
        })

    if ambient is not None and ambient <= 45:
        slow = [row for row in same_mix if (_early_psi(row) or 99999) < (row.get("target_strength_psi") or 4000) * 0.45]
        recs.append({
            "id": "cold-early",
            "title": "Cold ambient — slower early strength",
            "body": (
                f"Ambient {ambient}°F. This cement + sand pairing typically lags 1-day and 3-day breaks in the cold. "
                "Keep the accelerator decision with the plant manager; do not skip cylinders. "
                + (f"{len(slow)} similar confirmed loads showed slow early psi." if slow else "Watch the first-day cylinders before you strip.")
            ),
            "cite_batch_ids": [row.get("id") for row in slow[:4]],
        })

    consistent = []
    for row in same_mix:
        late = _late_psi(row)
        target = _num(row.get("target_strength_psi"))
        row_wcm = _num(row.get("w_cm"))
        row_ret = _admixture_dose(row.get("ingredients") or [], "retard")
        if late is not None and target and late >= target and row_wcm is not None:
            consistent.append((abs((row_wcm - (wcm or row_wcm))), row, row_wcm, row_ret, late))
    consistent.sort(key=lambda x: x[0])
    if consistent:
        _, best, best_wcm, best_ret, best_psi = consistent[0]
        recs.append({
            "id": "wcm-retarder",
            "title": "Most consistent 28-day on this mix code",
            "body": (
                f"Confirmed load {best.get('id')} hit {best_psi} psi with w/cm {best_wcm}"
                + (f" and retarder {best_ret} oz/cwt" if best_ret is not None else "")
                + ". Treat that as a starting point, not an automatic change."
            ),
            "suggested_w_cm": best_wcm,
            "cite_batch_ids": [best.get("id")],
        })

    if not recs:
        recs.append({
            "id": "hold-mix",
            "title": "Not enough history to suggest a change",
            "body": "Keep this mix as batched. Log air, spread, and cylinders so the next hot or cold day has something real to cite. The analyst will never rewrite dosages.",
            "cite_batch_ids": [row.get("id") for row in same_mix[:3]],
        })

    ncr_rows = list(ncrs or [])
    mix_hits = [n for n in ncr_rows if mix_code and n.get("mix_code") == mix_code]
    pour_hits = [n for n in ncr_rows if batch.get("pour_id") and n.get("pour_id") == batch.get("pour_id")]
    hot = mix_hits or pour_hits
    if len(hot) >= 3:
        recs.insert(0, {
            "id": "ncr-mix-cluster",
            "title": f"{len(hot)} NCRs on this mix / pour",
            "body": "Frequency only — suggested training focus. Do not auto-close NCRs and do not change the mix from this card.",
            "count": len(hot),
            "ai_writes_mix": False,
        })

    for rec in recs:
        rec["ai_writes_mix"] = False
        rec["weather"] = weather
        rec["w_cm"] = wcm
    return recs


def forecast_note(env: dict) -> Optional[dict]:
    ambient = _num((env or {}).get("ambient_f"))
    rh = _num((env or {}).get("rh_pct"))
    if ambient is None:
        return None
    if ambient >= 85 and (rh is None or rh <= 45):
        return {
            "id": "forecast-hot",
            "title": "Forecast / now: hot and dry",
            "body": "Starting adjustment to discuss: extra AEA and watch evaporation on the bed. Manager decides — the analyst does not change the batch.",
            "ai_writes_mix": False,
        }
    if ambient <= 45:
        return {
            "id": "forecast-cold",
            "title": "Forecast / now: cold",
            "body": "Starting adjustment to discuss: mix temperature, possible accelerator, longer mix time. Manager decides.",
            "ai_writes_mix": False,
        }
    return None
