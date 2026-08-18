from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import logging
from collections import Counter
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from starlette.middleware.cors import CORSMiddleware
import io

from db import db, client
from models import (
    now_iso,
    ProductType, ProductTypeCreate, Job, JobCreate, Pour, PourCreate,
    Bed, BedUpdate, Beam, BeamCreate, BeamUpdate,
    Inspection, InspectionCreate, TensionReport, TensionReportCreate, TensionCalcInput,
    CamberReading, CamberReadingCreate, Anomaly, AnomalyCreate,
    FinishSheet, FinishSheetCreate, PreDelivery, PreDeliveryCreate,
    LicenseActivateInput,
)
from auth import router as auth_router, get_current_user, seed_admin
from audit import write_audit, override_active
from control_routes import router as control_router
from security_core import assert_production_safe, is_production, security_headers_middleware
from tension import run_tension_calc, calc_theoretical_elongation, evaluate_tension
from seed import seed_plant, seed_l25390, seed_bed_assignments, seed_strand_rolls, seed_company, seed_beam_qr_tokens, seed_mix_designs, seed_mock_hardware_stations
from blueprint_routes import router as blueprint_router
from blueprint_intelligence_routes import router as blueprint_intelligence_router
from bed_routes import router as bed_router
from tension_routes import router as tension_router
from ar_routes import router as ar_router, emit_sync_event
from bed_layout import covers, map_production_status
from strand_roll_routes import router as strand_roll_router, assert_tension_allowed
from beam_qr import assemble_dossier
from beam_qr_routes import router as beam_qr_router
from company_routes import router as company_router
from cylinder_routes import router as cylinder_router
from owner_routes import router as owner_router, attach_board_forecasts, forecast_for_pour, mix_settings
from coach_routes import router as coach_router
from fresh_routes import router as fresh_router
from batch_routes import router as batch_router
from ncr_routes import router as ncr_router, open_ncr_from_anomaly
from ncr import attach_prompt, build_prompt, is_escalated
from maturity import evaluate_release_gate
from licensing import activate_license_state, ensure_feature_enabled, load_license_state, require_feature
import excel_export
import package_export

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="BedForge QC")
api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"message": "BedForge QC API", "status": "ok"}



def _as_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _station_item(item: dict, kind: str = "hardware") -> dict:
    pos = item.get("position") or {}
    return {
        "id": item.get("id") or item.get("name") or kind,
        "kind": item.get("kind") or kind,
        "name": item.get("name") or item.get("type_code") or kind.replace("_", " ").title(),
        "type_code": item.get("type_code") or "",
        "size": item.get("size") or "",
        "x_ft": _as_float(pos.get("station_ft") if isinstance(pos, dict) else item.get("station_ft")),
        "offset_in": _as_float(pos.get("offset_in") if isinstance(pos, dict) else item.get("offset_in")),
        "height_in": _as_float(pos.get("height_from_soffit_in") if isinstance(pos, dict) else item.get("height_from_soffit_in")),
        "diameter_in": _as_float(item.get("diameter_in") or item.get("diameter"), 0),
        "side": item.get("side") or (pos.get("face") if isinstance(pos, dict) else "") or item.get("face") or "",
        "embed": item.get("embed") or item.get("type_code") or "",
        "end": item.get("end") or "",
        "length_in": _as_float(item.get("length_in"), 0),
        "station_source": item.get("station_source") or "",
        "quantity": int(item.get("quantity") or item.get("quantity_at_station") or 1),
        "notes": item.get("notes") or "",
    }


def blueprint_from_legacy_spec(beam: dict, product_type: dict | None = None, spec: dict | None = None) -> dict:
    product_type = product_type or {}
    spec = spec or {}
    geometry = spec.get("geometry") or {}
    twin_type = geometry.get("twin_type") or beam.get("twin_type") or product_type.get("category") or "i_beam"
    length_ft = _as_float(geometry.get("length_ft"), _as_float(beam.get("length_ft"), _as_float(product_type.get("default_length_ft"), 100)))
    depth = _as_float(geometry.get("depth_in"), _as_float(product_type.get("depth_in"), 36))
    width = _as_float(geometry.get("width_in"), _as_float(product_type.get("width_in"), 18))
    cross_section = {
        "overall_depth_in": depth,
        "outer_depth_in": depth,
        "outer_width_in": width,
        "top_flange_width_in": _as_float(geometry.get("top_flange_width_in"), width),
        "top_flange_thickness_in": _as_float(geometry.get("top_flange_thick_in"), 6),
        "bottom_flange_width_in": _as_float(geometry.get("bot_flange_width_in"), width),
        "bottom_flange_thickness_in": _as_float(geometry.get("bot_flange_thick_in"), 6),
        "web_thickness_in": _as_float(geometry.get("web_thick_in"), 6),
        "wall_thickness_in": _as_float(geometry.get("wall_thickness_in"), 6),
        "void_width_in": _as_float(geometry.get("void_width_in"), max(width - 8, 0)),
        "void_depth_in": _as_float(geometry.get("void_depth_in"), max(depth - 8, 0)),
    }
    strands = spec.get("strands") or []
    rows = []
    for strand in strands:
        row = int(strand.get("row") or 0)
        while len(rows) <= row:
            rows.append({"row": len(rows), "count": 0, "height_in": 0, "offsets_in": []})
        rows[row]["count"] += 1
        rows[row]["height_in"] = _as_float(strand.get("soffit_in") or strand.get("y_in"), rows[row]["height_in"] or 2)
        rows[row]["offsets_in"].append(_as_float(strand.get("offset_in") or strand.get("x_in"), 0))
    if not rows:
        rows = [{"row": 0, "count": 8, "height_in": 2.5, "offsets_in": [-7, -5, -3, -1, 1, 3, 5, 7]}]
    hardware = [_station_item(item) for item in spec.get("hardware") or []]
    by_kind = {}
    for item in hardware:
        by_kind.setdefault(item.get("kind", "hardware"), []).append(item)
    hold_downs = [
        {
            "id": item.get("id"),
            "x_ft": _as_float(item.get("station_from_marked_end")),
            "height_in": _as_float(item.get("height"), 2.5),
            "offset_in": _as_float(item.get("offset_in")),
            "type": item.get("type_spec") or "hold-down",
            "status": item.get("status") or "pending",
        }
        for item in spec.get("hold_downs") or []
    ]
    stirrup_zones = spec.get("stirrup_zones") or []
    first_zone = stirrup_zones[0] if stirrup_zones else {}
    return {
        "length": length_ft,
        "product_family": twin_type,
        "cross_section": cross_section,
        "marked_end": {"label": spec.get("marked_end_id") or "MARKED END", "x_ft": 0},
        "unmarked_end": {"label": spec.get("unmarked_end_id") or "UNMARKED END", "x_ft": length_ft},
        "strand_pattern": {"rows": rows},
        "stirrups": {
            "zones": stirrup_zones,
            "start_ft": _as_float(first_zone.get("from_ft"), 0),
            "end_ft": _as_float(first_zone.get("to_ft"), length_ft),
            "spacing_in": _as_float(first_zone.get("spacing_in"), 24),
            "bar_size": first_zone.get("bar_size") or "#4",
        },
        "hold_downs": hold_downs,
        "lift_loops": by_kind.get("lift_loop", []),
        "inserts": by_kind.get("insert", []) + by_kind.get("inserts", []),
        "tubes": by_kind.get("tube", []) + by_kind.get("void_tube", []),
        "tie_rod_openings": by_kind.get("tie_rod", []),
        "drain_holes": by_kind.get("drain", []) + by_kind.get("drain_hole", []),
        "grout_grooves": by_kind.get("grout_groove", []),
        "bituminous_ends": by_kind.get("bituminous", []) + by_kind.get("bituminous_zone", []),
        "hardware": hardware,
        "tolerances": spec.get("tolerances") or {},
        "station_source": spec.get("station_source") or "",
        "station_notes": spec.get("station_notes") or "",
    }


