from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import logging
from collections import Counter
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, APIRouter, Depends, HTTPException
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
)
from auth import router as auth_router, get_current_user, seed_admin
from tension import run_tension_calc, calc_theoretical_elongation, evaluate_tension
from seed import seed_plant
import excel_export
import package_export

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="BedForge QC")
api = APIRouter(prefix="/api")


async def enrich_beam(beam: dict, include_details: bool = False) -> dict:
    data = dict(beam)
    if data.get("product_type_id"):
        data["product_type"] = await db.product_types.find_one({"id": data["product_type_id"]}, {"_id": 0})
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


async def build_package_context(package_type: str, pour_id: str = None, beam_id: str = None, job_id: str = None) -> dict:
    beams = await db.beams.find({}, {"_id": 0}).to_list(1000)
    jobs = {item["id"]: item for item in await db.jobs.find({}, {"_id": 0}).to_list(500)}
    pours = {item["id"]: item for item in await db.pours.find({}, {"_id": 0}).to_list(500)}
    beds = {item["id"]: item for item in await db.beds.find({}, {"_id": 0}).to_list(100)}
    product_types = {item["id"]: item for item in await db.product_types.find({}, {"_id": 0}).to_list(500)}
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

    for beam in selected_beams:
        beam["product_type"] = product_types.get(beam.get("product_type_id"), {})

    selected_pour_id = pour_id or selected_beams[0].get("pour_id")
    selected_job_id = job_id or selected_beams[0].get("job_id")
    selected_bed_ids = sorted({beam["bed_id"] for beam in selected_beams})

    for reading in camber_readings:
        reading["beam_mark"] = next((beam["mark"] for beam in selected_beams if beam["id"] == reading["beam_id"]), reading.get("beam_id"))
    for report in tension_reports:
        report["bed_number"] = beds.get(report["bed_id"], {}).get("bed_number")

    return {
        "package_type": package_type,
        "job": jobs.get(selected_job_id, {}),
        "pour": pours.get(selected_pour_id, {}),
        "beds": [beds[bed_id] for bed_id in selected_bed_ids if bed_id in beds],
        "beams": selected_beams,
        "inspections": [item for item in inspections if item.get("beam_id") in {beam["id"] for beam in selected_beams}],
        "anomalies": [item for item in anomalies if item.get("beam_id") in {beam["id"] for beam in selected_beams}],
        "camber_readings": [item for item in camber_readings if item.get("beam_id") in {beam["id"] for beam in selected_beams}],
        "tension_reports": [item for item in tension_reports if not selected_bed_ids or item.get("bed_id") in selected_bed_ids],
        "batch_record": next((item for item in batch_records if item.get("pour_id") == selected_pour_id), None),
        "ncrs": [item for item in ncrs if item.get("beam_id") in {beam["id"] for beam in selected_beams} or item.get("pour_id") == selected_pour_id],
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


@api.get("/beds/{bed_id}/twin")
async def get_bed_twin(bed_id: str, user=Depends(get_current_user)):
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
async def command_board(user=Depends(get_current_user)):
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
async def list_batch_records(user=Depends(get_current_user)):
    return await db.batch_records.find({}, {"_id": 0}).to_list(500)


@api.post("/batch-records")
async def create_batch_record(payload: BatchRecordCreate, user=Depends(get_current_user)):
    record = BatchRecord(**payload.model_dump(), created_by=user["name"])
    await db.batch_records.insert_one(record.model_dump())
    return record.model_dump()


# ---------------- NCR ----------------
@api.get("/ncrs")
async def list_ncrs(user=Depends(get_current_user)):
    return await db.ncrs.find({}, {"_id": 0}).to_list(500)


@api.post("/ncrs")
async def create_ncr(payload: NCRCreate, user=Depends(get_current_user)):
    count = await db.ncrs.count_documents({})
    ncr = NCR(
        code=f"NCR-{datetime.now(timezone.utc).strftime('%y')}-{count + 1:03d}",
        **payload.model_dump(),
        audit_trail=[{"status": "open", "user": user["name"], "note": "Created", "at": now_iso()}],
    )
    await db.ncrs.insert_one(ncr.model_dump())
    return ncr.model_dump()


@api.patch("/ncrs/{ncr_id}")
async def update_ncr(ncr_id: str, payload: NCRUpdate, user=Depends(get_current_user)):
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
    license_state = await db.licenses.find_one({"id": "license"}, {"_id": 0})
    if license_state:
        expires_at = license_state.get("expires_at")
        if expires_at and expires_at < now_iso()[:10] and license_state.get("status") != "expired":
            license_state["status"] = "expired"
            await db.licenses.update_one({"id": "license"}, {"$set": {"status": "expired", "updated_at": now_iso()}})
        return license_state
    created = LicenseState(
        status="trial",
        tier="trial",
        feature_flags={
            "digital_twin": True,
            "package_export": True,
            "ncr": True,
            "batch_plant": True,
            "licensing": True,
        },
    )
    await db.licenses.insert_one(created.model_dump())
    return created.model_dump()


@api.post("/license/activate")
async def activate_license(payload: LicenseActivateInput, user=Depends(get_current_user)):
    features = {
        "digital_twin": True,
        "package_export": True,
        "ncr": payload.tier in ("standard", "enterprise"),
        "batch_plant": payload.tier in ("standard", "enterprise"),
        "licensing": True,
        "advanced_exports": payload.tier == "enterprise",
    }
    updates = LicenseState(
        status="active",
        tier=payload.tier,
        license_key=payload.license_key,
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
async def export_form(form_type: str, beam_id: str = None, user=Depends(get_current_user)):
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
    user=Depends(get_current_user),
):
    if package_type not in ("pour_complete", "single_beam", "full_job"):
        raise HTTPException(status_code=400, detail="Unknown package type")
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
    allow_origins=os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.beds.create_index("bed_number")
    await db.beams.create_index("bed_id")
    await seed_admin()
    await seed_plant()
    logger.info("BedForge QC startup complete.")


@app.on_event("shutdown")
async def shutdown():
    client.close()
