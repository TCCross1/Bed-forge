from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import logging
import secrets
from collections import Counter
from datetime import date, datetime, timezone, timedelta
from fastapi import Response, FastAPI, APIRouter, Depends, HTTPException, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
import io

from db import db, client
from models import (
    ProductType, ProductTypeCreate, Job, JobCreate, Pour, PourCreate,
    Bed, BedUpdate, Beam, BeamCreate, BeamUpdate,
    Inspection, InspectionCreate, TensionReport, TensionReportCreate, TensionCalcInput,
    CamberReading, CamberReadingCreate, Anomaly, AnomalyCreate,
    BatchRecord, BatchRecordCreate, NCR, NCRCreate, NCRUpdate, LicenseState, LicenseActivateInput, now_iso,
    BlueprintDocument, BlueprintExtraction, BlueprintExtractionPatch, BlueprintField, BlueprintAuditEvent,
    BlueprintLockInput, LockedBlueprintRevision,
)
from beam_spec import materialize_job_beam_specs, twin_beam_from_spec
from auth import router as auth_router, get_current_user, require_roles, seed_admin
from tension import run_tension_calc, calc_theoretical_elongation, evaluate_tension
from seed import seed_plant
import excel_export
import package_export
from extraction_report import build_extraction_report_pdf
from blueprint_pipeline import (
    CRITICAL_FIELDS,
    EXTRACTOR_VERSION,
    FIELD_GROUPS,
    extract_structured_fields,
    normalize_locked_blueprint,
    parse_field_value,
    read_pdf_pages,
    read_pdf_pages_for_extract,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="BedForge QC")
api = APIRouter(prefix="/api")
BLUEPRINT_STORAGE_DIR = ROOT_DIR / "uploads" / "blueprints"
BLUEPRINT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

LICENSE_FEATURES_BY_TIER = {
    "trial": {
        "digital_twin": True,
        "package_export": True,
        "ncr": True,
        "batch_plant": True,
        "licensing": True,
        "command_board": True,
        "blueprint_intelligence": True,
        "advanced_exports": False,
    },
    "standard": {
        "digital_twin": True,
        "package_export": True,
        "ncr": True,
        "batch_plant": True,
        "licensing": True,
        "command_board": True,
        "blueprint_intelligence": True,
        "advanced_exports": False,
    },
    "enterprise": {
        "digital_twin": True,
        "package_export": True,
        "ncr": True,
        "batch_plant": True,
        "licensing": True,
        "command_board": True,
        "blueprint_intelligence": True,
        "advanced_exports": True,
    },
}


def license_features_for_tier(tier: str) -> dict:
    return dict(LICENSE_FEATURES_BY_TIER.get(tier, LICENSE_FEATURES_BY_TIER["trial"]))


def license_has_expired(expires_at: str) -> bool:
    if not expires_at:
        return False
    try:
        return date.fromisoformat(expires_at) < datetime.now(timezone.utc).date()
    except ValueError:
        return True


async def load_license_state() -> dict:
    license_state = await db.licenses.find_one({"id": "license"}, {"_id": 0})
    if not license_state:
        created = LicenseState(
            status="trial",
            tier="trial",
            feature_flags=license_features_for_tier("trial"),
        ).model_dump()
        await db.licenses.insert_one(created)
        return created

    updates = {}
    normalized_flags = {
        **license_features_for_tier(license_state.get("tier", "trial")),
        **license_state.get("feature_flags", {}),
    }
    if normalized_flags != license_state.get("feature_flags", {}):
        updates["feature_flags"] = normalized_flags
        license_state["feature_flags"] = normalized_flags
    if license_has_expired(license_state.get("expires_at", "")) and license_state.get("status") != "expired":
        updates["status"] = "expired"
        license_state["status"] = "expired"
    if updates:
        updates["updated_at"] = now_iso()
        license_state["updated_at"] = updates["updated_at"]
        await db.licenses.update_one({"id": "license"}, {"$set": updates})
    return license_state


async def ensure_feature_enabled(feature: str) -> dict:
    license_state = await load_license_state()
    if license_state.get("status") == "expired":
        raise HTTPException(status_code=403, detail="License expired")
    if not license_state.get("feature_flags", {}).get(feature, False):
        raise HTTPException(status_code=403, detail=f"Feature not licensed: {feature}")
    return license_state


def require_feature(feature: str, *roles: str):
    async def checker(user: dict = Depends(get_current_user)):
        if roles and user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        await ensure_feature_enabled(feature)
        return user
    return checker


async def upsert_beam_specs(specs: list) -> list:
    saved = []
    for spec in specs:
        try:
            query = {"document_id": spec.get("document_id"), "beam_mark": spec.get("beam_mark")}
            existing = await db.beam_specs.find_one(query, {"_id": 0})
            spec["updated_at"] = now_iso()
            if existing:
                spec["id"] = existing.get("id")
                spec["created_at"] = existing.get("created_at") or spec.get("created_at")
                await db.beam_specs.update_one({"id": existing["id"]}, {"$set": spec})
            else:
                await db.beam_specs.insert_one(spec)
            saved.append(spec)
        except Exception:
            logger.exception("Failed to upsert beam spec mark=%s document_id=%s", spec.get("beam_mark"), spec.get("document_id"))
            raise
    return saved


async def materialize_specs_for_revision(document: dict, extraction: dict, revision: dict, beam_ids: list | None = None) -> list:
    fields = {
        key: BlueprintField(**value) if not isinstance(value, BlueprintField) else value
        for key, value in (extraction.get("fields") or {}).items()
    }
    beam_ids_by_mark = {}
    for beam_id in beam_ids or revision.get("beam_ids") or []:
        beam = await db.beams.find_one({"id": beam_id}, {"_id": 0})
        if beam and beam.get("mark"):
            beam_ids_by_mark[str(beam["mark"])] = beam_id
    specs = materialize_job_beam_specs(
        fields,
        document=document,
        revision=revision,
        beam_ids_by_mark=beam_ids_by_mark,
    )
    return await upsert_beam_specs(specs)


