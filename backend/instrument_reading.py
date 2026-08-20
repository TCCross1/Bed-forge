"""DISTO / LDM instrument reading evaluation — no I/O, no Mongo."""
import logging

logger = logging.getLogger(__name__)

DEFAULT_TOLERANCE_IN = 0.125  # 1/8 in plant gate for laser / keyboard captures
OVERRIDE_ROLES = ("qc_supervisor", "admin", "executive")


def evaluate_instrument_reading(measured_in, target_in=None, tolerance_in=DEFAULT_TOLERANCE_IN):
    """Compare a DISTO/LDM shot to a spec target.

    Returns measured/target/delta, pass/fail status, and bound inches.
    A missing target is a capture-only pass (no spec gate yet).
    """
    try:
        measured = float(measured_in)
    except (TypeError, ValueError) as exc:
        raise ValueError("measured_in must be a number") from exc
    try:
        tol = abs(float(DEFAULT_TOLERANCE_IN if tolerance_in is None else tolerance_in))
    except (TypeError, ValueError) as exc:
        raise ValueError("tolerance_in must be a number") from exc

    result = {
        "measured_in": round(measured, 4),
        "target_in": None,
        "tolerance_in": round(tol, 4),
        "delta_in": None,
        "within_tolerance": True,
        "status": "pass",
        "lower_bound_in": None,
        "upper_bound_in": None,
    }
    if target_in in (None, ""):
        return result
    try:
        target = float(target_in)
    except (TypeError, ValueError) as exc:
        raise ValueError("target_in must be a number") from exc
    delta = measured - target
    within = abs(delta) <= tol
    result.update({
        "target_in": round(target, 4),
        "delta_in": round(delta, 4),
        "within_tolerance": within,
        "status": "pass" if within else "fail",
        "lower_bound_in": round(target - tol, 4),
        "upper_bound_in": round(target + tol, 4),
    })
    return result


def can_override_instrument(role: str) -> bool:
    return (role or "") in OVERRIDE_ROLES
