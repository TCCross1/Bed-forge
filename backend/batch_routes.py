"""Batch plant records — mixer drafts, manager confirm, weather, QC links, analyst (read-only)."""
import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from audit import write_audit
from auth import get_current_user, require_roles
from batch_plant import (
    AI_CAN_WRITE_MIX,
    apply_computed_batch,
    apply_recommendations_to_batch,
    build_recommendations,
    can_confirm,
    can_draft,
    confirm_blocker,
    copy_library_into_batch,
    forecast_note,
    hpa_to_inhg,
    is_immutable,
    solar_proxy,
    weather_failure_env,
    weather_label,
)
from company_routes import get_company_doc, public_view
from db import db
from models import (
    BatchAmendInput,
    BatchLinkQcInput,
    BatchRecord,
    BatchRecordCreate,
    BatchRecordUpdate,
    MixDesign,
    MixDesignCreate,
    new_id,
    now_iso,
)
from storage import company_logo_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["batch-plant"])

DRAFT = require_roles("production", "admin", "executive")
CONFIRM = require_roles("admin", "executive")


def _public(doc: dict) -> dict:
    out = dict(doc or {})
    out.pop("_id", None)
    return out


def _role(user: dict) -> str:
    return (user or {}).get("role") or ""


async def _batch(batch_id: str) -> dict:
    rec = await db.batch_records.find_one({"id": batch_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Batch not found")
    return rec


def _refuse_silent_edit(rec: dict):
    if is_immutable(rec):
        raise HTTPException(
            status_code=409,
            detail="Confirmed batches cannot be silently edited. Use an amendment with a written reason.",
        )


async def fetch_weather(lat: float, lon: float) -> dict:
    """Open-Meteo, no API key. Failures never block batching. Never log lat/lon."""
    env = {
        "source": "open-meteo",
        "env_flag": "",
        "captured_at": now_iso(),
        "manual_override": False,
    }
    try:
        import httpx

        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,pressure_msl,wind_speed_10m,weather_code",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": "auto",
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(url, params=params)
            res.raise_for_status()
            current = (res.json() or {}).get("current") or {}
        try:
            env["ambient_f"] = round(float(current.get("temperature_2m")), 1)
        except (TypeError, ValueError):
            env["ambient_f"] = None
        env["rh_pct"] = current.get("relative_humidity_2m")
        env["pressure_inhg"] = hpa_to_inhg(current.get("pressure_msl"))
        try:
            env["wind_mph"] = round(float(current.get("wind_speed_10m")), 1)
        except (TypeError, ValueError):
            env["wind_mph"] = None
        env["weather"] = weather_label(current.get("weather_code"))
        try:
            iso = str(current.get("time") or "")
            hour = datetime.fromisoformat(iso.replace("Z", "+00:00")).hour
        except Exception:
            hour = datetime.now(timezone.utc).hour
        env["solar_proxy"] = solar_proxy(hour, env.get("weather") or "")
        return env
    except Exception:
        logger.exception("open-meteo weather fetch failed")
        failed = weather_failure_env(manual_override=False)
        failed["env_flag"] = "estimated/manual"
        return failed


@router.get("/batch-plant/weather")
async def get_weather(lat: float = Query(...), lon: float = Query(...), user=Depends(get_current_user)):
    try:
        if abs(lat) > 90 or abs(lon) > 180:
            raise HTTPException(status_code=400, detail="Invalid coordinates")
        env = await fetch_weather(lat, lon)
        logger.info("weather fetched by=%s flag=%s", user.get("email"), env.get("env_flag") or "ok")
        return env
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_weather failed")
        return weather_failure_env(manual_override=True)


@router.get("/mix-designs")
async def list_mix_designs(user=Depends(get_current_user)):
    try:
        return await db.mix_designs.find({}, {"_id": 0}).sort("mix_code", 1).to_list(200)
    except Exception:
        logger.exception("list_mix_designs failed")
        raise HTTPException(status_code=500, detail="Failed to list mix designs")


@router.post("/mix-designs")
async def create_mix_design(payload: MixDesignCreate, user=Depends(DRAFT)):
    try:
        rec = MixDesign(**payload.model_dump(), created_by=user.get("name") or "")
        await db.mix_designs.insert_one(rec.model_dump())
        logger.info("mix design saved code=%s by=%s", rec.mix_code, user.get("email"))
        return rec.model_dump()
    except Exception:
        logger.exception("create_mix_design failed")
        raise HTTPException(status_code=500, detail="Failed to save mix design")


@router.get("/batches")
async def list_batches(
    job_id: Optional[str] = None,
    pour_id: Optional[str] = None,
    beam_id: Optional[str] = None,
    mix_code: Optional[str] = None,
    status: Optional[str] = None,
    date: Optional[str] = None,
    user=Depends(get_current_user),
):
    try:
        q = {}
        if job_id:
            q["job_id"] = str(job_id)
        if pour_id:
            q["pour_id"] = str(pour_id)
        if beam_id:
            q["beam_ids"] = str(beam_id)
        if mix_code:
            q["mix_code"] = str(mix_code)
        if status:
            q["status"] = str(status)
        rows = await db.batch_records.find(q, {"_id": 0}).sort("batched_at", -1).to_list(300)
        if date:
            rows = [r for r in rows if str(r.get("batched_at") or "").startswith(str(date))]
        logger.info("batches listed count=%s by=%s", len(rows), user.get("email"))
        return rows
    except Exception:
        logger.exception("list_batches failed")
        raise HTTPException(status_code=500, detail="Failed to list batches")


@router.get("/batches/previous")
async def previous_batch(mix_code: str = Query(...), user=Depends(get_current_user)):
    try:
        rec = await db.batch_records.find_one({"mix_code": mix_code}, {"_id": 0}, sort=[("batched_at", -1)])
        return rec or {}
    except Exception:
        logger.exception("previous_batch failed")
        raise HTTPException(status_code=500, detail="Failed to load previous batch")


@router.get("/batches/{batch_id}")
async def get_batch(batch_id: str, user=Depends(get_current_user)):
    try:
        rec = await _batch(batch_id)
        rec["ai_can_write_mix"] = AI_CAN_WRITE_MIX
        rec["can_confirm"] = can_confirm(_role(user)) and not is_immutable(rec)
        rec["can_edit"] = can_draft(_role(user)) and not is_immutable(rec)
        return rec
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_batch failed")
        raise HTTPException(status_code=500, detail="Failed to load batch")


@router.post("/batches")
async def create_batch(payload: BatchRecordCreate, request: Request, user=Depends(DRAFT)):
    try:
        data = payload.model_dump()
        copy_from = data.pop("copy_from_id", None)
        if copy_from:
            prev = await db.batch_records.find_one({"id": copy_from}, {"_id": 0})
            if prev:
                for key in ("ingredients", "mix_code", "mix_design_id", "target_strength_psi", "target_air_pct",
                            "target_slump_in", "target_spread_in", "target_temp_f", "batch_size", "batch_unit",
                            "mixing_time_sec", "sequence_notes"):
                    if not data.get(key) and prev.get(key) not in (None, "", []):
                        data[key] = prev.get(key)
        if data.get("mix_design_id"):
            design = await db.mix_designs.find_one({"id": data["mix_design_id"]}, {"_id": 0})
            data = copy_library_into_batch(data, design)
        job = await db.jobs.find_one({"id": data["job_id"]}, {"_id": 0})
        pour = await db.pours.find_one({"id": data["pour_id"]}, {"_id": 0})
        if not job or not pour:
            raise HTTPException(status_code=400, detail="Pick a real job and pour")
        data["batched_at"] = data.get("batched_at") or now_iso()
        data["mixer_operator"] = data.get("mixer_operator") or user.get("name") or ""
        data = apply_computed_batch(data)
        rec = BatchRecord(**data, created_by=user.get("name") or "", status="draft", immutable=False)
        stored = rec.model_dump()
        await db.batch_records.insert_one(stored)
        await write_audit(action="batch.create", user=user, request=request, entity_type="batch", entity_id=rec.id)
        logger.info("batch draft saved id=%s pour=%s by=%s", rec.id, rec.pour_id, user.get("email"))
        return _public(stored)
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_batch failed")
        raise HTTPException(status_code=500, detail="Failed to save batch draft")


@router.patch("/batches/{batch_id}")
async def update_batch(batch_id: str, payload: BatchRecordUpdate, request: Request, user=Depends(DRAFT)):
    try:
        rec = await _batch(batch_id)
        _refuse_silent_edit(rec)
        patch = {k: v for k, v in payload.model_dump().items() if v is not None}
        rec.update(patch)
        rec = apply_computed_batch(rec)
        rec["updated_at"] = now_iso()
        rec["status"] = "draft"
        rec["immutable"] = False
        await db.batch_records.replace_one({"id": batch_id}, rec)
        await write_audit(action="batch.update", user=user, request=request, entity_type="batch", entity_id=batch_id)
        logger.info("batch draft updated id=%s by=%s", batch_id, user.get("email"))
        return _public(rec)
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_batch failed")
        raise HTTPException(status_code=500, detail="Failed to update batch")


@router.post("/batches/{batch_id}/confirm")
async def confirm_batch(batch_id: str, request: Request, user=Depends(CONFIRM)):
    try:
        rec = await _batch(batch_id)
        if is_immutable(rec):
            raise HTTPException(status_code=409, detail="Already confirmed")
        rec = apply_computed_batch(rec)
        blocked = confirm_blocker(rec)
        if blocked:
            raise HTTPException(status_code=400, detail=blocked)
        rec["status"] = "confirmed"
        rec["immutable"] = True
        rec["confirmed_by"] = user.get("name") or user.get("email") or ""
        rec["confirmed_at"] = now_iso()
        rec["updated_at"] = rec["confirmed_at"]
        await db.batch_records.replace_one({"id": batch_id}, rec)
        await write_audit(action="batch.confirm", user=user, request=request, entity_type="batch", entity_id=batch_id)
        logger.info("batch confirmed id=%s by=%s", batch_id, user.get("email"))
        return _public(rec)
    except HTTPException:
        raise
    except Exception:
        logger.exception("confirm_batch failed")
        raise HTTPException(status_code=500, detail="Failed to confirm batch")


@router.post("/batches/{batch_id}/amend")
async def amend_batch(batch_id: str, payload: BatchAmendInput, request: Request, user=Depends(CONFIRM)):
    try:
        rec = await _batch(batch_id)
        if not is_immutable(rec):
            raise HTTPException(status_code=400, detail="Amend confirmed tickets only — drafts can still be edited")
        patch = {k: v for k, v in payload.patch.model_dump().items() if v is not None}
        child = dict(rec)
        child.update(patch)
        child = apply_computed_batch(child)
        child["id"] = new_id()
        child["parent_id"] = rec["id"]
        child["revision"] = int(rec.get("revision") or 1) + 1
        child["status"] = "draft"
        child["immutable"] = False
        child["confirmed_by"] = ""
        child["confirmed_at"] = None
        child["created_by"] = user.get("name") or ""
        child["created_at"] = now_iso()
        child["updated_at"] = child["created_at"]
        await db.batch_records.insert_one(child)
        await db.batch_amendments.insert_one({
            "id": child["id"],
            "parent_id": rec["id"],
            "reason": payload.reason,
            "by": user.get("email"),
            "created_at": now_iso(),
        })
        await write_audit(
            action="batch.amend",
            user=user,
            request=request,
            entity_type="batch",
            entity_id=rec["id"],
            reason=payload.reason,
            extra={"revision_id": child["id"]},
        )
        logger.info("batch amendment drafted parent=%s child=%s by=%s", rec["id"], child["id"], user.get("email"))
        return _public(child)
    except HTTPException:
        raise
    except Exception:
        logger.exception("amend_batch failed")
        raise HTTPException(status_code=500, detail="Failed to amend batch")


@router.post("/batches/{batch_id}/link-qc")
async def link_qc(batch_id: str, payload: BatchLinkQcInput, request: Request, user=Depends(get_current_user)):
    try:
        rec = await _batch(batch_id)
        fresh_ids = [str(x) for x in (payload.fresh_test_ids if payload.fresh_test_ids is not None else rec.get("fresh_test_ids") or []) if x]
        cyl_ids = [str(x) for x in (payload.cylinder_ids if payload.cylinder_ids is not None else rec.get("cylinder_ids") or []) if x]
        rec["fresh_test_ids"] = list(dict.fromkeys(fresh_ids))
        rec["cylinder_ids"] = list(dict.fromkeys(cyl_ids))
        rec["updated_at"] = now_iso()
        await db.batch_records.replace_one({"id": batch_id}, rec)
        await write_audit(action="batch.link_qc", user=user, request=request, entity_type="batch", entity_id=batch_id)
        logger.info("batch QC linked id=%s fresh=%s cyl=%s by=%s", batch_id, len(fresh_ids), len(cyl_ids), user.get("email"))
        return _public(rec)
    except HTTPException:
        raise
    except Exception:
        logger.exception("link_qc failed")
        raise HTTPException(status_code=500, detail="Failed to link QC")


@router.get("/batches/{batch_id}/recommendations")
async def batch_recommendations(batch_id: str, user=Depends(get_current_user)):
    try:
        rec = await _batch(batch_id)
        history = await db.batch_records.find({"status": "confirmed"}, {"_id": 0}).to_list(200)
        for row in history + [rec]:
            fids = row.get("fresh_test_ids") or []
            cids = row.get("cylinder_ids") or []
            row["linked_fresh"] = await db.fresh_concrete_tests.find({"id": {"$in": fids}}, {"_id": 0}).to_list(20) if fids else []
            row["linked_cylinders"] = await db.cylinders.find({"id": {"$in": cids}}, {"_id": 0}).to_list(40) if cids else []
        ncr_q = {"$or": []}
        if rec.get("pour_id"):
            ncr_q["$or"].append({"pour_id": rec["pour_id"]})
        if rec.get("mix_code"):
            ncr_q["$or"].append({"mix_code": rec["mix_code"]})
        ncrs = await db.ncrs.find(ncr_q if ncr_q["$or"] else {"id": "__none__"}, {"_id": 0}).to_list(200)
        recs = build_recommendations(rec, history, ncrs=ncrs)
        note = forecast_note(rec.get("environment") or {})
        if note:
            recs.insert(0, note)
        logger.info("batch recommendations id=%s count=%s write_mix=%s", batch_id, len(recs), AI_CAN_WRITE_MIX)
        return {"ai_writes_mix": AI_CAN_WRITE_MIX, "recommendations": recs}
    except HTTPException:
        raise
    except Exception:
        logger.exception("batch_recommendations failed")
        raise HTTPException(status_code=500, detail="Failed to build recommendations")


@router.post("/batches/{batch_id}/apply-recommendations")
async def refuse_apply_recommendations(batch_id: str, user=Depends(get_current_user)):
    try:
        rec = await _batch(batch_id)
        apply_recommendations_to_batch(rec, [])
        raise HTTPException(status_code=403, detail="AI cannot change the mix")
    except PermissionError:
        logger.info("blocked AI mix write id=%s by=%s", batch_id, user.get("email"))
        raise HTTPException(status_code=403, detail="AI cannot change the mix. Recommendations only.")
    except HTTPException:
        raise
    except Exception:
        logger.exception("refuse_apply_recommendations failed")
        raise HTTPException(status_code=403, detail="AI cannot change the mix")


def _csv_bytes(rec: dict) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["field", "value"])
    for key in ("id", "status", "revision", "mix_code", "mixer_operator", "batched_at", "w_cm", "truck_id", "confirmed_by"):
        writer.writerow([key, rec.get(key)])
    writer.writerow([])
    writer.writerow(["kind", "name", "source", "size", "weight_lb", "moisture_pct", "dosage", "unit"])
    for item in rec.get("ingredients") or []:
        writer.writerow([item.get("kind"), item.get("name"), item.get("source"), item.get("size"),
                         item.get("weight_lb"), item.get("moisture_pct"), item.get("dosage"), item.get("dosage_unit")])
    return buf.getvalue().encode("utf-8")


def _pdf_bytes(rec: dict, company: dict, logo) -> bytes:
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
            logger.exception("batch pdf logo failed")
    header = (company or {}).get("tag_header") or (company or {}).get("company_name") or "BedForge"
    c.setFillColorRGB(0.79, 0.64, 0.15)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1.8 * inch if logo else 0.6 * inch, y, header.upper())
    c.setFillColorRGB(1, 1, 1)
    c.setFillColorRGB(0.05, 0.05, 0.06)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(1.8 * inch if logo else 0.6 * inch, y - 18, "BATCH PLANT TICKET")
    y -= 50
    c.setFont("Helvetica", 10)
    c.setFillColorRGB(0.1, 0.1, 0.12)
    lines = [
        f"Status: {rec.get('status')}  rev {rec.get('revision')}  mix {rec.get('mix_code') or '—'}",
        f"Operator: {rec.get('mixer_operator') or '—'}  truck {rec.get('truck_id') or '—'}",
        f"Batched: {rec.get('batched_at')}  w/cm {rec.get('w_cm') if rec.get('w_cm') is not None else '—'}",
        f"Confirmed by: {rec.get('confirmed_by') or '—'}  at {rec.get('confirmed_at') or '—'}",
        f"Env: {(rec.get('environment') or {}).get('weather') or '—'}  {(rec.get('environment') or {}).get('ambient_f')}°F  flag={(rec.get('environment') or {}).get('env_flag') or 'ok'}",
    ]
    for line in lines:
        c.drawString(0.6 * inch, y, line[:110])
        y -= 14
    y -= 8
    c.setFont("Helvetica-Bold", 10)
    c.drawString(0.6 * inch, y, "Ingredients")
    y -= 14
    c.setFont("Helvetica", 9)
    for item in rec.get("ingredients") or []:
        row = f"{item.get('kind')}  {item.get('name')}  {item.get('weight_lb') or item.get('dosage') or ''} {item.get('dosage_unit') or 'lb'}"
        c.drawString(0.6 * inch, y, row[:110])
        y -= 12
        if y < 0.8 * inch:
            c.showPage()
            y = page_h - 0.8 * inch
    c.setFont("Helvetica", 8)
    c.drawString(0.6 * inch, 0.45 * inch, "Analyst recommendations never change this ticket. Plant manager decides.")
    c.save()
    buf.seek(0)
    return buf.read()


