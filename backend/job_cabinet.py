"""Open Job cabinet, Spec-edit gates, and job-scoped rolls / QC photos.

Plant Manager (admin/executive) may edit jobs, lock Spec DNA, and change structure.
QC Supervisor may do the same only with a logged override that proves a Plant Manager
password plus a written note. QC Tech is read-only on Spec DNA. No hardcoded passcodes.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, UploadFile
from models import Beam, Job, JobCreate, Pour, new_id, now_iso
from db import db
from auth import get_current_user, verify_password
from beam_spec import beam_record_from_locked_spec

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).parent
ROLL_STORAGE_DIR = ROOT_DIR / "uploads" / "rolls"
QC_PHOTO_STORAGE_DIR = ROOT_DIR / "uploads" / "qc-photos"

PLANT_MANAGER_ROLES = {"admin", "executive"}
SUPERVISOR_ROLES = {"qc_supervisor"}
BLUEPRINT_ADMIN_ROLES = {"admin", "executive", "qc_supervisor"}
QC_PHOTO_KINDS = ("strand_pattern", "side_profile", "marked_end_profile")
OVERRIDE_HOURS = 4
L25390_JOB_NUMBER = "L25390"

ROLL_FIELD_KEYS = (
    "heat_number",
    "reel_number",
    "lot_number",
    "pack_weight",
    "pack_length",
    "astm_standard",
    "strand_grade",
    "strand_type",
    "nominal_diameter",
    "area_in2",
    "received_date",
)


def role_can_edit_unsupervised(role: Optional[str]) -> bool:
    return (role or "") in PLANT_MANAGER_ROLES


def role_can_request_override(role: Optional[str]) -> bool:
    return (role or "") in SUPERVISOR_ROLES


def role_can_open_blueprint_studio(role: Optional[str]) -> bool:
    return (role or "") in BLUEPRINT_ADMIN_ROLES


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _expires_iso(hours: int = OVERRIDE_HOURS) -> str:
    return (_utc_now() + timedelta(hours=hours)).isoformat()


def decorate_job(job: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not job:
        return None
    job.setdefault("status", "open")
    job.setdefault("document_ids", [])
    job.setdefault("notes", "")
    job.setdefault("updated_at", job.get("created_at") or now_iso())
    return job


async def privileges_for(user: Dict[str, Any]) -> Dict[str, Any]:
    override = await active_override(user)
    can_edit = role_can_edit_unsupervised(user.get("role")) or bool(override)
    return {
        "role": user.get("role"),
        "can_edit_job": can_edit,
        "can_lock": can_edit,
        "can_patch_spec": can_edit,
        "can_request_override": role_can_request_override(user.get("role")),
        "can_open_blueprints": role_can_open_blueprint_studio(user.get("role")),
        "override_active": bool(override),
        "override_expires_at": (override or {}).get("expires_at"),
        "override_note": (override or {}).get("note") if override else None,
    }


async def active_override(user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        row = await db.job_edit_overrides.find_one(
            {"user_id": user.get("id"), "revoked": False},
            {"_id": 0},
        )
        if not row:
            return None
        expires = str(row.get("expires_at") or "")
        if expires and expires < now_iso():
            return None
        return row
    except Exception:
        logger.exception("Failed to load job override user_id=%s", user.get("id"))
        raise


async def can_edit_job_structure(user: Dict[str, Any]) -> bool:
    if role_can_edit_unsupervised(user.get("role")):
        return True
    if role_can_request_override(user.get("role")):
        return bool(await active_override(user))
    return False


async def require_job_editor(user: dict = Depends(get_current_user)):
    if await can_edit_job_structure(user):
        return user
    raise HTTPException(
        status_code=403,
        detail="Plant Manager authorization is required to edit this job. QC Supervisor needs a logged override.",
    )


async def require_blueprint_studio(user: dict = Depends(get_current_user)):
    if role_can_open_blueprint_studio(user.get("role")):
        return user
    raise HTTPException(
        status_code=403,
        detail="Blueprint administration is limited to Plant Manager and QC Supervisor.",
    )


async def require_spec_editor(user: dict = Depends(get_current_user)):
    if not role_can_open_blueprint_studio(user.get("role")):
        raise HTTPException(
            status_code=403,
            detail="Spec DNA is read-only for this role.",
        )
    if await can_edit_job_structure(user):
        return user
    raise HTTPException(
        status_code=403,
        detail="Spec DNA edits require Plant Manager authorization or an approved QC Supervisor override.",
    )


async def issue_override(user: Dict[str, Any], note: str, manager_email: str, manager_password: str) -> Dict[str, Any]:
    if not role_can_request_override(user.get("role")):
        logger.info("Rejected job override request role=%s user=%s", user.get("role"), user.get("email"))
        raise HTTPException(status_code=403, detail="Only a QC Supervisor can request a Plant Manager override.")
    cleaned_note = (note or "").strip()
    if len(cleaned_note) < 8:
        raise HTTPException(status_code=400, detail="Override requires a written proof note.")
    email = (manager_email or "").lower().strip()
    manager = await db.users.find_one({"email": email})
    if not manager or not role_can_edit_unsupervised(manager.get("role")):
        logger.info("Job override failed: manager not authorized email=%s", email)
        raise HTTPException(status_code=403, detail="Plant Manager credentials were not accepted.")
    hashed = manager.get("password_hash")
    if not hashed or not verify_password(manager_password, hashed):
        logger.info("Job override failed: manager password mismatch manager_id=%s", manager.get("id"))
        raise HTTPException(status_code=403, detail="Plant Manager credentials were not accepted.")
    record = {
        "id": new_id(),
        "user_id": user["id"],
        "user_email": user.get("email"),
        "manager_id": manager["id"],
        "manager_email": manager.get("email"),
        "note": cleaned_note,
        "revoked": False,
        "created_at": now_iso(),
        "expires_at": _expires_iso(),
    }
    try:
        await db.job_edit_overrides.update_many(
            {"user_id": user["id"], "revoked": False},
            {"$set": {"revoked": True, "revoked_at": now_iso()}},
        )
        await db.job_edit_overrides.insert_one(dict(record))
        logger.info(
            "Issued job override override_id=%s supervisor=%s manager_id=%s",
            record["id"],
            user.get("email"),
            manager.get("id"),
        )
    except Exception:
        logger.exception("Failed to persist job override user_id=%s", user.get("id"))
        raise
    public = {key: value for key, value in record.items() if key != "_id"}
    return public


async def revoke_override(user: Dict[str, Any]) -> Dict[str, Any]:
    try:
        result = await db.job_edit_overrides.update_many(
            {"user_id": user["id"], "revoked": False},
            {"$set": {"revoked": True, "revoked_at": now_iso()}},
        )
        logger.info("Revoked job overrides user=%s matched=%s", user.get("email"), result.matched_count)
        return {"revoked": True}
    except Exception:
        logger.exception("Failed to revoke job override user_id=%s", user.get("id"))
        raise


async def _cast_home_for_job(job_id: str) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Resolve an existing plant bed and the job pour. Does not invent a bed."""
    pour = None
    bed = None
    try:
        pour = await db.pours.find_one({"job_id": job_id}, {"_id": 0})
        if pour and pour.get("id"):
            bed = await db.beds.find_one({"current_pour_id": pour["id"]}, {"_id": 0})
        if not bed:
            beds = await db.beds.find({}, {"_id": 0}).to_list(50)
            beds = sorted(beds, key=lambda item: item.get("bed_number") or 0)
            bed = beds[0] if beds else None
    except Exception:
        logger.exception("Failed to resolve bed/pour for beam materialize job_id=%s", job_id)
        raise
    return bed, pour


