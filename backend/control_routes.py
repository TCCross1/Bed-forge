"""Upper-management control plane — search, people, audit, overrides, backup, security."""
import io
import json
import logging
import re
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from audit import write_audit
from auth import hash_password, require_exec, require_roles
from db import db
from models import (
    OverrideRequest, SecuritySettingsUpdate, UserAdminCreate, UserAdminUpdate, new_id, now_iso,
)
from security_core import EXEC_ROLES, ROLES, client_ip, ip_allowed, parse_cidrs, redact_value
from sessions import revoke_user_sessions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/control", tags=["control"])

EXPORT_COLLECTIONS = {
    "jobs": "jobs",
    "pours": "pours",
    "beds": "beds",
    "beams": "beams",
    "inspections": "inspections",
    "tension_reports": "tension_reports",
    "camber_readings": "camber_readings",
    "finish_sheets": "finish_sheets",
    "pre_delivery": "pre_delivery",
    "strand_rolls": "strand_rolls",
    "anomalies": "anomalies",
    "audit_log": "audit_log",
    "overrides": "overrides",
}

STRIP_FIELDS = {"password_hash": 0, "_id": 0, "photo_data": 0, "raw_text": 0}


async def office_guard(request: Request, user=Depends(require_exec())):
    try:
        settings = await db.company_settings.find_one({"id": "plant"}, {"_id": 0}) or {}
        if settings.get("office_ip_enforced"):
            ip = client_ip(request)
            if not ip_allowed(ip, settings.get("ip_allowlist") or []):
                await write_audit(action="security.ip_denied", user=user, request=request, ok=False)
                raise HTTPException(status_code=403, detail="This plant-manager action must come from an allowed office or VPN address.")
        return user
    except HTTPException:
        raise
    except Exception:
        logger.exception("office_guard failed")
        raise HTTPException(status_code=500, detail="Security check failed")


def _rx(q: str) -> dict:
    return {"$regex": re.escape(q), "$options": "i"}


@router.get("/search")
async def global_search(q: str = Query(..., min_length=2, max_length=80), user=Depends(require_roles(*EXEC_ROLES, "qc_supervisor"))):
    try:
        needle = q.strip()
        rx = _rx(needle)
        jobs = await db.jobs.find({"$or": [{"job_number": rx}, {"name": rx}, {"customer": rx}]}, {"_id": 0}).to_list(20)
        beams = await db.beams.find({"$or": [{"mark": rx}, {"id": needle}]}, {"_id": 0}).to_list(20)
        pours = await db.pours.find({"pour_number": rx}, {"_id": 0}).to_list(20)
        rolls = await db.strand_rolls.find(
            {"$or": [{"heat_number": rx}, {"reel_number": rx}, {"lot_number": rx}]},
            {"_id": 0, "raw_text": 0},
        ).to_list(20)
        users = await db.users.find({"$or": [{"email": rx}, {"name": rx}]}, {"_id": 0, "password_hash": 0}).to_list(20)
        logger.info("global search by=%s hits=%s", user.get("email"), len(jobs) + len(beams) + len(pours) + len(rolls))
        return {"q": needle, "jobs": jobs, "beams": beams, "pours": pours, "strand_rolls": rolls, "users": users}
    except Exception:
        logger.exception("global_search failed")
        raise HTTPException(status_code=500, detail="Search failed")


@router.get("/users")
async def control_users(user=Depends(office_guard)):
    try:
        rows = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(500)
        return {"users": rows}
    except Exception:
        logger.exception("control_users failed")
        raise HTTPException(status_code=500, detail="Failed to list users")


