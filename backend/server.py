from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import logging
from datetime import datetime, timezone
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
)
from auth import router as auth_router, get_current_user, seed_admin
from audit import write_audit, override_active
from control_routes import router as control_router
from security_core import assert_production_safe, is_production, security_headers_middleware
from tension import run_tension_calc, calc_theoretical_elongation, evaluate_tension
from seed import seed_plant, seed_l25390, seed_bed_assignments, seed_strand_rolls, seed_company, seed_beam_qr_tokens, seed_mix_designs
from blueprint_routes import router as blueprint_router
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
        return await db.beams.find({}, {"_id": 0}).to_list(1000)
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
        return await assemble_dossier(beam, full=True)
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


# ---------------- Forms Export ----------------
@api.get("/health")
async def health():
    return {"ok": True}


@api.get("/forms/export/{form_type}")
async def export_form(form_type: str, request: Request, beam_id: str = None, user=Depends(get_current_user)):
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
    await db.users.create_index("email", unique=True)
    await db.beds.create_index("bed_number")
    await db.beams.create_index("bed_id")
    await db.camber_readings.create_index("beam_id")
    await db.finish_sheets.create_index("beam_id")
    await db.pre_delivery.create_index("beam_id")
    await db.beam_specs.create_index("beam_id")
    await db.beam_specs.create_index("job_number")
    await db.blueprints.create_index("beam_id")
    await db.spec_measurements.create_index("spec_id")
    await db.bed_assignments.create_index([("bed_id", 1), ("scheduled_date", 1)])
    await db.bed_assignments.create_index("beam_id")
    await db.ar_measurements.create_index("beam_id")
    await db.ar_measurements.create_index("created_at")
    await db.ar_measurements.create_index("run_id")
    await db.ar_tape_runs.create_index("beam_id")
    await db.ar_tape_runs.create_index("created_at")
    await db.tape_calibrations.create_index("device_id")
    await db.tape_calibrations.create_index("calibrated_at")
    await db.tape_calibrations.create_index([("device_id", 1), ("passed", 1), ("calibrated_at", -1)])
    await db.sync_events.create_index("created_at")
    await db.devices.create_index([("user_id", 1), ("platform", 1), ("device_class", 1)])
    await db.strand_rolls.create_index("heat_number")
    await db.strand_rolls.create_index("logged_at")
    await db.strand_roll_assignments.create_index("bed_id")
    await db.strand_roll_assignments.create_index("roll_id")
    await db.strand_roll_assignments.create_index("pour_id")
    await db.cylinder_runs.create_index("run_date")
    await db.cylinder_runs.create_index("created_at")
    await db.cylinders.create_index("run_id")
    await db.cylinders.create_index("job_number")
    await db.company_settings.create_index("id")
    await db.audit_log.create_index("created_at")
    await db.audit_log.create_index("actor_id")
    await db.audit_log.create_index("action")
    await db.sessions.create_index("user_id")
    await db.sessions.create_index("id", unique=True)
    await db.overrides.create_index([("kind", 1), ("target_id", 1)])
    await db.login_attempts.create_index("created_at")
    await db.maturity_samples.create_index("pour_id")
    await db.maturity_samples.create_index("recorded_at")
    await db.owner_packages.create_index("pour_id")
    await db.owner_packages.create_index("created_at")
    await db.fresh_concrete_tests.create_index("pour_id")
    await db.fresh_concrete_tests.create_index("job_id")
    await db.fresh_concrete_tests.create_index("beam_ids")
    await db.fresh_concrete_tests.create_index("created_at")
    await db.batch_records.create_index("pour_id")
    await db.batch_records.create_index("job_id")
    await db.batch_records.create_index("mix_code")
    await db.batch_records.create_index("status")
    await db.batch_records.create_index("batched_at")
    await db.mix_designs.create_index("mix_code")
    await db.ncrs.create_index("status")
    await db.ncrs.create_index("severity")
    await db.ncrs.create_index("beam_ids")
    await db.ncrs.create_index("bed_id")
    await db.ncrs.create_index("job_id")
    await db.ncrs.create_index("anomaly_id")
    await db.ncrs.create_index("created_at")
    await db.ncrs.create_index([("source_type", 1), ("source_id", 1)])
    await seed_admin()
    await seed_company()
    await seed_plant()
    await seed_l25390()
    await seed_bed_assignments()
    await seed_strand_rolls()
    await seed_mix_designs()
    await seed_beam_qr_tokens()
    try:
        await db.beams.create_index("qr_token", unique=True, sparse=True)
    except Exception:
        logger.exception("qr_token unique index failed")
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
