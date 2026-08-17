"""Owner cost signals from QC holds — not accounting."""
from typing import Any, Dict, List

DEFAULT_NCR_USD = 2500.0
DEFAULT_SCRAP_USD = 8000.0
DEFAULT_BED_DAY_USD = 3500.0
DEFAULT_OVERTIME_USD = 1800.0


def money_settings(doc: dict) -> dict:
    src = doc or {}
    def num(key, default):
        try:
            return float(src.get(key) if src.get(key) is not None else default)
        except (TypeError, ValueError):
            return float(default)
    return {
        "ncr_cost_usd": num("ncr_cost_usd", DEFAULT_NCR_USD),
        "scrap_cost_usd": num("scrap_cost_usd", DEFAULT_SCRAP_USD),
        "bed_day_cost_usd": num("bed_day_cost_usd", DEFAULT_BED_DAY_USD),
        "overtime_hold_usd": num("overtime_hold_usd", DEFAULT_OVERTIME_USD),
    }


def build_finance_signals(
    *,
    beams: List[dict],
    anomalies: List[dict],
    assignments: List[dict],
    forecasts: List[dict],
    settings: dict,
) -> Dict[str, Any]:
    costs = money_settings(settings)
    holds = [b for b in beams if b.get("qc_state") == "hold"]
    failed = [b for b in beams if b.get("qc_state") == "failed"]
    majors = [a for a in anomalies if (a.get("severity") or "") == "major"]
    ncr_count = len(holds) + len(failed) + len(majors)
    ncr_cost = ncr_count * costs["ncr_cost_usd"]
    scrap_cost = len(failed) * costs["scrap_cost_usd"]

    curing_holds = [
        b for b in beams
        if b.get("qc_state") in ("hold", "failed")
        and (b.get("production_status") in ("poured", "cured") or b.get("status") in ("curing", "stripping", "casting"))
    ]
    overtime = len(curing_holds) * costs["overtime_hold_usd"]

    fail_risk = [f for f in forecasts if f.get("status") in ("fail_risk", "confirmed_fail", "borderline")]
    bed_days_risk = len({(f.get("bed_id") or f.get("pour_id") or f.get("beam_id")) for f in fail_risk})
    bed_day_cost = bed_days_risk * costs["bed_day_cost_usd"]

    occupied = {(a.get("bed_id"), str(a.get("scheduled_date") or "")[:10]) for a in assignments if a.get("bed_id") and a.get("scheduled_date")}
    bed_days_used = len(occupied)

    total_at_risk = round(ncr_cost + scrap_cost + overtime + bed_day_cost, 2)
    return {
        "currency": "USD",
        "settings": costs,
        "open_ncrs": ncr_count,
        "ncr_holds": len(holds),
        "ncr_failed": len(failed),
        "ncr_major_anomalies": len(majors),
        "estimated_ncr_cost": round(ncr_cost, 2),
        "scrap_count": len(failed),
        "estimated_scrap_cost": round(scrap_cost, 2),
        "overtime_flags": len(curing_holds),
        "estimated_overtime_cost": round(overtime, 2),
        "bed_days_used": bed_days_used,
        "bed_days_at_risk": bed_days_risk,
        "estimated_bed_day_risk": round(bed_day_cost, 2),
        "total_quality_dollars_at_risk": total_at_risk,
        "lines": [
            {"id": "ncr", "label": "Open NCRs / repairs", "count": ncr_count, "usd": round(ncr_cost, 2)},
            {"id": "scrap", "label": "Scrap / rework (failed beams)", "count": len(failed), "usd": round(scrap_cost, 2)},
            {"id": "overtime", "label": "Overtime flags on QC holds", "count": len(curing_holds), "usd": round(overtime, 2)},
            {"id": "beddays", "label": "Bed-days lost or at risk", "count": bed_days_risk, "usd": round(bed_day_cost, 2)},
        ],
        "hold_marks": [b.get("mark") for b in holds[:20]],
        "failed_marks": [b.get("mark") for b in failed[:20]],
        "disclaimer": "Cost signals only — not a general ledger. Rates live in plant settings.",
    }