async def enrich_beam_for_twin(beam: dict, include_details: bool = False) -> dict:
    data = dict(beam or {})
    product_type = None
    if data.get("product_type_id"):
        product_type = await db.product_types.find_one({"id": data["product_type_id"]}, {"_id": 0})
    spec = None
    if data.get("spec_id"):
        spec = await db.beam_specs.find_one({"id": data["spec_id"]}, {"_id": 0})
    if not spec and data.get("id"):
        latest = await db.beam_specs.find({"beam_id": data["id"]}, {"_id": 0}).sort("created_at", -1).to_list(1)
        spec = latest[0] if latest else None
    locked_revision = None
    if data.get("locked_blueprint_revision_id"):
        locked_revision = await db.locked_blueprint_revisions.find_one({"id": data["locked_blueprint_revision_id"]}, {"_id": 0})
    elif product_type and product_type.get("default_locked_blueprint_revision_id"):
        locked_revision = await db.locked_blueprint_revisions.find_one({"id": product_type["default_locked_blueprint_revision_id"]}, {"_id": 0})
    product_type = dict(product_type or {})
    if locked_revision:
        product_type["blueprint"] = locked_revision.get("normalized_blueprint", {})
        product_type["default_locked_blueprint_revision_id"] = locked_revision.get("id")
        product_type["name"] = product_type.get("name") or locked_revision.get("beam_mark") or data.get("mark")
        data["length_ft"] = locked_revision.get("normalized_blueprint", {}).get("length", data.get("length_ft"))
        data["twin_type"] = locked_revision.get("product_family", data.get("twin_type"))
        data["blueprint_source"] = {"status": "locked", "document_id": locked_revision.get("document_id"), "revision_id": locked_revision.get("id"), "beam_mark": locked_revision.get("beam_mark"), "locked_at": locked_revision.get("locked_at"), "critical_fields_complete": True}
    elif data.get("blueprint_document_id"):
        document = await db.blueprint_documents.find_one({"id": data["blueprint_document_id"]}, {"_id": 0})
        extraction = await db.blueprint_extractions.find_one({"id": document.get("latest_extraction_id")}, {"_id": 0}) if document and document.get("latest_extraction_id") else None
        product_type["blueprint"] = blueprint_from_legacy_spec(data, product_type, spec) if spec and spec.get("station_source") == "mock" else (product_type.get("blueprint") or blueprint_from_legacy_spec(data, product_type, spec))
        data["blueprint_source"] = {"status": "draft", "document_id": data.get("blueprint_document_id"), "revision_id": None, "beam_mark": extraction and extraction.get("fields", {}).get("beam_mark", {}).get("value"), "locked_at": None, "critical_fields_complete": False}
    else:
        product_type["blueprint"] = blueprint_from_legacy_spec(data, product_type, spec) if spec and spec.get("station_source") == "mock" else (product_type.get("blueprint") or blueprint_from_legacy_spec(data, product_type, spec))
        data["blueprint_source"] = {"status": "legacy_seed", "document_id": None, "revision_id": None, "beam_mark": data.get("mark"), "locked_at": None, "critical_fields_complete": False}
        if spec and spec.get("station_source"):
            data["blueprint_source"]["station_source"] = spec.get("station_source")
            data["blueprint_source"]["station_notes"] = spec.get("station_notes") or ""
    if not product_type.get("name") and spec:
        product_type["name"] = spec.get("product_name") or spec.get("geometry", {}).get("product_name") or data.get("mark")
    if product_type:
        data["product_type"] = product_type
    if spec:
        data["spec"] = spec
    if include_details and data.get("id"):
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


def within_same_day(value: str | None, now: datetime) -> bool:
    dt = parse_iso_dt(value)
    return bool(dt and dt.astimezone(timezone.utc).date() == now.astimezone(timezone.utc).date())


def command_board_shift(now: datetime) -> str:
    hour = now.astimezone(timezone.utc).hour
    if 6 <= hour < 14:
        return "Day"
    if 14 <= hour < 22:
        return "Swing"
    return "Night"


def estimate_release_time(bed: dict, batch_record: dict | None, now: datetime) -> str:
    if bed.get("status") in ("complete",):
        return "Ready now"
    offsets = {"idle": None, "setup": timedelta(hours=12), "tensioning": timedelta(hours=8), "casting": timedelta(hours=6), "curing": timedelta(hours=2), "stripping": timedelta(hours=1)}
    offset = offsets.get(bed.get("status"))
    if offset is None:
        return "Awaiting schedule"
    anchor = parse_iso_dt((batch_record or {}).get("created_at") or (batch_record or {}).get("batched_at")) or now
    return (anchor + offset).astimezone(timezone.utc).strftime("%H:%M UTC")


def command_lane_state(bed: dict, beams: list[dict], has_open_ncr: bool) -> dict:
    if has_open_ncr or any(beam.get("qc_state") in ("hold", "failed") for beam in beams):
        return {"key": "hold_ncr", "label": "HOLD / NCR", "accent": "#FF3366"}
    if bed.get("status") in ("casting", "curing"):
        return {"key": "pour_cure", "label": "POUR / CURE", "accent": "#2979FF"}
    if bed.get("status") in ("stripping", "complete") or any(beam.get("qc_state") in ("passed", "shipped") for beam in beams):
        return {"key": "ready_release", "label": "READY / RELEASE", "accent": "#00E676"}
    return {"key": "layout_strand", "label": "LAYOUT / STRAND", "accent": "#FFD600"}


async def build_package_context(package_type: str, pour_id: str = None, beam_id: str = None, job_id: str = None) -> dict:
    raw_beams = await db.beams.find({}, {"_id": 0}).to_list(1000)
    beams = [await enrich_beam_for_twin(beam, include_details=True) for beam in raw_beams]
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
        selected_pour_ids = sorted(item["id"] for item in pours.values() if item.get("job_id") == selected_job_id)
    else:
        selected_pour_ids = sorted({beam.get("pour_id") for beam in selected_beams if beam.get("pour_id")})
    selected_pour_id = pour_id or (selected_pour_ids[0] if len(selected_pour_ids) == 1 else None)
    selected_bed_ids = sorted({beam["bed_id"] for beam in selected_beams if beam.get("bed_id")})
    for reading in camber_readings:
        reading["beam_mark"] = next((beam["mark"] for beam in selected_beams if beam["id"] == reading.get("beam_id")), reading.get("beam_id"))
    for report in tension_reports:
        report["bed_number"] = beds.get(report.get("bed_id"), {}).get("bed_number")
    selected_beam_ids = {beam["id"] for beam in selected_beams}
    return {
        "package_type": package_type,
        "job": jobs.get(selected_job_id, {}),
        "pour": pours.get(selected_pour_id, {}),
        "pours": [pours[item_id] for item_id in selected_pour_ids if item_id in pours],
        "beds": [beds[bed_id] for bed_id in selected_bed_ids if bed_id in beds],
        "beams": selected_beams,
        "inspections": [item for item in inspections if item.get("beam_id") in selected_beam_ids],
        "anomalies": [item for item in anomalies if item.get("beam_id") in selected_beam_ids],
        "camber_readings": [item for item in camber_readings if item.get("beam_id") in selected_beam_ids],
        "tension_reports": [item for item in tension_reports if not selected_bed_ids or item.get("bed_id") in selected_bed_ids],
        "batch_record": next((item for item in batch_records if item.get("pour_id") == selected_pour_id), None),
        "batch_records": [item for item in batch_records if item.get("pour_id") in selected_pour_ids],
        "ncrs": [item for item in ncrs if item.get("beam_id") in selected_beam_ids or any(b in selected_beam_ids for b in item.get("beam_ids", [])) or item.get("pour_id") in selected_pour_ids],
    }


