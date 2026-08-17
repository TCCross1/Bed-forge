import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak

BRAND = "PRESTRESS SERVICES INDUSTRIES LLC"
FOOTER = "BedForge"

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="PackageTitle", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=colors.HexColor("#111827"), alignment=TA_LEFT))
styles.add(ParagraphStyle(name="SectionTitle", fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=colors.HexColor("#0F172A"), spaceBefore=8, spaceAfter=6))
styles.add(ParagraphStyle(name="BodyMono", fontName="Courier", fontSize=8.5, leading=11, textColor=colors.HexColor("#0F172A")))


def header_footer(canvas, doc):
    canvas.saveState()
    width, height = doc.pagesize
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(doc.leftMargin, height - 0.45 * inch, BRAND)
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(width - doc.rightMargin, 0.35 * inch, FOOTER)
    canvas.drawString(doc.leftMargin, 0.35 * inch, f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    canvas.restoreState()


def kv_table(rows, widths=(1.9 * inch, 4.9 * inch)):
    data = [[Paragraph(f"<b>{label}</b>", styles["BodyText"]), Paragraph(str(value or "—"), styles["BodyText"])] for label, value in rows]
    table = Table(data, colWidths=list(widths), hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F8FAFC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def grid_table(headers, rows, widths=None):
    data = [headers] + rows
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEADING", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def add_section(story, title, element):
    story.append(Paragraph(title, styles["SectionTitle"]))
    story.append(element)
    story.append(Spacer(1, 0.18 * inch))


def package_title(package_type):
    return {
        "pour_complete": "Pour Complete Package",
        "single_beam": "Single Beam Package",
        "full_job": "Full Job Package",
    }.get(package_type, "Package Export")


def build_package_pdf(context: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.55 * inch, rightMargin=0.55 * inch, topMargin=0.75 * inch, bottomMargin=0.55 * inch)
    story = []

    package_type = context.get("package_type", "pour_complete")
    job = context.get("job", {})
    pour = context.get("pour", {})
    beds = context.get("beds", [])
    beams = context.get("beams", [])
    inspections = context.get("inspections", [])
    tension_reports = context.get("tension_reports", [])
    camber_readings = context.get("camber_readings", [])
    batch_record = context.get("batch_record") or {}
    ncrs = context.get("ncrs", [])

    story.append(Paragraph(package_title(package_type), styles["PackageTitle"]))
    story.append(Spacer(1, 0.12 * inch))
    add_section(story, "Cover Sheet", kv_table([
        ("Job", f"{job.get('job_number', '—')} · {job.get('name', '—')}"),
        ("Customer / DOT Spec", f"{job.get('customer', '—')} / {job.get('state_spec', '—')}"),
        ("Pour", pour.get("pour_number", "—")),
        ("Beds", ", ".join(f"Bed {bed.get('bed_number')}" for bed in beds) or "—"),
        ("Beam Count", len(beams)),
        ("Personnel", ", ".join(sorted({item.get('inspector', '') for item in inspections if item.get('inspector')})) or "—"),
    ]))

    beam_rows = [[beam.get("mark", "—"), beam.get("product_type", {}).get("name", beam.get("twin_type", "—")), beam.get("length_ft", "—"), beam.get("qc_state", "—"), ", ".join(beam.get("traceability", {}).get("strand_rolls", [])) or "—"] for beam in beams]
    add_section(story, "Beam List", grid_table(["Beam", "Product", "Length (ft)", "QC", "Strand Rolls"], beam_rows or [["—", "—", "—", "—", "—"]], widths=[1.0 * inch, 2.8 * inch, 1.0 * inch, 1.0 * inch, 2.0 * inch]))

    batch_rows = [[batch_record.get("ticket_number", "—"), batch_record.get("mix_design", "—"), batch_record.get("ambient_temp_f", "—"), batch_record.get("concrete_temp_f", "—"), batch_record.get("humidity_pct", "—"), batch_record.get("weather", "—")]]
    add_section(story, "Batch Ticket + Environmental Conditions", grid_table(["Ticket", "Mix", "Ambient °F", "Concrete °F", "Humidity %", "Weather"], batch_rows, widths=[1.1 * inch, 2.1 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch, 1.2 * inch]))

    if batch_record.get("ingredients"):
        ingredient_rows = [[item.get("name", "—"), item.get("target_lb", item.get("target", "—")), item.get("actual_lb", item.get("actual", "—"))] for item in batch_record["ingredients"]]
        add_section(story, "Batch Ingredients", grid_table(["Ingredient", "Target", "Actual"], ingredient_rows, widths=[3.2 * inch, 1.2 * inch, 1.2 * inch]))

    qir_rows = [[item.get("beam_id", "—"), item.get("section", "—"), item.get("status", "—"), item.get("inspector", "—"), item.get("notes", "—")] for item in inspections]
    add_section(story, "QIR Summary / Full Sections", grid_table(["Beam ID", "Section", "Status", "Inspector", "Notes"], qir_rows or [["—", "—", "—", "—", "—"]], widths=[1.3 * inch, 1.2 * inch, 0.8 * inch, 1.2 * inch, 2.6 * inch]))

    story.append(PageBreak())

    tension_rows = [[item.get("bed_number", "—"), item.get("strand_size", "—"), item.get("theoretical_elongation_in", "—"), item.get("measured_elongation_in", "—"), item.get("variance_pct", "—"), "PASS" if item.get("within_tolerance") else "FAIL"] for item in tension_reports]
    add_section(story, "Tension / Elongation Report", grid_table(["Bed", "Strand", "Theo. In", "Measured In", "Variance %", "Result"], tension_rows or [["—", "—", "—", "—", "—", "—"]], widths=[0.8 * inch, 0.9 * inch, 1.0 * inch, 1.1 * inch, 1.0 * inch, 0.8 * inch]))

    camber_rows = []
    for item in camber_readings:
        mid = item.get("measured_camber_in", 0)
        camber_rows.append([item.get("beam_mark", item.get("beam_id", "—")), round(mid * 0.4, 2), round(mid, 2), round(mid * 0.45, 2), item.get("release_strength_psi", "—")])
    add_section(story, "Strength & 3-Point Camber Sheet", grid_table(["Beam", "End A", "Mid", "End B", "Release PSI"], camber_rows or [["—", "—", "—", "—", "—"]], widths=[1.2 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch, 1.2 * inch]))

    finish_rows = [[item.get("beam_id", "—"), item.get("status", "—"), item.get("notes", "—")] for item in inspections if item.get("section") in ("concrete", "finish")]
    add_section(story, "Finish / Post-Pour Sheet", grid_table(["Beam ID", "Status", "Notes"], finish_rows or [["—", "—", "—"]], widths=[1.3 * inch, 0.8 * inch, 4.4 * inch]))

    release_rows = [[item.get("beam_id", "—"), item.get("inspector", "—"), item.get("data", {}).get("signature", item.get("inspector", "—")), item.get("created_at", "—")[:10]] for item in inspections if item.get("section") == "pre_delivery"]
    add_section(story, "Pre-Delivery / Release Sign-off", grid_table(["Beam ID", "Inspector", "Digital Signature", "Date"], release_rows or [["—", "—", "—", "—"]], widths=[1.3 * inch, 1.4 * inch, 2.4 * inch, 1.0 * inch]))

    trace_rows = [[beam.get("mark", "—"), ", ".join(beam.get("traceability", {}).get("strand_rolls", [])) or "—", beam.get("traceability", {}).get("release_tag", "—")] for beam in beams]
    add_section(story, "Strand Roll Traceability Summary", grid_table(["Beam", "Strand Rolls", "Release Tag"], trace_rows or [["—", "—", "—"]], widths=[1.0 * inch, 4.4 * inch, 1.2 * inch]))

    ncr_rows = [[item.get("code", "—"), item.get("status", "—"), item.get("title", "—"), ", ".join(item.get("linked_photo_urls", [])) or "—"] for item in ncrs]
    add_section(story, "Linked NCRs and Key Photos", grid_table(["NCR", "Status", "Title", "Photos"], ncr_rows or [["—", "—", "—", "—"]], widths=[1.1 * inch, 1.1 * inch, 2.2 * inch, 2.6 * inch]))

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    buf.seek(0)
    return buf.read()