async def attach_beam_spec(data: dict, locked_revision: dict | None = None) -> dict:
    spec = None
    try:
        if data.get("id"):
            spec = await db.beam_specs.find_one({"beam_id": data["id"]}, {"_id": 0})
        if spec is None and locked_revision and data.get("mark"):
            spec = await db.beam_specs.find_one({
                "locked_revision_id": locked_revision.get("id"),
                "beam_mark": str(data.get("mark")),
            }, {"_id": 0})
    except Exception:
        logger.exception("Failed to load beam spec for beam_id=%s", data.get("id"))
        spec = None
    if not spec:
        return data
    data["beam_spec"] = spec
    product_type = dict(data.get("product_type") or {})
    product_type["blueprint"] = spec.get("blueprint") or product_type.get("blueprint") or {}
    geometry = spec.get("geometry") or {}
    if geometry.get("depth_in") is not None:
        product_type["depth_in"] = geometry["depth_in"]
    if geometry.get("width_in") is not None:
        product_type["width_in"] = geometry["width_in"]
    data["product_type"] = product_type
    if geometry.get("length_ft") is not None:
        data["length_ft"] = geometry["length_ft"]
    if spec.get("product_family"):
        data["twin_type"] = spec["product_family"]
    source = dict(data.get("blueprint_source") or {})
    source["spec_id"] = spec.get("id")
    source["section_source"] = spec.get("section_source") or geometry.get("section_source")
    data["blueprint_source"] = source
    return data


async def enrich_beam(beam: dict, include_details: bool = False) -> dict:
    data = dict(beam)
    if data.get("product_type_id"):
        data["product_type"] = await db.product_types.find_one({"id": data["product_type_id"]}, {"_id": 0})
    locked_revision = None
    if data.get("locked_blueprint_revision_id"):
        locked_revision = await db.locked_blueprint_revisions.find_one({"id": data["locked_blueprint_revision_id"]}, {"_id": 0})
    elif data.get("product_type", {}).get("default_locked_blueprint_revision_id"):
        locked_revision = await db.locked_blueprint_revisions.find_one({"id": data["product_type"]["default_locked_blueprint_revision_id"]}, {"_id": 0})
    if locked_revision:
        data["locked_blueprint_revision"] = locked_revision
        product_type = dict(data.get("product_type") or {})
        product_type["blueprint"] = locked_revision.get("normalized_blueprint", {})
        product_type["default_locked_blueprint_revision_id"] = locked_revision.get("id")
        product_type["name"] = product_type.get("name") or locked_revision.get("beam_mark") or data.get("mark")
        data["product_type"] = product_type
        data["length_ft"] = locked_revision.get("normalized_blueprint", {}).get("length", data.get("length_ft"))
        data["twin_type"] = locked_revision.get("product_family", data.get("twin_type"))
        data["blueprint_source"] = {
            "status": "locked",
            "document_id": locked_revision.get("document_id"),
            "revision_id": locked_revision.get("id"),
            "beam_mark": locked_revision.get("beam_mark"),
            "locked_at": locked_revision.get("locked_at"),
            "critical_fields_complete": True,
        }
    elif data.get("blueprint_document_id"):
        document = await db.blueprint_documents.find_one({"id": data["blueprint_document_id"]}, {"_id": 0})
        extraction = None
        if document and document.get("latest_extraction_id"):
            extraction = await db.blueprint_extractions.find_one({"id": document["latest_extraction_id"]}, {"_id": 0})
        data["blueprint_source"] = {
            "status": "draft",
            "document_id": data.get("blueprint_document_id"),
            "revision_id": None,
            "beam_mark": extraction and extraction.get("fields", {}).get("beam_mark", {}).get("value"),
            "locked_at": None,
            "critical_fields_complete": False,
        }
    else:
        data["blueprint_source"] = {
            "status": "legacy_seed",
            "document_id": None,
            "revision_id": None,
            "beam_mark": data.get("mark"),
            "locked_at": None,
            "critical_fields_complete": False,
        }
    data = await attach_beam_spec(data, locked_revision)
    if include_details:
        beam_id = data["id"]
        data["anomalies"] = await db.anomalies.find({"beam_id": beam_id}, {"_id": 0}).to_list(500)
        data["inspections"] = await db.inspections.find({"beam_id": beam_id}, {"_id": 0}).to_list(500)
        data["camber_readings"] = await db.camber_readings.find({"beam_id": beam_id}, {"_id": 0}).to_list(500)
    return data