def _ncr_public_github(doc: dict) -> dict:
    out = dict(doc or {})
    out["code"] = out.get("code") or f"NCR-{out.get('created_at', '')[:4] or '26'}-{str(out.get('id', ''))[:6].upper()}"
    out["title"] = out.get("title") or out.get("description") or out.get("sub_type") or "Non-conformance"
    out["owner"] = out.get("owner") or out.get("assigned_to") or out.get("assigned_role") or ""
    if out.get("status") == "investigating":
        out["status"] = "investigation"
    return out


# ---------------- Product Types ----------------
@api.get("/product-types")
async def list_product_types(user=Depends(get_current_user)):
    try:
        return await db.product_types.find({}, {"_id": 0}).to_list(500)
    except Exception:
        logger.exception("list_product_types failed user=%s", user.get("email"))
        raise HTTPException(status_code=500, detail="Failed to list product types")


@api.post("/product-types")
async def create_product_type(payload: ProductTypeCreate, user=Depends(get_current_user)):
    try:
        pt = ProductType(**payload.model_dump())
        await db.product_types.insert_one(pt.model_dump())
        logger.info("product type created id=%s by=%s", pt.id, user.get("email"))
        return pt.model_dump()
    except Exception:
        logger.exception("create_product_type failed user=%s", user.get("email"))
        raise HTTPException(status_code=500, detail="Failed to create product type")


# ---------------- Jobs ----------------
@api.get("/jobs")
async def list_jobs(user=Depends(get_current_user)):
    try:
        return await db.jobs.find({}, {"_id": 0}).to_list(500)
    except Exception:
        logger.exception("list_jobs failed")
        raise HTTPException(status_code=500, detail="Failed to list jobs")


@api.post("/jobs")
async def create_job(payload: JobCreate, user=Depends(get_current_user)):
    try:
        job = Job(**payload.model_dump())
        await db.jobs.insert_one(job.model_dump())
        logger.info("job created id=%s by=%s", job.id, user.get("email"))
        return job.model_dump()
    except Exception:
        logger.exception("create_job failed")
        raise HTTPException(status_code=500, detail="Failed to create job")


# ---------------- Pours ----------------
@api.get("/pours")
async def list_pours(job_id: str = None, user=Depends(get_current_user)):
    try:
        q = {"job_id": job_id} if job_id else {}
        return await db.pours.find(q, {"_id": 0}).to_list(500)
    except Exception:
        logger.exception("list_pours failed")
        raise HTTPException(status_code=500, detail="Failed to list pours")


@api.post("/pours")
async def create_pour(payload: PourCreate, user=Depends(get_current_user)):
    try:
        pour = Pour(**payload.model_dump())
        await db.pours.insert_one(pour.model_dump())
        logger.info("pour created id=%s by=%s", pour.id, user.get("email"))
        return pour.model_dump()
    except Exception:
        logger.exception("create_pour failed")
        raise HTTPException(status_code=500, detail="Failed to create pour")


# ---------------- Beds & Dashboard ----------------
@api.get("/beds")
async def list_beds(user=Depends(get_current_user)):
    try:
        return await db.beds.find({}, {"_id": 0}).sort("bed_number", 1).to_list(50)
    except Exception:
        logger.exception("list_beds failed")
        raise HTTPException(status_code=500, detail="Failed to list beds")


@api.get("/beds/{bed_id}/twin")
async def get_bed_twin(bed_id: str, user=Depends(require_feature("digital_twin"))):
    try:
        bed = await db.beds.find_one({"id": bed_id}, {"_id": 0})
        if not bed:
            raise HTTPException(status_code=404, detail="Bed not found")
        beams = await db.beams.find({"bed_id": bed_id}, {"_id": 0}).to_list(1000)
        beams = sorted(beams, key=lambda item: item.get("position_on_bed", 0))
        bed["beams"] = [await enrich_beam_for_twin(beam, include_details=True) for beam in beams]
        if bed.get("current_pour_id"):
            bed["pour"] = await db.pours.find_one({"id": bed["current_pour_id"]}, {"_id": 0})
        return bed
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_bed_twin failed id=%s", bed_id)
        raise HTTPException(status_code=500, detail="Failed to load bed twin")


@api.patch("/beds/{bed_id}")
async def update_bed(bed_id: str, payload: BedUpdate, user=Depends(get_current_user)):
    try:
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        if updates.get("status") == "tensioning":
            bed = await db.beds.find_one({"id": bed_id}, {"_id": 0})
            if not bed:
                raise HTTPException(status_code=404, detail="Bed not found")
            await assert_tension_allowed(bed_id, updates.get("current_pour_id") or bed.get("current_pour_id"))
        updates["updated_at"] = now_iso()
        await db.beds.update_one({"id": bed_id}, {"$set": updates})
        bed = await db.beds.find_one({"id": bed_id}, {"_id": 0})
        if not bed:
            raise HTTPException(status_code=404, detail="Bed not found")
        logger.info("bed updated id=%s by=%s", bed_id, user.get("email"))
        return bed
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_bed failed id=%s", bed_id)
        raise HTTPException(status_code=500, detail="Failed to update bed")