async def materialize_beams_from_locked_specs(specs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create one beam row per locked Spec mark. Idempotent on job_id + mark."""
    created_or_linked: List[Dict[str, Any]] = []
    locked = [
        spec for spec in (specs or [])
        if spec and spec.get("status") == "locked" and spec.get("beam_mark") and spec.get("job_id")
    ]
    locked.sort(key=lambda spec: str(spec.get("beam_mark") or ""))
    homes: Dict[str, tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = {}
    next_position: Dict[str, int] = {}
    try:
        for spec in locked:
            job_id = spec.get("job_id")
            mark = str(spec.get("beam_mark") or "").strip()
            if job_id not in homes:
                homes[job_id] = await _cast_home_for_job(job_id)
            bed, pour = homes[job_id]
            if not bed or not bed.get("id"):
                logger.error("Cannot materialize beam mark=%s job_id=%s — no plant bed exists", mark, job_id)
                continue
            existing = None
            if spec.get("beam_id"):
                existing = await db.beams.find_one({"id": spec["beam_id"]}, {"_id": 0})
            if not existing:
                existing = await db.beams.find_one({"job_id": job_id, "mark": mark}, {"_id": 0})
            if existing:
                payload = beam_record_from_locked_spec(
                    spec,
                    bed_id=existing.get("bed_id") or bed["id"],
                    pour_id=existing.get("pour_id") or (pour or {}).get("id"),
                    position_on_bed=existing.get("position_on_bed") or 1,
                )
                if not payload:
                    continue
                updates = {
                    "spec_id": payload.get("spec_id"),
                    "job_id": job_id,
                    "twin_type": payload.get("twin_type"),
                    "length_ft": payload.get("length_ft"),
                    "traceability": payload.get("traceability") or existing.get("traceability") or {},
                    "blueprint_document_id": payload.get("blueprint_document_id"),
                    "locked_blueprint_revision_id": payload.get("locked_blueprint_revision_id"),
                }
                await db.beams.update_one({"id": existing["id"]}, {"$set": updates})
                beam_id = existing["id"]
            else:
                if job_id not in next_position:
                    existing_on_job = await db.beams.find({"job_id": job_id}, {"_id": 0, "position_on_bed": 1}).to_list(500)
                    used = [int(item.get("position_on_bed") or 0) for item in existing_on_job]
                    next_position[job_id] = (max(used) if used else 0) + 1
                payload = beam_record_from_locked_spec(
                    spec,
                    bed_id=bed["id"],
                    pour_id=(pour or {}).get("id"),
                    position_on_bed=next_position[job_id],
                )
                if not payload:
                    continue
                beam = Beam(**payload)
                await db.beams.insert_one(beam.model_dump())
                beam_id = beam.id
                next_position[job_id] += 1
                logger.info("Materialized beam id=%s mark=%s job_id=%s spec_id=%s", beam_id, mark, job_id, spec.get("id"))
            if spec.get("beam_id") != beam_id:
                await db.beam_specs.update_one({"id": spec["id"]}, {"$set": {"beam_id": beam_id, "updated_at": now_iso()}})
                spec["beam_id"] = beam_id
            created_or_linked.append({"id": beam_id, "mark": mark, "spec_id": spec.get("id"), "job_id": job_id})
        logger.info("Beam materialize from locked specs count=%s marks=%s", len(created_or_linked), [item["mark"] for item in created_or_linked])
        return created_or_linked
    except Exception:
        logger.exception("Failed to materialize beams from locked Spec DNA")
        raise


async def materialize_beams_for_job(job_id: str) -> List[Dict[str, Any]]:
    """One-shot / repeatable backfill: locked Specs on this job become beam rows."""
    try:
        job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
        if not job:
            return []
        query: Dict[str, Any] = {"status": "locked"}
        clauses = [{"job_id": job_id}]
        if job.get("job_number"):
            clauses.append({"job_number": job["job_number"]})
        query["$or"] = clauses
        specs = await db.beam_specs.find(query, {"_id": 0}).to_list(500)
        for spec in specs:
            if not spec.get("job_id"):
                spec["job_id"] = job_id
        return await materialize_beams_from_locked_specs(specs)
    except Exception:
        logger.exception("Failed to backfill beams for job_id=%s", job_id)
        raise


async def ensure_l25390_job() -> Dict[str, Any]:
    """Create or attach Job L25390 so locked Specs have an Open Job cabinet."""
    try:
        job = decorate_job(await db.jobs.find_one({"job_number": L25390_JOB_NUMBER}, {"_id": 0}))
        if not job:
            created = Job(
                job_number=L25390_JOB_NUMBER,
                name="Larue County girders",
                customer="Kentucky Transportation Cabinet",
                state_spec="KYTC",
                status="open",
                notes="Open Job cabinet for locked L25390 Spec DNA.",
            )
            job = created.model_dump()
            await db.jobs.insert_one(dict(job))
            logger.info("Created Open Job L25390 id=%s", job["id"])
        specs = await db.beam_specs.find(
            {"job_number": L25390_JOB_NUMBER},
            {"_id": 0, "id": 1, "document_id": 1, "beam_id": 1, "beam_mark": 1},
        ).to_list(200)
        doc_ids = []
        for spec in specs:
            document_id = spec.get("document_id")
            if document_id and document_id not in doc_ids:
                doc_ids.append(document_id)
        hint_docs = await db.blueprint_documents.find(
            {
                "$or": [
                    {"job_id": job["id"]},
                    {"project_name_hint": {"$regex": "L25390", "$options": "i"}},
                ]
            },
            {"_id": 0, "id": 1},
        ).to_list(100)
        for document in hint_docs:
            if document.get("id") and document["id"] not in doc_ids:
                doc_ids.append(document["id"])
        spec_result = await db.beam_specs.update_many(
            {
                "job_number": L25390_JOB_NUMBER,
                "$or": [{"job_id": None}, {"job_id": {"$exists": False}}, {"job_id": ""}],
            },
            {"$set": {"job_id": job["id"]}},
        )
        beam_ids = [item.get("beam_id") for item in specs if item.get("beam_id")]
        marks = [item.get("beam_mark") for item in specs if item.get("beam_mark")]
        beam_clauses = []
        if beam_ids:
            beam_clauses.append({"id": {"$in": beam_ids}})
        if marks:
            beam_clauses.append({"mark": {"$in": marks}})
        if beam_clauses:
            await db.beams.update_many({"$or": beam_clauses}, {"$set": {"job_id": job["id"]}})
        if doc_ids:
            await db.blueprint_documents.update_many(
                {"id": {"$in": doc_ids}},
                {"$set": {"job_id": job["id"]}},
            )
        pour = await db.pours.find_one({"job_id": job["id"]}, {"_id": 0})
        if not pour:
            pour = Pour(
                job_id=job["id"],
                pour_number="P-L25390-1",
                pour_date=_utc_now().date().isoformat(),
                concrete_mix="",
                status="active",
            ).model_dump()
            await db.pours.insert_one(dict(pour))
            logger.info("Created active pour for L25390 pour_id=%s", pour["id"])
        updates = {}
        if job.get("status") not in ("open", "hold", "complete"):
            updates["status"] = "open"
        if sorted(job.get("document_ids") or []) != sorted(doc_ids):
            updates["document_ids"] = doc_ids
        if spec_result.modified_count or updates:
            updates["updated_at"] = now_iso()
            await db.jobs.update_one({"id": job["id"]}, {"$set": updates})
            job.update(updates)
        try:
            await materialize_beams_for_job(job["id"])
        except Exception:
            logger.exception("L25390 beam backfill failed job_id=%s", job.get("id"))
        return decorate_job(job)
    except Exception:
        logger.exception("Failed to ensure Open Job L25390")
        raise


async def list_jobs_decorated() -> List[Dict[str, Any]]:
    await ensure_l25390_job()
    jobs = await db.jobs.find({}, {"_id": 0}).to_list(500)
    decorated = []
    for job in jobs:
        item = decorate_job(job)
        spec_count = await db.beam_specs.count_documents({"job_id": item["id"]})
        if spec_count == 0:
            spec_count = await db.beam_specs.count_documents({"job_number": item.get("job_number")})
        item["spec_count"] = spec_count
        item["pour_count"] = await db.pours.count_documents({"job_id": item["id"]})
        decorated.append(item)
    decorated.sort(key=lambda item: (0 if item.get("job_number") == L25390_JOB_NUMBER else 1, str(item.get("job_number") or "")))
    return decorated


async def get_open_job_for_user(user: Dict[str, Any]) -> Dict[str, Any]:
    await ensure_l25390_job()
    session = await db.user_open_jobs.find_one({"user_id": user["id"]}, {"_id": 0})
    job = None
    if session and session.get("job_id"):
        job = decorate_job(await db.jobs.find_one({"id": session["job_id"]}, {"_id": 0}))
    if not job:
        job = decorate_job(await db.jobs.find_one({"job_number": L25390_JOB_NUMBER}, {"_id": 0}))
    if not job:
        job = decorate_job(await db.jobs.find_one({}, {"_id": 0}))
    pours = []
    specs = []
    if job:
        pours = await db.pours.find({"job_id": job["id"]}, {"_id": 0}).to_list(50)
        specs = await db.beam_specs.find(
            {"$or": [{"job_id": job["id"]}, {"job_number": job.get("job_number")}]},
            {"_id": 0, "id": 1, "beam_mark": 1, "geometry": 1, "job_number": 1},
        ).to_list(200)
    return {
        "job": job,
        "pours": pours,
        "marks": [item.get("beam_mark") for item in specs if item.get("beam_mark")],
        "privileges": await privileges_for(user),
    }


async def set_open_job_for_user(user: Dict[str, Any], job_id: str) -> Dict[str, Any]:
    job = decorate_job(await db.jobs.find_one({"id": job_id}, {"_id": 0}))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        await db.user_open_jobs.update_one(
            {"user_id": user["id"]},
            {"$set": {"user_id": user["id"], "job_id": job["id"], "updated_at": now_iso()}},
            upsert=True,
        )
        logger.info("Opened job_id=%s job_number=%s user=%s", job["id"], job.get("job_number"), user.get("email"))
    except Exception:
        logger.exception("Failed to persist open job user_id=%s job_id=%s", user.get("id"), job_id)
        raise
    return await get_open_job_for_user(user)


async def create_job_record(payload: JobCreate, user: Dict[str, Any]) -> Dict[str, Any]:
    existing = await db.jobs.find_one({"job_number": payload.job_number.strip()}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="A job with that number already exists")
    job = Job(**payload.model_dump(), status="open").model_dump()
    await db.jobs.insert_one(dict(job))
    logger.info("Created job_id=%s job_number=%s user=%s", job["id"], job["job_number"], user.get("email"))
    return decorate_job(job)


async def patch_job_record(job_id: str, updates: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    allowed_status = {"open", "hold", "complete"}
    cleaned = {key: value for key, value in updates.items() if value is not None}
    if "status" in cleaned and cleaned["status"] not in allowed_status:
        raise HTTPException(status_code=400, detail="Job status must be open, hold, or complete")
    if not cleaned:
        return decorate_job(job)
    cleaned["updated_at"] = now_iso()
    await db.jobs.update_one({"id": job_id}, {"$set": cleaned})
    logger.info("Patched job_id=%s fields=%s user=%s", job_id, sorted(cleaned.keys()), user.get("email"))
    return decorate_job(await db.jobs.find_one({"id": job_id}, {"_id": 0}))


async def job_cabinet(job_id: str) -> Dict[str, Any]:
    job = decorate_job(await db.jobs.find_one({"id": job_id}, {"_id": 0}))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    specs = await db.beam_specs.find(
        {"$or": [{"job_id": job_id}, {"job_number": job.get("job_number")}]},
        {"_id": 0},
    ).to_list(500)
    documents = await db.blueprint_documents.find({"job_id": job_id}, {"_id": 0, "storage_path": 0}).to_list(100)
    pours = await db.pours.find({"job_id": job_id}, {"_id": 0}).to_list(100)
    beams = await db.beams.find({"job_id": job_id}, {"_id": 0}).to_list(500)
    return {
        "job": job,
        "specs": specs,
        "documents": documents,
        "pours": pours,
        "beams": beams,
    }


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "photo.jpg")
    return cleaned[:80] or "photo.jpg"


async def create_roll_from_photos(
    files: List[UploadFile],
    kinds: str,
    user: Dict[str, Any],
    job: Optional[Dict[str, Any]],
    pour: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    roll_id = new_id()
    folder = ROLL_STORAGE_DIR / roll_id
    folder.mkdir(parents=True, exist_ok=True)
    kind_list = [item.strip() or "tag" for item in (kinds or "").split(",")] if kinds else []
    photos = []
    try:
        for index, upload in enumerate(files or []):
            payload = await upload.read()
            if not payload:
                continue
            filename = _safe_filename(upload.filename or f"photo-{index + 1}.jpg")
            path = folder / f"{index + 1}-{filename}"
            path.write_bytes(payload)
            kind = kind_list[index] if index < len(kind_list) else "tag"
            photos.append({
                "id": f"{roll_id}-{index + 1}",
                "kind": kind,
                "filename": path.name,
                "url": f"/api/strand-rolls/{roll_id}/photos/{path.name}",
            })
        roll = {
            "id": roll_id,
            "job_id": (job or {}).get("id"),
            "job_number": (job or {}).get("job_number") or "",
            "pour_id": (pour or {}).get("id"),
            "pour_date": (pour or {}).get("pour_date") or _utc_now().date().isoformat(),
            "bed_id": None,
            "status": "draft",
            "photos": photos,
            "assignments": [],
            "field_confidence": {},
            "low_confidence_fields": ["heat_number"],
            "extractor": "manual",
            "extractor_confidence": 0,
            "logged_by": user.get("name") or user.get("email"),
            "logged_at": now_iso(),
            "confirmed_at": None,
        }
        for key in ROLL_FIELD_KEYS:
            roll[key] = None if key == "area_in2" else ""
        await db.strand_rolls.insert_one(dict(roll))
        logger.info("Stored strand roll draft roll_id=%s job_id=%s photos=%s", roll_id, roll.get("job_id"), len(photos))
        return {key: value for key, value in roll.items() if key != "_id"}
    except Exception:
        logger.exception("Failed to store strand roll photos user=%s", user.get("email"))
        raise HTTPException(status_code=500, detail="Failed to store mill-tag photos")


async def list_rolls(job_id: Optional[str], pour_date: Optional[str]) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {}
    if job_id:
        query["job_id"] = job_id
    if pour_date:
        query["pour_date"] = pour_date
    rows = await db.strand_rolls.find(query, {"_id": 0}).sort("logged_at", -1).to_list(500)
    return rows


async def confirm_roll(roll_id: str, payload: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    roll = await db.strand_rolls.find_one({"id": roll_id}, {"_id": 0})
    if not roll:
        raise HTTPException(status_code=404, detail="Strand roll not found")
    heat = str(payload.get("heat_number") or "").strip()
    if not heat:
        raise HTTPException(status_code=400, detail="Heat number is required")
    duplicate = await db.strand_rolls.find_one({
        "id": {"$ne": roll_id},
        "job_id": roll.get("job_id"),
        "pour_date": roll.get("pour_date"),
        "heat_number": heat,
        "status": {"$in": ["confirmed", "assigned"]},
    }, {"_id": 0, "id": 1})
    if duplicate:
        raise HTTPException(status_code=409, detail="That heat is already logged for this job pour day.")
    updates = {key: payload.get(key) for key in ROLL_FIELD_KEYS if key in payload}
    updates["heat_number"] = heat
    updates["status"] = "confirmed"
    updates["confirmed_at"] = now_iso()
    updates["confirmed_by"] = user.get("name") or user.get("email")
    await db.strand_rolls.update_one({"id": roll_id}, {"$set": updates})
    logger.info("Confirmed strand roll roll_id=%s heat=%s user=%s", roll_id, heat, user.get("email"))
    return await db.strand_rolls.find_one({"id": roll_id}, {"_id": 0})


async def assign_roll(roll_id: str, bed_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    roll = await db.strand_rolls.find_one({"id": roll_id}, {"_id": 0})
    if not roll:
        raise HTTPException(status_code=404, detail="Strand roll not found")
    if roll.get("status") not in ("confirmed", "assigned"):
        raise HTTPException(status_code=400, detail="Confirm the mill tag before assigning it to a bed")
    bed = await db.beds.find_one({"id": bed_id}, {"_id": 0})
    if not bed:
        raise HTTPException(status_code=404, detail="Bed not found")
    assignment = {
        "bed_id": bed_id,
        "bed_number": bed.get("bed_number"),
        "assigned_at": now_iso(),
        "assigned_by": user.get("name") or user.get("email"),
        "pour_number": None,
        "beam_marks": [],
    }
    assignments = list(roll.get("assignments") or [])
    assignments = [item for item in assignments if item.get("bed_id") != bed_id]
    assignments.append(assignment)
    await db.strand_rolls.update_one(
        {"id": roll_id},
        {"$set": {"bed_id": bed_id, "status": "assigned", "assignments": assignments}},
    )
    logger.info("Assigned strand roll roll_id=%s bed_id=%s user=%s", roll_id, bed_id, user.get("email"))
    return {"roll": await db.strand_rolls.find_one({"id": roll_id}, {"_id": 0})}


async def upsert_qc_photo(
    job: Dict[str, Any],
    pour_date: str,
    kind: str,
    upload: UploadFile,
    user: Dict[str, Any],
) -> Dict[str, Any]:
    if kind not in QC_PHOTO_KINDS:
        raise HTTPException(status_code=400, detail="Unknown QC photo kind")
    payload = await upload.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Photo file was empty")
    if len(payload) > 12 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="QC photo exceeds 12 MB")
    folder = QC_PHOTO_STORAGE_DIR / job["id"] / pour_date
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{kind}-{_safe_filename(upload.filename or f'{kind}.jpg')}"
    path = folder / filename
    path.write_bytes(payload)
    record = {
        "id": new_id(),
        "job_id": job["id"],
        "job_number": job.get("job_number"),
        "pour_date": pour_date,
        "kind": kind,
        "filename": filename,
        "storage_path": str(path),
        "url": "",
        "created_by": user.get("name") or user.get("email"),
        "created_at": now_iso(),
    }
    record["url"] = f"/api/job-qc-photos/{record['id']}/file"
    try:
        await db.job_qc_photos.delete_many({"job_id": job["id"], "pour_date": pour_date, "kind": kind})
        await db.job_qc_photos.insert_one(dict(record))
        logger.info("Stored QC photo kind=%s job_id=%s pour_date=%s", kind, job["id"], pour_date)
    except Exception:
        logger.exception("Failed to store QC photo kind=%s job_id=%s", kind, job.get("id"))
        raise HTTPException(status_code=500, detail="Failed to store QC photo")
    return {key: value for key, value in record.items() if key not in ("_id", "storage_path")}


async def list_qc_photos(job_id: str, pour_date: Optional[str]) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {"job_id": job_id}
    if pour_date:
        query["pour_date"] = pour_date
    rows = await db.job_qc_photos.find(query, {"_id": 0, "storage_path": 0}).sort("created_at", -1).to_list(50)
    return rows


async def resolve_open_job_and_pour(user: Dict[str, Any], job_id: Optional[str] = None, pour_date: Optional[str] = None) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    cabinet = await get_open_job_for_user(user)
    job = cabinet.get("job")
    if job_id:
        job = decorate_job(await db.jobs.find_one({"id": job_id}, {"_id": 0})) or job
    pours = cabinet.get("pours") or []
    if job and job.get("id") != (cabinet.get("job") or {}).get("id"):
        pours = await db.pours.find({"job_id": job["id"]}, {"_id": 0}).to_list(50)
    pour = None
    if pour_date:
        pour = next((item for item in pours if item.get("pour_date") == pour_date), None)
    if not pour:
        pour = next((item for item in pours if item.get("status") == "active"), None) or (pours[0] if pours else None)
    return job, pour
