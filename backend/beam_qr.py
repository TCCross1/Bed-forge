"""Permanent beam QR identity — tokens, deep links, PNG, and laminate labels."""
import io
import logging
import os
import re
import secrets
from typing import List, Optional

from models import now_iso

logger = logging.getLogger(__name__)

TOKEN_BYTES = 8
TOKEN_RE = re.compile(r"^[0-9a-f]{16}$")


def new_qr_token() -> str:
    return secrets.token_hex(TOKEN_BYTES)


def public_app_url() -> str:
    env = (os.environ.get("PUBLIC_APP_URL") or "").strip()
    if env:
        return env.rstrip("/")
    origins = (os.environ.get("CORS_ORIGINS") or "http://localhost:3000").split(",")
    first = origins[0].strip().rstrip("/")
    if not first or first == "*":
        return "http://localhost:3000"
    return first


def beam_deep_link(token: str) -> str:
    return f"{public_app_url()}/b/{token}"


def parse_scanned_value(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    lowered = text.replace("https://", "").replace("http://", "")
    marker = "/b/"
    if marker in text:
        token = text.split(marker, 1)[1]
        token = token.split("?")[0].split("#")[0].strip("/")
        return token
    if marker in lowered:
        token = lowered.split(marker, 1)[1]
        token = token.split("?")[0].split("#")[0].strip("/")
        return token
    return text.strip("/")


def normalize_token(raw: str) -> str:
    token = parse_scanned_value(raw).lower()
    return token if TOKEN_RE.match(token) else ""


def qr_png_bytes(payload: str, box_size: int = 8) -> bytes:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M

    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=max(4, int(box_size)), border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _spec_summary(spec: Optional[dict]) -> dict:
    if not spec:
        return {}
    geo = spec.get("geometry") or {}
    strands = spec.get("strands") or []
    holds = spec.get("hold_downs") or []
    hardware = spec.get("hardware") or []
    return {
        "product_name": spec.get("product_name") or "",
        "job_number": spec.get("job_number") or "",
        "length_ft": geo.get("length_ft"),
        "depth_in": geo.get("depth_in"),
        "width_in": geo.get("width_in"),
        "strand_count": len(strands),
        "hold_down_count": len(holds),
        "hardware_count": len(hardware),
        "status": spec.get("status") or "",
    }


def limit_dossier(full: dict) -> dict:
    """Job-site scan view: identity, status, essential spec, drawings, twin spec. No QC worksheets."""
    spec = full.get("spec")
    return {
        "access": "limited",
        "id": full.get("id"),
        "mark": full.get("mark"),
        "qr_token": full.get("qr_token"),
        "qr_url": full.get("qr_url"),
        "status": full.get("status"),
        "qc_state": full.get("qc_state"),
        "production_status": full.get("production_status"),
        "twin_type": full.get("twin_type"),
        "length_ft": full.get("length_ft"),
        "job": full.get("job"),
        "pour": full.get("pour"),
        "bed": full.get("bed"),
        "marked_end": full.get("marked_end"),
        "product_type": full.get("product_type"),
        "spec_summary": full.get("spec_summary") or _spec_summary(spec),
        "spec": spec,
        "blueprints": full.get("blueprints") or [],
        "company": full.get("company") or {},
        "created_at": full.get("created_at"),
    }


async def ensure_beam_token(beam: dict) -> str:
    from db import db

    token = str(beam.get("qr_token") or "").strip()
    if token:
        return token
    token = new_qr_token()
    for _ in range(6):
        if not await db.beams.find_one({"qr_token": token}):
            break
        token = new_qr_token()
    stamp = now_iso()
    await db.beams.update_one({"id": beam["id"]}, {"$set": {"qr_token": token, "qr_created_at": stamp}})
    beam["qr_token"] = token
    beam["qr_created_at"] = stamp
    logger.info("beam QR token issued id=%s", beam.get("id"))
    return token


async def assemble_dossier(beam: dict, *, full: bool) -> dict:
    from db import db
    from company_routes import get_company_doc, public_view

    beam_id = beam["id"]
    token = await ensure_beam_token(beam)
    job = await db.jobs.find_one({"id": beam["job_id"]}, {"_id": 0}) if beam.get("job_id") else None
    pour = await db.pours.find_one({"id": beam["pour_id"]}, {"_id": 0}) if beam.get("pour_id") else None
    bed = await db.beds.find_one({"id": beam["bed_id"]}, {"_id": 0}) if beam.get("bed_id") else None
    assignment = None
    if beam.get("bed_id"):
        recs = await db.bed_assignments.find({"beam_id": beam_id}, {"_id": 0}).sort("scheduled_date", -1).to_list(1)
        assignment = recs[0] if recs else None
    marked = {}
    if bed:
        toward = (assignment or {}).get("marked_end_toward") or "header"
        marked = {
            "toward": toward,
            "label": bed.get("header_label") if toward == "header" else bed.get("bulkhead_label"),
            "header_label": bed.get("header_label") or "",
            "bulkhead_label": bed.get("bulkhead_label") or "",
        }
    spec = None
    if beam.get("spec_id"):
        spec = await db.beam_specs.find_one({"id": beam["spec_id"]}, {"_id": 0})
    if not spec:
        latest = await db.beam_specs.find({"beam_id": beam_id}, {"_id": 0}).sort("created_at", -1).to_list(1)
        spec = latest[0] if latest else None
    product = None
    if beam.get("product_type_id"):
        product = await db.product_types.find_one({"id": beam["product_type_id"]}, {"_id": 0})
    blueprints = await db.blueprints.find({"beam_id": beam_id}, {"_id": 0}).to_list(50)
    drawings = [
        {
            "id": bp.get("id"),
            "original_name": bp.get("original_name") or "",
            "content_type": bp.get("content_type") or "",
            "page_count": bp.get("page_count") or 0,
            "status": bp.get("status") or "",
            "url": f"/api/public/beams/{token}/drawings/{bp.get('id')}",
        }
        for bp in blueprints
    ]
    company = public_view(await get_company_doc())
    out = {
        "access": "full" if full else "limited",
        "id": beam_id,
        "mark": beam.get("mark"),
        "qr_token": token,
        "qr_url": beam_deep_link(token),
        "qr_created_at": beam.get("qr_created_at"),
        "status": beam.get("status"),
        "qc_state": beam.get("qc_state"),
        "production_status": beam.get("production_status"),
        "twin_type": beam.get("twin_type"),
        "length_ft": beam.get("length_ft"),
        "position_on_bed": beam.get("position_on_bed"),
        "job_id": beam.get("job_id"),
        "pour_id": beam.get("pour_id"),
        "bed_id": beam.get("bed_id"),
        "job": {"id": job.get("id"), "job_number": job.get("job_number"), "name": job.get("name"), "customer": job.get("customer")} if job else None,
        "pour": {"id": pour.get("id"), "pour_number": pour.get("pour_number"), "pour_date": pour.get("pour_date"), "concrete_mix": pour.get("concrete_mix")} if pour else None,
        "bed": {"id": bed.get("id"), "bed_number": bed.get("bed_number"), "name": bed.get("name"), "status": bed.get("status")} if bed else None,
        "marked_end": marked,
        "product_type": product,
        "spec": spec,
        "spec_summary": _spec_summary(spec),
        "blueprints": drawings,
        "company": company,
        "created_at": beam.get("created_at"),
    }
    if not full:
        return limit_dossier(out)

    recs = await db.strand_roll_assignments.find({"beam_ids": beam_id}, {"_id": 0}).to_list(50)
    if not recs and beam.get("bed_id"):
        recs = await db.strand_roll_assignments.find({"bed_id": beam["bed_id"]}, {"_id": 0}).to_list(50)
    roll_ids = [r.get("roll_id") for r in recs if r.get("roll_id")]
    rolls = await db.strand_rolls.find({"id": {"$in": roll_ids}}, {"_id": 0, "raw_text": 0}).to_list(50) if roll_ids else []
    tension = []
    if beam.get("bed_id"):
        tension = await db.tension_reports.find({"bed_id": beam["bed_id"]}, {"_id": 0}).to_list(50)
    cylinders = await db.cylinders.find({"beam_marks": beam.get("mark")}, {"_id": 0}).to_list(50)
    from ncr import public_ncr
    ncr_rows = await db.ncrs.find({"beam_ids": beam_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    out.update({
        "anomalies": await db.anomalies.find({"beam_id": beam_id}, {"_id": 0}).to_list(500),
        "inspections": await db.inspections.find({"beam_id": beam_id}, {"_id": 0}).to_list(500),
        "camber_readings": await db.camber_readings.find({"beam_id": beam_id}, {"_id": 0}).to_list(500),
        "finish_sheets": await db.finish_sheets.find({"beam_id": beam_id}, {"_id": 0}).to_list(500),
        "pre_delivery": await db.pre_delivery.find({"beam_id": beam_id}, {"_id": 0}).to_list(500),
        "measurements": await db.spec_measurements.find({"spec_id": spec["id"]}, {"_id": 0}).to_list(500) if spec else [],
        "ar_measurements": await db.ar_measurements.find({"beam_id": beam_id}, {"_id": 0, "photo_data": 0}).sort("created_at", -1).to_list(100),
        "tape_runs": await db.ar_tape_runs.find({"beam_id": beam_id}, {"_id": 0}).sort("created_at", -1).to_list(20),
        "strand_rolls": rolls,
        "traceability": {
            "heat_numbers": [r.get("heat_number") for r in rolls if r.get("heat_number")],
            "reel_numbers": [r.get("reel_number") for r in rolls if r.get("reel_number")],
            "chain": "Beam → strands → Strand Roll → Heat Number → Mill Test Certificate",
        },
        "tension_reports": tension,
        "cylinders": cylinders,
        "fresh_tests": await db.fresh_concrete_tests.find(
            {"$or": ([{"beam_ids": beam_id}] + ([{"pour_id": beam["pour_id"]}] if beam.get("pour_id") else []))},
            {"_id": 0},
        ).sort("created_at", -1).to_list(100),
        "batch_records": await db.batch_records.find(
            {"$or": ([{"beam_ids": beam_id}] + ([{"pour_id": beam["pour_id"]}] if beam.get("pour_id") else []))},
            {"_id": 0},
        ).sort("batched_at", -1).to_list(50),
        "ncrs": [public_ncr(r) for r in ncr_rows],
    })
    return out


def build_qr_label_pdf(rows: List[dict], company: dict, logo_path: Optional[str] = None) -> bytes:
    """Laminate-ready labels: logo + job + beam + QR. 2 columns, breathing room."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
    except ImportError as exc:
        logger.exception("reportlab missing — cannot build QR labels")
        raise RuntimeError("PDF engine is not installed") from exc

    company = company or {}
    header = (company.get("tag_header") or company.get("company_name") or "PRESTRESS SERVICES INDUSTRIES LLC")
    buf = io.BytesIO()
    page_w, page_h = letter
    c = canvas.Canvas(buf, pagesize=letter)
    margin_x = 0.45 * inch
    margin_y = 0.5 * inch
    gap_x = 0.2 * inch
    gap_y = 0.22 * inch
    cols, rows_n = 2, 3
    tag_w = (page_w - (2 * margin_x) - gap_x) / cols
    tag_h = (page_h - (2 * margin_y) - (gap_y * (rows_n - 1))) / rows_n
    logo = None
    if logo_path:
        try:
            logo = ImageReader(logo_path)
        except Exception:
            logger.exception("QR label logo load failed")

    def draw_label(x, y, row):
        c.setStrokeColorRGB(0, 0, 0)
        c.setFillColorRGB(1, 1, 1)
        c.setLineWidth(1.6)
        c.rect(x, y, tag_w, tag_h, stroke=1, fill=1)
        inner = 0.14 * inch
        tx = x + inner
        ty = y + tag_h - inner
        c.setFillColorRGB(0, 0, 0)
        if logo:
            try:
                c.drawImage(logo, tx, ty - 0.32 * inch, width=0.85 * inch, height=0.32 * inch, preserveAspectRatio=True, mask="auto")
                c.setFont("Helvetica-Bold", 8)
                c.drawRightString(x + tag_w - inner, ty - 0.16 * inch, str(header)[:36])
            except Exception:
                logger.exception("QR label logo draw failed")
                c.setFont("Helvetica-Bold", 9)
                c.drawString(tx, ty - 0.16 * inch, str(header)[:40])
        else:
            c.setFont("Helvetica-Bold", 9)
            c.drawString(tx, ty - 0.16 * inch, str(header)[:40])
        ty -= 0.42 * inch
        c.setLineWidth(0.6)
        c.line(tx, ty, x + tag_w - inner, ty)
        ty -= 0.26 * inch
        job = row.get("job_number") or ""
        mark = row.get("mark") or ""
        if job:
            c.setFont("Helvetica", 9)
            c.drawString(tx, ty, "JOB #")
            c.setFont("Helvetica-Bold", 16)
            c.drawString(tx + 0.55 * inch, ty - 0.02 * inch, str(job)[:18])
            ty -= 0.28 * inch
        if mark:
            c.setFont("Helvetica", 9)
            c.drawString(tx, ty, "BEAM")
            c.setFont("Helvetica-Bold", 18)
            c.drawString(tx + 0.55 * inch, ty - 0.02 * inch, str(mark)[:16])
        qr_png = row.get("qr_png")
        qr_size = 1.55 * inch
        qx = x + tag_w - inner - qr_size
        qy = y + inner + 0.28 * inch
        if qr_png:
            try:
                c.drawImage(ImageReader(io.BytesIO(qr_png)), qx, qy, width=qr_size, height=qr_size, mask="auto")
            except Exception:
                logger.exception("QR image draw failed")
        c.setFont("Helvetica", 7)
        c.drawString(tx, y + inner, "Scan for specs · drawings · twin · QC")

    if not rows:
        c.setFont("Helvetica", 12)
        c.drawString(margin_x, page_h / 2, "No beams selected for QR labels.")
        c.showPage()
    else:
        per_page = cols * rows_n
        for index, row in enumerate(rows):
            pos = index % per_page
            if pos == 0 and index > 0:
                c.showPage()
            col = pos % cols
            row_i = pos // cols
            x = margin_x + col * (tag_w + gap_x)
            y = page_h - margin_y - (row_i + 1) * tag_h - row_i * gap_y
            draw_label(x, y, row)
        c.showPage()
    c.save()
    return buf.getvalue()
