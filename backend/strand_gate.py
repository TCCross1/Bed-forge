"""Hard gate: a bed cannot start tensioning without a confirmed mill-traceable roll."""
from typing import Dict, Iterable, Optional

CONFIRMED_STATUSES = {"confirmed", "assigned", "depleted"}

GATE_MESSAGE = (
    "Strand roll not logged for this bed/pour. Scan the mill tag and confirm a heat number "
    "before tensioning."
)


def pour_matches(assignment: dict, pour_id: Optional[str]) -> bool:
    if not pour_id:
        return True
    assigned = (assignment or {}).get("pour_id") or ""
    return assigned == "" or assigned == pour_id


def roll_is_ready(roll: Optional[dict]) -> bool:
    if not roll:
        return False
    heat = str(roll.get("heat_number") or "").strip()
    status = (roll.get("status") or "").lower()
    return bool(heat) and status in CONFIRMED_STATUSES


def gate_ok(
    assignments: Iterable[dict],
    rolls_by_id: Dict[str, dict],
    pour_id: Optional[str] = None,
) -> bool:
    for rec in assignments or []:
        if not pour_matches(rec, pour_id):
            continue
        if roll_is_ready(rolls_by_id.get(rec.get("roll_id"))):
            return True
    return False


def matching_assignments(assignments: Iterable[dict], pour_id: Optional[str] = None) -> list:
    return [rec for rec in (assignments or []) if pour_matches(rec, pour_id)]
