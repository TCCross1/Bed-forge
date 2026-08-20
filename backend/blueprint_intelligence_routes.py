import io
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from auth import get_current_user
from db import db
from licensing import require_feature
from models import (
    BlueprintAuditEvent,
    BlueprintDocument,
    BlueprintExtraction,
    BlueprintExtractionPatch,
    BlueprintField,
    BlueprintLockInput,
    LockedBlueprintRevision,
    now_iso,
)
from blueprint_pipeline import (
    CRITICAL_FIELDS,
    FIELD_GROUPS,
    extract_structured_fields,
    normalize_locked_blueprint,
    parse_field_value,
    read_pdf_pages,
)

ROOT_DIR = Path(__file__).parent
BLUEPRINT_STORAGE_DIR = ROOT_DIR / "uploads" / "blueprints"
BLUEPRINT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
router = APIRouter(prefix="/api", tags=["blueprint-intelligence"])


async def record_blueprint_event(document_id: str, user: dict, event_type: str, details: dict | None = None):
    event = BlueprintAuditEvent(
        document_id=document_id,
        event_type=event_type,
        actor_name=user.get("name", ""),
        actor_role=user.get("role", ""),
        details=details or {},
    )
    await db.blueprint_audit_events.insert_one(event.model_dump())


async def fetch_blueprint_document(document_id: str) -> dict:
    document = await db.blueprint_documents.find_one({"id": document_id}, {"_id": 0})
    if not document:
        raise HTTPException(status_code=404, detail="Blueprint document not found")
    return document


async def fetch_blueprint_extraction(extraction_id: str) -> dict:
    extraction = await db.blueprint_extractions.find_one({"id": extraction_id}, {"_id": 0})
    if not extraction:
        raise HTTPException(status_code=404, detail="Blueprint extraction not found")
    return extraction


async def blueprint_detail(document_id: str) -> dict:
    document = await fetch_blueprint_document(document_id)
    extraction = None
    locked_revision = None
    if document.get("latest_extraction_id"):
        extraction = await db.blueprint_extractions.find_one({"id": document["latest_extraction_id"]}, {"_id": 0})
    if document.get("locked_revision_id"):
        locked_revision = await db.locked_blueprint_revisions.find_one({"id": document["locked_revision_id"]}, {"_id": 0})
    audit = await db.blueprint_audit_events.find({"document_id": document_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {
        **document,
        "latest_extraction": extraction,
        "locked_revision": locked_revision,
        "audit_events": audit,
        "field_groups": FIELD_GROUPS,
        "critical_fields": sorted(CRITICAL_FIELDS),
    }


@router.get("/blueprints")
async def list_blueprints(user=Depends(require_feature("blueprint_intelligence"))):
    documents = await db.blueprint_documents.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [await blueprint_detail(item["id"]) for item in documents]


@router.get("/blueprints/{document_id}")
async def get_blueprint(document_id: str, user=Depends(require_feature("blueprint_intelligence"))):
    return await blueprint_detail(document_id)


@router.post("/blueprints/upload")
async def upload_blueprint(
    file: UploadFile = File(...),
    job_id: str | None = Form(default=None),
    beam_id: str | None = Form(default=None),
    product_type_id: str | None = Form(default=None),
    product_family_hint: str | None = Form(default=""),
    beam_mark_hint: str | None = Form(default=""),
    project_name_hint: str | None = Form(default=""),
    user=Depends(require_feature("blueprint_intelligence")),
):
    filename = file.filename or "blueprint.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF blueprint uploads are supported")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded blueprint file was empty")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Blueprint PDF exceeds 20 MB upload limit")
    document = BlueprintDocument(
        filename=filename,
        storage_path="",
        content_type=file.content_type or "application/pdf",
        file_size_bytes=len(content),
        job_id=job_id or None,
        beam_id=beam_id or None,
        product_type_id=product_type_id or None,
        product_family_hint=(product_family_hint or "").strip(),
        beam_mark_hint=(beam_mark_hint or "").strip(),
        project_name_hint=(project_name_hint or "").strip(),
        created_by=user.get("name", ""),
    )
    storage_path = BLUEPRINT_STORAGE_DIR / f"{document.id}.pdf"
    storage_path.write_bytes(content)
    page_text = read_pdf_pages(storage_path)
    document.storage_path = str(storage_path)
    document.page_count = len(page_text)
    document.updated_at = now_iso()
    await db.blueprint_documents.insert_one(document.model_dump())
    await record_blueprint_event(document.id, user, "upload", {"filename": filename, "page_count": document.page_count})
    return await blueprint_detail(document.id)


