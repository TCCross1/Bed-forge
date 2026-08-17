"""Strand elongation / tension calculations for prestressed concrete beds."""
from typing import Optional

from beam_spec import DEFAULT_MODULUS_KSI


def calc_theoretical_elongation(
    jacking_force_kip: float,
    bed_length_ft: float,
    strand_area_in2: float,
    modulus_ksi: float,
) -> float:
    """Theoretical elongation (in) = (P * L) / (A * E).

    P = jacking force per strand (kip)
    L = bed / strand length (in)  -> convert ft to in
    A = strand cross-sectional area (in^2)
    E = modulus of elasticity (ksi)
    """
    if strand_area_in2 <= 0 or modulus_ksi <= 0:
        return 0.0
    length_in = bed_length_ft * 12.0
    return (jacking_force_kip * length_in) / (strand_area_in2 * modulus_ksi)


def evaluate_tension(theoretical_in: float, measured_in: float, tolerance_pct: float = 5.0):
    """Return (variance_pct, within_tolerance) comparing measured vs theoretical."""
    if theoretical_in <= 0:
        return 0.0, False
    variance = (measured_in - theoretical_in) / theoretical_in * 100.0
    within = abs(variance) <= tolerance_pct
    return round(variance, 2), within


def run_tension_calc(payload: dict) -> dict:
    theo = calc_theoretical_elongation(
        payload["jacking_force_kip"],
        payload["bed_length_ft"],
        payload["strand_area_in2"],
        payload["modulus_ksi"],
    )
    theo = round(theo, 3)
    measured = payload.get("measured_elongation_in")
    result = {
        "theoretical_elongation_in": theo,
        "tolerance_pct": 5.0,
        "lower_bound_in": round(theo * 0.95, 3),
        "upper_bound_in": round(theo * 1.05, 3),
    }
    if measured is not None:
        variance, within = evaluate_tension(theo, measured)
        result["measured_elongation_in"] = measured
        result["variance_pct"] = variance
        result["within_tolerance"] = within
    return result


def strand_capture_result(
    *,
    jacking_force_kip: float,
    bed_length_ft: float,
    strand_area_in2: float,
    modulus_ksi: float = DEFAULT_MODULUS_KSI,
    measured_elongation_in: Optional[float] = None,
    na: bool = False,
) -> dict:
    theo = round(calc_theoretical_elongation(
        jacking_force_kip, bed_length_ft, strand_area_in2, modulus_ksi,
    ), 3)
    payload = {
        "theoretical_elongation": theo,
        "jacking_force": jacking_force_kip,
        "measured_elongation": None,
        "variance_pct": None,
        "within_tolerance": None,
        "na": bool(na),
        "status": "na" if na else "pending",
        "lower_bound_in": round(theo * 0.95, 3),
        "upper_bound_in": round(theo * 1.05, 3),
    }
    if na:
        return payload
    if measured_elongation_in is None:
        return payload
    variance, within = evaluate_tension(theo, float(measured_elongation_in))
    payload["measured_elongation"] = float(measured_elongation_in)
    payload["variance_pct"] = variance
    payload["within_tolerance"] = within
    payload["status"] = "pass" if within else "fail"
    return payload
