"""Pure AR level math — no I/O, no Mongo."""
import math

from models import LEVEL_TOLERANCE_IN


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