@router.get("/blueprints/{document_id}/file")
async def download_blueprint_file(document_id: str, user=Depends(require_feature("blueprint_intelligence"))):
    document = await fetch_blueprint_document(document_id)
    storage_path = Path(document["storage_path"])
    if not storage_path.exists():
        raise HTTPException(status_code=404, detail="Stored blueprint PDF is missing")
    return StreamingResponse(
        io.BytesIO(storage_path.read_bytes()),
        media_type=document.get("content_type", "application/pdf"),
        headers={"Content-Disposition": f"attachment; filename={document['filename']}"},
    )


@router.post("/blueprints/{document_id}/extract")
async def extract_blueprint(document_id: str, user=Depends(require_feature("blueprint_intelligence", "qc_supervisor", "admin", "executive"))):
    document = await fetch_blueprint_document(document_id)
    storage_path = Path(document["storage_path"])
    if not storage_path.exists():
        raise HTTPException(status_code=404, detail="Stored blueprint PDF is missing")
    page_text = read_pdf_pages(storage_path)
    result = extract_structured_fields(page_text, {
        "product_family_hint": document.get("product_family_hint", ""),
        "beam_mark_hint": document.get("beam_mark_hint", ""),
        "project_name_hint": document.get("project_name_hint", ""),
    })
    extraction = BlueprintExtraction(
        document_id=document_id,
        status=result.status,
        summary=result.summary,
        page_text=result.page_text,
        field_groups=result.field_groups,
        fields=result.fields,
        confirmed_count=sum(1 for field in result.fields.values() if field.status in ("confirmed", "manually_confirmed")),
        unconfirmed_count=sum(1 for field in result.fields.values() if field.status == "unconfirmed"),
        fail_reasons=result.fail_reasons,
        created_by=user.get("name", ""),
    )
    await db.blueprint_extractions.insert_one(extraction.model_dump())
    await db.blueprint_documents.update_one({"id": document_id}, {"$set": {
        "status": extraction.status,
        "latest_extraction_id": extraction.id,
        "latest_summary": extraction.summary,
        "page_count": len(page_text),
        "updated_at": now_iso(),
    }})
    await record_blueprint_event(document_id, user, "extract", {"extraction_id": extraction.id, "status": extraction.status})
    return await blueprint_detail(document_id)


