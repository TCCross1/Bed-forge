"""Read-only live checks for Ask Expert against the BedForge contract.

Calls the same data paths as GET /api/auth/me, /jobs/open, /jobs, /blueprints,
/beam-specs, /beam-specs/{id}/twin, /batches, and /command-board. Never writes
mix, never issues overrides. If a read fails, the finding is cannot verify —
never a guessed Pass.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from bedforge_contract import CONTRACT_VERSION, REFERENCE_MARKS, section_titles
from beam_spec import embedded_hardware_for_twin, twin_beam_from_spec
from db import db
from models import CylinderCrushInput

logger = logging.getLogger(__name__)

AUDIT_NEEDLES = (
    "what needs to be fixed",
    "what needs fixing",
    "audit",
    "gap",
    "gaps",
    "product contract",
    "fail/warn",
    "fail warn pass",
    "what's broken",
    "whats broken",
    "fix list",
    "prioritized",
)

TWIN_NEEDLES = ("twin", "spec dna", "job specs", "insert", "mesh")

_MARK_RE = re.compile(r"\b(?:mk|mark)\s*[:#.-]?\s*([A-Za-z0-9-]{1,16})\b", re.I)
_JOB_RE = re.compile(r"\b(L\d{4,}[A-Za-z0-9-]*)\b", re.I)


def is_audit_ask(question: str) -> bool:
    q = (question or "").lower()
    if any(n in q for n in AUDIT_NEEDLES):
        return True
    if "fixed?" in q or "fix?" in q:
        return True
    if any(n in q for n in TWIN_NEEDLES) and ("vs" in q or "versus" in q or "spec" in q):
        return True
    return False


def parse_job_mark(question: str) -> Tuple[Optional[str], Optional[str]]:
    text = question or ""
    job = None
    mark = None
    job_match = _JOB_RE.search(text)
    if job_match:
        job = job_match.group(1).upper()
    mark_match = _MARK_RE.search(text)
    if mark_match:
        mark = str(mark_match.group(1)).upper().lstrip("0") or mark_match.group(1)
        if mark.isdigit():
            mark = str(int(mark))
    return job, mark


def _status_rank(status: str) -> int:
    return {"Fail": 0, "Warn": 1, "cannot verify": 2, "Pass": 3}.get(status, 9)


def _finding(section: str, status: str, evidence: str, fix: str = "") -> Dict[str, str]:
    titles = section_titles()
    return {
        "section": section,
        "title": titles.get(section, section),
        "status": status,
        "evidence": evidence,
        "fix": fix,
    }


def declared_embed_count(spec: Optional[Dict[str, Any]], kind: str = "insert") -> int:
    hardware = embedded_hardware_for_twin(spec)
    return len(hardware.get(kind) or [])


def audit_twin_vs_spec(
    spec: Optional[Dict[str, Any]],
    twin: Optional[Dict[str, Any]],
    *,
    job_number: str = "",
    mark: str = "",
) -> List[Dict[str, str]]:
    """Compare Spec DNA embed counts to the twin payload the mesh would consume."""
    label = f"{job_number or 'job'} MK {mark or '?'}".strip()
    if not spec:
        return [_finding(
            "C",
            "cannot verify",
            f"No Spec DNA found for {label}. GET /api/beam-specs",
            "Lock the shop PDF on /blueprints then open /job-specs.",
        )]
    if not twin:
        return [_finding(
            "C",
            "cannot verify",
            f"Spec exists for {label} but twin payload was not built. GET /api/beam-specs/{{id}}/twin",
            "Do not guess Pass. Rebuild the spec twin payload.",
        )]

    findings: List[Dict[str, str]] = []
    identity = spec.get("identity") or {}
    spec_job = identity.get("job_number") or spec.get("job_number") or job_number
    spec_mark = spec.get("beam_mark") or mark
    findings.append(_finding(
        "B",
        "Pass" if spec.get("id") else "Warn",
        f"Spec DNA loaded {spec_job} MK {spec_mark} status={spec.get('status') or 'unknown'} id={spec.get('id')}.",
        "",
    ))

    demo = bool(twin.get("demo")) or str(twin.get("id") or "").startswith("demo")
    if demo and spec.get("id"):
        findings.append(_finding(
            "B",
            "Fail",
            f"Spec exists for MK {spec_mark} but twin still looks like demo geometry.",
            "Drive /job-specs from GET /api/beam-specs/{id}/twin — never seed demo when Spec DNA exists.",
        ))
    else:
        findings.append(_finding(
            "B",
            "Pass",
            f"Twin payload is Spec-backed for MK {spec_mark} (GET /api/beam-specs/{{id}}/twin).",
            "",
        ))

    declared = declared_embed_count(spec, "insert")
    payload = (twin.get("embedded_hardware") or {}).get("insert")
    if payload is None:
        mesh_items: List[Dict[str, Any]] = []
        missing_key = True
    else:
        mesh_items = list(payload) if isinstance(payload, list) else []
        missing_key = False
    mesh_count = len(mesh_items)
    stationed = [item for item in mesh_items if item.get("station_ft") is not None and not item.get("position_unconfirmed")]
    unconfirmed = [item for item in mesh_items if item.get("position_unconfirmed") or item.get("station_ft") is None]

    if declared > 0 and (missing_key or mesh_count == 0):
        findings.append(_finding(
            "C",
            "Fail",
            f"Insert count vs mesh: Spec MK {spec_mark} declares {declared} insert(s); "
            f"twin embedded_hardware.insert is empty (silent omit). Panel count would not match visible mesh.",
            "Render each Spec insert at its station, or an explicit UNCONFIRMED placeholder — never drop the count.",
        ))
    elif declared > 0 and mesh_count != declared:
        findings.append(_finding(
            "C",
            "Fail",
            f"Insert count vs mesh: Spec declares {declared} insert(s); twin mesh has {mesh_count}.",
            "embedded_hardware_for_twin must copy Spec quantity 1:1 into the twin payload.",
        ))
    elif declared > 0 and unconfirmed and not stationed:
        findings.append(_finding(
            "C",
            "Warn",
            f"Insert count vs mesh: Spec MK {spec_mark} declares {declared} insert(s); "
            f"twin has {mesh_count} with UNCONFIRMED station (placeholder required, no invented station).",
            "Keep the placeholder. Confirm F-64 (or type) station from the shop PDF on /blueprints before locking a fake location.",
        ))
    elif declared == 0 and mesh_count == 0:
        findings.append(_finding(
            "C",
            "Pass",
            f"Insert count vs mesh: Spec MK {spec_mark} has 0 inserts and twin hardware insert list is empty.",
            "",
        ))
    else:
        findings.append(_finding(
            "C",
            "Pass",
            f"Insert count vs mesh: Spec MK {spec_mark} declares {declared}; twin mesh has {mesh_count} "
            f"({len(stationed)} stationed, {len(unconfirmed)} UNCONFIRMED placeholder).",
            "",
        ))
    return findings


def _static_implementation_findings() -> List[Dict[str, str]]:
    """Honest contract vs code facts that do not need live plant data."""
    findings: List[Dict[str, str]] = []
    crush_fields = set(CylinderCrushInput.model_fields.keys())
    has_photo = any("photo" in key.lower() or "image" in key.lower() for key in crush_fields)
    has_stamp = any("timestamp" in key.lower() or "photo_at" in key.lower() for key in crush_fields)
    if not has_photo or not has_stamp:
        findings.append(_finding(
            "F",
            "Warn",
            "Cylinder/crush photo timestamp is not on CylinderCrushInput yet (crush_psi/date/age/batch_id exist; no photo stamp).",
            "When implemented, capture crush photo + timestamp and link cylinder to beam/pour. Do not claim it works now.",
        ))
    else:
        findings.append(_finding(
            "F",
            "Pass",
            "Cylinder crush input includes photo timestamp fields.",
            "",
        ))
    return findings


def _match_spec(specs: List[Dict[str, Any]], job_number: Optional[str], mark: Optional[str]) -> Optional[Dict[str, Any]]:
    wanted_job = (job_number or "").strip().upper()
    wanted_mark = (mark or "").strip().upper()
    scored: List[Tuple[int, Dict[str, Any]]] = []
    for spec in specs:
        identity = spec.get("identity") or {}
        spec_job = str(identity.get("job_number") or spec.get("job_number") or "").upper()
        spec_mark = str(spec.get("beam_mark") or "").upper()
        score = 0
        if wanted_job and spec_job == wanted_job:
            score += 2
        if wanted_mark and spec_mark == wanted_mark:
            score += 3
        if wanted_mark and spec_mark.lstrip("0") == wanted_mark.lstrip("0"):
            score += 3
        if score:
            scored.append((score, spec))
    if not scored:
        return None
    scored.sort(key=lambda row: -row[0])
    return scored[0][1]


def format_audit_report(findings: List[Dict[str, str]], *, question: str, live_ok: bool, errors: List[str]) -> str:
    by_status = {"Fail": [], "Warn": [], "cannot verify": [], "Pass": []}
    for row in findings:
        by_status.setdefault(row.get("status") or "cannot verify", []).append(row)

    fail_n = len(by_status["Fail"])
    warn_n = len(by_status["Warn"])
    skip_n = len(by_status["cannot verify"])
    pass_n = len(by_status["Pass"])

    lines = [
        "Summary",
        f"Ask Expert scored BedForge contract v{CONTRACT_VERSION} for: {question.strip()}",
        f"Live API checks: {'wired' if live_ok else 'cannot verify'} · Fail {fail_n} · Warn {warn_n} · cannot verify {skip_n} · Pass {pass_n}",
    ]
    if errors:
        lines.append("Live errors: " + "; ".join(errors[:6]))
    lines.append("")

    def emit(title: str, rows: List[Dict[str, str]]) -> None:
        lines.append(title)
        if not rows:
            lines.append("None.")
            lines.append("")
            return
        for row in rows:
            lines.append(f"{row['section']}) {row['title']} — {row['status']}")
            lines.append(f"Evidence: {row['evidence']}")
            if row.get("fix"):
                lines.append(f"Fix: {row['fix']}")
            lines.append("")

    emit("Failures", by_status["Fail"])
    emit("Warnings", by_status["Warn"])
    emit("Cannot verify", by_status["cannot verify"])
    emit("Pass", by_status["Pass"])

    lines.append("Suggested order of work")
    ordered = sorted(
        [row for row in findings if row.get("status") in ("Fail", "Warn")],
        key=lambda row: (_status_rank(row.get("status") or ""), row.get("section") or ""),
    )
    if not ordered:
        lines.append("1. No Fail/Warn from this snapshot. Re-run after locking Spec DNA if a mark was empty.")
    else:
        for index, row in enumerate(ordered, start=1):
            action = row.get("fix") or row.get("evidence")
            lines.append(f"{index}. [{row['status']}] {row['section']}) {row['title']} — {action}")
    lines.append("")
    lines.append("Grounded in bedforge_contract.py. I will not invent Spec numbers, mix doses, or mark a missing feature Pass.")
    return "\n".join(lines).strip()


async def _safe(label: str, coro, errors: List[str]):
    try:
        return await coro
    except Exception as exc:
        logger.exception("ask expert live check failed label=%s", label)
        errors.append(f"{label}: {exc.__class__.__name__}")
        return None


async def gather_live_audit(user: Dict[str, Any], question: str) -> Dict[str, Any]:
    """Best-effort read-only snapshot. Partial failure never becomes Pass."""
    from job_cabinet import get_open_job_for_user, list_jobs_decorated

    errors: List[str] = []
    findings: List[Dict[str, str]] = []
    live_ok = True
    asked_job, asked_mark = parse_job_mark(question)
    twin_focus = any(n in (question or "").lower() for n in TWIN_NEEDLES) or bool(asked_mark)

    role = (user or {}).get("role") or ""
    if role:
        findings.append(_finding(
            "E",
            "Pass",
            f"auth/me role={role} email={(user or {}).get('email') or 'signed-in'}. Menus are role-gated in Layout.",
            "",
        ))
        if role == "qc_tech":
            findings.append(_finding(
                "E",
                "Pass",
                "QC tech session: verify build + tests vs Spec. Planner/batch confirm stay off this role.",
                "",
            ))
    else:
        live_ok = False
        findings.append(_finding("E", "cannot verify", "auth/me had no role.", "Re-login as Plant Admin or QC."))

    opened = await _safe("GET /api/jobs/open", get_open_job_for_user(user), errors)
    jobs = await _safe("GET /api/jobs", list_jobs_decorated(), errors)

    if opened is None:
        live_ok = False
        findings.append(_finding(
            "D",
            "cannot verify",
            "GET /api/jobs/open failed. Do not guess Pass.",
            "Fix open-job persistence (PUT /api/jobs/open) then retry.",
        ))
    else:
        job = (opened or {}).get("job") or {}
        job_number = job.get("job_number") or ""
        if job_number:
            findings.append(_finding(
                "D",
                "Pass",
                f"Open job is {job_number} via GET /api/jobs/open. Marks in cabinet: {len((opened or {}).get('marks') or [])}.",
                "",
            ))
        else:
            findings.append(_finding(
                "D",
                "Fail",
                "GET /api/jobs/open returned no job_number. Plant Admin cannot scope Tags/Tension/QC.",
                "Open a job from the dashboard (PUT /api/jobs/open) without a generic 500.",
            ))
        if not asked_job:
            asked_job = job_number or asked_job

    if jobs is None:
        live_ok = False
        findings.append(_finding("D", "cannot verify", "GET /api/jobs failed.", "Repair job cabinet list."))
    elif jobs:
        findings.append(_finding(
            "D",
            "Pass",
            f"Job cabinet lists {len(jobs)} job(s): {', '.join(str(item.get('job_number') or '?') for item in jobs[:8])}.",
            "",
        ))
    else:
        findings.append(_finding(
            "D",
            "Warn",
            "GET /api/jobs returned an empty cabinet.",
            "Seed or import jobs so Open Job has a target.",
        ))

    blueprints = await _safe(
        "GET /api/blueprints",
        db.blueprint_documents.find({}, {"_id": 0, "id": 1, "filename": 1, "job_number": 1, "status": 1}).to_list(200),
        errors,
    )
    if blueprints is None:
        live_ok = False
        findings.append(_finding("A", "cannot verify", "GET /api/blueprints failed.", "Do not guess extraction health."))
    elif not blueprints:
        findings.append(_finding(
            "A",
            "Warn",
            "No blueprint documents in GET /api/blueprints. Upload → extract → review → lock is required before Spec DNA.",
            "Upload the shop PDF on /blueprints. Do not invent stations.",
        ))
    else:
        locked = sum(1 for item in blueprints if str(item.get("status") or "").lower() in ("locked", "complete"))
        findings.append(_finding(
            "A",
            "Pass" if locked or blueprints else "Warn",
            f"Blueprints: {len(blueprints)} document(s), locked/complete={locked}. Assessment PDF: GET /api/blueprints/{{id}}/extraction-report.pdf.",
            "" if locked else "Review and lock extraction. Unconfirmed stays unconfirmed.",
        ))

    specs = await _safe("GET /api/beam-specs", db.beam_specs.find({}, {"_id": 0}).to_list(1000), errors)
    if specs is None:
        live_ok = False
        findings.append(_finding("B", "cannot verify", "GET /api/beam-specs failed.", "Do not invent Spec numbers."))
        specs = []
    elif not specs:
        findings.append(_finding(
            "B",
            "Warn",
            "No beam Specs in GET /api/beam-specs. Twin must not hardcode demo geometry as if Spec DNA existed.",
            "Lock a blueprint so Spec DNA materializes (L25390 201–209 length families).",
        ))
    else:
        marks = sorted({str(item.get("beam_mark") or "") for item in specs if item.get("beam_mark")})
        findings.append(_finding(
            "B",
            "Pass",
            f"{len(specs)} Spec(s) in plant. Marks: {', '.join(marks[:12])}{'…' if len(marks) > 12 else ''}.",
            "",
        ))

    target = _match_spec(specs, asked_job, asked_mark)
    if twin_focus and asked_mark and not target:
        ref = REFERENCE_MARKS.get(((asked_job or "").upper(), str(asked_mark)))
        if ref:
            findings.append(_finding(
                "C",
                "Warn",
                f"Insert count vs mesh: live GET /api/beam-specs has no {asked_job} MK {asked_mark}. "
                f"Contract reference for that mark declares {ref['inserts']} {ref['insert_type']} insert(s), "
                f"station {ref['station']}. Live twin mesh cannot be scored — do not guess Pass. {ref['note']}",
                "Lock the L25390 shop PDF on /blueprints, open /job-specs, and confirm Inserts count matches mesh or UNCONFIRMED placeholder.",
            ))
        else:
            findings.append(_finding(
                "C",
                "cannot verify",
                f"No Spec DNA for {asked_job or 'open job'} MK {asked_mark}. Cannot score insert count vs mesh.",
                "Lock the named job so MK exists, then retry Audit twin vs Spec DNA.",
            ))
    elif not target and specs:
        if asked_job:
            target = _match_spec(specs, asked_job, None)
        if not target:
            target = specs[0]

    twin = None
    if target:
        try:
            twin = twin_beam_from_spec(target)
        except Exception:
            live_ok = False
            logger.exception("twin_beam_from_spec failed spec_id=%s", (target or {}).get("id"))
            errors.append("GET /api/beam-specs/{id}/twin")
            findings.append(_finding(
                "C",
                "cannot verify",
                f"twin_beam_from_spec raised for MK {(target or {}).get('beam_mark')}.",
                "Do not guess Pass on insert mesh.",
            ))
        if twin is not None:
            findings.extend(audit_twin_vs_spec(
                target,
                twin,
                job_number=str((target.get("identity") or {}).get("job_number") or target.get("job_number") or asked_job or ""),
                mark=str(target.get("beam_mark") or asked_mark or ""),
            ))

    batches = await _safe(
        "GET /api/batches",
        db.batch_records.find({}, {"_id": 0, "id": 1, "mix_code": 1, "status": 1, "environment": 1, "weather": 1}).to_list(50),
        errors,
    )
    vault = await _safe(
        "GET /api/batch-intelligence/events",
        db.batch_events.find({}, {"_id": 0, "type": 1}).to_list(20),
        errors,
    )
    if batches is None:
        live_ok = False
        findings.append(_finding("G", "cannot verify", "GET /api/batches failed.", "Do not invent mix doses."))
    else:
        live_weather = 0
        for row in batches:
            env = row.get("environment") if isinstance(row.get("environment"), dict) else {}
            if env.get("ambient_f") not in (None, "") or env.get("temperature_f") not in (None, "") or row.get("weather"):
                live_weather += 1
        if not batches:
            findings.append(_finding(
                "G",
                "Warn",
                "Batch Plant has no tickets yet (GET /api/batches empty). Mix Intelligence must not invent doses.",
                "Draft on /batch. Use POST /api/batch-intelligence/recommend — suggestion only until manager Accept.",
            ))
        else:
            findings.append(_finding(
                "G",
                "Pass",
                f"{len(batches)} batch ticket(s) via GET /api/batches. Vault sample={len(vault or [])}.",
                "",
            ))
        if batches and live_weather == 0:
            findings.append(_finding(
                "G",
                "Warn",
                "Live weather for current conditions is not present on listed batch tickets (environment.ambient_f empty).",
                "Wire current conditions into the existing Batch Plant mix card — do not add a second plant product.",
            ))

    beds = await _safe("GET /api/command-board", db.beds.find({}, {"_id": 0, "id": 1, "bed_number": 1, "status": 1}).to_list(50), errors)
    if beds is None:
        live_ok = False
        findings.append(_finding("H", "cannot verify", "Beds read for command-board failed.", "Do not guess kiosk Pass."))
    elif not beds:
        findings.append(_finding(
            "H",
            "Warn",
            "No beds for GET /api/command-board kiosk.",
            "Seed beds. TV wall is read-only.",
        ))
    else:
        findings.append(_finding(
            "H",
            "Pass",
            f"{len(beds)} bed(s) available for the Command Board kiosk (GET /api/command-board).",
            "",
        ))

    ncrs = await _safe("GET /api/ncrs", db.ncrs.find({}, {"_id": 0, "id": 1, "status": 1, "beam_ids": 1, "batch_id": 1}).to_list(80), errors)
    inspections = await _safe(
        "GET /api/inspections",
        db.inspections.find({}, {"_id": 0, "id": 1, "beam_id": 1}).to_list(40),
        errors,
    )
    if ncrs is None or inspections is None:
        live_ok = False
        findings.append(_finding("F", "cannot verify", "QIR/NCR live read failed.", "Do not mark QC Pass."))
    else:
        linked = sum(1 for row in ncrs if row.get("beam_ids") or row.get("batch_id") or row.get("pour_id"))
        findings.append(_finding(
            "F",
            "Pass" if inspections or ncrs else "Warn",
            f"QC live: inspections={len(inspections)} ncrs={len(ncrs)} ncrs-linked-to-beam/pour/batch={linked}. "
            f"Routes: /inspection /tension /camber /finish /release /ncr.",
            "" if (inspections or ncrs) else "Run QIR and file NCR against the open job beam — do not bypass gates.",
        ))

    findings.extend(_static_implementation_findings())
    findings.append(_finding(
        "I",
        "Pass" if role else "cannot verify",
        "Ask Expert is authenticated, read-only, and cannot issue overrides. License gates remain on twin/batch/board/packages.",
        "",
    ))

    if errors:
        live_ok = False

    # De-dupe section C/B when twin_focus produced both static and live rows — keep all; report formatter groups them.
    return {
        "findings": findings,
        "live_ok": live_ok,
        "errors": errors,
        "asked_job": asked_job,
        "asked_mark": asked_mark,
        "spec_id": (target or {}).get("id"),
        "twin_inserts": len(((twin or {}).get("embedded_hardware") or {}).get("insert") or []) if twin else None,
    }


def compose_audit_answer(question: str, live: Optional[Dict[str, Any]] = None) -> str:
    live = live or {}
    findings = list(live.get("findings") or [])
    if not findings:
        findings = [
            _finding(
                sid,
                "cannot verify",
                f"No live snapshot for {title}. Do not guess Pass.",
                f"Ask again while signed in so Ask Expert can read {APIS_HINT.get(sid, 'plant APIs')}.",
            )
            for sid, title in section_titles().items()
        ]
        findings.extend(_static_implementation_findings())
    return format_audit_report(
        findings,
        question=question,
        live_ok=bool(live.get("live_ok")),
        errors=list(live.get("errors") or []),
    )


APIS_HINT = {
    "A": "GET /api/blueprints",
    "B": "GET /api/beam-specs",
    "C": "GET /api/beam-specs/{id}/twin",
    "D": "GET /api/jobs/open",
    "E": "GET /api/auth/me",
    "F": "GET /api/inspections and /api/ncrs",
    "G": "GET /api/batches",
    "H": "GET /api/command-board",
    "I": "role + license gates",
}
