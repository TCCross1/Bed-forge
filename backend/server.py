from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import logging
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
)
from auth import router as auth_router, get_current_user, seed_admin
from tension import run_tension_calc, calc_theoretical_elongation, evaluate_tension
from seed import seed_plant
import excel_export

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="BedForge QC")
api = APIRouter(prefix="/api")


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


# ---------------- Beams ----------------
@api.get("/beams")
async def list_beams(user=Depends(get_current_user)):
    return await db.beams.find({}, {"_id": 0}).to_list(1000)


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
    beam["anomalies"] = await db.anomalies.find({"beam_id": beam_id}, {"_id": 0}).to_list(500)
    beam["inspections"] = await db.inspections.find({"beam_id": beam_id}, {"_id": 0}).to_list(500)
    beam["camber_readings"] = await db.camber_readings.find({"beam_id": beam_id}, {"_id": 0}).to_list(500)
    if beam.get("product_type_id"):
        beam["product_type"] = await db.product_types.find_one({"id": beam["product_type_id"]}, {"_id": 0})
    return beam


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
