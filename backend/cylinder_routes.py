"""Cylinder tag runs — morning setup, beam entry, print rows, crush-test link."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
import io

from audit import write_audit
from auth import get_current_user
from company_routes import get_company_doc, public_view
from cylinder_tags import (
    build_pdf_bytes,
    build_run_payload,
    cylinder_sets_for_slot,
)
from db import db
from models import CylinderCrushInput, CylinderTagRunInput, now_iso, new_id
from storage import company_logo_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["cylinder-tags"])


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _public_run(doc: dict) -> dict:
    doc = dict(doc or {})
    doc.pop("_id", None)
    return doc


async def _replace_cylinders(run_id: str, slots: list, user: dict):
    existing = await db.cylinders.find({"run_id": run_id}, {"_id": 0}).to_list(200)
    prev_by_key = {
        (c.get("job_slot"), c.get("cylinder_copy"), c.get("job_number")): c
        for c in existing
    }
    stamp = now_iso()
    docs = []
    keep_ids = []
    for slot in slots:
        for item in cylinder_sets_for_slot(slot, run_id):
            prev = prev_by_key.get((item["job_slot"], item["cylinder_copy"], item["job_number"]))
            if prev:
                item["id"] = prev["id"]
                item["created_at"] = prev.get("created_at") or stamp
                for key in ("crush_psi", "crush_date", "crush_age_days", "required_psi", "release_ok", "notes", "tested_by", "status"):
                    if prev.get(key) not in (None, ""):
                        item[key] = prev.get(key)
            else:
                item["id"] = new_id()
                item["created_at"] = stamp
                item["logged_by"] = user.get("name") or ""
            item["updated_at"] = stamp
            docs.append(item)
            keep_ids.append(item["id"])
    if keep_ids:
        await db.cylinders.delete_many({"run_id": run_id, "id": {"$nin": keep_ids}})
    else:
        await db.cylinders.delete_many({"run_id": run_id})
    for doc in docs:
        await db.cylinders.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)
    return docs


@router.post("/cylinder-runs/preview")
async def preview_cylinder_run(payload: CylinderTagRunInput, user=Depends(get_current_user)):
    try:
        built = build_run_payload(payload.model_dump())
        return built
    except Exception:
        logger.exception("preview_cylinder_run failed")
        raise HTTPException(status_code=500, detail="Failed to preview cylinder tags")


@router.get("/cylinder-runs")
async def list_cylinder_runs(user=Depends(get_current_user)):
    try:
        rows = await db.cylinder_runs.find({}, {"_id": 0, "slots": 0, "print_rows": 0}).sort("created_at", -1).to_list(200)
        return rows
    except Exception:
        logger.exception("list_cylinder_runs failed")
        raise HTTPException(status_code=500, detail="Failed to list cylinder tag runs")


@router.post("/cylinder-runs")
async def create_cylinder_run(payload: CylinderTagRunInput, user=Depends(get_current_user)):
    try:
        body = payload.model_dump()
        if not body.get("run_date"):
            body["run_date"] = _today()
        built = build_run_payload(body)
        run_id = new_id()
        cylinders = await _replace_cylinders(run_id, built["slots"], user)
        doc = {
            "id": run_id,
            "run_date": built["run_date"],
            "job_count": built["job_count"],
            "slots": built["slots"],
            "summaries": built["summaries"],
            "print_rows": built["print_rows"],
            "total_physical_labels": built["total_physical_labels"],
            "ready_jobs": built["ready_jobs"],
            "incomplete_jobs": built["incomplete_jobs"],
            "print_ready": built["print_ready"],
            "notes": payload.notes or "",
            "status": "ready" if built["print_ready"] else ("incomplete" if built["incomplete_jobs"] else "draft"),
            "printed_at": None,
            "created_by": user.get("name") or "",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        await db.cylinder_runs.insert_one(doc)
        logger.info(
            "cylinder run saved id=%s labels=%s ready=%s by=%s",
            run_id, doc["total_physical_labels"], doc["ready_jobs"], user.get("email"),
        )
        saved = _public_run(doc)
        saved["cylinders"] = [{k: v for k, v in c.items() if k != "_id"} for c in cylinders]
        return saved
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_cylinder_run failed")
        raise HTTPException(status_code=500, detail="Failed to save cylinder tag run")


@router.get("/cylinder-runs/{run_id}")
async def get_cylinder_run(run_id: str, user=Depends(get_current_user)):
    try:
        doc = await db.cylinder_runs.find_one({"id": run_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Cylinder tag run not found")
        cylinders = await db.cylinders.find({"run_id": run_id}, {"_id": 0}).to_list(200)
        doc["cylinders"] = cylinders
        return doc
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_cylinder_run failed id=%s", run_id)
        raise HTTPException(status_code=500, detail="Failed to load cylinder tag run")


@router.patch("/cylinder-runs/{run_id}")
async def update_cylinder_run(run_id: str, payload: CylinderTagRunInput, user=Depends(get_current_user)):
    try:
        existing = await db.cylinder_runs.find_one({"id": run_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Cylinder tag run not found")
        body = payload.model_dump()
        if not body.get("run_date"):
            body["run_date"] = existing.get("run_date") or _today()
        built = build_run_payload(body)
        cylinders = await _replace_cylinders(run_id, built["slots"], user)
        updates = {
            "run_date": built["run_date"],
            "job_count": built["job_count"],
            "slots": built["slots"],
            "summaries": built["summaries"],
            "print_rows": built["print_rows"],
            "total_physical_labels": built["total_physical_labels"],
            "ready_jobs": built["ready_jobs"],
            "incomplete_jobs": built["incomplete_jobs"],
            "print_ready": built["print_ready"],
            "notes": payload.notes if payload.notes is not None else existing.get("notes") or "",
            "status": "ready" if built["print_ready"] else ("incomplete" if built["incomplete_jobs"] else "draft"),
            "updated_at": now_iso(),
        }
        await db.cylinder_runs.update_one({"id": run_id}, {"$set": updates})
        saved = await db.cylinder_runs.find_one({"id": run_id}, {"_id": 0})
        saved["cylinders"] = [{k: v for k, v in c.items() if k != "_id"} for c in cylinders]
        logger.info("cylinder run updated id=%s labels=%s by=%s", run_id, built["total_physical_labels"], user.get("email"))
        return saved
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_cylinder_run failed id=%s", run_id)
        raise HTTPException(status_code=500, detail="Failed to update cylinder tag run")


@router.post("/cylinder-runs/{run_id}/print")
async def mark_cylinder_run_printed(run_id: str, user=Depends(get_current_user)):
    try:
        doc = await db.cylinder_runs.find_one({"id": run_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Cylinder tag run not found")
        if not doc.get("print_rows"):
            raise HTTPException(status_code=409, detail="No tags are ready to print")
        stamp = now_iso()
        await db.cylinder_runs.update_one(
            {"id": run_id},
            {"$set": {"printed_at": stamp, "status": "printed", "updated_at": stamp}},
        )
        saved = await db.cylinder_runs.find_one({"id": run_id}, {"_id": 0})
        logger.info("cylinder run printed id=%s labels=%s by=%s", run_id, len(doc.get("print_rows") or []), user.get("email"))
        return saved
    except HTTPException:
        raise
    except Exception:
        logger.exception("mark_cylinder_run_printed failed id=%s", run_id)
        raise HTTPException(status_code=500, detail="Failed to mark cylinder tags printed")


@router.get("/cylinder-runs/{run_id}/pdf")
async def download_cylinder_pdf(run_id: str, user=Depends(get_current_user)):
    try:
        doc = await db.cylinder_runs.find_one({"id": run_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Cylinder tag run not found")
        rows = doc.get("print_rows") or []
        if not rows:
            raise HTTPException(status_code=409, detail="No tags are ready to print")
        company_doc = await get_company_doc()
        company = public_view(company_doc)
        logo = company_logo_path(company_doc.get("logo_filename") or "") or company_logo_path("")
        logo_file = str(logo) if logo and logo.exists() else None
        pdf = build_pdf_bytes(rows, company, logo_file)
        filename = f"cylinder-tags-{doc.get('run_date') or run_id[:8]}.pdf"
        logger.info("cylinder PDF built id=%s labels=%s by=%s", run_id, len(rows), user.get("email"))
        return StreamingResponse(
            io.BytesIO(pdf),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        logger.exception("download_cylinder_pdf failed id=%s", run_id)
        raise HTTPException(status_code=500, detail="Failed to build cylinder tag PDF")


@router.get("/cylinders")
async def list_cylinders(
    run_id: str = None,
    job_number: str = None,
    job_id: str = None,
    pour_number: str = None,
    beam_mark: str = None,
    user=Depends(get_current_user),
):
    try:
        query = {}
        if run_id:
            query["run_id"] = run_id
        if job_number:
            query["job_number"] = job_number
        if job_id:
            query["job_id"] = job_id
        if pour_number:
            query["pour_number"] = pour_number
        rows = await db.cylinders.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
        if beam_mark:
            mark = beam_mark.strip()
            rows = [r for r in rows if mark in (r.get("beam_marks") or [])]
        return rows
    except Exception:
        logger.exception("list_cylinders failed")
        raise HTTPException(status_code=500, detail="Failed to list cylinders")


@router.patch("/cylinders/{cylinder_id}/crush")
async def record_cylinder_crush(cylinder_id: str, payload: CylinderCrushInput, request: Request, user=Depends(get_current_user)):
    try:
        doc = await db.cylinders.find_one({"id": cylinder_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Cylinder set not found")
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        crush = updates.get("crush_psi", doc.get("crush_psi"))
        required = updates.get("required_psi", doc.get("required_psi"))
        if crush is not None and required is not None and updates.get("release_ok") is None:
            try:
                updates["release_ok"] = float(crush) >= float(required)
            except (TypeError, ValueError):
                pass
        if crush is not None:
            updates["status"] = "released" if updates.get("release_ok") else "tested"
            if updates.get("release_ok") is False:
                updates["status"] = "failed"
            elif updates.get("release_ok"):
                updates["status"] = "released"
        updates["updated_at"] = now_iso()
        updates["tested_by"] = user.get("name") or ""
        await db.cylinders.update_one({"id": cylinder_id}, {"$set": updates})
        saved = await db.cylinders.find_one({"id": cylinder_id}, {"_id": 0})
        await write_audit(
            action="cylinder.crush",
            user=user,
            request=request,
            entity_type="cylinder",
            entity_id=cylinder_id,
            after={"crush_psi": saved.get("crush_psi"), "release_ok": saved.get("release_ok")},
        )
        logger.info(
            "cylinder crush recorded id=%s psi=%s release=%s by=%s",
            cylinder_id, bool(saved.get("crush_psi")), saved.get("release_ok"), user.get("email"),
        )
        if saved.get("release_ok") is False:
            from ncr import attach_prompt, build_prompt
            marks = saved.get("beam_marks") or []
            saved = attach_prompt(saved, build_prompt(
                source_type="cylinder",
                source_id=cylinder_id,
                title="Cylinder below required — file an NCR",
                category="material",
                severity="major",
                description=f"{saved.get('crush_psi')} psi vs {saved.get('required_psi')} required",
                beam_id="",
                pour_id=saved.get("pour_id") or "",
                job_id=saved.get("job_id") or "",
            ))
            if marks:
                saved["ncr_prompt"]["description"] = saved["ncr_prompt"]["description"] + f" · {', '.join(marks[:4])}"
        return saved
    except HTTPException:
        raise
    except Exception:
        logger.exception("record_cylinder_crush failed id=%s", cylinder_id)
        raise HTTPException(status_code=500, detail="Failed to record cylinder crush")
