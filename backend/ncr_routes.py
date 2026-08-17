"""NCR API — create, workflow, photos, export. Anomalies stay the twin pin; NCRs are the accountability record."""
import csv
import io
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from audit import write_audit
from auth import get_current_user
from company_routes import get_company_doc, public_view
from db import db
from models import NCR, NCRCreate, NCRTransition, NCRUpdate, now_iso, new_id
from ncr import (
    OPEN_STATUSES,
    can_create,
    can_raise_severity,
    frequency_insights,
    is_immutable,
    match_open_source,
    ncr_from_anomaly,
    photo_filenames,
    public_ncr,
    sanitize_category,
    sanitize_severity,
    sanitize_status,
    transition_blockers,
)
from storage import company_logo_path, file_response, save_vault_file, vault_file_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["ncr"])
PHOTO_MAX = 8 * 1024 * 1024
PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def _history_row(user: dict, action: str, note: str = "", status: str = "") -> dict:
    return {
        "at": now_iso(),
        "by": (user or {}).get("email") or (user or {}).get("name") or "",
        "role": (user or {}).get("role") or "",
        "action": action,
        "status": status,
        "note": (note or "")[:500],
    }


def _media_type(filename: str) -> str:
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in (filename or "") else ".jpg"
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(ext, "image/jpeg")


