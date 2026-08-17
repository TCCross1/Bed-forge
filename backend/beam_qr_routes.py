"""Public beam QR dossier, QR PNG, and laminate label printing."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse, FileResponse
import io

from auth import get_current_user, get_optional_user
from beam_qr import (
    assemble_dossier,
    beam_deep_link,
    build_qr_label_pdf,
    ensure_beam_token,
    normalize_token,
    qr_png_bytes,
)
from company_routes import get_company_doc, public_view
from db import db
from models import QrLabelRequest
from storage import company_logo_path, list_files

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["beam-qr"])


async def _beam_by_token(token: str) -> dict:
    token = normalize_token(token)
    if not token:
        raise HTTPException(status_code=404, detail="Beam not found")
    beam = await db.beams.find_one({"qr_token": token}, {"_id": 0})
    if not beam:
        raise HTTPException(status_code=404, detail="Beam not found")
    return beam


async def _label_rows(beams: list) -> list:
    rows = []
    jobs = {j["id"]: j for j in await db.jobs.find({}, {"_id": 0, "id": 1, "job_number": 1}).to_list(500)}
    for beam in beams:
        token = await ensure_beam_token(beam)
        url = beam_deep_link(token)
        job = jobs.get(beam.get("job_id") or "")
        rows.append({
            "id": beam.get("id"),
            "mark": beam.get("mark") or "",
            "job_number": (job or {}).get("job_number") or "",
            "qr_token": token,
            "qr_url": url,
            "qr_png": qr_png_bytes(url, box_size=10),
        })
    return rows


@router.get("/public/beams/{token}")
async def public_beam_dossier(token: str, user=Depends(get_optional_user)):
    try:
        beam = await _beam_by_token(token)
        full = bool(user)
        dossier = await assemble_dossier(beam, full=full)
        logger.info("beam dossier scan token=%s full=%s", bool(token), full)
        return dossier
    except HTTPException:
        raise
    except Exception:
        logger.exception("public_beam_dossier failed")
        raise HTTPException(status_code=500, detail="Failed to load beam record")


@router.get("/public/beams/{token}/qr.png")
async def public_beam_qr_png(token: str):
    try:
        png = qr_png_bytes(beam_deep_link(token))
        return Response(
            content=png,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("public_beam_qr_png failed")
        raise HTTPException(status_code=500, detail="Failed to build QR image")


@router.get("/public/beams/{token}/drawings/{blueprint_id}")
async def public_beam_drawing(token: str, blueprint_id: str):
    try:
        beam = await _beam_by_token(token)
        rec = await db.blueprints.find_one({"id": blueprint_id}, {"_id": 0})
        if not rec or rec.get("beam_id") != beam.get("id"):
            raise HTTPException(status_code=404, detail="Drawing not found")
        files = list_files(blueprint_id)
        if not files:
            raise HTTPException(status_code=404, detail="Drawing file missing")
        return FileResponse(files[0], filename=rec.get("original_name") or files[0].name)
    except HTTPException:
        raise
    except Exception:
        logger.exception("public_beam_drawing failed")
        raise HTTPException(status_code=500, detail="Failed to load drawing")


@router.get("/beams/{beam_id}/qr.png")
async def beam_qr_png(beam_id: str, user=Depends(get_current_user)):
    try:
        beam = await db.beams.find_one({"id": beam_id}, {"_id": 0})
        if not beam:
            raise HTTPException(status_code=404, detail="Beam not found")
        token = await ensure_beam_token(beam)
        png = qr_png_bytes(beam_deep_link(token))
        return Response(
            content=png,
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=3600"},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("beam_qr_png failed id=%s", beam_id)
        raise HTTPException(status_code=500, detail="Failed to build QR image")


@router.get("/beams/{beam_id}/qr-label.pdf")
async def reprint_beam_qr_label(beam_id: str, user=Depends(get_current_user)):
    try:
        beam = await db.beams.find_one({"id": beam_id}, {"_id": 0})
        if not beam:
            raise HTTPException(status_code=404, detail="Beam not found")
        rows = await _label_rows([beam])
        company_doc = await get_company_doc()
        company = public_view(company_doc)
        logo = company_logo_path(company_doc.get("logo_filename") or "") or company_logo_path("")
        pdf = build_qr_label_pdf(rows, company, str(logo) if logo else None)
        filename = f"qr-{beam.get('mark') or beam_id[:8]}.pdf"
        logger.info("QR label reprinted beam=%s by=%s", beam_id, user.get("email"))
        return StreamingResponse(
            io.BytesIO(pdf),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("reprint_beam_qr_label failed id=%s", beam_id)
        raise HTTPException(status_code=500, detail="Failed to reprint QR label")


@router.post("/qr-labels")
async def generate_qr_labels(payload: QrLabelRequest, user=Depends(get_current_user)):
    try:
        query = {}
        if payload.beam_ids:
            query["id"] = {"$in": payload.beam_ids}
        elif payload.pour_id:
            query["pour_id"] = payload.pour_id
        elif payload.job_id:
            query["job_id"] = payload.job_id
        else:
            raise HTTPException(status_code=400, detail="Select a pour, job, or beams")
        beams = await db.beams.find(query, {"_id": 0}).sort("mark", 1).to_list(200)
        if not beams:
            raise HTTPException(status_code=404, detail="No beams found for QR labels")
        rows = await _label_rows(beams)
        company_doc = await get_company_doc()
        company = public_view(company_doc)
        logo = company_logo_path(company_doc.get("logo_filename") or "") or company_logo_path("")
        pdf = build_qr_label_pdf(rows, company, str(logo) if logo else None)
        logger.info("QR labels generated count=%s by=%s", len(rows), user.get("email"))
        return StreamingResponse(
            io.BytesIO(pdf),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=beam-qr-labels.pdf"},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("generate_qr_labels failed")
        raise HTTPException(status_code=500, detail="Failed to generate QR labels")


@router.get("/qr-labels/pack")
async def qr_pack_preview(pour_id: Optional[str] = None, job_id: Optional[str] = None, user=Depends(get_current_user)):
    try:
        query = {}
        if pour_id:
            query["pour_id"] = pour_id
        elif job_id:
            query["job_id"] = job_id
        else:
            raise HTTPException(status_code=400, detail="Select a pour or job")
        beams = await db.beams.find(query, {"_id": 0}).sort("mark", 1).to_list(200)
        out = []
        jobs = {j["id"]: j for j in await db.jobs.find({}, {"_id": 0, "id": 1, "job_number": 1}).to_list(500)}
        for beam in beams:
            token = await ensure_beam_token(beam)
            job = jobs.get(beam.get("job_id") or "")
            out.append({
                "id": beam.get("id"),
                "mark": beam.get("mark"),
                "job_number": (job or {}).get("job_number") or "",
                "qr_token": token,
                "qr_url": beam_deep_link(token),
                "qr_png_url": f"/api/public/beams/{token}/qr.png",
            })
        return {"beams": out, "count": len(out)}
    except HTTPException:
        raise
    except Exception:
        logger.exception("qr_pack_preview failed")
        raise HTTPException(status_code=500, detail="Failed to load QR pack")