@api.get("/dashboard")
async def dashboard(user=Depends(get_current_user)):
    try:
        beds = await db.beds.find({}, {"_id": 0}).sort("bed_number", 1).to_list(50)
        beams = await db.beams.find({}, {"_id": 0}).to_list(1000)
        pours = await db.pours.find({}, {"_id": 0}).to_list(500)
        pour_map = {p["id"]: p for p in pours}

        today = datetime.now(timezone.utc).date().isoformat()
        assignments = await db.bed_assignments.find({}, {"_id": 0}).to_list(2000)
        assign_by_bed = {}
        for rec in assignments:
            if covers(rec, today):
                assign_by_bed.setdefault(rec["bed_id"], []).append(rec)
        for recs in assign_by_bed.values():
            recs.sort(key=lambda a: a.get("position_on_bed") or 0)
        beam_map = {b["id"]: b for b in beams}

        beams_by_bed = {}
        for b in beams:
            if not b.get("bed_id"):
                continue
            beams_by_bed.setdefault(b["bed_id"], []).append(b)

        bed_cards = []
        for bed in beds:
            recs = assign_by_bed.get(bed["id"], [])
            if recs:
                bbeams = []
                for rec in recs:
                    beam = beam_map.get(rec["beam_id"])
                    if not beam:
                        continue
                    bbeams.append({
                        **beam,
                        "production_status": rec.get("production_status") or beam.get("production_status") or map_production_status(beam.get("status"), beam.get("qc_state")),
                        "station_ft": rec.get("station_ft"),
                        "assignment_id": rec.get("id"),
                        "position_on_bed": rec.get("position_on_bed") or beam.get("position_on_bed"),
                    })
            else:
                bbeams = sorted(beams_by_bed.get(bed["id"], []), key=lambda b: b.get("position_on_bed") or 0)
            pour = pour_map.get(bed.get("current_pour_id"))
            bed_cards.append({
                **bed,
                "beam_count": len(bbeams),
                "beams": bbeams,
                "pour_number": pour["pour_number"] if pour else None,
                "layout_date": today,
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
            "open_ncrs": await db.ncrs.count_documents({"status": {"$nin": ["closed", "rejected"]}}),
            "overdue_ncrs": 0,
        }
        open_rows = await db.ncrs.find(
            {"status": {"$nin": ["closed", "rejected"]}},
            {"_id": 0, "status": 1, "severity": 1, "created_at": 1},
        ).to_list(400)
        stats["overdue_ncrs"] = sum(1 for row in open_rows if is_escalated(row))
        forecast_stats = await attach_board_forecasts(bed_cards)
        stats.update({
            "release_expected_pass": forecast_stats.get("expected_pass", 0) + forecast_stats.get("confirmed_pass", 0),
            "release_borderline": forecast_stats.get("borderline", 0),
            "release_fail_risk": forecast_stats.get("fail_risk", 0) + forecast_stats.get("confirmed_fail", 0),
        })
        return {"beds": bed_cards, "stats": stats}
    except Exception:
        logger.exception("dashboard failed user=%s", user.get("email"))
        raise HTTPException(status_code=500, detail="Failed to load dashboard")


# ---------------- Beams ----------------
@api.get("/beams")
async def list_beams(user=Depends(get_current_user)):
    try:
        beams = await db.beams.find({}, {"_id": 0}).to_list(1000)
        return [await enrich_beam_for_twin(beam) for beam in beams]
    except Exception:
        logger.exception("list_beams failed")
        raise HTTPException(status_code=500, detail="Failed to list beams")


@api.post("/beams")
async def create_beam(payload: BeamCreate, user=Depends(get_current_user)):
    try:
        beam = Beam(**payload.model_dump())
        await db.beams.insert_one(beam.model_dump())
        logger.info("beam created id=%s mark=%s by=%s", beam.id, beam.mark, user.get("email"))
        return beam.model_dump()
    except Exception:
        logger.exception("create_beam failed")
        raise HTTPException(status_code=500, detail="Failed to create beam")


@api.get("/beams/{beam_id}")
async def get_beam(beam_id: str, user=Depends(get_current_user)):
    try:
        beam = await db.beams.find_one({"id": beam_id}, {"_id": 0})
        if not beam:
            raise HTTPException(status_code=404, detail="Beam not found")
        dossier = await assemble_dossier(beam, full=True)
        enriched = await enrich_beam_for_twin(beam, include_details=True)
        dossier.update({k: v for k, v in enriched.items() if k not in dossier or k in ("product_type", "spec", "blueprint_source", "anomalies", "inspections", "camber_readings")})
        return dossier
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_beam failed id=%s", beam_id)
        raise HTTPException(status_code=500, detail="Failed to load beam")


@api.patch("/beams/{beam_id}")
async def update_beam(beam_id: str, payload: BeamUpdate, user=Depends(get_current_user)):
    try:
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        await db.beams.update_one({"id": beam_id}, {"$set": updates})
        beam = await db.beams.find_one({"id": beam_id}, {"_id": 0})
        if not beam:
            raise HTTPException(status_code=404, detail="Beam not found")
        logger.info("beam updated id=%s by=%s fields=%s", beam_id, user.get("email"), list(updates.keys()))
        return beam
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_beam failed id=%s", beam_id)
        raise HTTPException(status_code=500, detail="Failed to update beam")


# ---------------- Inspections ----------------
@api.get("/inspections")
async def list_inspections(beam_id: str = None, user=Depends(get_current_user)):
    try:
        q = {"beam_id": beam_id} if beam_id else {}
        return await db.inspections.find(q, {"_id": 0}).to_list(1000)
    except Exception:
        logger.exception("list_inspections failed")
        raise HTTPException(status_code=500, detail="Failed to list inspections")


@api.post("/inspections")
async def create_inspection(payload: InspectionCreate, user=Depends(get_current_user)):
    try:
        insp = Inspection(**payload.model_dump(), inspector=user["name"])
        dumped = insp.model_dump()
        await db.inspections.insert_one(dumped)
        logger.info("inspection created id=%s section=%s beam=%s by=%s", insp.id, insp.section, insp.beam_id, user.get("email"))
        if insp.status in ("fail", "hold"):
            dumped = attach_prompt(dumped, build_prompt(
                source_type="inspection",
                source_id=insp.id,
                title="QIR fail — file an NCR",
                category="process",
                severity="major" if insp.status == "fail" else "minor",
                description=f"{insp.section} {insp.status}",
                beam_id=insp.beam_id,
            ))
        return dumped
    except Exception:
        logger.exception("create_inspection failed")
        raise HTTPException(status_code=500, detail="Failed to create inspection")


# ---------------- Tension ----------------
@api.post("/tension/calculate")
async def tension_calculate(payload: TensionCalcInput, user=Depends(get_current_user)):
    try:
        result = run_tension_calc(payload.model_dump())
        logger.info("tension calculate by=%s theo=%s", user.get("email"), result.get("theoretical_elongation_in"))
        return result
    except Exception:
        logger.exception("tension_calculate failed")
        raise HTTPException(status_code=500, detail="Failed to calculate tension")


@api.get("/tension-reports")
async def list_tension_reports(user=Depends(get_current_user)):
    try:
        reports = await db.tension_reports.find({}, {"_id": 0}).to_list(500)
        beds = {b["id"]: b for b in await db.beds.find({}, {"_id": 0}).to_list(50)}
        for r in reports:
            r["bed_number"] = beds.get(r["bed_id"], {}).get("bed_number")
        return reports
    except Exception:
        logger.exception("list_tension_reports failed")
        raise HTTPException(status_code=500, detail="Failed to list tension reports")


@api.post("/tension-reports")
async def create_tension_report(payload: TensionReportCreate, user=Depends(get_current_user)):
    try:
        data = payload.model_dump()
        await assert_tension_allowed(data["bed_id"], data.get("pour_id"))
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
        dumped = report.model_dump()
        await db.tension_reports.insert_one(dumped)
        logger.info("tension report saved id=%s bed=%s by=%s", report.id, report.bed_id, user.get("email"))
        if not within:
            dumped = attach_prompt(dumped, build_prompt(
                source_type="tension",
                source_id=report.id,
                title="Elongation outside ±5% — file an NCR",
                category="strand",
                severity="major",
                description=f"variance {var}%",
                bed_id=report.bed_id,
                pour_id=report.pour_id or "",
            ))
        return dumped
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_tension_report failed")
        raise HTTPException(status_code=500, detail="Failed to save tension report")


# ---------------- Camber ----------------
@api.get("/camber-readings")
async def list_camber(beam_id: str = None, user=Depends(get_current_user)):
    try:
        q = {"beam_id": beam_id} if beam_id else {}
        return await db.camber_readings.find(q, {"_id": 0}).to_list(1000)
    except Exception:
        logger.exception("list_camber failed")
        raise HTTPException(status_code=500, detail="Failed to list camber readings")


@api.post("/camber-readings")
async def create_camber(payload: CamberReadingCreate, user=Depends(get_current_user)):
    try:
        data = payload.model_dump()
        if not data.get("midspan_in") and data.get("measured_camber_in"):
            data["midspan_in"] = data["measured_camber_in"]
        if not data.get("measured_camber_in") and data.get("midspan_in"):
            data["measured_camber_in"] = data["midspan_in"]
        cr = CamberReading(**data, inspector=user["name"])
        dumped = cr.model_dump()
        await db.camber_readings.insert_one(dumped)
        logger.info("camber reading saved id=%s beam=%s by=%s", cr.id, cr.beam_id, user.get("email"))
        req = float(cr.required_strength_psi or 0)
        rel = float(cr.release_strength_psi or 0)
        if req and rel and rel < req:
            dumped = attach_prompt(dumped, build_prompt(
                source_type="camber",
                source_id=cr.id,
                title="Release strength below required — file an NCR",
                category="material",
                severity="major",
                description=f"{rel} psi vs {req} required",
                beam_id=cr.beam_id,
            ))
        return dumped
    except Exception:
        logger.exception("create_camber failed")
        raise HTTPException(status_code=500, detail="Failed to save camber reading")


# ---------------- Finish Sheets ----------------
@api.get("/finish-sheets")
async def list_finish_sheets(beam_id: str = None, user=Depends(get_current_user)):
    try:
        q = {"beam_id": beam_id} if beam_id else {}
        return await db.finish_sheets.find(q, {"_id": 0}).to_list(1000)
    except Exception:
        logger.exception("list_finish_sheets failed")
        raise HTTPException(status_code=500, detail="Failed to list finish sheets")


@api.post("/finish-sheets")
async def create_finish_sheet(payload: FinishSheetCreate, user=Depends(get_current_user)):
    try:
        sheet = FinishSheet(**payload.model_dump(), inspector=user["name"])
        dumped = sheet.model_dump()
        await db.finish_sheets.insert_one(dumped)
        if payload.status == "fail":
            await db.beams.update_one({"id": payload.beam_id}, {"$set": {"qc_state": "failed"}})
        elif payload.status == "hold":
            await db.beams.update_one({"id": payload.beam_id}, {"$set": {"qc_state": "hold"}})
        logger.info("finish sheet saved id=%s beam=%s by=%s", sheet.id, sheet.beam_id, user.get("email"))
        if payload.status in ("fail", "hold"):
            dumped = attach_prompt(dumped, build_prompt(
                source_type="finish",
                source_id=sheet.id,
                title="Finish sheet fail — file an NCR",
                category="visual",
                severity="major" if payload.status == "fail" else "minor",
                description=payload.status,
                beam_id=sheet.beam_id,
            ))
        return dumped
    except Exception:
        logger.exception("create_finish_sheet failed")
        raise HTTPException(status_code=500, detail="Failed to save finish sheet")


# ---------------- Pre-Delivery ----------------
@api.get("/pre-delivery")
async def list_pre_delivery(beam_id: str = None, user=Depends(get_current_user)):
    try:
        q = {"beam_id": beam_id} if beam_id else {}
        return await db.pre_delivery.find(q, {"_id": 0}).to_list(1000)
    except Exception:
        logger.exception("list_pre_delivery failed")
        raise HTTPException(status_code=500, detail="Failed to list pre-delivery records")


@api.post("/pre-delivery")
async def create_pre_delivery(payload: PreDeliveryCreate, user=Depends(get_current_user)):
    try:
        data = payload.model_dump()
        released = bool(data.get("released"))
        beam = await db.beams.find_one({"id": payload.beam_id}, {"_id": 0})
        if not beam:
            raise HTTPException(status_code=404, detail="Beam not found")
        decision = None
        if released:
            mix = await mix_settings()
            pour = None
            if beam.get("pour_id"):
                pour = await db.pours.find_one({"id": beam["pour_id"]}, {"_id": 0})
            forecasts = await forecast_for_pour(pour or {"id": beam.get("pour_id") or ""}, [beam], mix)
            fc = forecasts[0] if forecasts else {}
            ov = await override_active("release_strength", beam["id"])
            decision = evaluate_release_gate(
                required_psi=fc.get("required_psi") or mix.get("required_psi") or 4000,
                crush_psi=fc.get("crush_psi"),
                predicted_psi=fc.get("predicted_psi"),
                override_active=bool(ov),
            )
            logger.info(
                "release gate beam=%s allow=%s via=%s crush=%s pred=%s req=%s by=%s",
                beam.get("id"), decision.get("allow"), decision.get("via"),
                decision.get("crush_psi"), decision.get("predicted_psi"), decision.get("required_psi"),
                user.get("email"),
            )
            if not decision.get("allow"):
                prompt = build_prompt(
                    source_type="release",
                    source_id=beam["id"],
                    title="Release gate fail — file an NCR",
                    category="material",
                    severity="critical",
                    description=decision.get("reason") or "below required strength",
                    beam_id=beam["id"],
                    bed_id=beam.get("bed_id") or "",
                    pour_id=beam.get("pour_id") or "",
                    job_id=beam.get("job_id") or "",
                )
                raise HTTPException(
                    status_code=409,
                    detail={"message": decision.get("reason"), "ncr_prompt": prompt, "release_decision": decision},
                )
        record = PreDelivery(
            **data,
            inspector=user["name"],
            release_at=now_iso() if released else None,
        )
        dumped = record.model_dump()
        if decision:
            dumped["release_decision"] = decision
        await db.pre_delivery.insert_one(dumped)
        if released:
            await db.beams.update_one(
                {"id": payload.beam_id},
                {"$set": {
                    "qc_state": "shipped",
                    "status": "complete",
                    "release_decision": {**decision, "at": now_iso(), "by": user.get("email")},
                }},
            )
            logger.info("beam released id=%s by=%s truck=%s dest=%s via=%s", payload.beam_id, user.get("email"), payload.truck_number, payload.destination, (decision or {}).get("via"))
        else:
            logger.info("pre-delivery draft saved id=%s beam=%s by=%s", record.id, record.beam_id, user.get("email"))
        return dumped
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_pre_delivery failed")
        raise HTTPException(status_code=500, detail="Failed to save pre-delivery record")


# ---------------- Anomalies / Crack Map ----------------
@api.get("/anomalies")
async def list_anomalies(beam_id: str = None, user=Depends(get_current_user)):
    try:
        q = {"beam_id": beam_id} if beam_id else {}
        return await db.anomalies.find(q, {"_id": 0}).to_list(1000)
    except Exception:
        logger.exception("list_anomalies failed")
        raise HTTPException(status_code=500, detail="Failed to list anomalies")


@api.post("/anomalies")
async def create_anomaly(payload: AnomalyCreate, request: Request, user=Depends(get_current_user)):
    try:
        an = Anomaly(**payload.model_dump(), inspector=user["name"])
        dumped = an.model_dump()
        await db.anomalies.insert_one(dumped)
        ncr = await open_ncr_from_anomaly(dumped, user, request)
        dumped["ncr_id"] = ncr.get("id")
        dumped = attach_prompt(dumped, build_prompt(
            source_type="anomaly",
            source_id=an.id,
            title="Twin pin opened an NCR — add photos and containment",
            category="visual",
            severity=ncr.get("severity") or "minor",
            description=an.note or an.type,
            beam_id=an.beam_id,
        ))
        dumped["ncr_prompt"]["ncr_id"] = ncr.get("id")
        if an.severity in ("moderate", "major"):
            await emit_sync_event(
                "hold" if an.severity == "major" else "anomaly",
                f"{an.type.upper()} · {an.severity} on beam",
                user,
                beam_id=an.beam_id,
                anomaly_id=an.id,
                ncr_id=ncr.get("id"),
            )
        logger.info("anomaly created id=%s ncr=%s beam=%s by=%s", an.id, ncr.get("id"), an.beam_id, user.get("email"))
        return dumped
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_anomaly failed")
        raise HTTPException(status_code=500, detail="Failed to save anomaly")



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
        beams_by_bed.setdefault(beam.get("bed_id"), []).append(beam)
    inspections_by_beam = {}
    for item in inspections:
        inspections_by_beam.setdefault(item.get("beam_id"), []).append(item)
    ncrs_by_beam = {}
    open_ncrs = []
    for item in ncrs:
        if item.get("status") not in ("closed", "rejected"):
            open_ncrs.append(item)
            for beam_id in item.get("beam_ids", []) or ([item.get("beam_id")] if item.get("beam_id") else []):
                ncrs_by_beam.setdefault(beam_id, []).append(item)
    batch_by_pour = {item.get("pour_id"): item for item in batch_records}
    releases_today_ids = {item["beam_id"] for item in inspections if item.get("beam_id") and item.get("section") == "pre_delivery" and item.get("status") == "pass" and within_same_day(item.get("created_at"), now)}
    if not releases_today_ids:
        releases_today_ids = {beam["id"] for beam in beams if beam.get("qc_state") in ("passed", "shipped") and within_same_day(beam.get("created_at"), now)}
    release_cycle_hours = []
    for beam in beams:
        events = [item for item in inspections_by_beam.get(beam.get("id"), []) if item.get("section") == "pre_delivery" and item.get("status") == "pass"]
        start = parse_iso_dt(beam.get("created_at"))
        finish = max((parse_iso_dt(item.get("created_at")) for item in events), default=None)
        if start and finish:
            release_cycle_hours.append(round((finish - start).total_seconds() / 3600, 1))
    latest_strengths = sorted(camber_readings, key=lambda item: parse_iso_dt(item.get("reading_date")) or parse_iso_dt(item.get("created_at")) or now, reverse=True)[:6]
    strength_trend = [{"label": f"Beam {next((beam.get('mark') for beam in beams if beam.get('id') == item.get('beam_id')), '—')}", "value": item.get("release_strength_psi", 0), "required": item.get("required_strength_psi", 0)} for item in reversed(latest_strengths)]
    camber_passes = [abs((item.get("measured_camber_in") or 0) - (item.get("design_camber_in") or 0)) <= 0.25 for item in camber_readings]
    tension_passes = [bool(item.get("within_tolerance")) for item in tension_reports]
    lanes = []
    for bed in beds:
        bed_beams = sorted(beams_by_bed.get(bed.get("id"), []), key=lambda item: item.get("position_on_bed", 0))
        pour = pours_by_id.get(bed.get("current_pour_id"))
        batch_record = batch_by_pour.get((pour or {}).get("id"))
        inspectors = [item.get("inspector") for beam in bed_beams for item in inspections_by_beam.get(beam.get("id"), []) if item.get("inspector")]
        open_lane_ncrs = [item for beam in bed_beams for item in ncrs_by_beam.get(beam.get("id"), [])]
        lane_state = command_lane_state(bed, bed_beams, bool(open_lane_ncrs))
        lanes.append({
            "id": bed.get("id"), "bed_number": bed.get("bed_number"), "name": bed.get("name"), "status": bed.get("status", "idle"),
            "lane_state": lane_state, "pour_number": (pour or {}).get("pour_number"),
            "beam_order": " / ".join(beam.get("mark", "—") for beam in bed_beams) or "No active beam order",
            "qc_owner": next((item.get("assigned_to") or item.get("owner") for item in open_lane_ncrs if item.get("assigned_to") or item.get("owner")), None) or (Counter(inspectors).most_common(1)[0][0] if inspectors else "Unassigned"),
            "estimated_release": estimate_release_time(bed, batch_record, now), "ncr_count": len(open_lane_ncrs),
            "beams": [{"id": beam.get("id"), "mark": beam.get("mark"), "position_on_bed": beam.get("position_on_bed"), "length_ft": beam.get("length_ft"), "status": beam.get("status"), "qc_state": beam.get("qc_state"), "release_tag": (beam.get("traceability") or {}).get("release_tag")} for beam in bed_beams],
        })
    severity_counts = {"minor": 0, "moderate": 0, "major": 0}
    for item in open_ncrs:
        sev = item.get("severity", "major")
        if sev in severity_counts:
            severity_counts[sev] += 1
    events = [{"timestamp": bed.get("updated_at"), "message": f"Bed {bed.get('bed_number')} status {bed.get('status', 'idle').upper()}"} for bed in beds]
    events += [{"timestamp": item.get("created_at") or item.get("batched_at"), "message": f"Batch {item.get('ticket_number') or item.get('mix_code') or '—'} captured for pour {pours_by_id.get(item.get('pour_id'), {}).get('pour_number', '—')}"} for item in batch_records]
    events += [{"timestamp": item.get("updated_at") or item.get("created_at"), "message": f"{_ncr_public_github(item).get('code')} {_ncr_public_github(item).get('status', 'open').replace('_', ' ').upper()} · {_ncr_public_github(item).get('title')}"} for item in open_ncrs]
    events += [{"timestamp": item.get("created_at"), "message": f"Tension report complete for Bed {next((bed.get('bed_number') for bed in beds if bed.get('id') == item.get('bed_id')), '—')} · {'WITHIN TOL' if item.get('within_tolerance') else 'OUT OF TOL'}"} for item in tension_reports]
    events += [{"timestamp": item.get("reading_date") or item.get("created_at"), "message": f"Camber / strength logged for {next((beam.get('mark') for beam in beams if beam.get('id') == item.get('beam_id')), item.get('beam_id', '—'))} · {item.get('release_strength_psi', 0)} PSI"} for item in camber_readings]
    events = sorted([item for item in events if parse_iso_dt(item.get("timestamp"))], key=lambda item: parse_iso_dt(item["timestamp"]), reverse=True)[:12]
    return {"generated_at": now_iso(), "plant": "BedForge Command Center", "shift": command_board_shift(now), "summary": {"beds_active": len([bed for bed in beds if bed.get("status") not in ("idle", "complete")]), "beams_in_process": len([beam for beam in beams if beam.get("qc_state") not in ("passed", "shipped")]), "releases_today": len(releases_today_ids), "open_ncrs": len(open_ncrs)}, "lanes": lanes, "analytics": {"releases_today": len(releases_today_ids), "layout_to_release_hours": round(sum(release_cycle_hours) / len(release_cycle_hours), 1) if release_cycle_hours else None, "open_ncrs_by_severity": severity_counts, "camber_pass_rate": round((sum(camber_passes) / len(camber_passes)) * 100, 1) if camber_passes else None, "tension_within_tolerance_rate": round((sum(tension_passes) / len(tension_passes)) * 100, 1) if tension_passes else None, "strength_trend": strength_trend}, "events": events}


@api.get("/batch-records")
async def list_batch_records(user=Depends(require_feature("batch_plant"))):
    records = await db.batch_records.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    out = []
    for rec in records:
        env = rec.get("environment") or {}
        out.append({**rec, "ticket_number": rec.get("ticket_number") or rec.get("truck_id") or rec.get("id", "")[:8], "mix_design": rec.get("mix_design") or rec.get("mix_code") or "", "ambient_temp_f": rec.get("ambient_temp_f") or env.get("ambient_f"), "concrete_temp_f": rec.get("concrete_temp_f") or env.get("mix_temp_f") or rec.get("target_temp_f"), "humidity_pct": rec.get("humidity_pct") or env.get("rh_pct"), "wind_mph": rec.get("wind_mph") or env.get("wind_mph"), "weather": rec.get("weather") or env.get("weather", "")})
    return out


@api.post("/batch-records")
async def create_batch_record(payload: dict, user=Depends(require_feature("batch_plant"))):
    data = dict(payload or {})
    pour = await db.pours.find_one({"id": data.get("pour_id")}, {"_id": 0}) if data.get("pour_id") else None
    if not data.get("job_id"):
        data["job_id"] = (pour or {}).get("job_id") or ""
    if not data.get("job_id") and data.get("beam_ids"):
        beam = await db.beams.find_one({"id": data["beam_ids"][0]}, {"_id": 0})
        data["job_id"] = (beam or {}).get("job_id") or ""
    if not data.get("job_id") or not data.get("pour_id"):
        raise HTTPException(status_code=400, detail="A real pour/job is required")
    record = {
        "id": data.get("id") or __import__("uuid").uuid4().__str__(), "status": "confirmed", "immutable": True, "revision": 1,
        "job_id": data["job_id"], "pour_id": data["pour_id"], "bed_ids": data.get("bed_ids") or [], "beam_ids": data.get("beam_ids") or [],
        "ticket_number": data.get("ticket_number", ""), "mix_design": data.get("mix_design", data.get("mix_code", "")), "mix_code": data.get("mix_code") or data.get("mix_design", ""),
        "ingredients": data.get("ingredients") or [], "admixtures": data.get("admixtures") or [], "cylinders": data.get("cylinders") or [],
        "environment": {"ambient_f": data.get("ambient_temp_f"), "mix_temp_f": data.get("concrete_temp_f"), "rh_pct": data.get("humidity_pct"), "wind_mph": data.get("wind_mph"), "weather": data.get("weather", "")},
        "ambient_temp_f": data.get("ambient_temp_f"), "concrete_temp_f": data.get("concrete_temp_f"), "humidity_pct": data.get("humidity_pct"), "wind_mph": data.get("wind_mph"), "weather": data.get("weather", ""),
        "notes": data.get("notes", ""), "created_by": user.get("name", ""), "created_at": now_iso(), "updated_at": now_iso(), "batched_at": data.get("batched_at") or now_iso(),
    }
    await db.batch_records.insert_one(record)
    return record


@api.get("/ncrs")
async def list_ncrs(user=Depends(require_feature("ncr"))):
    rows = await db.ncrs.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [_ncr_public_github(row) for row in rows]


@api.post("/ncrs")
async def create_ncr(payload: dict, user=Depends(require_feature("ncr"))):
    data = dict(payload or {})
    beam_id = data.get("beam_id") or ((data.get("beam_ids") or [None])[0])
    beam = await db.beams.find_one({"id": beam_id}, {"_id": 0}) if beam_id else None
    count = await db.ncrs.count_documents({})
    rec = {"id": __import__("uuid").uuid4().__str__(), "code": f"NCR-{datetime.now(timezone.utc).strftime('%y')}-{count + 1:03d}", "title": data.get("title") or data.get("description") or "Non-conformance", "status": "open", "severity": data.get("severity", "major"), "description": data.get("description") or data.get("title") or "Non-conformance", "containment": data.get("containment") or "Contain and evaluate affected product.", "owner": data.get("owner", ""), "assigned_to": data.get("owner", ""), "beam_id": beam_id, "beam_ids": [beam_id] if beam_id else [], "job_id": data.get("job_id") or (beam or {}).get("job_id") or "", "pour_id": data.get("pour_id") or (beam or {}).get("pour_id") or "", "bed_id": data.get("bed_id") or (beam or {}).get("bed_id") or "", "source_type": data.get("source_type", "manual"), "source_id": data.get("source_id", ""), "created_by": user.get("email", ""), "discovered_by": user.get("name", ""), "created_at": now_iso(), "updated_at": now_iso(), "audit_trail": [{"status": "open", "user": user.get("name", ""), "note": "Created", "at": now_iso()}], "history": [{"status": "open", "by": user.get("email", ""), "action": "create", "at": now_iso()}]}
    await db.ncrs.insert_one(rec)
    return _ncr_public_github(rec)


@api.patch("/ncrs/{ncr_id}")
async def update_ncr(ncr_id: str, payload: dict, user=Depends(require_feature("ncr"))):
    current = await db.ncrs.find_one({"id": ncr_id}, {"_id": 0})
    if not current:
        raise HTTPException(status_code=404, detail="NCR not found")
    updates = {k: v for k, v in (payload or {}).items() if v is not None}
    if updates.get("status") == "investigation":
        updates["status"] = "investigation"
    if "owner" in updates:
        updates["assigned_to"] = updates["owner"]
    if "title" in updates:
        updates["description"] = updates.get("description") or updates["title"]
    updates["updated_at"] = now_iso()
    await db.ncrs.update_one({"id": ncr_id}, {"$set": updates})
    row = await db.ncrs.find_one({"id": ncr_id}, {"_id": 0})
    return _ncr_public_github(row)


@api.get("/license")
async def get_license(user=Depends(get_current_user)):
    return await load_license_state()


@api.post("/license/activate")
async def activate_license(payload: LicenseActivateInput, user=Depends(require_feature("licensing", "admin"))):
    return await activate_license_state(payload)


@api.get("/packages/export/pdf")
async def export_package_pdf(package_type: str = "pour_complete", pour_id: str = None, beam_id: str = None, job_id: str = None, user=Depends(require_feature("package_export"))):
    if package_type not in ("pour_complete", "single_beam", "full_job"):
        raise HTTPException(status_code=400, detail="Unknown package type")
    if package_type == "full_job":
        await ensure_feature_enabled("advanced_exports")
    context = await build_package_context(package_type, pour_id=pour_id, beam_id=beam_id, job_id=job_id)
    data = package_export.build_package_pdf(context)
    return StreamingResponse(io.BytesIO(data), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={package_type}.pdf"})


# ---------------- Forms Export ----------------
@api.get("/health")
async def health():
    return {"ok": True}


@api.get("/forms/export/{form_type}")
async def export_form(form_type: str, request: Request, beam_id: str = None, user=Depends(require_feature("package_export"))):
    if form_type not in excel_export.BUILDERS:
        raise HTTPException(status_code=400, detail="Unknown form type")

    try:
        beams = {b["id"]: b for b in await db.beams.find({}, {"_id": 0}).to_list(1000)}
        beds = {b["id"]: b for b in await db.beds.find({}, {"_id": 0}).to_list(50)}
        jobs = {j["id"]: j for j in await db.jobs.find({}, {"_id": 0}).to_list(500)}
        ptypes = {p["id"]: p for p in await db.product_types.find({}, {"_id": 0}).to_list(500)}

        company = await db.company_settings.find_one({"id": "plant"}, {"_id": 0}) or {}
        context = {"company_name": company.get("company_name") or "PRESTRESS SERVICES INDUSTRIES LLC"}
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
        elif form_type == "finish":
            sheets = await db.finish_sheets.find({"beam_id": beam_id} if beam_id else {}, {"_id": 0}).to_list(500)
            for s in sheets:
                s["beam_mark"] = beams.get(s["beam_id"], {}).get("mark", "")
            context["finish_sheets"] = sheets
        elif form_type == "pre_delivery":
            records = await db.pre_delivery.find({"beam_id": beam_id} if beam_id else {}, {"_id": 0}).to_list(500)
            for r in records:
                r["beam_mark"] = beams.get(r["beam_id"], {}).get("mark", "")
            context["pre_delivery"] = records

        builder_name, filename = excel_export.BUILDERS[form_type]
        data = getattr(excel_export, builder_name)(context)
        logger.info("form exported type=%s by=%s", form_type, user.get("email"))
        await write_audit(action="export.form", user=user, request=request, entity_type=form_type, entity_id=beam_id or "")
        return StreamingResponse(
            io.BytesIO(data),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}.xlsx"},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("export_form failed type=%s", form_type)
        raise HTTPException(status_code=500, detail="Failed to export form")


app.include_router(auth_router)
app.include_router(api)
app.include_router(blueprint_intelligence_router)
app.include_router(blueprint_router)
app.include_router(bed_router)
app.include_router(tension_router)
app.include_router(ar_router)
app.include_router(strand_roll_router)
app.include_router(beam_qr_router)
app.include_router(company_router)
app.include_router(cylinder_router)
app.include_router(control_router)
app.include_router(owner_router)
app.include_router(coach_router)
app.include_router(fresh_router)
app.include_router(batch_router)
app.include_router(ncr_router)

security_headers_middleware(app)

_cors = os.environ.get("CORS_ORIGINS", "http://localhost:3000")
if is_production() and (not _cors or _cors.strip() == "*"):
    _cors = ""
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[o.strip() for o in _cors.split(",") if o.strip() and o.strip() != "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    assert_production_safe()
    async def create_index_safe(collection, *args, **kwargs):
        try:
            await collection.create_index(*args, **kwargs)
        except Exception as exc:
            logger.warning("index creation skipped collection=%s index=%s reason=%s", collection.name, args[0] if args else "", exc)

    indexes = [
        (db.users, "email", {"unique": True}), (db.beds, "bed_number", {}), (db.beams, "bed_id", {}),
        (db.camber_readings, "beam_id", {}), (db.finish_sheets, "beam_id", {}), (db.pre_delivery, "beam_id", {}),
        (db.beam_specs, "beam_id", {}), (db.beam_specs, "job_number", {}), (db.blueprint_documents, "beam_id", {}),
        (db.blueprint_documents, "created_at", {}), (db.blueprint_extractions, "document_id", {}), (db.locked_blueprint_revisions, "document_id", {}),
        (db.blueprint_audit_events, "document_id", {}), (db.licenses, "id", {}), (db.blueprints, "beam_id", {}),
        (db.spec_measurements, "spec_id", {}), (db.bed_assignments, [("bed_id", 1), ("scheduled_date", 1)], {}), (db.bed_assignments, "beam_id", {}),
        (db.ar_measurements, "beam_id", {}), (db.ar_measurements, "created_at", {}), (db.ar_measurements, "run_id", {}),
        (db.ar_tape_runs, "beam_id", {}), (db.ar_tape_runs, "created_at", {}), (db.tape_calibrations, "device_id", {}),
        (db.tape_calibrations, "calibrated_at", {}), (db.tape_calibrations, [("device_id", 1), ("passed", 1), ("calibrated_at", -1)], {}),
        (db.sync_events, "created_at", {}), (db.devices, [("user_id", 1), ("platform", 1), ("device_class", 1)], {}),
        (db.strand_rolls, "heat_number", {}), (db.strand_rolls, "logged_at", {}), (db.strand_roll_assignments, "bed_id", {}),
        (db.strand_roll_assignments, "roll_id", {}), (db.strand_roll_assignments, "pour_id", {}), (db.cylinder_runs, "run_date", {}),
        (db.cylinder_runs, "created_at", {}), (db.cylinders, "run_id", {}), (db.cylinders, "job_number", {}),
        (db.company_settings, "id", {}), (db.audit_log, "created_at", {}), (db.audit_log, "actor_id", {}),
        (db.audit_log, "action", {}), (db.sessions, "user_id", {}), (db.sessions, "id", {"unique": True}),
        (db.overrides, [("kind", 1), ("target_id", 1)], {}), (db.login_attempts, "created_at", {}),
        (db.maturity_samples, "pour_id", {}), (db.maturity_samples, "recorded_at", {}), (db.owner_packages, "pour_id", {}),
        (db.owner_packages, "created_at", {}), (db.fresh_concrete_tests, "pour_id", {}), (db.fresh_concrete_tests, "job_id", {}),
        (db.fresh_concrete_tests, "beam_ids", {}), (db.fresh_concrete_tests, "created_at", {}), (db.batch_records, "pour_id", {}),
        (db.batch_records, "job_id", {}), (db.batch_records, "mix_code", {}), (db.batch_records, "status", {}),
        (db.batch_records, "batched_at", {}), (db.mix_designs, "mix_code", {}), (db.ncrs, "status", {}),
        (db.ncrs, "severity", {}), (db.ncrs, "beam_ids", {}), (db.ncrs, "bed_id", {}),
        (db.ncrs, "job_id", {}), (db.ncrs, "anomaly_id", {}), (db.ncrs, "created_at", {}),
        (db.ncrs, [("source_type", 1), ("source_id", 1)], {}),
    ]
    for collection, index, kwargs in indexes:
        await create_index_safe(collection, index, **kwargs)
    await seed_admin()
    await seed_company()
    await seed_plant()
    await seed_l25390()
    await seed_bed_assignments()
    await seed_mock_hardware_stations()
    await seed_strand_rolls()
    await seed_mix_designs()
    await seed_beam_qr_tokens()
    await create_index_safe(db.beams, "qr_token", unique=True, sparse=True)
    logger.info("BedForge QC startup complete.")


@app.on_event("shutdown")
async def shutdown():
    client.close()


def mount_frontend_spa():
    """Serve the CRA production build when present (Emergent single-service deploy)."""
    build = Path(__file__).resolve().parents[1] / "frontend" / "build"
    index = build / "index.html"
    if not index.is_file():
        logger.info("frontend/build missing — API-only mode")
        return

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        try:
            if full_path.startswith("api/") or full_path == "api":
                raise HTTPException(status_code=404, detail="Not found")
            root = build.resolve()
            target = (root / full_path).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                raise HTTPException(status_code=404, detail="Not found")
            if target.is_file():
                return FileResponse(target)
            return FileResponse(index)
        except HTTPException:
            raise
        except Exception:
            logger.exception("spa_fallback failed path=%s", full_path)
            raise HTTPException(status_code=500, detail="Failed to serve app")

    logger.info("serving frontend SPA from %s", build)


mount_frontend_spa()
