"""Blueprint Intelligence extraction report PDF — for print verification."""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from blueprint_pipeline import CRITICAL_FIELDS, FIELD_GROUPS

BRAND = "PRESTRESS SERVICES INDUSTRIES LLC"
FOOTER = "BedForge QC — DEV EXTRACTION REPORT"

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="BrandTitle", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=colors.HexColor("#111827"), alignment=TA_LEFT))
styles.add(ParagraphStyle(name="SubTitle", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=colors.HexColor("#0F172A"), alignment=TA_LEFT))
styles.add(ParagraphStyle(name="SectionTitle", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#0F172A"), spaceBefore=10, spaceAfter=4))
styles.add(ParagraphStyle(name="BodyText2", fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#111827")))
styles.add(ParagraphStyle(name="SmallMuted", fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#475569")))
styles.add(ParagraphStyle(name="Warn", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=colors.HexColor("#B45309")))
styles.add(ParagraphStyle(name="FooterStyle", fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#64748B"), alignment=TA_CENTER))


def _clean(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value)


def _field_map(extraction: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw = extraction.get("fields") or {}
    out: Dict[str, Dict[str, Any]] = {}
    if isinstance(raw, dict):
        for key, val in raw.items():
            if hasattr(val, "model_dump"):
                out[key] = val.model_dump()
            elif isinstance(val, dict):
                out[key] = val
            else:
                out[key] = {"value": val}
    elif isinstance(raw, list):
        for item in raw:
            if hasattr(item, "model_dump"):
                item = item.model_dump()
            if isinstance(item, dict) and item.get("key"):
                out[item["key"]] = item
    return out


def _group_table(group_name: str, keys: List[str], fields: Dict[str, Dict[str, Any]]) -> Table:
    header = [
        Paragraph("<b>Field</b>", styles["BodyText2"]),
        Paragraph("<b>Value</b>", styles["BodyText2"]),
        Paragraph("<b>Conf</b>", styles["BodyText2"]),
        Paragraph("<b>State</b>", styles["BodyText2"]),
        Paragraph("<b>Page</b>", styles["BodyText2"]),
    ]
    rows = [header]
    for key in keys:
        f = fields.get(key, {})
        value = f.get("value", f.get("text", "—"))
        conf = f.get("confidence", f.get("confidence_label", "—"))
        state = f.get("status", f.get("confirmation", f.get("state", "—")))
        page = f.get("source_page", f.get("page", "—"))
        rows.append([
            Paragraph(key, styles["BodyText2"]),
            Paragraph(_clean(value), styles["BodyText2"]),
            Paragraph(_clean(conf), styles["BodyText2"]),
            Paragraph(_clean(state), styles["BodyText2"]),
            Paragraph(_clean(page), styles["BodyText2"]),
        ])
    table = Table(rows, colWidths=[1.7 * inch, 2.6 * inch, 0.7 * inch, 1.1 * inch, 0.6 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F8FAFC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def build_extraction_report_pdf(document: Dict[str, Any], extraction: Optional[Dict[str, Any]] = None) -> bytes:
    extraction = extraction or {}
    fields = _field_map(extraction)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title="BedForge Extraction Report",
    )
    story: List[Any] = []
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    story.append(Paragraph(BRAND, styles["BrandTitle"]))
    story.append(Paragraph("Blueprint Intelligence — Extraction Report", styles["SubTitle"]))
    story.append(Paragraph("DEV / VERIFICATION ONLY — compare side-by-side with source print", styles["SmallMuted"]))
    story.append(Spacer(1, 8))

    meta_rows = [
        ("Source file", document.get("filename") or document.get("original_filename") or "—"),
        ("Document ID", document.get("id") or document.get("_id") or "—"),
        ("Pages", document.get("page_count") or extraction.get("page_count") or "—"),
        ("Status", extraction.get("status") or document.get("status") or "—"),
        ("Product family", (fields.get("product_family") or {}).get("value") or document.get("product_type") or "—"),
        ("Job number", (fields.get("job_number") or {}).get("value") or "—"),
        ("Beam mark", (fields.get("beam_mark") or {}).get("value") or "—"),
        ("Generated", stamp),
    ]
    meta = Table(
        [[Paragraph(f"<b>{k}</b>", styles["BodyText2"]), Paragraph(_clean(v), styles["BodyText2"])] for k, v in meta_rows],
        colWidths=[1.6 * inch, 5.1 * inch],
    )
    meta.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(meta)
    story.append(Spacer(1, 10))

    blocking = []
    for key in CRITICAL_FIELDS:
        f = fields.get(key) or {}
        state = str(f.get("status") or f.get("confirmation") or "").lower()
        val = f.get("value")
        if not val or state in {"unconfirmed", "needs_review", ""}:
            blocking.append(key)
    if blocking:
        story.append(Paragraph("Critical fields needing verification", styles["SectionTitle"]))
        story.append(Paragraph(", ".join(blocking), styles["Warn"]))
        story.append(Spacer(1, 6))

    group_titles = {
        "title_block": "1. Title Block / Identity",
        "geometry": "2. Geometry",
        "strand_system": "3. Strand System",
        "hardware": "4. Hardware",
        "ends_and_qc": "5. Ends & QC",
    }
    for group_key, keys in FIELD_GROUPS.items():
        story.append(Paragraph(group_titles.get(group_key, group_key), styles["SectionTitle"]))
        story.append(_group_table(group_key, keys, fields))

    story.append(Spacer(1, 14))
    story.append(Paragraph(f"{FOOTER}  ·  {stamp}", styles["FooterStyle"]))
    story.append(Paragraph("Use this report to verify AI extraction against the original shop drawing.", styles["FooterStyle"]))

    doc.build(story)
    return buffer.getvalue()