@router.patch("/blueprints/{document_id}/extraction")
async def patch_blueprint_extraction(document_id: str, payload: BlueprintExtractionPatch, user=Depends(require_feature("blueprint_intelligence", "qc_supervisor", "admin", "executive"))):
    document = await fetch_blueprint_document(document_id)
    if not document.get("latest_extraction_id"):
        raise HTTPException(status_code=400, detail="Blueprint has not been extracted yet")
    extraction = await fetch_blueprint_extraction(document["latest_extraction_id"])
    fields = extraction.get("fields", {})
    changed_fields = []
    for key, patch in payload.fields.items():
        if key not in fields:
            continue
        existing = BlueprintField(**fields[key])
        if patch.value is not None:
            existing.value = parse_field_value(patch.value)
        if patch.confidence is not None:
            existing.confidence = patch.confidence
        if patch.source_page is not None:
            existing.source_page = patch.source_page
        if patch.status is not None:
            existing.status = patch.status
        if patch.extraction_notes is not None:
            existing.extraction_notes = patch.extraction_notes
        fields[key] = existing.model_dump()
        changed_fields.append(key)
    confirmed_count = sum(1 for field in fields.values() if field.get("status") in ("confirmed", "manually_confirmed"))
    unconfirmed_count = sum(1 for field in fields.values() if field.get("status") == "unconfirmed")
    missing_critical = sorted(key for key in CRITICAL_FIELDS if fields.get(key, {}).get("status") == "unconfirmed")
    fail_reasons = [f"Critical fields require manual verification before lock: {', '.join(missing_critical)}."] if missing_critical else []
    status = "needs_review" if missing_critical or unconfirmed_count else "extracted"
    summary = f"Reviewer updated {len(changed_fields)} fields. {confirmed_count} confirmed, {unconfirmed_count} unconfirmed."
    await db.blueprint_extractions.update_one({"id": extraction["id"]}, {"$set": {
        "fields": fields,
        "status": status,
        "summary": summary,
        "confirmed_count": confirmed_count,
        "unconfirmed_count": unconfirmed_count,
        "fail_reasons": fail_reasons,
        "updated_at": now_iso(),
    }})
    await db.blueprint_documents.update_one({"id": document_id}, {"$set": {"status": status, "latest_summary": summary, "updated_at": now_iso()}})
    await record_blueprint_event(document_id, user, "edit", {"fields": changed_fields})
    return await blueprint_detail(document_id)


@router.post("/blueprints/{document_id}/lock")
async def lock_blueprint(document_id: str, payload: BlueprintLockInput, user=Depends(require_feature("blueprint_intelligence", "qc_supervisor", "admin", "executive"))):
    document = await fetch_blueprint_document(document_id)
    if not document.get("latest_extraction_id"):
        raise HTTPException(status_code=400, detail="Blueprint must be extracted before it can be locked")
    extraction = await fetch_blueprint_extraction(document["latest_extraction_id"])
    fields = {key: BlueprintField(**value) for key, value in extraction.get("fields", {}).items()}
    missing_critical = sorted(key for key in CRITICAL_FIELDS if fields.get(key, BlueprintField()).status == "unconfirmed")
    if missing_critical:
        raise HTTPException(status_code=400, detail=f"Cannot lock blueprint until critical fields are confirmed: {', '.join(missing_critical)}")
    revision_number = 1 + await db.locked_blueprint_revisions.count_documents({"document_id": document_id})
    normalized = normalize_locked_blueprint(fields)
    product_family = fields["product_family"].value or document.get("product_family_hint") or "i_beam"
    beam_mark = fields["beam_mark"].value or document.get("beam_mark_hint") or "UNCONFIRMED"
    beam_ids = payload.beam_ids or ([document["beam_id"]] if document.get("beam_id") else [])
    revision = LockedBlueprintRevision(
        document_id=document_id,
        extraction_id=extraction["id"],
        revision_number=revision_number,
        product_family=product_family,
        beam_mark=beam_mark,
        normalized_blueprint=normalized,
        source_fields=fields,
        beam_ids=beam_ids,
        product_type_id=payload.product_type_id or document.get("product_type_id"),
        notes=payload.notes,
        locked_by=user.get("name", ""),
    )
    await db.locked_blueprint_revisions.insert_one(revision.model_dump())
    await db.blueprint_documents.update_one({"id": document_id}, {"$set": {"status": "locked", "locked_revision_id": revision.id, "updated_at": now_iso()}})
    if revision.product_type_id:
        await db.product_types.update_one({"id": revision.product_type_id}, {"$set": {"default_locked_blueprint_revision_id": revision.id, "updated_at": now_iso()}})
    for beam_id in beam_ids:
        await db.beams.update_one({"id": beam_id}, {"$set": {"blueprint_document_id": document_id, "locked_blueprint_revision_id": revision.id}})
    await record_blueprint_event(document_id, user, "lock", {"revision_id": revision.id, "beam_ids": beam_ids, "product_type_id": revision.product_type_id})
    return await blueprint_detail(document_id)
