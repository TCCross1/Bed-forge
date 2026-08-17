"""DOT / owner pour packet — branded PDF + Excel workbook."""
import io
import logging
from datetime import datetime, timezone
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

logger = logging.getLogger(__name__)

HEADER_FILL = PatternFill(start_color="12151C", end_color="12151C", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11, name="Arial")
TITLE_FONT = Font(bold=True, size=16, name="Arial")
THIN = Side(style="thin", color="999999")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def build_package_xlsx(ctx: dict) -> bytes:
    wb = Workbook()
    cover = wb.active
    cover.title = "Cover"
    company = (ctx.get("company") or {}).get("company_name") or "PRESTRESS SERVICES INDUSTRIES LLC"
    pour = ctx.get("pour") or {}
    job = ctx.get("job") or {}
    cover["A1"] = company
    cover["A1"].font = TITLE_FONT
    cover["A2"] = "DOT / OWNER QUALITY PACKAGE"
    cover["A2"].font = Font(bold=True, size=13, name="Arial")
    cover["A4"] = "Job"
    cover["B4"] = job.get("job_number") or ""
    cover["A5"] = "Customer"
    cover["B5"] = job.get("customer") or ""
    cover["A6"] = "Pour"
    cover["B6"] = pour.get("pour_number") or ""
    cover["A7"] = "Pour date"
    cover["B7"] = pour.get("pour_date") or ""
    cover["A8"] = "Beams"
    cover["B8"] = ", ".join(ctx.get("beam_marks") or [])
    cover["A9"] = "Generated"
    cover["B9"] = _stamp()

    def sheet(name, headers, rows):
        ws = wb.create_sheet(name[:31])
        for i, h in enumerate(headers, 1):
            c = ws.cell(row=1, column=i, value=h)
            c.font = HEADER_FONT
            c.fill = HEADER_FILL
            c.alignment = Alignment(horizontal="center")
            c.border = BORDER
        for r, row in enumerate(rows, 2):
            for i, val in enumerate(row, 1):
                cell = ws.cell(row=r, column=i, value=val)
                cell.border = BORDER
        for col in "ABCDEFGHIJK":
            ws.column_dimensions[col].width = 18

    sheet("QIR", ["Beam", "Section", "Status", "Inspector", "Date"], [
        [i.get("beam_mark"), i.get("section"), i.get("status"), i.get("inspector"), str(i.get("created_at") or "")[:10]]
        for i in ctx.get("inspections") or []
    ])
    sheet("Tension", ["Bed", "Jack", "Elongation", "Within", "By"], [
        [t.get("bed_number"), t.get("jack_id") or t.get("jack"), t.get("measured_elongation_in") or t.get("elongation_in"),
         "YES" if t.get("within_tolerance") else "NO", t.get("created_by") or t.get("inspector") or ""]
        for t in ctx.get("tension_reports") or []
    ])
    sheet("Strength_Camber", ["Beam", "Required psi", "Release psi", "Midspan in", "Date"], [
        [c.get("beam_mark"), c.get("required_strength_psi"), c.get("release_strength_psi"), c.get("midspan_in"), str(c.get("created_at") or "")[:10]]
        for c in ctx.get("camber_readings") or []
    ])
    sheet("Cylinders", ["Job", "Copy", "Crush psi", "Required", "Release OK", "Date"], [
        [c.get("job_number"), c.get("cylinder_copy"), c.get("crush_psi"), c.get("required_psi"),
         "YES" if c.get("release_ok") else ("NO" if c.get("crush_psi") else ""), c.get("crush_date") or ""]
        for c in ctx.get("cylinders") or []
    ])
    sheet("Finish", ["Beam", "Status", "Inspector", "Date"], [
        [f.get("beam_mark"), f.get("status"), f.get("inspector") or f.get("created_by"), str(f.get("created_at") or "")[:10]]
        for f in ctx.get("finish_sheets") or []
    ])
    sheet("Pre_Delivery", ["Beam", "Truck", "Destination", "Released", "Date"], [
        [p.get("beam_mark"), p.get("truck_number"), p.get("destination"), "YES" if p.get("released") else "NO", str(p.get("created_at") or "")[:10]]
        for p in ctx.get("pre_delivery") or []
    ])
    sheet("Strand_Heat", ["Heat", "Reel", "Grade", "Status"], [
        [r.get("heat_number"), r.get("reel_number"), r.get("strand_grade"), r.get("status")]
        for r in ctx.get("strand_rolls") or []
    ])
    sheet("Drawings", ["File", "Beam", "Pages"], [
        [d.get("filename") or d.get("original_name"), d.get("beam_mark"), d.get("page_count")]
        for d in ctx.get("drawings") or []
    ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def build_package_pdf(ctx: dict, logo_path: Optional[str] = None) -> bytes:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
    except ImportError as exc:
        logger.exception("reportlab missing — cannot build owner package")
        raise RuntimeError("PDF engine is not installed") from exc

    company = ctx.get("company") or {}
    header = company.get("tag_header") or company.get("company_name") or "PRESTRESS SERVICES INDUSTRIES LLC"
    job = ctx.get("job") or {}
    pour = ctx.get("pour") or {}
    buf = io.BytesIO()
    page_w, page_h = letter
    c = canvas.Canvas(buf, pagesize=letter)

    def footer(page_no):
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(0.45, 0.48, 0.55)
        c.drawString(0.7 * inch, 0.45 * inch, f"{header}  ·  DOT / Owner package  ·  {page_no}")
        c.drawRightString(page_w - 0.7 * inch, 0.45 * inch, _stamp())

    def new_page(title):
        c.showPage()
        banner(title)

    def banner(title):
        c.setFillColorRGB(0.04, 0.05, 0.06)
        c.rect(0, page_h - 1.15 * inch, page_w, 1.15 * inch, fill=1, stroke=0)
        c.setFillColorRGB(0.16, 0.47, 1.0)
        c.rect(0, page_h - 1.18 * inch, page_w, 0.04 * inch, fill=1, stroke=0)
        if logo_path:
            try:
                img = ImageReader(logo_path)
                c.drawImage(img, 0.6 * inch, page_h - 1.02 * inch, width=1.1 * inch, height=0.72 * inch, mask="auto", preserveAspectRatio=True, anchor="sw")
            except Exception:
                logger.exception("package logo draw failed")
        c.setFillColorRGB(0.79, 0.64, 0.15)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(1.9 * inch if logo_path else 0.7 * inch, page_h - 0.42 * inch, header.upper())
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(1.9 * inch if logo_path else 0.7 * inch, page_h - 0.72 * inch, title)
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(0.72, 0.75, 0.82)
        c.drawString(1.9 * inch if logo_path else 0.7 * inch, page_h - 0.95 * inch,
                     f"Job {job.get('job_number') or '—'}  ·  Pour {pour.get('pour_number') or '—'}  ·  {pour.get('pour_date') or ''}")

    def lines(y, rows, size=10):
        c.setFont("Helvetica", size)
        c.setFillColorRGB(0.84, 0.85, 0.89)
        for row in rows:
            if y < 0.9 * inch:
                footer(c.getPageNumber())
                new_page(c._doc.title if False else "DOT / Owner package (cont.)")
                y = page_h - 1.5 * inch
            c.drawString(0.7 * inch, y, str(row)[:110])
            y -= 14
        return y

    banner("DOT / OWNER QUALITY PACKAGE")
    y = page_h - 1.55 * inch
    y = lines(y, [
        f"Customer: {job.get('customer') or '—'}",
        f"Job name: {job.get('name') or '—'}",
        f"Pour mix: {pour.get('concrete_mix') or '—'}",
        f"Beams: {', '.join(ctx.get('beam_marks') or []) or '—'}",
        f"Contents: QIR, Tension, Strength & Camber, Cylinders, Finish, Pre-Delivery, Strand heat, Drawings, Photos",
        "",
        "This packet is the plant record for the owner / DOT. Drawings listed are the locked shop set.",
    ])
    footer(c.getPageNumber())

    def section(title, rows):
        c.showPage()
        banner(title)
        yy = page_h - 1.5 * inch
        if not rows:
            c.setFillColorRGB(0.55, 0.58, 0.65)
            c.setFont("Helvetica-Oblique", 10)
            c.drawString(0.7 * inch, yy, "No records in this section for the pour.")
            footer(c.getPageNumber())
            return
        yy = lines(yy, rows, size=9)
        footer(c.getPageNumber())

    section("1. Quality Inspection Report (QIR)", [
        f"{i.get('beam_mark') or '—'}  ·  {i.get('section') or ''}  ·  {i.get('status') or ''}  ·  {i.get('inspector') or ''}  ·  {str(i.get('created_at') or '')[:16]}"
        for i in ctx.get("inspections") or []
    ])
    section("2. Tension Report", [
        f"Bed {t.get('bed_number') or '—'}  ·  elong {t.get('measured_elongation_in') or t.get('elongation_in') or '—'} in  ·  {'IN TOL' if t.get('within_tolerance') else 'CHECK'}  ·  {str(t.get('created_at') or '')[:16]}"
        for t in ctx.get("tension_reports") or []
    ])
    section("3. Strength & Camber", [
        f"{c.get('beam_mark') or '—'}  ·  req {c.get('required_strength_psi') or '—'} psi  ·  release {c.get('release_strength_psi') or '—'} psi  ·  mid {c.get('midspan_in') or '—'} in"
        for c in ctx.get("camber_readings") or []
    ] + [
        f"CYL {cyl.get('job_number') or ''} copy {cyl.get('cylinder_copy') or ''}  ·  crush {cyl.get('crush_psi') or 'pending'} psi  ·  req {cyl.get('required_psi') or ''}  ·  {'PASS' if cyl.get('release_ok') else ('FAIL' if cyl.get('crush_psi') else 'OPEN')}"
        for cyl in ctx.get("cylinders") or []
    ])
    section("4. Finish Sheet", [
        f"{f.get('beam_mark') or '—'}  ·  {f.get('status') or ''}  ·  {str(f.get('created_at') or '')[:16]}"
        for f in ctx.get("finish_sheets") or []
    ])
    section("5. Pre-Delivery / Release", [
        f"{p.get('beam_mark') or '—'}  ·  truck {p.get('truck_number') or '—'}  ·  {p.get('destination') or '—'}  ·  {'RELEASED' if p.get('released') else 'HOLD'}"
        for p in ctx.get("pre_delivery") or []
    ])
    section("6. Strand roll / heat log", [
        f"HEAT {r.get('heat_number') or '—'}  ·  REEL {r.get('reel_number') or '—'}  ·  {r.get('strand_grade') or ''}  ·  {r.get('status') or ''}"
        for r in ctx.get("strand_rolls") or []
    ])
    section("7. Drawings", [
        f"{d.get('filename') or d.get('original_name') or 'drawing'}  ·  beam {d.get('beam_mark') or '—'}  ·  {d.get('page_count') or ''} p"
        for d in ctx.get("drawings") or []
    ])
    section("8. Photos / field captures", [
        f"{p.get('kind') or 'photo'}  ·  {p.get('label') or p.get('filename') or ''}  ·  {p.get('beam_mark') or ''}"
        for p in ctx.get("photos") or []
    ] or ["No photos attached. Mill tags and anomalies remain in the beam dossier."])

    c.save()
    buf.seek(0)
    return buf.read()
