import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak

BRAND = "PRESTRESS SERVICES INDUSTRIES LLC"
FOOTER = "BedForge"

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="BrandTitle", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=colors.HexColor("#111827"), alignment=TA_LEFT))
styles.add(ParagraphStyle(name="PackageTitle", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=colors.HexColor("#0F172A"), alignment=TA_LEFT))
styles.add(ParagraphStyle(name="CoverNote", fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#475569"), alignment=TA_LEFT))
styles.add(ParagraphStyle(name="SectionTitle", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=colors.HexColor("#0F172A"), spaceBefore=7, spaceAfter=5))
styles.add(ParagraphStyle(name="BodyMono", fontName="Courier", fontSize=8.5, leading=11, textColor=colors.HexColor("#0F172A")))
styles.add(ParagraphStyle(name="SmallLabel", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.HexColor("#475569")))


def header_footer(canvas, doc):
    canvas.saveState()
    width, height = doc.pagesize
    canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
    canvas.line(doc.leftMargin, height - 0.52 * inch, width - doc.rightMargin, height - 0.52 * inch)
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(doc.leftMargin, height - 0.38 * inch, BRAND)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawRightString(width - doc.rightMargin, height - 0.38 * inch, "Controlled production package")
    canvas.line(doc.leftMargin, 0.48 * inch, width - doc.rightMargin, 0.48 * inch)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(doc.leftMargin, 0.28 * inch, f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    canvas.drawRightString(width - doc.rightMargin, 0.28 * inch, FOOTER)
    canvas.restoreState()


def safe_join(values):
    items = [str(item) for item in values if item]
    return ", ".join(items) if items else "—"


def kv_table(rows, widths=(1.75 * inch, 4.85 * inch)):
    data = [[Paragraph(f"<b>{label}</b>", styles["BodyText"]), Paragraph(str(value or "—"), styles["BodyText"])] for label, value in rows]
    table = Table(data, colWidths=list(widths), hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F8FAFC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def grid_table(headers, rows, widths=None):
    data = [headers] + rows
    table = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEADING", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for idx in range(1, len(data)):
        style.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#F8FAFC" if idx % 2 else "#FFFFFF")))
    table.setStyle(TableStyle(style))
    return table


def signoff_table(rows):
    table = Table(rows, colWidths=[1.9 * inch, 2.35 * inch, 1.55 * inch, 1.1 * inch], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEADING", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#94A3B8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def add_section(story, number, title, element):
    story.append(Paragraph(f"{number}. {title}", styles["SectionTitle"]))
    story.append(element)
    story.append(Spacer(1, 0.16 * inch))


def package_title(package_type):
    return {
        "pour_complete": "Pour Complete Package",
        "single_beam": "Single Beam Package",
        "full_job": "Full Job Package",
    }.get(package_type, "Package Export")


def package_scope(package_type, job, pour, beams):
    if package_type == "single_beam":
        beam = beams[0] if beams else {}
        return f"Single beam · {beam.get('mark', '—')}"
    if package_type == "full_job":
        return f"Full job · {job.get('job_number', '—')}"
    return f"Pour complete · {pour.get('pour_number', '—')}"


def cover_sections(beams, batch_record, anomalies):
    sections = [
        ["1", "Beam schedule", f"{len(beams)} beam(s), marks, bed positions, QC state, traceability"],
        ["2", "Batch and environment", "Ticket, mix, weather, temperatures, humidity"],
        ["3", "Tension / elongation", "Bed tension records with tolerance result"],
        ["4", "Quality inspection summary", "Inspection sections, inspector, notes"],
        ["5", "Finish / camber / release", "Post-pour finish, camber, release checks"],
        ["6", "Anomalies / NCR / sign-off", "Beam anomalies, linked NCRs, release and package sign-offs"],
    ]
    if batch_record.get("ingredients"):
        sections.insert(2, ["2A", "Batch ingredients", "Target versus actual ingredient weights"])
    if anomalies:
        sections.insert(-1, ["5D", "Anomaly log", "Captured crack, spall, chip, stain, and other beam defects"])
    return sections


def build_package_pdf(context: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.55 * inch, rightMargin=0.55 * inch, topMargin=0.78 * inch, bottomMargin=0.62 * inch)
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
    anomalies = context.get("anomalies", [])

    inspectors = sorted({item.get("inspector") for item in inspections if item.get("inspector")})
    bed_labels = [f"Bed {bed.get('bed_number')}" for bed in beds if bed.get("bed_number") is not None]

    story.append(Paragraph(BRAND, styles["BrandTitle"]))
    story.append(Spacer(1, 0.04 * inch))
    story.append(Paragraph(package_title(package_type), styles["PackageTitle"]))
    story.append(Spacer(1, 0.04 * inch))
    story.append(Paragraph("Plant / DOT-ready production record package", styles["CoverNote"]))
    story.append(Spacer(1, 0.14 * inch))

    story.append(kv_table([
        ("Scope", package_scope(package_type, job, pour, beams)),
        ("Job", f"{job.get('job_number', '—')} · {job.get('name', '—')}"),
        ("Customer", job.get("customer", "—")),
        ("DOT / Spec", job.get("state_spec", "—")),
        ("Pour", pour.get("pour_number", "—")),
        ("Beds", safe_join(bed_labels)),
        ("Beam count", len(beams)),
        ("Beam marks", safe_join(beam.get("mark") for beam in beams)),
        ("Personnel", safe_join(inspectors)),
        ("Generated UTC", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")),
    ]))
    story.append(Spacer(1, 0.18 * inch))

    add_section(
        story,
        "COVER",
        "Package Contents",
        grid_table(
            ["Ref", "Section", "Purpose"],
            cover_sections(beams, batch_record, anomalies),
            widths=[0.7 * inch, 2.2 * inch, 3.85 * inch],
        ),
    )
    add_section(
        story,
        "COVER",
        "Release / Receipt Sign-Off",
        signoff_table([
            ["Role", "Name / Signature", "Company / Title", "Date"],
            ["Prepared by", safe_join(inspectors[:1]) or "__________________", "QC / Production", "____________"],
            ["Released by", "__________________", "PSI QC Supervisor", "____________"],
            ["Received by", "__________________", "DOT / Owner Rep", "____________"],
        ]),
    )

    story.append(PageBreak())

    beam_rows = [
        [
            beam.get("mark", "—"),
            beam.get("product_type", {}).get("name", beam.get("twin_type", "—")),
            next((bed.get("bed_number") for bed in beds if bed.get("id") == beam.get("bed_id")), "—"),
            beam.get("position_on_bed", "—"),
            beam.get("length_ft", "—"),
            beam.get("qc_state", "—"),
            safe_join(beam.get("traceability", {}).get("strand_rolls", [])),
        ]
        for beam in beams
    ]
    add_section(story, 1, "Beam Schedule", grid_table(["Beam", "Product", "Bed", "Pos", "Length (ft)", "QC", "Strand Rolls"], beam_rows or [["—", "—", "—", "—", "—", "—", "—"]], widths=[0.8 * inch, 2.1 * inch, 0.55 * inch, 0.55 * inch, 0.85 * inch, 0.8 * inch, 2.0 * inch]))

    batch_rows = [[batch_record.get("ticket_number", "—"), batch_record.get("mix_design", "—"), batch_record.get("ambient_temp_f", "—"), batch_record.get("concrete_temp_f", "—"), batch_record.get("humidity_pct", "—"), batch_record.get("wind_mph", "—"), batch_record.get("weather", "—")]]
    add_section(story, 2, "Batch Ticket and Environmental Conditions", grid_table(["Ticket", "Mix", "Ambient °F", "Concrete °F", "Humidity %", "Wind MPH", "Weather"], batch_rows, widths=[1.0 * inch, 1.8 * inch, 0.9 * inch, 1.0 * inch, 0.9 * inch, 0.9 * inch, 1.15 * inch]))

    if batch_record.get("ingredients"):
        ingredient_rows = [[item.get("name", "—"), item.get("target_lb", item.get("target", "—")), item.get("actual_lb", item.get("actual", "—"))] for item in batch_record["ingredients"]]
        add_section(story, "2A", "Batch Ingredients", grid_table(["Ingredient", "Target (lb)", "Actual (lb)"], ingredient_rows, widths=[3.7 * inch, 1.35 * inch, 1.35 * inch]))

    tension_rows = [[item.get("bed_number", "—"), item.get("strand_size", "—"), item.get("theoretical_elongation_in", "—"), item.get("measured_elongation_in", "—"), item.get("variance_pct", "—"), "PASS" if item.get("within_tolerance") else "FAIL"] for item in tension_reports]
    add_section(story, 3, "Tension and Elongation Report", grid_table(["Bed", "Strand", "Theo. In", "Measured In", "Variance %", "Result"], tension_rows or [["—", "—", "—", "—", "—", "—"]], widths=[0.75 * inch, 1.0 * inch, 1.0 * inch, 1.15 * inch, 1.0 * inch, 0.85 * inch]))

    qir_rows = [[item.get("beam_id", "—"), item.get("section", "—"), item.get("status", "—"), item.get("inspector", "—"), item.get("notes", "—")] for item in inspections]
    add_section(story, 4, "Quality Inspection Summary", grid_table(["Beam ID", "Section", "Status", "Inspector", "Notes"], qir_rows or [["—", "—", "—", "—", "—"]], widths=[1.15 * inch, 1.2 * inch, 0.85 * inch, 1.2 * inch, 2.55 * inch]))

    finish_rows = [[item.get("beam_id", "—"), item.get("status", "—"), item.get("notes", "—")] for item in inspections if item.get("section") in ("concrete", "finish")]
    add_section(story, 5, "Finish and Post-Pour Review", grid_table(["Beam ID", "Status", "Notes"], finish_rows or [["—", "—", "—"]], widths=[1.2 * inch, 0.9 * inch, 4.5 * inch]))

    camber_rows = []
    for item in camber_readings:
        mid = item.get("measured_camber_in", 0)
        camber_rows.append([item.get("beam_mark", item.get("beam_id", "—")), round(mid * 0.4, 2), round(mid, 2), round(mid * 0.45, 2), item.get("release_strength_psi", "—"), item.get("required_strength_psi", "—")])
    add_section(story, "5A", "Strength and 3-Point Camber", grid_table(["Beam", "End A", "Mid", "End B", "Release PSI", "Req. PSI"], camber_rows or [["—", "—", "—", "—", "—", "—"]], widths=[1.1 * inch, 0.9 * inch, 0.85 * inch, 0.9 * inch, 1.15 * inch, 1.0 * inch]))

    release_rows = [[item.get("beam_id", "—"), item.get("inspector", "—"), item.get("data", {}).get("signature", item.get("inspector", "—")), item.get("created_at", "—")[:10]] for item in inspections if item.get("section") == "pre_delivery"]
    add_section(story, "5B", "Pre-Delivery Release Sign-Off", grid_table(["Beam ID", "Inspector", "Digital Signature", "Date"], release_rows or [["—", "—", "—", "—"]], widths=[1.25 * inch, 1.4 * inch, 2.5 * inch, 1.0 * inch]))

    trace_rows = [[beam.get("mark", "—"), safe_join(beam.get("traceability", {}).get("strand_rolls", [])), beam.get("traceability", {}).get("release_tag", "—")] for beam in beams]
    add_section(story, "5C", "Strand Roll Traceability", grid_table(["Beam", "Strand Rolls", "Release Tag"], trace_rows or [["—", "—", "—"]], widths=[1.0 * inch, 4.4 * inch, 1.2 * inch]))

    anomaly_rows = [[item.get("beam_id", "—"), item.get("type", "—"), item.get("severity", "—"), item.get("length_in", "—"), item.get("note", "—")] for item in anomalies]
    add_section(story, "5D", "Anomaly Log", grid_table(["Beam ID", "Type", "Severity", "Length (in)", "Note"], anomaly_rows or [["—", "—", "—", "—", "—"]], widths=[1.1 * inch, 1.0 * inch, 0.9 * inch, 0.9 * inch, 2.9 * inch]))

    ncr_rows = [[item.get("code", "—"), item.get("status", "—"), item.get("title", "—"), safe_join(item.get("linked_photo_urls", []))] for item in ncrs]
    add_section(story, 6, "Linked NCRs and Key Photos", grid_table(["NCR", "Status", "Title", "Photos"], ncr_rows or [["—", "—", "—", "—"]], widths=[1.0 * inch, 1.0 * inch, 2.2 * inch, 2.8 * inch]))

    add_section(
        story,
        "6A",
        "Package Acceptance Sign-Off",
        signoff_table([
            ["Role", "Name / Signature", "Company / Title", "Date"],
            ["QC Manager", "__________________", "PSI", "____________"],
            ["Production Manager", "__________________", "PSI", "____________"],
            ["Engineer / DOT Review", "__________________", "Owner / DOT", "____________"],
        ]),
    )

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    buf.seek(0)
    return buf.read()