async def _ncr(ncr_id: str) -> dict:
    rec = await db.ncrs.find_one({"id": ncr_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="NCR not found")
    return rec


async def _fill_identity(data: dict) -> dict:
    beam_ids = [str(b) for b in (data.get("beam_ids") or []) if b]
    if data.get("beam_id") and data["beam_id"] not in beam_ids:
        beam_ids.insert(0, str(data["beam_id"]))
    data["beam_ids"] = beam_ids
    if beam_ids and (not data.get("job_id") or not data.get("pour_id") or not data.get("bed_id")):
        beam = await db.beams.find_one({"id": beam_ids[0]}, {"_id": 0})
        if beam:
            data["job_id"] = data.get("job_id") or beam.get("job_id") or ""
            data["pour_id"] = data.get("pour_id") or beam.get("pour_id") or ""
            data["bed_id"] = data.get("bed_id") or beam.get("bed_id") or ""
    return data


async def _existing_open(source_type: str = "", source_id: str = "", anomaly_id: str = "") -> Optional[dict]:
    q_or = []
    if anomaly_id:
        q_or.append({"anomaly_id": anomaly_id})
    if source_id and source_type not in ("", "manual"):
        q_or.append({"source_type": source_type, "source_id": source_id})
    if not q_or:
        return None
    rows = await db.ncrs.find({"$or": q_or, "status": {"$in": list(OPEN_STATUSES)}}, {"_id": 0}).to_list(20)
    return match_open_source(rows, source_type=source_type, source_id=source_id, anomaly_id=anomaly_id)


async def open_ncr_from_anomaly(anomaly: dict, user: dict, request: Optional[Request] = None) -> dict:
    """One NCR per twin pin. Never a second disconnected defect row."""
    if not can_create((user or {}).get("role") or ""):
        raise HTTPException(status_code=403, detail="Not allowed to file an NCR")
    existing = await _existing_open(source_type="anomaly", source_id=anomaly.get("id") or "", anomaly_id=anomaly.get("id") or "")
    if existing:
        logger.info("ncr from anomaly idempotent id=%s anomaly=%s", existing.get("id"), anomaly.get("id"))
        return public_ncr(existing)
    beam = await db.beams.find_one({"id": anomaly.get("beam_id")}, {"_id": 0}) if anomaly.get("beam_id") else None
    payload = ncr_from_anomaly(anomaly, beam)
    rec = NCR(
        **{k: v for k, v in payload.items() if k in NCR.model_fields},
        discovered_by=(user or {}).get("name") or "",
        created_by=(user or {}).get("email") or "",
        history=[_history_row(user, "create", "Opened from 3D twin pin", "open")],
    )
    stored = rec.model_dump()
    await db.ncrs.insert_one(stored)
    await db.anomalies.update_one({"id": anomaly.get("id")}, {"$set": {"ncr_id": rec.id}})
    if rec.severity in ("major", "critical") and rec.beam_ids:
        await db.beams.update_one({"id": rec.beam_ids[0]}, {"$set": {"qc_state": "hold"}})
    await write_audit(action="ncr.create", user=user, request=request, entity_type="ncr", entity_id=rec.id, extra={"source": "anomaly"})
    logger.info("ncr from anomaly id=%s anomaly=%s by=%s", rec.id, anomaly.get("id"), (user or {}).get("email"))
    return public_ncr(stored)


@router.get("/ncrs")
async def list_ncrs(
    beam_id: Optional[str] = None,
    bed_id: Optional[str] = None,
    job_id: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    overdue: Optional[bool] = None,
    user=Depends(get_current_user),
):
    try:
        q = {}
        if beam_id:
            q["beam_ids"] = str(beam_id)
        if bed_id:
            q["bed_id"] = str(bed_id)
        if job_id:
            q["job_id"] = str(job_id)
        if status:
            q["status"] = sanitize_status(status)
        if severity:
            q["severity"] = sanitize_severity(severity)
        rows = await db.ncrs.find(q, {"_id": 0}).sort("created_at", -1).to_list(400)
        out = [public_ncr(r) for r in rows]
        if overdue:
            out = [r for r in out if r.get("overdue") or r.get("escalated")]
        logger.info("ncrs listed count=%s by=%s", len(out), user.get("email"))
        return out
    except Exception:
        logger.exception("list_ncrs failed")
        raise HTTPException(status_code=500, detail="Failed to list NCRs")


@router.get("/ncrs/insights")
async def ncr_insights(user=Depends(get_current_user)):
    try:
        rows = await db.ncrs.find({}, {"_id": 0}).sort("created_at", -1).to_list(400)
        recs = frequency_insights(rows)
        logger.info("ncr insights count=%s by=%s", len(recs), user.get("email"))
        return {
            "ai_writes_mix": False,
            "recommendations": recs,
            "open": sum(1 for r in rows if r.get("status") not in ("closed", "rejected")),
        }
    except Exception:
        logger.exception("ncr_insights failed")
        raise HTTPException(status_code=500, detail="Failed to load NCR insights")


@router.get("/ncrs/{ncr_id}")
async def get_ncr(ncr_id: str, user=Depends(get_current_user)):
    try:
        return public_ncr(await _ncr(ncr_id))
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_ncr failed")
        raise HTTPException(status_code=500, detail="Failed to load NCR")


@router.post("/ncrs")
async def create_ncr(payload: NCRCreate, request: Request, user=Depends(get_current_user)):
    try:
        if not can_create(user.get("role") or ""):
            raise HTTPException(status_code=403, detail="Not allowed to file an NCR")
        data = payload.model_dump()
        if not (data.get("description") or "").strip():
            raise HTTPException(status_code=400, detail="Describe the non-conformance")
        if not (data.get("containment") or "").strip():
            raise HTTPException(status_code=400, detail="Record the immediate containment action")
        data = await _fill_identity(data)
        existing = await _existing_open(
            source_type=data.get("source_type") or "",
            source_id=data.get("source_id") or "",
            anomaly_id=data.get("anomaly_id") or "",
        )
        if existing:
            logger.info("ncr create idempotent id=%s source=%s by=%s", existing.get("id"), data.get("source_type"), user.get("email"))
            return public_ncr(existing)
        rec = NCR(
            **{k: v for k, v in data.items() if k in NCR.model_fields},
            category=sanitize_category(data.get("category")),
            severity=sanitize_severity(data.get("severity")),
            discovered_by=user.get("name") or "",
            created_by=user.get("email") or "",
            history=[_history_row(user, "create", "Filed", "open")],
        )
        stored = rec.model_dump()
        await db.ncrs.insert_one(stored)
        if rec.severity in ("major", "critical") and rec.beam_ids:
            await db.beams.update_one({"id": rec.beam_ids[0]}, {"$set": {"qc_state": "hold"}})
        await write_audit(action="ncr.create", user=user, request=request, entity_type="ncr", entity_id=rec.id)
        logger.info("ncr created id=%s sev=%s cat=%s by=%s", rec.id, rec.severity, rec.category, user.get("email"))
        return public_ncr(stored)
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_ncr failed")
        raise HTTPException(status_code=500, detail="Failed to file NCR")


@router.patch("/ncrs/{ncr_id}")
async def update_ncr(ncr_id: str, payload: NCRUpdate, request: Request, user=Depends(get_current_user)):
    try:
        rec = await _ncr(ncr_id)
        if is_immutable(rec):
            raise HTTPException(status_code=409, detail="Closed NCRs are immutable. A supervisor reopens with a written reason.")
        patch = {k: v for k, v in payload.model_dump().items() if v is not None}
        if "category" in patch:
            patch["category"] = sanitize_category(patch["category"])
        if "severity" in patch:
            patch["severity"] = sanitize_severity(patch["severity"])
            if not can_raise_severity(user.get("role") or "", rec.get("severity"), patch["severity"]):
                raise HTTPException(status_code=403, detail="Only a supervisor can raise NCR severity")
        rec.update(patch)
        rec["updated_at"] = now_iso()
        rec.setdefault("history", []).append(_history_row(user, "edit", "Fields updated", rec.get("status")))
        await db.ncrs.replace_one({"id": ncr_id}, rec)
        await write_audit(action="ncr.update", user=user, request=request, entity_type="ncr", entity_id=ncr_id)
        logger.info("ncr updated id=%s by=%s", ncr_id, user.get("email"))
        return public_ncr(rec)
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_ncr failed")
        raise HTTPException(status_code=500, detail="Failed to update NCR")


@router.post("/ncrs/{ncr_id}/transition")
async def transition_ncr(ncr_id: str, payload: NCRTransition, request: Request, user=Depends(get_current_user)):
    try:
        rec = await _ncr(ncr_id)
        dest = sanitize_status(payload.status)
        role = user.get("role") or ""
        if payload.root_cause:
            rec["root_cause"] = payload.root_cause.strip()[:2000]
        if payload.corrective_action:
            rec["corrective_action"] = payload.corrective_action.strip()[:2000]
        if payload.verification_by:
            rec["verification_by"] = payload.verification_by.strip()[:120]
        if payload.verification_how:
            rec["verification_how"] = payload.verification_how.strip()[:2000]
        if payload.signoff:
            rec["signoff"] = payload.signoff.strip()[:120]
        block = transition_blockers(rec, dest, role, payload.note)
        if block:
            code = 400 if "Written reason" in block else 409
            raise HTTPException(status_code=code, detail=block)
        if dest == "closed":
            rec["closed_at"] = now_iso()
            rec["closed_by"] = user.get("email") or ""
        if dest == "investigating" and sanitize_status(rec.get("status")) in ("closed", "rejected"):
            rec["closed_at"] = None
            rec["closed_by"] = ""
        rec["status"] = dest
        rec["updated_at"] = now_iso()
        rec.setdefault("history", []).append(_history_row(user, "transition", payload.note, dest))
        await db.ncrs.replace_one({"id": ncr_id}, rec)
        await write_audit(
            action="ncr.transition",
            user=user,
            request=request,
            entity_type="ncr",
            entity_id=ncr_id,
            reason=payload.note,
            extra={"status": dest},
        )
        logger.info("ncr transition id=%s status=%s by=%s", ncr_id, dest, user.get("email"))
        return public_ncr(rec)
    except HTTPException:
        raise
    except Exception:
        logger.exception("transition_ncr failed")
        raise HTTPException(status_code=500, detail="Failed to move NCR")


@router.post("/ncrs/{ncr_id}/photos")
async def upload_ncr_photo(ncr_id: str, request: Request, file: UploadFile = File(...), user=Depends(get_current_user)):
    try:
        if not can_create(user.get("role") or ""):
            raise HTTPException(status_code=403, detail="Not allowed to attach NCR photos")
        rec = await _ncr(ncr_id)
        if is_immutable(rec):
            raise HTTPException(status_code=409, detail="Closed NCRs cannot take new photos")
        raw = await file.read()
        if len(raw) > PHOTO_MAX:
            raise HTTPException(status_code=400, detail="Photo exceeds 8 MB")
        name = file.filename or "ncr.jpg"
        ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ".jpg"
        if ext not in PHOTO_EXT:
            raise HTTPException(status_code=400, detail="Use JPEG, PNG, or WebP")
        beam_id = (rec.get("beam_ids") or ["unassigned"])[0]
        fname = f"ncr-{ncr_id[:8]}-{new_id()[:6]}{ext}"
        save_vault_file("plant", rec.get("job_id") or "unassigned", rec.get("pour_id") or "unassigned", beam_id, "photos", fname, raw)
        photos = photo_filenames(rec)
        photos.append(fname)
        rec["photos"] = photos
        rec["updated_at"] = now_iso()
        rec.setdefault("history", []).append(_history_row(user, "photo", fname, rec.get("status")))
        await db.ncrs.replace_one({"id": ncr_id}, rec)
        await write_audit(action="ncr.photo", user=user, request=request, entity_type="ncr", entity_id=ncr_id, extra={"filename": fname})
        logger.info("ncr photo attached id=%s name=%s by=%s", ncr_id, fname, user.get("email"))
        return public_ncr(rec)
    except HTTPException:
        raise
    except Exception:
        logger.exception("upload_ncr_photo failed")
        raise HTTPException(status_code=500, detail="Failed to attach photo")


@router.get("/ncrs/{ncr_id}/photos/{filename}")
async def get_ncr_photo(ncr_id: str, filename: str, user=Depends(get_current_user)):
    try:
        rec = await _ncr(ncr_id)
        names = photo_filenames(rec)
        if filename not in names:
            raise HTTPException(status_code=404, detail="Photo not found")
        beam_id = (rec.get("beam_ids") or ["unassigned"])[0]
        path = vault_file_path("plant", rec.get("job_id") or "unassigned", rec.get("pour_id") or "unassigned", beam_id, "photos", filename)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Photo not found")
        logger.info("ncr photo served id=%s name=%s by=%s", ncr_id, filename, user.get("email"))
        return file_response(path, filename, _media_type(filename))
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid photo path")
    except Exception:
        logger.exception("get_ncr_photo failed")
        raise HTTPException(status_code=500, detail="Failed to load photo")


@router.get("/ncrs/{ncr_id}/export.csv")
async def export_ncr_csv(ncr_id: str, request: Request, user=Depends(get_current_user)):
    try:
        rec = public_ncr(await _ncr(ncr_id))
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["field", "value"])
        for key in ("id", "status", "severity", "category", "sub_type", "description", "containment", "root_cause",
                    "corrective_action", "preventive_action", "verification_by", "signoff", "discovered_by", "created_at"):
            writer.writerow([key, rec.get(key)])
        writer.writerow(["beam_ids", ",".join(rec.get("beam_ids") or [])])
        await write_audit(action="ncr.export", user=user, request=request, entity_type="ncr", entity_id=ncr_id, extra={"kind": "csv"})
        return StreamingResponse(
            io.BytesIO(buf.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=ncr-{ncr_id[:8]}.csv"},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("export_ncr_csv failed")
        raise HTTPException(status_code=500, detail="Failed to export CSV")


@router.get("/ncrs/{ncr_id}/export.pdf")
async def export_ncr_pdf(ncr_id: str, request: Request, user=Depends(get_current_user)):
    try:
        rec = public_ncr(await _ncr(ncr_id))
        company = public_view(await get_company_doc())
        logo = company_logo_path("")
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader

        buf = io.BytesIO()
        page_w, page_h = letter
        c = canvas.Canvas(buf, pagesize=letter)
        y = page_h - 0.7 * inch
        if logo:
            try:
                c.drawImage(ImageReader(str(logo)), 0.6 * inch, y - 0.35 * inch, width=1.0 * inch, height=0.55 * inch, mask="auto", preserveAspectRatio=True)
            except Exception:
                logger.exception("ncr pdf logo failed")
        header = (company or {}).get("tag_header") or (company or {}).get("company_name") or "BedForge"
        c.setFont("Helvetica-Bold", 11)
        c.drawString(1.8 * inch if logo else 0.6 * inch, y, str(header).upper())
        c.setFont("Helvetica-Bold", 16)
        c.drawString(1.8 * inch if logo else 0.6 * inch, y - 18, "NON-CONFORMANCE REPORT")
        y -= 50
        c.setFont("Helvetica", 10)
        lines = [
            f"ID {rec.get('id')}  ·  {rec.get('status')}  ·  {rec.get('severity')}  ·  {rec.get('category')}/{rec.get('sub_type') or '—'}",
            f"Beams: {', '.join(rec.get('beam_ids') or []) or '—'}  bed {rec.get('bed_id') or '—'}",
            f"Discovered by {rec.get('discovered_by') or '—'}  at {rec.get('created_at')}",
            f"Description: {(rec.get('description') or '')[:400]}",
            f"Containment: {(rec.get('containment') or '')[:400]}",
            f"Root cause: {(rec.get('root_cause') or '')[:400]}",
            f"CA: {(rec.get('corrective_action') or '')[:400]}",
            f"PA: {(rec.get('preventive_action') or '')[:400]}",
            f"Verified by {rec.get('verification_by') or '—'}  sign-off {rec.get('signoff') or '—'}",
        ]
        for line in lines:
            c.drawString(0.6 * inch, y, line[:110])
            y -= 14
            if y < 0.8 * inch:
                c.showPage()
                y = page_h - 0.8 * inch
        c.setFont("Helvetica", 8)
        c.drawString(0.6 * inch, 0.45 * inch, "NCR does not bypass tension or release gates. Closed records are immutable.")
        c.save()
        buf.seek(0)
        await write_audit(action="ncr.export", user=user, request=request, entity_type="ncr", entity_id=ncr_id, extra={"kind": "pdf"})
        return StreamingResponse(
            buf,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=ncr-{ncr_id[:8]}.pdf"},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("export_ncr_pdf failed")
        raise HTTPException(status_code=500, detail="Failed to export PDF")