@router.post("/users")
async def create_user(payload: UserAdminCreate, request: Request, user=Depends(office_guard)):
    try:
        email = payload.email.lower()
        if await db.users.find_one({"email": email}):
            raise HTTPException(status_code=400, detail="Email already exists")
        role = payload.role if payload.role in ROLES else "qc_tech"
        rec = {
            "id": new_id(),
            "email": email,
            "password_hash": hash_password(payload.password),
            "name": payload.name,
            "role": role,
            "disabled": False,
            "must_change_password": True,
            "created_at": now_iso(),
            "created_by": user.get("email"),
        }
        await db.users.insert_one(rec)
        await write_audit(action="user.create", user=user, request=request, entity_type="user", entity_id=rec["id"], after={"email": email, "role": role})
        logger.info("user created email=%s role=%s by=%s", email, role, user.get("email"))
        rec.pop("password_hash", None)
        return rec
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_user failed")
        raise HTTPException(status_code=500, detail="Failed to create user")


@router.patch("/users/{user_id}")
async def update_user(user_id: str, payload: UserAdminUpdate, request: Request, user=Depends(office_guard)):
    try:
        target = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
        if target.get("id") == user.get("id") and payload.disabled:
            raise HTTPException(status_code=400, detail="You cannot disable your own account")
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        if updates.get("role") and updates["role"] not in ROLES:
            raise HTTPException(status_code=400, detail="Unknown role")
        if not updates:
            return target
        updates["updated_at"] = now_iso()
        await db.users.update_one({"id": user_id}, {"$set": updates})
        if updates.get("disabled"):
            await revoke_user_sessions(user_id, "disabled")
        saved = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        await write_audit(action="user.update", user=user, request=request, entity_type="user", entity_id=user_id, before=target, after=saved)
        logger.info("user updated id=%s by=%s", user_id, user.get("email"))
        return saved
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_user failed")
        raise HTTPException(status_code=500, detail="Failed to update user")


@router.post("/users/{user_id}/revoke")
async def revoke_user(user_id: str, request: Request, user=Depends(office_guard)):
    try:
        target = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
        sessions = await revoke_user_sessions(user_id, "manager_revoke")
        devices = await db.devices.update_many({"user_id": user_id}, {"$set": {"revoked": True, "revoked_at": now_iso(), "revoked_by": user.get("email")}})
        await write_audit(action="user.revoke", user=user, request=request, entity_type="user", entity_id=user_id, extra={"sessions": sessions})
        logger.info("user revoked id=%s sessions=%s by=%s", user_id, sessions, user.get("email"))
        return {"ok": True, "sessions_revoked": sessions, "devices_revoked": int(devices.modified_count or 0)}
    except HTTPException:
        raise
    except Exception:
        logger.exception("revoke_user failed")
        raise HTTPException(status_code=500, detail="Failed to revoke user")


@router.get("/devices")
async def list_devices(user=Depends(office_guard)):
    try:
        rows = await db.devices.find({}, {"_id": 0, "push_token": 0}).sort("updated_at", -1).to_list(500)
        return {"devices": rows}
    except Exception:
        logger.exception("list_devices failed")
        raise HTTPException(status_code=500, detail="Failed to list devices")


@router.post("/devices/{device_id}/revoke")
async def revoke_device(device_id: str, request: Request, user=Depends(office_guard)):
    try:
        rec = await db.devices.find_one({"id": device_id}, {"_id": 0})
        if not rec:
            raise HTTPException(status_code=404, detail="Device not found")
        await db.devices.update_one({"id": device_id}, {"$set": {"revoked": True, "revoked_at": now_iso(), "revoked_by": user.get("email")}})
        await db.sessions.update_many(
            {"device_id": device_id, "revoked": {"$ne": True}},
            {"$set": {"revoked": True, "revoked_reason": "device", "revoked_at": now_iso()}},
        )
        await write_audit(action="device.revoke", user=user, request=request, entity_type="device", entity_id=device_id)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        logger.exception("revoke_device failed")
        raise HTTPException(status_code=500, detail="Failed to revoke device")


@router.get("/audit")
async def list_audit(limit: int = 100, action: Optional[str] = None, user=Depends(office_guard)):
    try:
        query = {"action": action} if action else {}
        rows = await db.audit_log.find(query, {"_id": 0}).sort("created_at", -1).to_list(max(1, min(limit, 500)))
        return {"events": rows, "count": len(rows)}
    except Exception:
        logger.exception("list_audit failed")
        raise HTTPException(status_code=500, detail="Failed to load audit log")