def parse_iso_dt(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def command_board_shift(now: datetime) -> str:
    hour = now.astimezone(timezone.utc).hour
    if 6 <= hour < 14:
        return "Day"
    if 14 <= hour < 22:
        return "Swing"
    return "Night"


def within_same_day(value: str | None, now: datetime) -> bool:
    dt = parse_iso_dt(value)
    return bool(dt and dt.astimezone(timezone.utc).date() == now.astimezone(timezone.utc).date())


def estimate_release_time(bed: dict, batch_record: dict | None, now: datetime) -> str:
    if bed.get("status") in ("complete",):
        return "Ready now"
    offsets = {
        "idle": None,
        "setup": timedelta(hours=12),
        "tensioning": timedelta(hours=8),
        "casting": timedelta(hours=6),
        "curing": timedelta(hours=2),
        "stripping": timedelta(hours=1),
    }
    offset = offsets.get(bed.get("status"))
    if offset is None:
        return "Awaiting schedule"
    anchor = parse_iso_dt((batch_record or {}).get("created_at")) or now
    return (anchor + offset).astimezone(timezone.utc).strftime("%H:%M UTC")


def command_lane_state(bed: dict, beams: list[dict], has_open_ncr: bool) -> dict:
    if has_open_ncr or any(beam.get("qc_state") in ("hold", "failed") for beam in beams):
        return {"key": "hold_ncr", "label": "HOLD / NCR", "accent": "#FF3366"}
    if bed.get("status") in ("casting", "curing"):
        return {"key": "pour_cure", "label": "POUR / CURE", "accent": "#2979FF"}
    if bed.get("status") in ("stripping", "complete") or any(beam.get("qc_state") in ("passed", "shipped") for beam in beams):
        return {"key": "ready_release", "label": "READY / RELEASE", "accent": "#00E676"}
    return {"key": "layout_strand", "label": "LAYOUT / STRAND", "accent": "#FFD600"}


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


async def build_package_context(package_type: str, pour_id: str = None, beam_id: str = None, job_id: str = None) -> dict:
    raw_beams = await db.beams.find({}, {"_id": 0}).to_list(1000)
    beams = [await enrich_beam(beam, include_details=True) for beam in raw_beams]
    jobs = {item["id"]: item for item in await db.jobs.find({}, {"_id": 0}).to_list(500)}
    pours = {item["id"]: item for item in await db.pours.find({}, {"_id": 0}).to_list(500)}
    beds = {item["id"]: item for item in await db.beds.find({}, {"_id": 0}).to_list(100)}
    inspections = await db.inspections.find({}, {"_id": 0}).to_list(5000)
    anomalies = await db.anomalies.find({}, {"_id": 0}).to_list(5000)
    camber_readings = await db.camber_readings.find({}, {"_id": 0}).to_list(5000)
    tension_reports = await db.tension_reports.find({}, {"_id": 0}).to_list(5000)
    batch_records = await db.batch_records.find({}, {"_id": 0}).to_list(500)
    ncrs = await db.ncrs.find({}, {"_id": 0}).to_list(500)

    if package_type == "single_beam":
        if not beam_id and beams:
            beam_id = beams[0]["id"]
        selected_beams = [beam for beam in beams if beam["id"] == beam_id]
    elif package_type == "full_job":
        if not job_id and beams:
            job_id = beams[0].get("job_id")
        selected_beams = [beam for beam in beams if beam.get("job_id") == job_id]
    else:
        if not pour_id and beams:
            pour_id = beams[0].get("pour_id")
        selected_beams = [beam for beam in beams if beam.get("pour_id") == pour_id]

    if not selected_beams:
        raise HTTPException(status_code=404, detail="No beams found for package request")

    selected_job_id = job_id or selected_beams[0].get("job_id")
    if package_type == "full_job":
        selected_pour_ids = sorted(
            item["id"] for item in pours.values()
            if item.get("job_id") == selected_job_id
        )
    else:
        selected_pour_ids = sorted({
            beam.get("pour_id") for beam in selected_beams if beam.get("pour_id")
        })
    selected_pour_id = pour_id or (selected_pour_ids[0] if len(selected_pour_ids) == 1 else None)
    selected_bed_ids = sorted({beam["bed_id"] for beam in selected_beams})

    for reading in camber_readings:
        reading["beam_mark"] = next((beam["mark"] for beam in selected_beams if beam["id"] == reading["beam_id"]), reading.get("beam_id"))
    for report in tension_reports:
        report["bed_number"] = beds.get(report["bed_id"], {}).get("bed_number")

    return {
        "package_type": package_type,
        "job": jobs.get(selected_job_id, {}),
        "pour": pours.get(selected_pour_id, {}),
        "pours": [pours[item_id] for item_id in selected_pour_ids if item_id in pours],
        "beds": [beds[bed_id] for bed_id in selected_bed_ids if bed_id in beds],
        "beams": selected_beams,
        "inspections": [item for item in inspections if item.get("beam_id") in {beam["id"] for beam in selected_beams}],
        "anomalies": [item for item in anomalies if item.get("beam_id") in {beam["id"] for beam in selected_beams}],
        "camber_readings": [item for item in camber_readings if item.get("beam_id") in {beam["id"] for beam in selected_beams}],
        "tension_reports": [item for item in tension_reports if not selected_bed_ids or item.get("bed_id") in selected_bed_ids],
        "batch_record": next((item for item in batch_records if item.get("pour_id") == selected_pour_id), None),
        "batch_records": [item for item in batch_records if item.get("pour_id") in selected_pour_ids],
        "ncrs": [
            item for item in ncrs
            if item.get("beam_id") in {beam["id"] for beam in selected_beams}
            or item.get("pour_id") in selected_pour_ids
        ],
    }


@api.get("/")
async def root():
    return {"message": "BedForge QC API", "status": "ok"}


# ---------------- Product Types ----------------
@api.get("/product-types")
async def list_product_types(user=Depends(get_current_user)):
    return await db.product_types.find({}, {"_id": 0}).to_list(500)


@api.post("/product-types")
async def create_product_type(payload: ProductTypeCreate, user=Depends(get_current_user)):
    pt = ProductType(**payload.model_dump())
    await db.product_types.insert_one(pt.model_dump())
    return pt.model_dump()


# ---------------- Blueprint Intelligence ----------------
@api.get("/blueprints")
async def list_blueprints(user=Depends(require_feature("blueprint_intelligence"))):
    documents = await db.blueprint_documents.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [await blueprint_detail(item["id"]) for item in documents]


@api.get("/blueprints/{document_id}")
async def get_blueprint(document_id: str, user=Depends(require_feature("blueprint_intelligence"))):
    return await blueprint_detail(document_id)


@api.post("/blueprints/upload")
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


@api.get("/blueprints/{document_id}/file")
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



@api.get("/blueprints/{document_id}/extraction-report.pdf")
async def download_extraction_report(document_id: str, user=Depends(require_feature("blueprint_intelligence"))):
    """Download Blueprint Assessment PDF for print verification against plant shop drawings."""
    try:
        document = await fetch_blueprint_document(document_id)
        extraction = None
        locked_revision = None
        latest_id = document.get("latest_extraction_id")
        if latest_id:
            extraction = await fetch_blueprint_extraction(latest_id)
        locked_id = document.get("locked_revision_id")
        if locked_id:
            locked_revision = await db.locked_blueprint_revisions.find_one({"id": locked_id}, {"_id": 0})
        pdf_bytes = build_extraction_report_pdf(document, extraction, locked_revision=locked_revision)
        base = document.get("filename") or document.get("original_filename") or document_id
        safe_name = str(base).replace("/", "_").replace("\\", "_")
        if not safe_name.lower().endswith(".pdf"):
            safe_name = f"{safe_name}.pdf"
        filename = f"blueprint-assessment-{safe_name}"
        logger.info(
            "Blueprint assessment PDF downloaded document_id=%s user=%s bytes=%s",
            document_id,
            user.get("email") or user.get("name"),
            len(pdf_bytes),
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to generate Blueprint Assessment PDF document_id=%s", document_id)
        raise HTTPException(status_code=500, detail="Failed to generate Blueprint Assessment PDF")

@api.post("/blueprints/{document_id}/extract")
async def extract_blueprint(document_id: str, user=Depends(require_feature("blueprint_intelligence", "qc_supervisor", "admin"))):
    document = await fetch_blueprint_document(document_id)
    storage_path = Path(document["storage_path"])
    if not storage_path.exists():
        raise HTTPException(status_code=404, detail="Stored blueprint PDF is missing")

    try:
        logger.info("Blueprint extract start document_id=%s path=%s", document_id, storage_path)
        page_text, page_sources = read_pdf_pages_for_extract(storage_path)
        result = extract_structured_fields(page_text, {
            "product_family_hint": document.get("product_family_hint", ""),
            "beam_mark_hint": document.get("beam_mark_hint", ""),
            "project_name_hint": document.get("project_name_hint", ""),
        }, page_sources=page_sources)
        extraction = BlueprintExtraction(
            document_id=document_id,
            status=result.status,
            extractor_version=EXTRACTOR_VERSION,
            summary=result.summary,
            page_text=result.page_text,
            page_sources=result.page_sources,
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
        await record_blueprint_event(document_id, user, "extract", {
            "extraction_id": extraction.id,
            "status": extraction.status,
            "ocr_pages": sum(1 for src in result.page_sources if "ocr" in (src or "")),
        })
        logger.info(
            "Blueprint extract complete document_id=%s status=%s confirmed=%s unconfirmed=%s ocr_pages=%s",
            document_id,
            extraction.status,
            extraction.confirmed_count,
            extraction.unconfirmed_count,
            sum(1 for src in result.page_sources if "ocr" in (src or "")),
        )
        return await blueprint_detail(document_id)
    except Exception:
        logger.exception("Blueprint extract failed document_id=%s path=%s", document_id, storage_path)
        raise


@api.patch("/blueprints/{document_id}/extraction")
async def patch_blueprint_extraction(document_id: str, payload: BlueprintExtractionPatch, user=Depends(require_feature("blueprint_intelligence", "qc_supervisor", "admin"))):
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
    fail_reasons = []
    missing_critical = sorted(key for key in CRITICAL_FIELDS if fields.get(key, {}).get("status") == "unconfirmed")
    if missing_critical:
        fail_reasons.append(f"Critical fields require manual verification before lock: {', '.join(missing_critical)}.")
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
    await db.blueprint_documents.update_one({"id": document_id}, {"$set": {
        "status": status,
        "latest_summary": summary,
        "updated_at": now_iso(),
    }})
    await record_blueprint_event(document_id, user, "edit", {"fields": changed_fields})
    return await blueprint_detail(document_id)


@api.post("/blueprints/{document_id}/lock")
async def lock_blueprint(document_id: str, payload: BlueprintLockInput, user=Depends(require_feature("blueprint_intelligence", "qc_supervisor", "admin"))):
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
    if isinstance(beam_mark, list):
        beam_mark = "/".join(str(item) for item in beam_mark)
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
    await db.blueprint_documents.update_one({"id": document_id}, {"$set": {
        "status": "locked",
        "locked_revision_id": revision.id,
        "updated_at": now_iso(),
    }})
    if revision.product_type_id:
        await db.product_types.update_one({"id": revision.product_type_id}, {"$set": {
            "default_locked_blueprint_revision_id": revision.id,
            "updated_at": now_iso(),
        }})
    for beam_id in beam_ids:
        await db.beams.update_one({"id": beam_id}, {"$set": {
            "blueprint_document_id": document_id,
            "locked_blueprint_revision_id": revision.id,
        }})
    await record_blueprint_event(document_id, user, "lock", {"revision_id": revision.id, "beam_ids": beam_ids, "product_type_id": revision.product_type_id})
    try:
        specs = await materialize_specs_for_revision(document, extraction, revision.model_dump(), beam_ids)
        logger.info("Locked blueprint materialized %s specs document_id=%s", len(specs), document_id)
    except Exception:
        logger.exception("Blueprint lock succeeded but Spec materialization failed document_id=%s", document_id)
    return await blueprint_detail(document_id)


@api.get("/beam-specs")
async def list_beam_specs(
    job_id: str | None = None,
    job_number: str | None = None,
    document_id: str | None = None,
    beam_id: str | None = None,
    beam_mark: str | None = None,
    user=Depends(get_current_user),
):
    try:
        revision_query = {"document_id": document_id} if document_id else {}
        revisions = await db.locked_blueprint_revisions.find(revision_query, {"_id": 0}).to_list(500)
        for revision in revisions:
            existing = await db.beam_specs.find({"locked_revision_id": revision.get("id")}, {"_id": 0}).to_list(1)
            if existing:
                continue
            document = await db.blueprint_documents.find_one({"id": revision.get("document_id")}, {"_id": 0})
            extraction = await db.blueprint_extractions.find_one({"id": revision.get("extraction_id")}, {"_id": 0})
            if document and extraction:
                await materialize_specs_for_revision(document, extraction, revision, revision.get("beam_ids") or [])
        query = {}
        if job_id:
            query["job_id"] = job_id
        if job_number:
            query["job_number"] = job_number
        if document_id:
            query["document_id"] = document_id
        if beam_id:
            query["beam_id"] = beam_id
        if beam_mark:
            query["beam_mark"] = beam_mark
        specs = await db.beam_specs.find(query, {"_id": 0}).to_list(1000)
        specs.sort(key=lambda item: (
            0 if str(item.get("job_number") or "").strip() else 1,
            str(item.get("job_number") or ""),
            str(item.get("beam_mark") or ""),
        ))
        logger.info("Listed %s beam specs user=%s", len(specs), user.get("email"))
        return specs
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to list beam specs")
        raise HTTPException(status_code=500, detail="Failed to list beam specs")


@api.get("/beam-specs/{spec_id}")
async def get_beam_spec(spec_id: str, user=Depends(get_current_user)):
    spec = await db.beam_specs.find_one({"id": spec_id}, {"_id": 0})
    if not spec:
        raise HTTPException(status_code=404, detail="Beam spec not found")
    return spec


@api.get("/beam-specs/{spec_id}/twin")
async def get_beam_spec_twin(spec_id: str, user=Depends(get_current_user)):
    spec = await db.beam_specs.find_one({"id": spec_id}, {"_id": 0})
    if not spec:
        raise HTTPException(status_code=404, detail="Beam spec not found")
    try:
        return twin_beam_from_spec(spec)
    except Exception:
        logger.exception("Failed to build twin payload for spec_id=%s", spec_id)
        raise HTTPException(status_code=500, detail="Failed to build spec twin")


# ---------------- Jobs ----------------
@api.get("/jobs")
async def list_jobs(user=Depends(get_current_user)):
    return await db.jobs.find({}, {"_id": 0}).to_list(500)


@api.post("/jobs")
async def create_job(payload: JobCreate, user=Depends(get_current_user)):
    job = Job(**payload.model_dump())
    await db.jobs.insert_one(job.model_dump())
    return job.model_dump()


# ---------------- Pours ----------------
@api.get("/pours")
async def list_pours(user=Depends(get_current_user)):
    return await db.pours.find({}, {"_id": 0}).to_list(500)


@api.post("/pours")
async def create_pour(payload: PourCreate, user=Depends(get_current_user)):
    pour = Pour(**payload.model_dump())
    await db.pours.insert_one(pour.model_dump())
    return pour.model_dump()


# ---------------- Beds & Dashboard ----------------
@api.get("/beds")
async def list_beds(user=Depends(get_current_user)):
    return await db.beds.find({}, {"_id": 0}).sort("bed_number", 1).to_list(50)


@api.get("/beds/calendar")
async def beds_calendar(start: str | None = None, days: int = 7, user=Depends(get_current_user)):
    """Week grid for Bed Twin Planner. Declared before /beds/{bed_id} so GET is not 405."""
    try:
        beds = await db.beds.find({}, {"_id": 0}).sort("bed_number", 1).to_list(50)
        return {"beds": beds, "cells": [], "start": start, "days": days}
    except Exception:
        logger.exception("Failed to load bed calendar")
        raise HTTPException(status_code=500, detail="Failed to load bed calendar")


@api.get("/beds/suggest")
async def beds_suggest(date: str | None = None, user=Depends(get_current_user)):
    return {"suggestions": [], "date": date}


@api.get("/planner/pool")
async def planner_pool(date: str | None = None, user=Depends(get_current_user)):
    try:
        jobs = await db.jobs.find({}, {"_id": 0}).to_list(500)
        beams = await db.beams.find({}, {"_id": 0}).to_list(2000)
        for beam in beams:
            beam["assigned"] = bool(beam.get("bed_id"))
        return {"jobs": jobs, "beams": beams, "date": date}
    except Exception:
        logger.exception("Failed to load planner pool")
        raise HTTPException(status_code=500, detail="Failed to load planner pool")


@api.get("/beds/{bed_id}/layout")
async def bed_layout(bed_id: str, date: str | None = None, user=Depends(get_current_user)):
    try:
        bed = await db.beds.find_one({"id": bed_id}, {"_id": 0})
        if not bed:
            raise HTTPException(status_code=404, detail="Bed not found")
        beams = await db.beams.find({"bed_id": bed_id}, {"_id": 0}).to_list(500)
        beams = sorted(beams, key=lambda item: item.get("position_on_bed", 0) or 0)
        used = sum(float(item.get("length_ft") or 0) for item in beams)
        length = float(bed.get("length_ft") or 0)
        remaining = round(max(length - used, 0.0), 2)
        util = round((used / length) * 100, 1) if length else 0
        assignments = []
        for beam in beams:
            assignments.append({
                "id": beam.get("id"),
                "beam_id": beam.get("id"),
                "mark": beam.get("mark"),
                "job_id": beam.get("job_id"),
                "pour_id": beam.get("pour_id"),
                "length_ft": beam.get("length_ft"),
                "position_on_bed": beam.get("position_on_bed"),
                "production_status": beam.get("status"),
                "marked_end_toward": "header",
            })
        return {
            "bed": bed,
            "assignments": assignments,
            "remaining_ft": remaining,
            "utilization_pct": util,
            "over_typical": len(assignments) > 4,
            "active_beam_id": (assignments[0]["beam_id"] if assignments else None),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to load bed layout bed_id=%s", bed_id)
        raise HTTPException(status_code=500, detail="Failed to load bed layout")


@api.get("/beds/{bed_id}/twin")
async def get_bed_twin(bed_id: str, user=Depends(require_feature("digital_twin"))):
    bed = await db.beds.find_one({"id": bed_id}, {"_id": 0})
    if not bed:
        raise HTTPException(status_code=404, detail="Bed not found")
    beams = await db.beams.find({"bed_id": bed_id}, {"_id": 0}).to_list(1000)
    beams = sorted(beams, key=lambda item: item.get("position_on_bed", 0))
    bed["beams"] = [await enrich_beam(beam, include_details=True) for beam in beams]
    if bed.get("current_pour_id"):
        bed["pour"] = await db.pours.find_one({"id": bed["current_pour_id"]}, {"_id": 0})
    return bed


@api.patch("/beds/{bed_id}")
async def update_bed(bed_id: str, payload: BedUpdate, user=Depends(get_current_user)):
    from models import now_iso
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updates["updated_at"] = now_iso()
    await db.beds.update_one({"id": bed_id}, {"$set": updates})
    bed = await db.beds.find_one({"id": bed_id}, {"_id": 0})
    if not bed:
        raise HTTPException(status_code=404, detail="Bed not found")
    return bed


@api.get("/dashboard")
async def dashboard(user=Depends(get_current_user)):
    beds = await db.beds.find({}, {"_id": 0}).sort("bed_number", 1).to_list(50)
    beams = await db.beams.find({}, {"_id": 0}).to_list(1000)
    pours = await db.pours.find({}, {"_id": 0}).to_list(500)
    pour_map = {p["id"]: p for p in pours}

    beams_by_bed = {}
    for b in beams:
        beams_by_bed.setdefault(b["bed_id"], []).append(b)

    bed_cards = []
    for bed in beds:
        bbeams = beams_by_bed.get(bed["id"], [])
        pour = pour_map.get(bed.get("current_pour_id"))
        bed_cards.append({
            **bed,
            "beam_count": len(bbeams),
            "beams": bbeams,
            "pour_number": pour["pour_number"] if pour else None,
        })

    total_beams = len(beams)
    stats = {
        "total_beds": len(beds),
        "active_beds": len([b for b in beds if b["status"] not in ("idle", "complete")]),
        "total_beams": total_beams,
        "passed": len([b for b in beams if b["qc_state"] == "passed"]),
        "in_progress": len([b for b in beams if b["qc_state"] == "in_progress"]),
        "hold": len([b for b in beams if b["qc_state"] == "hold"]),
        "failed": len([b for b in beams if b["qc_state"] == "failed"]),
        "open_anomalies": await db.anomalies.count_documents({}),
    }
    return {"beds": bed_cards, "stats": stats}


@api.get("/command-board")
async def command_board(user=Depends(require_feature("command_board"))):
    now = datetime.now(timezone.utc)
    beds = await db.beds.find({}, {"_id": 0}).sort("bed_number", 1).to_list(50)
    beams = await db.beams.find({}, {"_id": 0}).to_list(1000)
    pours = await db.pours.find({}, {"_id": 0}).to_list(500)
    inspections = await db.inspections.find({}, {"_id": 0}).to_list(5000)
    ncrs = await db.ncrs.find({}, {"_id": 0}).to_list(500)
    batch_records = await db.batch_records.find({}, {"_id": 0}).to_list(500)
    tension_reports = await db.tension_reports.find({}, {"_id": 0}).to_list(5000)
    camber_readings = await db.camber_readings.find({}, {"_id": 0}).to_list(5000)

    pours_by_id = {item["id"]: item for item in pours}
    beams_by_bed = {}
    for beam in beams:
        beams_by_bed.setdefault(beam["bed_id"], []).append(beam)
    inspections_by_beam = {}
    for item in inspections:
        inspections_by_beam.setdefault(item["beam_id"], []).append(item)

    ncrs_by_beam = {}
    open_ncrs = []
    for item in ncrs:
        if item.get("status") != "closed":
            open_ncrs.append(item)
            if item.get("beam_id"):
                ncrs_by_beam.setdefault(item["beam_id"], []).append(item)

    batch_by_pour = {}
    for item in batch_records:
        batch_by_pour[item["pour_id"]] = item

    releases_today_ids = {
        item["beam_id"]
        for item in inspections
        if item.get("section") == "pre_delivery" and item.get("status") == "pass" and within_same_day(item.get("created_at"), now)
    }
    if not releases_today_ids:
        releases_today_ids = {
            beam["id"] for beam in beams
            if beam.get("qc_state") in ("passed", "shipped") and within_same_day(beam.get("created_at"), now)
        }

    release_cycle_hours = []
    for beam in beams:
        beam_inspections = inspections_by_beam.get(beam["id"], [])
        release_events = [
            item for item in beam_inspections
            if item.get("section") == "pre_delivery" and item.get("status") == "pass"
        ]
        if not release_events:
            continue
        start = parse_iso_dt(beam.get("created_at"))
        finish = max(
            (parse_iso_dt(item.get("created_at")) for item in release_events),
            default=None,
        )
        if start and finish:
            release_cycle_hours.append(round((finish - start).total_seconds() / 3600, 1))

    latest_strengths = sorted(
        camber_readings,
        key=lambda item: parse_iso_dt(item.get("reading_date")) or parse_iso_dt(item.get("created_at")) or now,
        reverse=True,
    )[:6]
    strength_trend = [
        {
            "label": f"Beam {next((beam.get('mark') for beam in beams if beam.get('id') == item.get('beam_id')), '—')}",
            "value": item.get("release_strength_psi", 0),
            "required": item.get("required_strength_psi", 0),
        }
        for item in reversed(latest_strengths)
    ]

    camber_passes = [
        abs((item.get("measured_camber_in") or 0) - (item.get("design_camber_in") or 0)) <= 0.25
        for item in camber_readings
    ]
    tension_passes = [bool(item.get("within_tolerance")) for item in tension_reports]

    lanes = []
    for bed in beds:
        bed_beams = sorted(beams_by_bed.get(bed["id"], []), key=lambda item: item.get("position_on_bed", 0))
        pour = pours_by_id.get(bed.get("current_pour_id"))
        batch_record = batch_by_pour.get((pour or {}).get("id"))
        inspectors = [
            item.get("inspector")
            for beam in bed_beams
            for item in inspections_by_beam.get(beam["id"], [])
            if item.get("inspector")
        ]
        open_lane_ncrs = [item for beam in bed_beams for item in ncrs_by_beam.get(beam["id"], [])]
        lane_state = command_lane_state(bed, bed_beams, bool(open_lane_ncrs))
        lanes.append({
            "id": bed["id"],
            "bed_number": bed["bed_number"],
            "name": bed["name"],
            "status": bed.get("status", "idle"),
            "lane_state": lane_state,
            "pour_number": (pour or {}).get("pour_number"),
            "beam_order": " / ".join(beam.get("mark", "—") for beam in bed_beams) or "No active beam order",
            "qc_owner": next((item.get("owner") for item in open_lane_ncrs if item.get("owner")), None) or (Counter(inspectors).most_common(1)[0][0] if inspectors else "Unassigned"),
            "estimated_release": estimate_release_time(bed, batch_record, now),
            "ncr_count": len(open_lane_ncrs),
            "beams": [
                {
                    "id": beam["id"],
                    "mark": beam.get("mark"),
                    "position_on_bed": beam.get("position_on_bed"),
                    "length_ft": beam.get("length_ft"),
                    "status": beam.get("status"),
                    "qc_state": beam.get("qc_state"),
                    "release_tag": (beam.get("traceability") or {}).get("release_tag"),
                }
                for beam in bed_beams
            ],
        })

    severity_counts = {"minor": 0, "moderate": 0, "major": 0}
    for item in open_ncrs:
        severity = item.get("severity", "major")
        if severity in severity_counts:
            severity_counts[severity] += 1

    events = []
    for bed in beds:
        events.append({
            "timestamp": bed.get("updated_at"),
            "message": f"Bed {bed.get('bed_number')} status {bed.get('status', 'idle').upper()}",
        })
    for item in batch_records:
        events.append({
            "timestamp": item.get("created_at"),
            "message": f"Batch {item.get('ticket_number', '—')} captured for pour {pours_by_id.get(item.get('pour_id'), {}).get('pour_number', '—')}",
        })
    for item in open_ncrs:
        events.append({
            "timestamp": item.get("updated_at") or item.get("created_at"),
            "message": f"{item.get('code', 'NCR')} {item.get('status', 'open').replace('_', ' ').upper()} · {item.get('title', 'NCR event')}",
        })
    for item in tension_reports:
        bed_number = next((bed.get("bed_number") for bed in beds if bed.get("id") == item.get("bed_id")), "—")
        events.append({
            "timestamp": item.get("created_at"),
            "message": f"Tension report complete for Bed {bed_number} · {'WITHIN TOL' if item.get('within_tolerance') else 'OUT OF TOL'}",
        })
    for item in camber_readings:
        beam_mark = next((beam.get("mark") for beam in beams if beam.get("id") == item.get("beam_id")), item.get("beam_id", "—"))
        events.append({
            "timestamp": item.get("reading_date") or item.get("created_at"),
            "message": f"Camber / strength logged for {beam_mark} · {item.get('release_strength_psi', 0)} PSI",
        })

    events = sorted(
        [item for item in events if parse_iso_dt(item.get("timestamp"))],
        key=lambda item: parse_iso_dt(item["timestamp"]),
        reverse=True,
    )[:12]

    return {
        "generated_at": now_iso(),
        "plant": "BedForge Command Center",
        "shift": command_board_shift(now),
        "summary": {
            "beds_active": len([bed for bed in beds if bed.get("status") not in ("idle", "complete")]),
            "beams_in_process": len([beam for beam in beams if beam.get("qc_state") not in ("passed", "shipped")]),
            "releases_today": len(releases_today_ids),
            "open_ncrs": len(open_ncrs),
        },
        "lanes": lanes,
        "analytics": {
            "releases_today": len(releases_today_ids),
            "layout_to_release_hours": round(sum(release_cycle_hours) / len(release_cycle_hours), 1) if release_cycle_hours else None,
            "open_ncrs_by_severity": severity_counts,
            "camber_pass_rate": round((sum(camber_passes) / len(camber_passes)) * 100, 1) if camber_passes else None,
            "tension_within_tolerance_rate": round((sum(tension_passes) / len(tension_passes)) * 100, 1) if tension_passes else None,
            "strength_trend": strength_trend,
        },
        "events": events,
    }


# ---------------- Beams ----------------
@api.get("/beams")
async def list_beams(user=Depends(get_current_user)):
    beams = await db.beams.find({}, {"_id": 0}).to_list(1000)
    return [await enrich_beam(beam) for beam in beams]


@api.post("/beams")
async def create_beam(payload: BeamCreate, user=Depends(get_current_user)):
    beam = Beam(**payload.model_dump())
    await db.beams.insert_one(beam.model_dump())
    return beam.model_dump()


@api.get("/beams/{beam_id}")
async def get_beam(beam_id: str, user=Depends(get_current_user)):
    beam = await db.beams.find_one({"id": beam_id}, {"_id": 0})
    if not beam:
        raise HTTPException(status_code=404, detail="Beam not found")
    return await enrich_beam(beam, include_details=True)


@api.patch("/beams/{beam_id}")
async def update_beam(beam_id: str, payload: BeamUpdate, user=Depends(get_current_user)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    await db.beams.update_one({"id": beam_id}, {"$set": updates})
    beam = await db.beams.find_one({"id": beam_id}, {"_id": 0})
    if not beam:
        raise HTTPException(status_code=404, detail="Beam not found")
    return beam


# ---------------- Inspections ----------------
@api.get("/inspections")
async def list_inspections(beam_id: str = None, user=Depends(get_current_user)):
    q = {"beam_id": beam_id} if beam_id else {}
    return await db.inspections.find(q, {"_id": 0}).to_list(1000)


@api.post("/inspections")
async def create_inspection(payload: InspectionCreate, user=Depends(get_current_user)):
    insp = Inspection(**payload.model_dump(), inspector=user["name"])
    await db.inspections.insert_one(insp.model_dump())
    return insp.model_dump()


# ---------------- Tension ----------------
@api.post("/tension/calculate")
async def tension_calculate(payload: TensionCalcInput, user=Depends(get_current_user)):
    return run_tension_calc(payload.model_dump())


@api.get("/tension-reports")
async def list_tension_reports(user=Depends(get_current_user)):
    reports = await db.tension_reports.find({}, {"_id": 0}).to_list(500)
    beds = {b["id"]: b for b in await db.beds.find({}, {"_id": 0}).to_list(50)}
    for r in reports:
        r["bed_number"] = beds.get(r["bed_id"], {}).get("bed_number")
    return reports


@api.post("/tension-reports")
async def create_tension_report(payload: TensionReportCreate, user=Depends(get_current_user)):
    data = payload.model_dump()
    theo = calc_theoretical_elongation(
        data["jacking_force_kip"], data["bed_length_ft"],
        data["strand_area_in2"], data["modulus_ksi"],
    )
    measured = data.get("measured_elongation_in") or 0.0
    var, within = evaluate_tension(theo, measured)
    report = TensionReport(
        bed_id=data["bed_id"], pour_id=data.get("pour_id"),
        strand_size=data["strand_size"], strand_area_in2=data["strand_area_in2"],
        modulus_ksi=data["modulus_ksi"], bed_length_ft=data["bed_length_ft"],
        jacking_force_kip=data["jacking_force_kip"], num_strands=data["num_strands"],
        theoretical_elongation_in=round(theo, 3), measured_elongation_in=measured,
        variance_pct=var, within_tolerance=within,
    )
    await db.tension_reports.insert_one(report.model_dump())
    return report.model_dump()


# ---------------- Camber ----------------
@api.post("/camber-readings")
async def create_camber(payload: CamberReadingCreate, user=Depends(get_current_user)):
    cr = CamberReading(**payload.model_dump())
    await db.camber_readings.insert_one(cr.model_dump())
    return cr.model_dump()


# ---------------- Anomalies / Crack Map ----------------
@api.get("/anomalies")
async def list_anomalies(beam_id: str = None, user=Depends(get_current_user)):
    q = {"beam_id": beam_id} if beam_id else {}
    return await db.anomalies.find(q, {"_id": 0}).to_list(1000)


@api.post("/anomalies")
async def create_anomaly(payload: AnomalyCreate, user=Depends(get_current_user)):
    an = Anomaly(**payload.model_dump(), inspector=user["name"])
    await db.anomalies.insert_one(an.model_dump())
    return an.model_dump()


# ---------------- Batch Plant ----------------
@api.get("/batch-records")
async def list_batch_records(user=Depends(require_feature("batch_plant"))):
    return await db.batch_records.find({}, {"_id": 0}).to_list(500)


@api.post("/batch-records")
async def create_batch_record(payload: BatchRecordCreate, user=Depends(require_feature("batch_plant"))):
    record = BatchRecord(**payload.model_dump(), created_by=user["name"])
    await db.batch_records.insert_one(record.model_dump())
    return record.model_dump()


# ---------------- NCR ----------------
@api.get("/ncrs")
async def list_ncrs(user=Depends(require_feature("ncr"))):
    return await db.ncrs.find({}, {"_id": 0}).to_list(500)


@api.post("/ncrs")
async def create_ncr(payload: NCRCreate, user=Depends(require_feature("ncr"))):
    count = await db.ncrs.count_documents({})
    ncr = NCR(
        code=f"NCR-{datetime.now(timezone.utc).strftime('%y')}-{count + 1:03d}",
        **payload.model_dump(),
        audit_trail=[{"status": "open", "user": user["name"], "note": "Created", "at": now_iso()}],
    )
    await db.ncrs.insert_one(ncr.model_dump())
    return ncr.model_dump()


@api.patch("/ncrs/{ncr_id}")
async def update_ncr(ncr_id: str, payload: NCRUpdate, user=Depends(require_feature("ncr"))):
    current = await db.ncrs.find_one({"id": ncr_id}, {"_id": 0})
    if not current:
        raise HTTPException(status_code=404, detail="NCR not found")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    audit = list(current.get("audit_trail", []))
    if updates.get("status") and updates["status"] != current.get("status"):
        audit.append({"status": updates["status"], "user": user["name"], "note": "Workflow update", "at": now_iso()})
    updates["audit_trail"] = audit
    updates["updated_at"] = now_iso()
    await db.ncrs.update_one({"id": ncr_id}, {"$set": updates})
    return await db.ncrs.find_one({"id": ncr_id}, {"_id": 0})


# ---------------- Licensing ----------------
@api.get("/license")
async def get_license(user=Depends(get_current_user)):
    return await load_license_state()


@api.post("/license/activate")
async def activate_license(payload: LicenseActivateInput, user=Depends(require_roles("admin"))):
    configured_key = os.environ.get("LICENSE_ACTIVATION_KEY", "").strip()
    if not configured_key:
        raise HTTPException(status_code=503, detail="License activation is not configured")
    if not secrets.compare_digest(payload.license_key, configured_key):
        raise HTTPException(status_code=403, detail="Invalid license activation key")
    try:
        expires_at = date.fromisoformat(payload.expires_at)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Expiration date must use YYYY-MM-DD") from exc
    if expires_at < datetime.now(timezone.utc).date():
        raise HTTPException(status_code=400, detail="License expiration date cannot be in the past")

    features = license_features_for_tier(payload.tier)
    updates = LicenseState(
        status="active",
        tier=payload.tier,
        license_key=f"****{payload.license_key[-4:]}",
        expires_at=payload.expires_at,
        feature_flags=features,
        last_checked_at=now_iso(),
        updated_at=now_iso(),
    )
    current = await db.licenses.find_one({"id": "license"}, {"_id": 0})
    if current:
        await db.licenses.update_one({"id": "license"}, {"$set": updates.model_dump()})
    else:
        await db.licenses.insert_one(updates.model_dump())
    return updates.model_dump()


# ---------------- Forms Export ----------------
@api.get("/forms/export/{form_type}")
async def export_form(form_type: str, beam_id: str = None, user=Depends(require_feature("package_export"))):
    if form_type not in excel_export.BUILDERS:
        raise HTTPException(status_code=400, detail="Unknown form type")

    beams = {b["id"]: b for b in await db.beams.find({}, {"_id": 0}).to_list(1000)}
    beds = {b["id"]: b for b in await db.beds.find({}, {"_id": 0}).to_list(50)}
    jobs = {j["id"]: j for j in await db.jobs.find({}, {"_id": 0}).to_list(500)}
    ptypes = {p["id"]: p for p in await db.product_types.find({}, {"_id": 0}).to_list(500)}

    context = {}
    if form_type == "qir":
        beam = beams.get(beam_id) or (list(beams.values())[0] if beams else {})
        context["beam"] = beam
        context["job"] = jobs.get(beam.get("job_id"), {})
        pt = ptypes.get(beam.get("product_type_id"), {})
        context["product_type_name"] = pt.get("name", "")
        context["inspections"] = await db.inspections.find({"beam_id": beam.get("id")}, {"_id": 0}).to_list(500)
    elif form_type == "tension":
        reports = await db.tension_reports.find({}, {"_id": 0}).to_list(500)
        for r in reports:
            r["bed_number"] = beds.get(r["bed_id"], {}).get("bed_number")
        context["tension_reports"] = reports
    elif form_type == "camber":
        readings = await db.camber_readings.find({}, {"_id": 0}).to_list(500)
        for r in readings:
            r["beam_mark"] = beams.get(r["beam_id"], {}).get("mark", "")
        context["camber_readings"] = readings
    elif form_type == "crackmap":
        anomalies = await db.anomalies.find({}, {"_id": 0}).to_list(1000)
        for a in anomalies:
            a["beam_mark"] = beams.get(a["beam_id"], {}).get("mark", "")
        context["anomalies"] = anomalies

    builder_name, filename = excel_export.BUILDERS[form_type]
    data = getattr(excel_export, builder_name)(context)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}.xlsx"},
    )


@api.get("/packages/export/pdf")
async def export_package_pdf(
    package_type: str = "pour_complete",
    pour_id: str = None,
    beam_id: str = None,
    job_id: str = None,
    user=Depends(require_feature("package_export")),
):
    if package_type not in ("pour_complete", "single_beam", "full_job"):
        raise HTTPException(status_code=400, detail="Unknown package type")
    if package_type == "full_job":
        await ensure_feature_enabled("advanced_exports")
    context = await build_package_context(package_type, pour_id=pour_id, beam_id=beam_id, job_id=job_id)
    data = package_export.build_package_pdf(context)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={package_type}.pdf"},
    )


app.include_router(auth_router)
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[origin.strip() for origin in os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",") if origin.strip()],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.beds.create_index("bed_number")
    await db.beams.create_index("bed_id")
    await db.blueprint_documents.create_index("beam_id")
    await db.blueprint_documents.create_index("created_at")
    await db.blueprint_extractions.create_index("document_id")
    await db.locked_blueprint_revisions.create_index("document_id")
    await db.blueprint_audit_events.create_index("document_id")
    await db.beam_specs.create_index("document_id")
    await db.beam_specs.create_index("beam_mark")
    await seed_admin()
    await seed_plant()
    logger.info("BedForge QC startup complete.")


@app.on_event("shutdown")
async def shutdown():
    client.close()
