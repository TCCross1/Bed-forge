"""NCR workflow, linkage, and close rules — no I/O, no Mongo."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

STATUSES = ("open", "investigating", "corrective_action", "verification", "closed", "rejected")
SEVERITIES = ("minor", "major", "critical")
CATEGORIES = ("dimensional", "visual", "material", "process", "documentation", "strand", "hardware", "batch")
PHOTO_REQUIRED = ("dimensional", "visual", "material", "strand", "hardware", "batch")
OPEN_STATUSES = ("open", "investigating", "corrective_action", "verification")
MANAGE_ROLES = ("qc_supervisor", "admin", "executive")
CREATE_ROLES = ("qc_tech", "qc_supervisor", "production", "admin", "executive")

TRANSITIONS = {
    "open": ("investigating", "rejected"),
    "investigating": ("corrective_action", "rejected", "open"),
    "corrective_action": ("verification", "investigating"),
    "verification": ("closed", "corrective_action"),
    "closed": ("investigating",),
    "rejected": ("investigating",),
}

OVERDUE_HOURS = {"critical": 4.0, "major": 24.0, "minor": 72.0}

ANOMALY_SEVERITY = {"minor": "minor", "moderate": "major", "major": "critical"}
ANOMALY_CATEGORY = {
    "crack": "visual",
    "spall": "visual",
    "honeycomb": "visual",
    "chip": "visual",
    "stain": "visual",
    "other": "visual",
}


def parse_iso(value: str) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def sanitize_status(value: str) -> str:
    text = str(value or "open").strip().lower()
    return text if text in STATUSES else "open"


def sanitize_severity(value: str) -> str:
    text = str(value or "minor").strip().lower()
    if text == "moderate":
        return "major"
    return text if text in SEVERITIES else "minor"


def sanitize_category(value: str) -> str:
    text = str(value or "visual").strip().lower()
    return text if text in CATEGORIES else "visual"


def photos_required(category: str) -> bool:
    return sanitize_category(category) in PHOTO_REQUIRED


def can_manage(role: str) -> bool:
    return (role or "") in MANAGE_ROLES


def can_close(role: str, severity: str) -> bool:
    sev = sanitize_severity(severity)
    if sev in ("major", "critical"):
        return can_manage(role)
    return (role or "") in CREATE_ROLES


def can_reopen(role: str) -> bool:
    return can_manage(role)


def allowed_next(status: str) -> tuple:
    return TRANSITIONS.get(sanitize_status(status), ())


def validate_transition(current: str, nxt: str, role: str) -> Optional[str]:
    cur = sanitize_status(current)
    dest = sanitize_status(nxt)
    if dest not in allowed_next(cur):
        return f"Cannot move from {cur} to {dest}"
    if dest == "closed" and not can_close(role, "minor"):
        return "Not allowed to close this NCR"
    if cur in ("closed", "rejected") and dest == "investigating" and not can_reopen(role):
        return "Only a supervisor can reopen a closed NCR"
    return None


def close_blockers(rec: dict, role: str) -> Optional[str]:
    """None if close is allowed. Message otherwise."""
    sev = sanitize_severity((rec or {}).get("severity"))
    if not can_close(role, sev):
        return "QC supervisor or plant manager must close Major and Critical NCRs"
    if sev in ("major", "critical"):
        if not str((rec or {}).get("root_cause") or "").strip():
            return "Root cause is required before closing a Major or Critical NCR"
        if not str((rec or {}).get("corrective_action") or "").strip():
            return "Corrective action is required before closing a Major or Critical NCR"
        if not str((rec or {}).get("verification_by") or "").strip():
            return "Verification (who checked) is required before closing a Major or Critical NCR"
        if not str((rec or {}).get("signoff") or "").strip():
            return "Electronic sign-off is required before closing a Major or Critical NCR"
    cat = sanitize_category((rec or {}).get("category"))
    photos = (rec or {}).get("photos") or []
    if photos_required(cat) and not photos:
        return "Photos are required for this NCR category"
    return None


def is_immutable(rec: dict) -> bool:
    return sanitize_status((rec or {}).get("status")) in ("closed", "rejected")


def age_hours(rec: dict, now: Optional[datetime] = None) -> float:
    stamp = parse_iso((rec or {}).get("created_at") or "")
    if stamp is None:
        return 0.0
    end = now or datetime.now(timezone.utc)
    return max(0.0, (end - stamp).total_seconds() / 3600.0)


def is_overdue(rec: dict, now: Optional[datetime] = None) -> bool:
    if sanitize_status((rec or {}).get("status")) not in OPEN_STATUSES:
        return False
    sev = sanitize_severity((rec or {}).get("severity"))
    limit = OVERDUE_HOURS.get(sev, 72.0)
    return age_hours(rec, now) >= limit


def is_escalated(rec: dict, now: Optional[datetime] = None) -> bool:
    if sanitize_status((rec or {}).get("status")) not in OPEN_STATUSES:
        return False
    if sanitize_severity((rec or {}).get("severity")) == "critical":
        return True
    return is_overdue(rec, now)


def map_anomaly_severity(value: str) -> str:
    return ANOMALY_SEVERITY.get(str(value or "").strip().lower(), "minor")


def map_anomaly_category(kind: str) -> str:
    return ANOMALY_CATEGORY.get(str(kind or "").strip().lower(), "visual")


def ncr_from_anomaly(anomaly: dict, beam: Optional[dict] = None) -> dict:
    an = anomaly or {}
    beam = beam or {}
    return {
        "beam_ids": [an.get("beam_id")] if an.get("beam_id") else [],
        "job_id": beam.get("job_id") or "",
        "pour_id": beam.get("pour_id") or "",
        "bed_id": beam.get("bed_id") or "",
        "anomaly_id": an.get("id") or "",
        "source_type": "anomaly",
        "source_id": an.get("id") or "",
        "category": map_anomaly_category(an.get("type")),
        "sub_type": an.get("type") or "crack",
        "severity": map_anomaly_severity(an.get("severity")),
        "description": (an.get("note") or f"{an.get('type') or 'defect'} on twin").strip(),
        "twin_position": an.get("position") or {},
        "photos": [an["photo_url"]] if an.get("photo_url") else [],
        "containment": "Pinned on the 3D twin. Isolate the station until QC walks it.",
    }


def build_prompt(
    *,
    source_type: str,
    source_id: str,
    title: str,
    category: str,
    severity: str,
    description: str,
    beam_id: str = "",
    bed_id: str = "",
    pour_id: str = "",
    job_id: str = "",
    batch_id: str = "",
) -> dict:
    return {
        "title": title,
        "source_type": source_type,
        "source_id": source_id,
        "category": sanitize_category(category),
        "severity": sanitize_severity(severity),
        "description": (description or "")[:500],
        "beam_id": beam_id or "",
        "bed_id": bed_id or "",
        "pour_id": pour_id or "",
        "job_id": job_id or "",
        "batch_id": batch_id or "",
    }


def attach_prompt(payload: dict, prompt: Optional[dict]) -> dict:
    out = dict(payload or {})
    if prompt:
        out["ncr_prompt"] = prompt
    return out


def frequency_insights(rows: List[dict], *, window_days: int = 90) -> List[dict]:
    """Recommendations only — never auto-close, never change mix."""
    recs: List[dict] = []
    open_rows = [r for r in (rows or []) if sanitize_status(r.get("status")) in OPEN_STATUSES]
    if not open_rows and not rows:
        return [{
            "id": "ncr-empty",
            "title": "No NCR history yet",
            "body": "File the first one from a failed check or a twin pin. Frequency insights show up after a handful of records.",
            "ai_writes_mix": False,
        }]
    by_sub: Dict[str, int] = {}
    by_bed: Dict[str, int] = {}
    by_cat: Dict[str, int] = {}
    for rec in rows or []:
        sub = str(rec.get("sub_type") or rec.get("category") or "other")
        by_sub[sub] = by_sub.get(sub, 0) + 1
        bed = str(rec.get("bed_id") or "")
        if bed:
            by_bed[bed] = by_bed.get(bed, 0) + 1
        by_cat[sanitize_category(rec.get("category"))] = by_cat.get(sanitize_category(rec.get("category")), 0) + 1
    hot_sub = sorted(by_sub.items(), key=lambda kv: -kv[1])
    if hot_sub and hot_sub[0][1] >= 3:
        name, count = hot_sub[0]
        recs.append({
            "id": "ncr-hot-type",
            "title": f"{name} keeps coming back",
            "body": f"{count} NCRs of type “{name}” in this window. Suggested training focus — do not auto-close anything.",
            "count": count,
            "ai_writes_mix": False,
        })
    hot_bed = sorted(by_bed.items(), key=lambda kv: -kv[1])
    if hot_bed and hot_bed[0][1] >= 3:
        bed_id, count = hot_bed[0]
        recs.append({
            "id": "ncr-hot-bed",
            "title": "One bed is collecting defects",
            "body": f"Bed {bed_id} has {count} NCRs. Walk inserts and form alignment on that line before the next pour.",
            "count": count,
            "ai_writes_mix": False,
        })
    overdue = [r for r in open_rows if is_overdue(r)]
    if overdue:
        recs.append({
            "id": "ncr-overdue",
            "title": f"{len(overdue)} NCR(s) past the clock",
            "body": "Critical is 4 hours. Major is 24. Minor is 72. A supervisor should verify or reopen with a written reason — the analyst will not close them.",
            "count": len(overdue),
            "ai_writes_mix": False,
        })
    if not recs:
        recs.append({
            "id": "ncr-watch",
            "title": f"{len(open_rows)} open NCR(s)",
            "body": "No cluster yet. Keep filing from failed checks so the next 90 days have something real to cite.",
            "ai_writes_mix": False,
        })
    for rec in recs:
        rec["ai_writes_mix"] = False
        rec["window_days"] = window_days
    return recs


def public_ncr(doc: dict) -> dict:
    out = dict(doc or {})
    out.pop("_id", None)
    out["status"] = sanitize_status(out.get("status"))
    out["severity"] = sanitize_severity(out.get("severity"))
    out["category"] = sanitize_category(out.get("category"))
    out["overdue"] = is_overdue(out)
    out["escalated"] = is_escalated(out)
    out["immutable"] = is_immutable(out)
    out["photos_required"] = photos_required(out.get("category"))
    return out