@router.get("/security")
async def get_security(user=Depends(office_guard)):
    try:
        doc = await db.company_settings.find_one({"id": "plant"}, {"_id": 0}) or {}
        return {
            "session_minutes": doc.get("session_minutes", 480),
            "idle_minutes": doc.get("idle_minutes", 30),
            "ip_allowlist": doc.get("ip_allowlist") or [],
            "office_ip_enforced": bool(doc.get("office_ip_enforced")),
            "bind_device": bool(doc.get("bind_device")),
            "retention_days": doc.get("retention_days", 2555),
            "camber_tolerance_in": doc.get("camber_tolerance_in", 0.125),
            "length_tolerance_in": doc.get("length_tolerance_in", 0.5),
            "legal_hold": bool(doc.get("legal_hold")),
            "ncr_cost_usd": doc.get("ncr_cost_usd", 2500),
            "scrap_cost_usd": doc.get("scrap_cost_usd", 8000),
            "bed_day_cost_usd": doc.get("bed_day_cost_usd", 3500),
            "overtime_hold_usd": doc.get("overtime_hold_usd", 1800),
            "required_release_psi": doc.get("required_release_psi", 4000),
            "maturity_su_psi": doc.get("maturity_su_psi", 8500),
            "maturity_k_hours": doc.get("maturity_k_hours", 18),
        }
    except Exception:
        logger.exception("get_security failed")
        raise HTTPException(status_code=500, detail="Failed to load security settings")


@router.patch("/security")
async def update_security(payload: SecuritySettingsUpdate, request: Request, user=Depends(office_guard)):
    try:
        before = await db.company_settings.find_one({"id": "plant"}, {"_id": 0}) or {}
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        if "ip_allowlist" in updates:
            parse_cidrs(updates["ip_allowlist"])
        if not updates:
            return await get_security(user)
        updates["updated_by"] = user.get("email")
        updates["updated_at"] = now_iso()
        await db.company_settings.update_one({"id": "plant"}, {"$set": updates}, upsert=True)
        saved = await get_security(user)
        await write_audit(action="security.update", user=user, request=request, entity_type="company", entity_id="plant", before=redact_value(before), after=saved)
        logger.info("security settings updated by=%s", user.get("email"))
        return saved
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_security failed")
        raise HTTPException(status_code=500, detail="Failed to update security settings")


@router.post("/override")
async def create_override(payload: OverrideRequest, request: Request, user=Depends(office_guard)):
    try:
        kind = payload.kind.strip()
        if kind not in ("strand_tension", "spec_unlock", "qc_force"):
            raise HTTPException(status_code=400, detail="Unknown override kind")
        if not payload.reason.strip():
            raise HTTPException(status_code=400, detail="A written reason is required")
        expires = (datetime.now(timezone.utc) + timedelta(hours=max(1, min(payload.hours, 72)))).isoformat()
        rec = {
            "id": new_id(),
            "kind": kind,
            "target_id": payload.target_id,
            "reason": payload.reason.strip()[:500],
            "created_by": user.get("email"),
            "created_at": now_iso(),
            "expires_at": expires,
            "revoked": False,
        }
        if kind == "spec_unlock":
            spec = await db.beam_specs.find_one({"id": payload.target_id}, {"_id": 0})
            if not spec:
                raise HTTPException(status_code=404, detail="BeamSpec not found")
            await db.beam_specs.update_one({"id": payload.target_id}, {"$set": {"status": "reviewed", "unlocked_by": user.get("email"), "unlocked_at": now_iso()}})
        if kind == "qc_force":
            beam = await db.beams.find_one({"id": payload.target_id}, {"_id": 0})
            if not beam:
                raise HTTPException(status_code=404, detail="Beam not found")
            rec["before_qc_state"] = beam.get("qc_state")
            await db.beams.update_one({"id": payload.target_id}, {"$set": {"qc_state": "passed", "override_reason": payload.reason.strip()}})
        await db.overrides.insert_one(rec)
        await write_audit(action="override.create", user=user, request=request, entity_type=kind, entity_id=payload.target_id, after=rec, reason=payload.reason)
        logger.info("override kind=%s target=%s by=%s", kind, payload.target_id, user.get("email"))
        rec.pop("_id", None)
        return rec
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_override failed")
        raise HTTPException(status_code=500, detail="Failed to create override")


