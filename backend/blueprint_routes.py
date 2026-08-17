"""Blueprint upload, BeamSpec CRUD, lock, and measured-vs-design compare."""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from auth import get_current_user, require_roles
from beam_spec import BeamSpec, BeamSpecPatch, SpecMeasurementCreate, compare_measurement
from db import db
from extract import extract_beam_spec
from models import now_iso
from storage import file_response, list_files, save_upload, MAX_BYTES
from beam_spec import Blueprint
from l25390 import build_l25390_spec
from corpus import clone_spec, corpus_summaries, load_gold_specs

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["blueprints"])


async def _get_spec(spec_id: str) -> dict:
    spec = await db.beam_specs.find_one({"id": spec_id}, {"_id": 0})
    if not spec:
        raise HTTPException(status_code=404, detail="BeamSpec not found")
    return spec


@router.post("/blueprints/upload")
async def upload_blueprints(
    files: List[UploadFile] = File(...),
    beam_id: Optional[str] = Form(None),
    job_id: Optional[str] = Form(None),
    pour_id: Optional[str] = Form(None),
    beam_mark: Optional[str] = Form(None),
    extract: bool = Form(True),
    user=Depends(get_current_user),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    bp = Blueprint(
        beam_id=beam_id,
        job_id=job_id,
        original_name=", ".join(f.filename or "drawing" for f in files),
        uploaded_by=user["name"],
        status="uploaded",
        page_count=len(files),
    )
    stored = []
    try:
        for upload in files:
            data = await upload.read()
            if len(data) > MAX_BYTES:
                raise HTTPException(status_code=400, detail=f"{upload.filename} exceeds 25 MB")
            path = save_upload(bp.id, upload.filename or "drawing.bin", data)
            stored.append(path)
            bp.size_bytes += len(data)
            bp.content_type = upload.content_type or bp.content_type
            bp.stored_name = path.name
        bp.status = "extracting" if extract else "uploaded"
        await db.blueprints.insert_one(bp.model_dump())
        logger.info("blueprint uploaded id=%s files=%s by=%s", bp.id, bp.original_name, user.get("email"))

        result = bp.model_dump()
        if extract:
            try:
                spec, extractor = extract_beam_spec(
                    stored,
                    beam_id=beam_id,
                    job_id=job_id,
                    pour_id=pour_id,
                    blueprint_id=bp.id,
                    beam_mark=beam_mark or "B1",
                )
            except Exception:
                await db.blueprints.update_one({"id": bp.id}, {"$set": {"status": "failed", "error": "extraction_failed"}})
                logger.exception("blueprint extraction failed id=%s", bp.id)
                raise HTTPException(status_code=500, detail="Failed to extract BeamSpec from shop drawing")
            spec.status = "extracted"
            dumped = spec.model_dump()
            await db.beam_specs.insert_one(dumped)
            await db.blueprints.update_one({"id": bp.id}, {"$set": {"status": "extracted", "extractor": extractor}})
            result["status"] = "extracted"
            result["extractor"] = extractor
            result["spec"] = dumped
            logger.info("blueprint extracted id=%s spec=%s extractor=%s", bp.id, spec.id, extractor)
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        logger.warning("blueprint upload rejected: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("upload_blueprints failed")
        raise HTTPException(status_code=500, detail="Failed to upload shop drawing")


@router.get("/blueprints")
async def list_blueprints(beam_id: Optional[str] = None, user=Depends(get_current_user)):
    try:
        q = {"beam_id": beam_id} if beam_id else {}
        return await db.blueprints.find(q, {"_id": 0}).to_list(200)
    except Exception:
        logger.exception("list_blueprints failed")
        raise HTTPException(status_code=500, detail="Failed to list blueprints")


@router.get("/blueprints/{blueprint_id}/file")
async def download_blueprint(blueprint_id: str, user=Depends(get_current_user)):
    rec = await db.blueprints.find_one({"id": blueprint_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    files = list_files(blueprint_id)
    if not files:
        raise HTTPException(status_code=404, detail="File missing")
    path = files[0]
    return file_response(path, rec.get("original_name") or path.name, rec.get("content_type") or "application/octet-stream")


@router.post("/blueprints/{blueprint_id}/extract")
async def reextract(blueprint_id: str, beam_mark: Optional[str] = None, user=Depends(get_current_user)):
    rec = await db.blueprints.find_one({"id": blueprint_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    files = list_files(blueprint_id)
    if not files:
        raise HTTPException(status_code=404, detail="No stored files to extract")
    try:
        spec, extractor = extract_beam_spec(
            files,
            beam_id=rec.get("beam_id"),
            job_id=rec.get("job_id"),
            blueprint_id=blueprint_id,
            beam_mark=beam_mark or "B1",
        )
        dumped = spec.model_dump()
        await db.beam_specs.insert_one(dumped)
        await db.blueprints.update_one({"id": blueprint_id}, {"$set": {"status": "extracted", "extractor": extractor}})
        logger.info("reextract spec=%s extractor=%s by=%s", spec.id, extractor, user.get("email"))
        return dumped
    except Exception:
        logger.exception("reextract failed id=%s", blueprint_id)
        raise HTTPException(status_code=500, detail="Extraction failed")


@router.get("/beam-specs")
async def list_specs(beam_id: Optional[str] = None, user=Depends(get_current_user)):
    try:
        q = {"beam_id": beam_id} if beam_id else {}
        return await db.beam_specs.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    except Exception:
        logger.exception("list_specs failed")
        raise HTTPException(status_code=500, detail="Failed to list beam specs")


@router.get("/beam-specs/reference/l25390")
async def reference_l25390(user=Depends(get_current_user)):
    try:
        return build_l25390_spec().model_dump()
    except Exception:
        logger.exception("reference_l25390 failed")
        raise HTTPException(status_code=500, detail="Failed to load L25390 reference spec")


@router.post("/beam-specs/from-l25390")
async def create_from_l25390(beam_id: Optional[str] = None, user=Depends(get_current_user)):
    try:
        beam = None
        if beam_id:
            beam = await db.beams.find_one({"id": beam_id}, {"_id": 0})
            if not beam:
                raise HTTPException(status_code=404, detail="Beam not found")
        spec = build_l25390_spec(
            beam_id=beam_id,
            job_id=beam.get("job_id") if beam else None,
            pour_id=beam.get("pour_id") if beam else None,
            beam_mark=beam.get("mark") if beam else "B1",
        )
        spec.status = "extracted"
        spec.review_notes = (
            "Attached from Larue County contract 255390 / L25390 Type 2 shop-drawing reference. "
            "QC Supervisor must verify against the print before lock."
        )
        dumped = spec.model_dump()
        await db.beam_specs.insert_one(dumped)
        logger.info("l25390 spec created id=%s beam=%s by=%s", spec.id, beam_id, user.get("email"))
        return dumped
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_from_l25390 failed")
        raise HTTPException(status_code=500, detail="Failed to create L25390 reference spec")


@router.get("/beam-specs/corpus")
async def list_corpus(user=Depends(get_current_user)):
    try:
        return {"count": len(corpus_summaries()), "items": corpus_summaries()}
    except Exception:
        logger.exception("list_corpus failed")
        raise HTTPException(status_code=500, detail="Failed to list training corpus")


@router.post("/beam-specs/from-corpus")
async def create_from_corpus(catalog_id: str, beam_id: Optional[str] = None, user=Depends(get_current_user)):
    try:
        gold = next((s for s in load_gold_specs() if s.catalog_id == catalog_id), None)
        if not gold:
            raise HTTPException(status_code=404, detail="Corpus spec not found")
        beam = None
        if beam_id:
            beam = await db.beams.find_one({"id": beam_id}, {"_id": 0})
            if not beam:
                raise HTTPException(status_code=404, detail="Beam not found")
        spec = clone_spec(
            gold,
            beam_id=beam_id,
            job_id=beam.get("job_id") if beam else None,
            pour_id=beam.get("pour_id") if beam else None,
            beam_mark=beam.get("mark") if beam else "B1",
        )
        spec.status = "extracted"
        spec.review_notes = (
            f"Attached from training corpus {gold.catalog_id} ({gold.source_agency} {gold.source_drawing}). "
            "QC Supervisor must verify against the shop drawing before lock."
        )
        dumped = spec.model_dump()
        await db.beam_specs.insert_one(dumped)
        logger.info("corpus spec created id=%s catalog=%s beam=%s by=%s", spec.id, catalog_id, beam_id, user.get("email"))
        return dumped
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_from_corpus failed catalog=%s", catalog_id)
        raise HTTPException(status_code=500, detail="Failed to attach corpus spec")


@router.get("/beam-specs/{spec_id}")
async def get_spec(spec_id: str, user=Depends(get_current_user)):
    spec = await _get_spec(spec_id)
    spec["measurements"] = await db.spec_measurements.find({"spec_id": spec_id}, {"_id": 0}).to_list(500)
    return spec


@router.patch("/beam-specs/{spec_id}")
async def patch_spec(spec_id: str, payload: BeamSpecPatch, user=Depends(get_current_user)):
    spec = await _get_spec(spec_id)
    if spec.get("status") == "locked":
        raise HTTPException(status_code=409, detail="Spec is locked. Unlock is not allowed; upload a revision.")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "geometry" in updates and hasattr(updates["geometry"], "model_dump"):
        updates["geometry"] = updates["geometry"].model_dump()
    for key in ("strands", "hardware", "stirrup_zones", "hold_downs"):
        if key in updates:
            updates[key] = [x.model_dump() if hasattr(x, "model_dump") else x for x in updates[key]]
    updates["updated_at"] = now_iso()
    updates["reviewed_by"] = user["name"]
    if updates.get("status") not in (None, "extracted", "reviewed"):
        updates["status"] = "reviewed"
    elif payload.status is None:
        updates["status"] = "reviewed"
    await db.beam_specs.update_one({"id": spec_id}, {"$set": updates})
    logger.info("beam spec reviewed id=%s by=%s", spec_id, user.get("email"))
    return await _get_spec(spec_id)


@router.post("/beam-specs/{spec_id}/lock")
async def lock_spec(spec_id: str, user=Depends(require_roles("admin", "executive", "qc_supervisor"))):
    spec = await _get_spec(spec_id)
    if spec.get("status") == "locked":
        return spec
    stamp = now_iso()
    await db.beam_specs.update_one({"id": spec_id}, {"$set": {
        "status": "locked",
        "locked_by": user["name"],
        "locked_at": stamp,
        "updated_at": stamp,
    }})
    if spec.get("beam_id"):
        geo = spec.get("geometry") or {}
        await db.beams.update_one({"id": spec["beam_id"]}, {"$set": {
            "length_ft": geo.get("length_ft") or 0,
            "twin_type": geo.get("twin_type") or "i_beam",
            "spec_id": spec_id,
            "qc_state": "in_progress",
        }})
    logger.info("beam spec locked id=%s by=%s", spec_id, user.get("email"))
    from audit import write_audit
    await write_audit(action="spec.lock", user=user, entity_type="beam_spec", entity_id=spec_id)
    return await _get_spec(spec_id)


@router.post("/beam-specs/{spec_id}/measurements")
async def add_measurement(spec_id: str, payload: SpecMeasurementCreate, user=Depends(get_current_user)):
    spec_doc = await _get_spec(spec_id)
    try:
        spec = BeamSpec(**spec_doc)
        rec = compare_measurement(spec, payload, user["name"])
        dumped = rec.model_dump()
        await db.spec_measurements.insert_one(dumped)
        logger.info(
            "measurement saved spec=%s element=%s within=%s by=%s",
            spec_id, payload.element_id, rec.within_tolerance, user.get("email"),
        )
        return dumped
    except HTTPException:
        raise
    except Exception:
        logger.exception("add_measurement failed spec=%s", spec_id)
        raise HTTPException(status_code=500, detail="Failed to save measurement")


@router.get("/beam-specs/{spec_id}/compare")
async def compare_spec(spec_id: str, user=Depends(get_current_user)):
    spec = await _get_spec(spec_id)
    measurements = await db.spec_measurements.find({"spec_id": spec_id}, {"_id": 0}).to_list(500)
    latest = {}
    for m in measurements:
        latest[m["element_id"]] = m
    rows = []
    for item in spec.get("hardware") or []:
        m = latest.get(item["id"])
        rows.append({
            "element_id": item["id"],
            "kind": item.get("kind"),
            "name": item.get("name"),
            "type_code": item.get("type_code"),
            "design_station_ft": item.get("position", {}).get("station_ft"),
            "tolerance_in": item.get("tolerance_in"),
            "measurement": m,
            "within_tolerance": None if not m else m.get("within_tolerance"),
        })
    failed = len([r for r in rows if r["within_tolerance"] is False])
    passed = len([r for r in rows if r["within_tolerance"] is True])
    return {
        "spec_id": spec_id,
        "status": spec.get("status"),
        "checked": passed + failed,
        "passed": passed,
        "failed": failed,
        "rows": rows,
    }
