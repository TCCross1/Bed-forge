"""Owner-ROI APIs: release forecast, DOT packages, finance signals."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from audit import write_audit
from auth import get_current_user, require_roles
from company_routes import get_company_doc, public_view
from db import db
from finance_signals import build_finance_signals
from maturity import DEFAULT_REQUIRED_PSI, forecast_release, next_morning_iso
from models import MaturitySampleCreate, OwnerPackageCreate, now_iso, new_id
from package_export import build_package_pdf, build_package_xlsx
from security_core import EXEC_ROLES
from storage import company_logo_path, save_vault_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["owner-roi"])
EXEC = require_roles(*EXEC_ROLES)


async def mix_settings() -> dict:
    doc = await db.company_settings.find_one({"id": "plant"}, {"_id": 0}) or {}
    def num(key, default):
        try:
            return float(doc.get(key) if doc.get(key) is not None else default)
        except (TypeError, ValueError):
            return float(default)
    return {
        "required_psi": num("required_release_psi", DEFAULT_REQUIRED_PSI),
        "su_psi": num("maturity_su_psi", 8500),
        "k_hours": num("maturity_k_hours", 18),
        "datum_c": 0.0,
        "raw": doc,
    }


def _pour_start(pour: dict) -> Optional[str]:
    return pour.get("poured_at") or pour.get("pour_date") or pour.get("created_at")


async def _samples_for_pour(pour_id: str):
    return await db.maturity_samples.find({"pour_id": pour_id}, {"_id": 0}).sort("recorded_at", 1).to_list(500)


async def _crush_for_marks(marks: list) -> dict:
    if not marks:
        return {}
    rows = await db.cylinders.find({"beam_marks": {"$in": list(marks)}}, {"_id": 0}).to_list(200)
    best = {}
    for row in rows:
        for mark in row.get("beam_marks") or []:
            if mark not in marks:
                continue
            prev = best.get(mark)
            if not prev or (row.get("crush_psi") and not prev.get("crush_psi")):
                best[mark] = row
            elif row.get("updated_at") and (not prev.get("updated_at") or row["updated_at"] > prev["updated_at"]):
                if row.get("crush_psi") is not None:
                    best[mark] = row
    return best


async def forecast_for_pour(pour: dict, beams: list, mix: dict) -> list:
    pour_id = pour.get("id")
    samples = await _samples_for_pour(pour_id) if pour_id else []
    marks = [b.get("mark") for b in beams if b.get("mark")]
    crush_map = await _crush_for_marks(marks)
    pull_at = next_morning_iso()
    start = _pour_start(pour)
    out = []
    for beam in beams:
        crush = crush_map.get(beam.get("mark") or "") or {}
        fc = forecast_release(
            required_psi=mix["required_psi"],
            samples=samples,
            pour_at=start,
            pull_at=pull_at,
            crush_psi=crush.get("crush_psi"),
            crush_id=crush.get("id"),
            su_psi=mix["su_psi"],
            k_hours=mix["k_hours"],
            datum_c=mix["datum_c"],
        )
        fc.update({
            "beam_id": beam.get("id"),
            "mark": beam.get("mark"),
            "bed_id": beam.get("bed_id"),
            "pour_id": pour_id,
            "qc_state": beam.get("qc_state"),
            "production_status": beam.get("production_status"),
        })
        out.append(fc)
    return out


async def attach_board_forecasts(bed_cards: list) -> dict:
    mix = await mix_settings()
    pours = {p["id"]: p for p in await db.pours.find({}, {"_id": 0}).to_list(500)}
    counts = {"expected_pass": 0, "borderline": 0, "fail_risk": 0, "confirmed_pass": 0, "confirmed_fail": 0, "unknown": 0}
    by_pour = {}
    for bed in bed_cards:
        for beam in bed.get("beams") or []:
            pour = pours.get(beam.get("pour_id") or bed.get("current_pour_id") or "")
            if not pour:
                beam["release_forecast"] = {"status": "unknown", "label": "No pour", "advice": "Assign a pour to forecast release."}
                counts["unknown"] += 1
                continue
            pid = pour["id"]
            if pid not in by_pour:
                pour_beams = [b for card in bed_cards for b in (card.get("beams") or []) if b.get("pour_id") == pid]
                if not pour_beams:
                    pour_beams = [beam]
                by_pour[pid] = {f["beam_id"]: f for f in await forecast_for_pour(pour, pour_beams, mix)}
            fc = by_pour[pid].get(beam.get("id"))
            if not fc:
                fc = {"status": "unknown", "label": "No maturity yet"}
            beam["release_forecast"] = fc
            counts[fc.get("status") or "unknown"] = counts.get(fc.get("status") or "unknown", 0) + 1
    return counts


@router.post("/maturity/samples")
async def create_maturity_sample(payload: MaturitySampleCreate, request: Request, user=Depends(get_current_user)):
    try:
        if payload.temp_f < -20 or payload.temp_f > 180:
            raise HTTPException(status_code=400, detail="Temperature out of range")
        pour_id = payload.pour_id
        if payload.beam_id and not pour_id:
            beam = await db.beams.find_one({"id": payload.beam_id}, {"_id": 0})
            if beam:
                pour_id = beam.get("pour_id")
        if pour_id:
            pour = await db.pours.find_one({"id": pour_id}, {"_id": 0})
            if not pour:
                raise HTTPException(status_code=404, detail="Pour not found")
        rec = {
            "id": new_id(),
            "pour_id": pour_id,
            "bed_id": payload.bed_id,
            "beam_id": payload.beam_id,
            "temp_f": float(payload.temp_f),
            "recorded_at": payload.recorded_at or now_iso(),
            "source": (payload.source or "probe")[:40],
            "note": (payload.note or "")[:500],
            "created_by": user.get("name") or "",
            "created_at": now_iso(),
        }
        await db.maturity_samples.insert_one(rec)
        await write_audit(action="maturity.sample", user=user, request=request, entity_type="pour", entity_id=pour_id or "", extra={"temp_f": rec["temp_f"]})
        logger.info("maturity sample id=%s pour=%s temp_f=%s by=%s", rec["id"], pour_id, rec["temp_f"], user.get("email"))
        rec.pop("_id", None)
        return rec
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_maturity_sample failed")
        raise HTTPException(status_code=500, detail="Failed to save maturity reading")


@router.get("/maturity/samples")
async def list_maturity_samples(pour_id: Optional[str] = None, user=Depends(get_current_user)):
    try:
        q = {"pour_id": pour_id} if pour_id else {}
        return await db.maturity_samples.find(q, {"_id": 0}).sort("recorded_at", -1).to_list(200)
    except Exception:
        logger.exception("list_maturity_samples failed")
        raise HTTPException(status_code=500, detail="Failed to list maturity readings")


@router.get("/release-forecast")
async def release_forecast(pour_id: Optional[str] = None, beam_id: Optional[str] = None, user=Depends(get_current_user)):
    try:
        mix = await mix_settings()
        if beam_id:
            beam = await db.beams.find_one({"id": beam_id}, {"_id": 0})
            if not beam:
                raise HTTPException(status_code=404, detail="Beam not found")
            pour = await db.pours.find_one({"id": beam.get("pour_id")}, {"_id": 0}) if beam.get("pour_id") else None
            if not pour:
                return {"pour": None, "forecasts": [{"beam_id": beam_id, "mark": beam.get("mark"), "status": "unknown", "label": "No pour", "advice": "Assign a pour to forecast release."}]}
            rows = await forecast_for_pour(pour, [beam], mix)
            return {"pour": {"id": pour.get("id"), "pour_number": pour.get("pour_number"), "pour_date": pour.get("pour_date")}, "forecasts": rows, "samples": await _samples_for_pour(pour["id"])}
        if pour_id:
            pour = await db.pours.find_one({"id": pour_id}, {"_id": 0})
            if not pour:
                raise HTTPException(status_code=404, detail="Pour not found")
            beams = await db.beams.find({"pour_id": pour_id}, {"_id": 0}).to_list(200)
            rows = await forecast_for_pour(pour, beams, mix)
            return {"pour": {"id": pour.get("id"), "pour_number": pour.get("pour_number"), "pour_date": pour.get("pour_date")}, "forecasts": rows, "samples": await _samples_for_pour(pour_id)}
        pours = await db.pours.find({}, {"_id": 0}).sort("created_at", -1).to_list(40)
        out = []
        for pour in pours:
            beams = await db.beams.find({"pour_id": pour["id"]}, {"_id": 0}).to_list(200)
            if not beams:
                continue
            rows = await forecast_for_pour(pour, beams, mix)
            out.append({"pour": {"id": pour.get("id"), "pour_number": pour.get("pour_number"), "pour_date": pour.get("pour_date")}, "forecasts": rows})
        return {"pours": out}
    except HTTPException:
        raise
    except Exception:
        logger.exception("release_forecast failed")
        raise HTTPException(status_code=500, detail="Failed to forecast release strength")


async def _package_context(pour_id: str) -> dict:
    pour = await db.pours.find_one({"id": pour_id}, {"_id": 0})
    if not pour:
        raise HTTPException(status_code=404, detail="Pour not found")
    job = await db.jobs.find_one({"id": pour.get("job_id")}, {"_id": 0}) if pour.get("job_id") else None
    beams = await db.beams.find({"pour_id": pour_id}, {"_id": 0}).to_list(200)
    beam_ids = [b["id"] for b in beams]
    marks = [b.get("mark") for b in beams if b.get("mark")]
    inspections = await db.inspections.find({"beam_id": {"$in": beam_ids}}, {"_id": 0}).to_list(500) if beam_ids else []
    for row in inspections:
        row["beam_mark"] = next((b.get("mark") for b in beams if b["id"] == row.get("beam_id")), "")
    camber = await db.camber_readings.find({"beam_id": {"$in": beam_ids}}, {"_id": 0}).to_list(500) if beam_ids else []
    for row in camber:
        row["beam_mark"] = next((b.get("mark") for b in beams if b["id"] == row.get("beam_id")), "")
    finish = await db.finish_sheets.find({"beam_id": {"$in": beam_ids}}, {"_id": 0}).to_list(500) if beam_ids else []
    for row in finish:
        row["beam_mark"] = next((b.get("mark") for b in beams if b["id"] == row.get("beam_id")), "")
    pred = await db.pre_delivery.find({"beam_id": {"$in": beam_ids}}, {"_id": 0}).to_list(500) if beam_ids else []
    for row in pred:
        row["beam_mark"] = next((b.get("mark") for b in beams if b["id"] == row.get("beam_id")), "")
    bed_ids = list({b.get("bed_id") for b in beams if b.get("bed_id")})
    tension = await db.tension_reports.find({"bed_id": {"$in": bed_ids}}, {"_id": 0}).to_list(200) if bed_ids else []
    beds = {b["id"]: b for b in await db.beds.find({}, {"_id": 0}).to_list(50)}
    for row in tension:
        row["bed_number"] = beds.get(row.get("bed_id"), {}).get("bed_number")
    cylinders = await db.cylinders.find({"pour_id": pour_id}, {"_id": 0}).to_list(200)
    if not cylinders and pour.get("pour_number"):
        cylinders = await db.cylinders.find({"pour_number": pour.get("pour_number")}, {"_id": 0}).to_list(200)
    recs = await db.strand_roll_assignments.find({"pour_id": pour_id}, {"_id": 0}).to_list(50)
    if not recs and bed_ids:
        recs = await db.strand_roll_assignments.find({"bed_id": {"$in": bed_ids}}, {"_id": 0}).to_list(50)
    roll_ids = [r.get("roll_id") for r in recs if r.get("roll_id")]
    rolls = await db.strand_rolls.find({"id": {"$in": roll_ids}}, {"_id": 0, "raw_text": 0}).to_list(50) if roll_ids else []
    drawings = await db.blueprints.find({"beam_id": {"$in": beam_ids}}, {"_id": 0}).to_list(100) if beam_ids else []
    for d in drawings:
        beam = next((b for b in beams if b["id"] == d.get("beam_id")), None)
        d["beam_mark"] = (beam or {}).get("mark")
        d["filename"] = d.get("original_name") or d.get("filename") or d.get("id")
    anomalies = await db.anomalies.find({"beam_id": {"$in": beam_ids}}, {"_id": 0}).to_list(200) if beam_ids else []
    photos = []
    for a in anomalies:
        photos.append({"kind": "anomaly", "label": f"{a.get('type')} {a.get('severity')}", "beam_mark": next((b.get("mark") for b in beams if b["id"] == a.get("beam_id")), ""), "filename": a.get("photo_url") or ""})
    for r in rolls:
        for ph in r.get("photos") or []:
            photos.append({"kind": "mill_tag", "label": ph.get("kind") or "tag", "filename": ph.get("filename"), "beam_mark": ""})
    company_doc = await get_company_doc()
    return {
        "pour": pour,
        "job": job or {},
        "beams": beams,
        "beam_marks": marks,
        "inspections": inspections,
        "tension_reports": tension,
        "camber_readings": camber,
        "finish_sheets": finish,
        "pre_delivery": pred,
        "cylinders": cylinders,
        "strand_rolls": rolls,
        "drawings": drawings,
        "photos": photos,
        "company": public_view(company_doc),
        "company_doc": company_doc,
    }


@router.post("/packages")
async def create_owner_package(payload: OwnerPackageCreate, request: Request, user=Depends(get_current_user)):
    try:
        ctx = await _package_context(payload.pour_id)
        company_doc = ctx.get("company_doc") or {}
        logo = company_logo_path(company_doc.get("logo_filename") or "") or company_logo_path("")
        logo_file = str(logo) if logo and logo.exists() else None
        pdf = build_package_pdf(ctx, logo_file)
        xlsx = build_package_xlsx(ctx) if payload.include_excel else b""
        pkg_id = new_id()
        pour = ctx["pour"]
        job = ctx["job"]
        pdf_name = f"DOT-package-{pour.get('pour_number') or pkg_id[:8]}.pdf"
        pdf_path = save_vault_file("plant", job.get("id") or "unassigned", pour.get("id"), "pour", "packages", pdf_name, pdf)
        xlsx_name = ""
        xlsx_path = ""
        if xlsx:
            xlsx_name = f"DOT-package-{pour.get('pour_number') or pkg_id[:8]}.xlsx"
            xp = save_vault_file("plant", job.get("id") or "unassigned", pour.get("id"), "pour", "packages", xlsx_name, xlsx)
            xlsx_path = str(xp)
        rec = {
            "id": pkg_id,
            "pour_id": pour.get("id"),
            "job_id": job.get("id"),
            "job_number": job.get("job_number"),
            "pour_number": pour.get("pour_number"),
            "beam_marks": ctx.get("beam_marks") or [],
            "pdf_filename": pdf_name,
            "pdf_path": str(pdf_path),
            "xlsx_filename": xlsx_name,
            "xlsx_path": xlsx_path,
            "note": (payload.note or "")[:500],
            "created_by": user.get("name") or "",
            "created_at": now_iso(),
        }
        await db.owner_packages.insert_one(rec)
        await write_audit(action="package.generate", user=user, request=request, entity_type="pour", entity_id=pour.get("id") or "", extra={"package_id": pkg_id})
        logger.info("owner package id=%s pour=%s by=%s", pkg_id, pour.get("id"), user.get("email"))
        rec.pop("_id", None)
        rec.pop("pdf_path", None)
        rec.pop("xlsx_path", None)
        rec["pdf_bytes"] = len(pdf)
        rec["xlsx_bytes"] = len(xlsx)
        return rec
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        logger.exception("create_owner_package failed")
        raise HTTPException(status_code=500, detail="Failed to generate owner package")


@router.get("/packages")
async def list_owner_packages(pour_id: Optional[str] = None, user=Depends(get_current_user)):
    try:
        q = {"pour_id": pour_id} if pour_id else {}
        rows = await db.owner_packages.find(q, {"_id": 0, "pdf_path": 0, "xlsx_path": 0}).sort("created_at", -1).to_list(100)
        return rows
    except Exception:
        logger.exception("list_owner_packages failed")
        raise HTTPException(status_code=500, detail="Failed to list owner packages")


@router.get("/packages/{package_id}/pdf")
async def download_package_pdf(package_id: str, user=Depends(get_current_user)):
    rec = await db.owner_packages.find_one({"id": package_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Package not found")
    from pathlib import Path
    from storage import file_response
    path = Path(rec.get("pdf_path") or "")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Package file missing")
    await write_audit(action="package.download", user=user, entity_type="package", entity_id=package_id)
    return file_response(path, rec.get("pdf_filename") or "package.pdf", "application/pdf")


@router.get("/packages/{package_id}/xlsx")
async def download_package_xlsx(package_id: str, user=Depends(get_current_user)):
    rec = await db.owner_packages.find_one({"id": package_id}, {"_id": 0})
    if not rec or not rec.get("xlsx_path"):
        raise HTTPException(status_code=404, detail="Excel package not found")
    from pathlib import Path
    from storage import file_response
    path = Path(rec.get("xlsx_path"))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Excel file missing")
    await write_audit(action="package.download", user=user, entity_type="package", entity_id=package_id, extra={"kind": "xlsx"})
    return file_response(path, rec.get("xlsx_filename") or "package.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/finance/signals")
async def finance_signals(user=Depends(EXEC)):
    try:
        mix = await mix_settings()
        beams = await db.beams.find({}, {"_id": 0}).to_list(2000)
        anomalies = await db.anomalies.find({}, {"_id": 0}).to_list(2000)
        assignments = await db.bed_assignments.find({}, {"_id": 0}).to_list(4000)
        pours = await db.pours.find({}, {"_id": 0}).to_list(200)
        forecasts = []
        for pour in pours:
            pbeams = [b for b in beams if b.get("pour_id") == pour.get("id")]
            if not pbeams:
                continue
            forecasts.extend(await forecast_for_pour(pour, pbeams, mix))
        payload = build_finance_signals(
            beams=beams,
            anomalies=anomalies,
            assignments=assignments,
            forecasts=forecasts,
            settings=mix["raw"],
        )
        logger.info("finance signals ncr=%s at_risk=%s by=%s", payload.get("open_ncrs"), payload.get("total_quality_dollars_at_risk"), user.get("email"))
        return payload
    except Exception:
        logger.exception("finance_signals failed")
        raise HTTPException(status_code=500, detail="Failed to load financial signals")