@router.get("/overrides")
async def list_overrides(user=Depends(office_guard)):
    try:
        rows = await db.overrides.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
        return {"overrides": rows}
    except Exception:
        logger.exception("list_overrides failed")
        raise HTTPException(status_code=500, detail="Failed to list overrides")


@router.post("/overrides/{override_id}/revoke")
async def revoke_override(override_id: str, request: Request, user=Depends(office_guard)):
    try:
        rec = await db.overrides.find_one({"id": override_id}, {"_id": 0})
        if not rec:
            raise HTTPException(status_code=404, detail="Override not found")
        await db.overrides.update_one({"id": override_id}, {"$set": {"revoked": True, "revoked_by": user.get("email"), "revoked_at": now_iso()}})
        await write_audit(action="override.revoke", user=user, request=request, entity_type="override", entity_id=override_id)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        logger.exception("revoke_override failed")
        raise HTTPException(status_code=500, detail="Failed to revoke override")


@router.get("/export/{collection}")
async def export_collection(collection: str, request: Request, user=Depends(office_guard)):
    try:
        name = EXPORT_COLLECTIONS.get(collection)
        if not name:
            raise HTTPException(status_code=404, detail="Unknown data set")
        rows = await db[name].find({}, STRIP_FIELDS).to_list(5000)
        await write_audit(action="export.dataset", user=user, request=request, entity_type=name, extra={"count": len(rows)})
        payload = json.dumps(redact_value(rows), default=str).encode("utf-8")
        logger.info("export collection=%s count=%s by=%s", name, len(rows), user.get("email"))
        return StreamingResponse(
            io.BytesIO(payload),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={name}.json"},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("export_collection failed")
        raise HTTPException(status_code=500, detail="Failed to export data")


@router.get("/backup")
async def backup_plant(request: Request, user=Depends(office_guard)):
    try:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in EXPORT_COLLECTIONS.values():
                rows = await db[name].find({}, STRIP_FIELDS).to_list(8000)
                zf.writestr(f"{name}.json", json.dumps(redact_value(rows), default=str))
            users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(500)
            zf.writestr("users.json", json.dumps(users, default=str))
            zf.writestr("RESTORE.txt", "Restore is an offline plant-manager procedure. Stop the app, restore MongoDB from this JSON, restore encrypted files from the uploads volume, then start BedForge. Never restore onto a live attacked host.")
        await write_audit(action="export.backup", user=user, request=request, entity_type="plant")
        logger.info("backup generated by=%s", user.get("email"))
        buf.seek(0)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=bedforge-backup-{stamp}.zip"},
        )
    except Exception:
        logger.exception("backup_plant failed")
        raise HTTPException(status_code=500, detail="Failed to build backup")


@router.get("/retention")
async def retention_report(user=Depends(office_guard)):
    try:
        settings = await db.company_settings.find_one({"id": "plant"}, {"_id": 0}) or {}
        days = int(settings.get("retention_days") or 2555)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        hold = bool(settings.get("legal_hold"))
        counts = {}
        for name in ("beams", "inspections", "strand_rolls", "ar_measurements"):
            counts[name] = await db[name].count_documents({"created_at": {"$lt": cutoff}})
        return {"retention_days": days, "legal_hold": hold, "cutoff": cutoff, "eligible_counts": counts, "purge_blocked": hold}
    except Exception:
        logger.exception("retention_report failed")
        raise HTTPException(status_code=500, detail="Failed to load retention report")