@router.get("/batches/{batch_id}/export.csv")
async def export_batch_csv(batch_id: str, request: Request, user=Depends(get_current_user)):
    try:
        rec = await _batch(batch_id)
        await write_audit(action="batch.export", user=user, request=request, entity_type="batch", entity_id=batch_id, extra={"kind": "csv"})
        logger.info("batch csv export id=%s by=%s", batch_id, user.get("email"))
        return StreamingResponse(
            io.BytesIO(_csv_bytes(rec)),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=batch-{batch_id[:8]}.csv"},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("export_batch_csv failed")
        raise HTTPException(status_code=500, detail="Failed to export CSV")


@router.get("/batches/{batch_id}/export.pdf")
async def export_batch_pdf(batch_id: str, request: Request, user=Depends(get_current_user)):
    try:
        rec = await _batch(batch_id)
        raw_company = await get_company_doc()
        company = public_view(raw_company)
        logo = company_logo_path((raw_company or {}).get("logo_filename") or "") or company_logo_path("")
        await write_audit(action="batch.export", user=user, request=request, entity_type="batch", entity_id=batch_id, extra={"kind": "pdf"})
        logger.info("batch pdf export id=%s by=%s", batch_id, user.get("email"))
        return StreamingResponse(
            io.BytesIO(_pdf_bytes(rec, company, logo)),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=batch-{batch_id[:8]}.pdf"},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("export_batch_pdf failed")
        raise HTTPException(status_code=500, detail="Failed to export PDF")
