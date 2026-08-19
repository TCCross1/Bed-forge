"""Blueprint Assessment PDF — complete print-verification pack for Blueprint Intelligence."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from blueprint_pipeline import CRITICAL_FIELDS, FIELD_GROUPS, normalize_locked_blueprint
from models import BlueprintField

logger = logging.getLogger(__name__)

FOOTER = "BedForge Blueprint Assessment — for print verification only"
OCR_NOTICE = "Sparse/empty text pages are rasterized and OCR'd (pytesseract). Field notes label source as text_layer, ocr, or text_layer+ocr."

NAVY = colors.HexColor("#0F172A")
SLATE = colors.HexColor("#475569")
INK = colors.HexColor("#111827")
ROW = colors.HexColor("#F8FAFC")
GRID = colors.HexColor("#CBD5E1")
WARN = colors.HexColor("#B45309")
TEAL = colors.HexColor("#0F766E")

GROUP_TITLES = {
    "title_block": "C1. Title Block / Identity",
    "geometry": "C2. Geometry",
    "strand_system": "C3. Strand System",
    "hardware": "C4. Hardware",
    "ends_and_qc": "C5. Ends, QC & Finishes",
}

IDENTITY_ROWS: List[Tuple[str, str, bool]] = [
    ("job_number", "Job number", False),
    ("cid", "CID", False),
    ("beam_mark", "Beam mark (compact)", False),
    ("beam_marks", "Beam marks (all)", False),
    ("product_family", "Product family / beam type", False),
    ("county_dot", "County / DOT", False),
    ("bridge_id", "Bridge ID", False),
    ("route", "Route", False),
    ("overall_length_ft", "Overall length", False),
    ("casting_length_ft", "Casting length", False),
    ("mark_length_families", "Mark length families", False),
    ("overall_depth_in", "Depth", False),
    ("strand_diameter_in", "Strand diameter", False),
    ("strand_grade", "Strand grade", False),
    ("strand_final_pull_lb", "Strand final pull", False),
    ("hold_down_type", "Hold-down type", False),
    ("lift_loop_spec", "Lift-loop spec", False),
]

TWIN_DRIVERS: List[Tuple[str, str]] = [
    ("product_family", "Selects I-beam vs box-beam cross-section family"),
    ("overall_length_ft", "Twin length (normalized_blueprint.length)"),
    ("overall_depth_in", "I-beam overall depth"),
    ("top_flange_width_in", "I-beam top flange width"),
    ("top_flange_thickness_in", "I-beam top flange thickness"),
    ("bottom_flange_width_in", "I-beam bottom flange width"),
    ("bottom_flange_thickness_in", "I-beam bottom flange thickness"),
    ("web_thickness_in", "I-beam web thickness"),
    ("outer_width_in", "Box-beam outer width"),
    ("outer_depth_in", "Box-beam outer depth"),
    ("wall_thickness_in", "Box-beam wall"),
    ("void_width_in", "Box-beam void width"),
    ("void_depth_in", "Box-beam void depth"),
    ("strand_pattern_rows", "Strand row DNA (else invented from counts)"),
    ("strand_count", "Fallback strand count"),
    ("straight_strand_count", "Fallback straight-row count"),
    ("draped_strand_count", "Drape profile + draped row"),
    ("hold_downs", "Hold-down stations / drape low points"),
    ("lift_loops", "Lift-loop stations"),
    ("inserts", "Insert stations"),
    ("tubes", "Tube stations"),
    ("tie_rod_openings", "Tie-rod stations"),
    ("drain_holes", "Drain stations"),
    ("grout_grooves", "Grout-groove stations"),
    ("stirrups", "Stirrup spacing (regions not modeled)"),
    ("marked_end_rule", "Marked-end label"),
    ("bituminous_ends", "Bituminous / cutoff pockets"),
    ("jacking_force_kip", "Tension reference jacking force"),
    ("target_elongation_in", "Tension reference elongation"),
    ("strand_diameter_in", "Tension reference diameter"),
    ("strand_area_in2", "Tension reference area"),
    ("strand_grade", "270K / low-relaxation identity"),
    ("strand_final_pull_lb", "Final pull (lb) into tension reference"),
    ("hold_down_type", "Hold-down hardware type (H-56-S)"),
    ("lift_loop_spec", "Lift-loop specification (no invented counts)"),
    ("beam_marks", "Multi-beam DNA mark list"),
    ("mark_length_families", "Per-mark overall/casting length families"),
    ("casting_length_ft", "Casting length for bed setup"),
]

SCHEMA_GAPS = [
    "bed layout / bulkhead stations (still plant-setup, not twin DNA)",
    "invented hardware quantities (intentionally omitted unless BOM text is explicit)",
]

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="BrandTitle", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=INK, alignment=TA_LEFT))
styles.add(ParagraphStyle(name="SubTitle", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=NAVY, alignment=TA_LEFT))
styles.add(ParagraphStyle(name="SectionTitle", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=NAVY, spaceBefore=10, spaceAfter=5))
styles.add(ParagraphStyle(name="IdentityLabel", fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=NAVY))
styles.add(ParagraphStyle(name="BodyText2", fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK, alignment=TA_LEFT))
styles.add(ParagraphStyle(name="SmallMuted", fontName="Helvetica", fontSize=8, leading=10, textColor=SLATE))
styles.add(ParagraphStyle(name="Warn", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=WARN))
styles.add(ParagraphStyle(name="OkNote", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=TEAL))
styles.add(ParagraphStyle(name="FooterStyle", fontName="Helvetica", fontSize=8, leading=10, textColor=SLATE, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="MonoExcerpt", fontName="Courier", fontSize=7.5, leading=9.5, textColor=INK))


def _clean(value: Any, limit: int = 900) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, (list, dict)):
        text = json.dumps(value, default=str, ensure_ascii=True)
    else:
        text = str(value)
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit] + "…"
    return escape(text)


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


def _field_bits(field: Optional[Dict[str, Any]]) -> Tuple[Any, str, str, Any, str]:
    field = field or {}
    value = field.get("value", field.get("text"))
    conf = field.get("confidence", field.get("confidence_label") or "—")
    state = field.get("status", field.get("confirmation", field.get("state") or "—"))
    page = field.get("source_page", field.get("page"))
    notes = field.get("extraction_notes") or ""
    return value, str(conf or "—"), str(state or "—"), page, str(notes or "")


def _has_value(value: Any) -> bool:
    if value is None or value == "" or value == "—":
        return False
    if isinstance(value, (list, dict)) and not value:
        return False
    return True


def _is_weak(field: Optional[Dict[str, Any]]) -> bool:
    value, conf, state, _page, _notes = _field_bits(field)
    state_l = state.lower()
    conf_l = conf.lower()
    if state_l == "not_applicable":
        return False
    if not _has_value(value):
        return True
    if state_l in {"unconfirmed", "needs_review", ""}:
        return True
    if conf_l == "low":
        return True
    return False


def _kv_table(rows: List[Tuple[str, Any]], label_w: float = 1.85, value_w: float = 5.15) -> Table:
    data = [
        [Paragraph(f"<b>{escape(str(k))}</b>", styles["BodyText2"]), Paragraph(_clean(v, limit=1200), styles["BodyText2"])]
        for k, v in rows
    ]
    table = Table(data, colWidths=[label_w * inch, value_w * inch])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _inventory_table(keys: List[str], fields: Dict[str, Dict[str, Any]], extra_rows: Optional[List[List[Any]]] = None) -> Table:
    header = [
        Paragraph("<b>Field</b>", styles["BodyText2"]),
        Paragraph("<b>Value</b>", styles["BodyText2"]),
        Paragraph("<b>Conf</b>", styles["BodyText2"]),
        Paragraph("<b>Status</b>", styles["BodyText2"]),
        Paragraph("<b>Page</b>", styles["BodyText2"]),
        Paragraph("<b>extraction_notes</b>", styles["BodyText2"]),
    ]
    rows = [header]
    for key in keys:
        value, conf, state, page, notes = _field_bits(fields.get(key))
        rows.append([
            Paragraph(escape(key), styles["BodyText2"]),
            Paragraph(_clean(value, limit=500), styles["BodyText2"]),
            Paragraph(_clean(conf, limit=40), styles["BodyText2"]),
            Paragraph(_clean(state, limit=40), styles["BodyText2"]),
            Paragraph(_clean(page, limit=20), styles["BodyText2"]),
            Paragraph(_clean(notes, limit=400), styles["BodyText2"]),
        ])
    if extra_rows:
        rows.extend(extra_rows)
    table = Table(rows, colWidths=[1.25 * inch, 1.85 * inch, 0.6 * inch, 0.95 * inch, 0.5 * inch, 1.85 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("BACKGROUND", (0, 1), (-1, -1), ROW),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _identity_extra_row(label: str, key: str, note: str) -> List[Any]:
    return [
        Paragraph(escape(key), styles["IdentityLabel"]),
        Paragraph("— (not in current extractor schema)", styles["BodyText2"]),
        Paragraph("—", styles["BodyText2"]),
        Paragraph("not_in_schema", styles["BodyText2"]),
        Paragraph("—", styles["BodyText2"]),
        Paragraph(_clean(note, limit=400), styles["BodyText2"]),
    ]


def _draw_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(SLATE)
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(letter[0] / 2.0, 0.38 * inch, FOOTER)
    canvas.drawRightString(letter[0] - 0.55 * inch, 0.38 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _typed_fields(fields: Dict[str, Dict[str, Any]]) -> Dict[str, BlueprintField]:
    typed: Dict[str, BlueprintField] = {}
    for key, raw in fields.items():
        try:
            typed[key] = BlueprintField(**(raw or {}))
        except Exception:
            logger.warning("Skipping malformed extraction field %s in assessment PDF", key)
    return typed


def _twin_readiness(fields: Dict[str, Dict[str, Any]], locked_revision: Optional[Dict[str, Any]]) -> Tuple[List[str], List[str], Dict[str, Any]]:
    ready: List[str] = []
    missing: List[str] = []
    dna: Dict[str, Any] = {}
    typed = _typed_fields(fields)
    if typed:
        try:
            dna = normalize_locked_blueprint(typed)
        except Exception:
            logger.exception("normalize_locked_blueprint failed while building assessment PDF")
            dna = {}
    if locked_revision and locked_revision.get("normalized_blueprint"):
        dna = locked_revision.get("normalized_blueprint") or dna
    for key, purpose in TWIN_DRIVERS:
        field = fields.get(key) or {}
        value, _conf, state, _page, _notes = _field_bits(field)
        usable = _has_value(value) and str(state).lower() not in {"unconfirmed", "not_applicable"}
        if usable:
            ready.append(f"{key} — {purpose}")
        elif str(state).lower() == "not_applicable":
            continue
        else:
            missing.append(f"{key} — {purpose}")
    return ready, missing, dna


def build_extraction_report_pdf(
    document: Dict[str, Any],
    extraction: Optional[Dict[str, Any]] = None,
    locked_revision: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Build the Blueprint Assessment PDF. Signature stays compatible with older callers."""
    try:
        extraction = extraction or {}
        locked_revision = locked_revision or {}
        fields = _field_map(extraction)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        status = (extraction.get("status") or document.get("status") or "uploaded").upper()
        extractor = extraction.get("extractor_version") or "controlled_regex_ocr_v2"
        page_text = extraction.get("page_text") or []
        page_sources = extraction.get("page_sources") or []
        page_count = document.get("page_count") or len(page_text) or 0

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=0.5 * inch,
            rightMargin=0.5 * inch,
            topMargin=0.5 * inch,
            bottomMargin=0.6 * inch,
            title="BedForge Blueprint Assessment",
            author="BedForge QC",
        )
        story: List[Any] = []

        story.append(Paragraph("BedForge QC — Blueprint Intelligence", styles["BrandTitle"]))
        story.append(Paragraph("Blueprint Assessment Pack", styles["SubTitle"]))
        story.append(Paragraph("Internal verification artifact. Compare side-by-side with plant shop drawings. Prestressed plant branding is secondary.", styles["SmallMuted"]))
        story.append(Spacer(1, 8))

        cover_rows = [
            ("Document ID", document.get("id") or document.get("_id") or "—"),
            ("Filename", document.get("filename") or document.get("original_filename") or "—"),
            ("Uploaded", document.get("created_at") or "—"),
            ("Updated", document.get("updated_at") or "—"),
            ("Page count", page_count),
            ("Linked job_id", document.get("job_id") or "—"),
            ("Linked beam_id", document.get("beam_id") or "—"),
            ("Product type id", document.get("product_type_id") or "—"),
            ("Upload hints", f"family={document.get('product_family_hint') or '—'}; mark={document.get('beam_mark_hint') or '—'}; project={document.get('project_name_hint') or '—'}"),
            ("Extraction status", status),
            ("Document status", (document.get("status") or "—")),
            ("Locked revision", (locked_revision.get("id") or document.get("locked_revision_id") or "—")),
            ("Extractor version", extractor),
            ("Extraction created", extraction.get("created_at") or "— (run Extract to populate)"),
            ("Confirmed / unconfirmed", f"{extraction.get('confirmed_count', '—')} / {extraction.get('unconfirmed_count', '—')}"),
            ("Generated", stamp),
        ]
        story.append(Paragraph("A. Cover / identity", styles["SectionTitle"]))
        story.append(_kv_table(cover_rows))
        fail_reasons = extraction.get("fail_reasons") or []
        if fail_reasons:
            story.append(Spacer(1, 6))
            story.append(Paragraph("Controlled fail reasons", styles["Warn"]))
            for reason in fail_reasons:
                story.append(Paragraph(f"• {_clean(reason, limit=400)}", styles["BodyText2"]))

        story.append(Paragraph("B. Critical identity", styles["SectionTitle"]))
        story.append(Paragraph("Large first-pass identity for plant-job comparison (Job L25390 / CID / Type 2 / marks / lengths). Schema-absent keys are listed explicitly so missing DNA is visible.", styles["SmallMuted"]))
        ident_header = [
            Paragraph("<b>Field</b>", styles["BodyText2"]),
            Paragraph("<b>Value</b>", styles["BodyText2"]),
            Paragraph("<b>Conf</b>", styles["BodyText2"]),
            Paragraph("<b>Status</b>", styles["BodyText2"]),
            Paragraph("<b>Page</b>", styles["BodyText2"]),
            Paragraph("<b>extraction_notes</b>", styles["BodyText2"]),
        ]
        ident_rows = [ident_header]
        for key, label, virtual in IDENTITY_ROWS:
            if virtual and key not in fields:
                ident_rows.append(_identity_extra_row(label, key, f"{label} is not extracted by {extractor}."))
                continue
            value, conf, state, page, notes = _field_bits(fields.get(key))
            display_notes = notes
            if key == "beam_mark" and document.get("beam_mark_hint"):
                display_notes = (display_notes + " " if display_notes else "") + f"Upload hint: {document.get('beam_mark_hint')}"
            ident_rows.append([
                Paragraph(escape(f"{label} ({key})"), styles["IdentityLabel"]),
                Paragraph(_clean(value, limit=400), styles["BodyText2"]),
                Paragraph(_clean(conf, limit=40), styles["BodyText2"]),
                Paragraph(_clean(state, limit=40), styles["BodyText2"]),
                Paragraph(_clean(page, limit=20), styles["BodyText2"]),
                Paragraph(_clean(display_notes, limit=400), styles["BodyText2"]),
            ])
        ident_table = Table(ident_rows, colWidths=[1.55 * inch, 1.7 * inch, 0.55 * inch, 0.9 * inch, 0.45 * inch, 1.85 * inch])
        ident_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.45, GRID),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#ECFEFF")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(ident_table)

        story.append(Paragraph("C. Full field inventory", styles["SectionTitle"]))
        story.append(Paragraph("Every FIELD_GROUPS key currently known to Blueprint Intelligence, including empty and not-applicable fields.", styles["SmallMuted"]))
        listed = set()
        for group_key, keys in FIELD_GROUPS.items():
            listed.update(keys)
            story.append(Paragraph(f"{GROUP_TITLES.get(group_key, group_key)} ({group_key})", styles["SectionTitle"]))
            story.append(_inventory_table(keys, fields))
        extras = sorted(k for k in fields.keys() if k not in listed)
        if extras:
            story.append(Paragraph("C6. Additional extracted keys (not in FIELD_GROUPS)", styles["SectionTitle"]))
            story.append(_inventory_table(extras, fields))

        story.append(PageBreak())
        story.append(Paragraph("D. Missing / weak fields", styles["SectionTitle"]))
        story.append(Paragraph("CRITICAL_FIELDS that are empty, low-confidence, or UNCONFIRMED. These block or weaken lock / twin use.", styles["SmallMuted"]))
        weak_critical = []
        for key in sorted(CRITICAL_FIELDS):
            field = fields.get(key) or {}
            value, conf, state, page, notes = _field_bits(field)
            if _is_weak(field):
                weak_critical.append((key, f"value={_clean(value, 80)} | conf={conf} | status={state} | page={_clean(page, 20)} | {notes or 'no notes'}"))
        if weak_critical:
            for key, detail in weak_critical:
                story.append(Paragraph(f"• <b>{escape(key)}</b> — {_clean(detail, 500)}", styles["Warn"]))
        elif not fields:
            story.append(Paragraph("No extraction on file. Run Extract before assessing critical fields.", styles["Warn"]))
        else:
            story.append(Paragraph("All CRITICAL_FIELDS currently have a value and are not unconfirmed/low.", styles["OkNote"]))

        other_weak = []
        for key, field in sorted(fields.items()):
            if key in CRITICAL_FIELDS:
                continue
            if _is_weak(field):
                value, conf, state, page, _notes = _field_bits(field)
                other_weak.append(f"{key} [{state}/{conf}] page={_clean(page, 12)} value={_clean(value, 80)}")
        if other_weak:
            story.append(Paragraph("Other empty / unconfirmed / low-confidence fields", styles["SectionTitle"]))
            for line in other_weak:
                story.append(Paragraph(f"• {_clean(line, 400)}", styles["BodyText2"]))

        story.append(Paragraph("Schema gaps vs L25390-class shop drawings (not extracted today)", styles["SectionTitle"]))
        for gap in SCHEMA_GAPS:
            story.append(Paragraph(f"• {_clean(gap, 200)}", styles["BodyText2"]))

        story.append(PageBreak())
        story.append(Paragraph("E. Page text evidence appendix", styles["SectionTitle"]))
        story.append(Paragraph(OCR_NOTICE, styles["SmallMuted"]))
        if not page_text:
            story.append(Paragraph("No page_text stored on this document. Either Extract has not been run, or neither the text layer nor OCR produced tokens.", styles["BodyText2"]))
            if page_count:
                story.append(Paragraph(f"Upload recorded page_count={page_count}. Re-run Extract to capture per-page text evidence.", styles["SmallMuted"]))
        for index, raw in enumerate(page_text, start=1):
            text = (raw or "").strip()
            source = page_sources[index - 1] if index - 1 < len(page_sources) else "text_layer"
            story.append(Paragraph(f"Page {index} · source={escape(str(source))}", styles["SectionTitle"]))
            if not text:
                story.append(Paragraph("IMAGE-ONLY / EMPTY after native text + OCR. No tokens were extracted from this page.", styles["Warn"]))
            else:
                excerpt = text if len(text) <= 1800 else text[:1800] + "…"
                story.append(Paragraph(f"Merged excerpt ({len(text)} chars, source={escape(str(source))}):", styles["SmallMuted"]))
                story.append(Paragraph(escape(excerpt).replace("\n", "<br/>"), styles["MonoExcerpt"]))

        story.append(PageBreak())
        story.append(Paragraph("F. Twin DNA readiness", styles["SectionTitle"]))
        story.append(Paragraph("Fields that would currently drive a 3D twin after lock via normalize_locked_blueprint(). Draft extractions do not render a production twin until Verify &amp; Lock.", styles["SmallMuted"]))
        ready, missing, dna = _twin_readiness(fields, locked_revision)
        lock_status = "LOCKED" if (locked_revision.get("id") or document.get("locked_revision_id")) else "NOT LOCKED — twin stays draft/legacy until lock"
        story.append(_kv_table([
            ("Twin lock state", lock_status),
            ("Normalized length", (dna or {}).get("length")),
            ("Cross-section keys", sorted(((dna or {}).get("cross_section") or {}).keys()) or "—"),
            ("Strand pattern rows", len(((dna or {}).get("strand_pattern") or {}).get("rows") or [])),
            ("Lift loops / hold-downs", f"{len((dna or {}).get('lift_loops') or [])} / {len((dna or {}).get('hold_downs') or [])}"),
            ("Locked revision id", locked_revision.get("id") or "—"),
        ]))
        story.append(Paragraph("Would drive twin today (extracted + confirmed/manually_confirmed)", styles["SectionTitle"]))
        if ready:
            for item in ready:
                story.append(Paragraph(f"• {_clean(item, 300)}", styles["BodyText2"]))
        else:
            story.append(Paragraph("None. Extract and confirm geometry/strand/hardware before lock.", styles["Warn"]))
        story.append(Paragraph("Required twin inputs still missing or unconfirmed", styles["SectionTitle"]))
        if missing:
            for item in missing:
                story.append(Paragraph(f"• {_clean(item, 300)}", styles["BodyText2"]))
        else:
            story.append(Paragraph("No mapped twin drivers are empty/unconfirmed (family-N/A fields omitted).", styles["OkNote"]))
        story.append(Paragraph("Normalized DNA snapshot (what lock would persist)", styles["SectionTitle"]))
        story.append(Paragraph(_clean(dna or "— no DNA (no extraction fields)", limit=2500), styles["MonoExcerpt"]))

        story.append(Spacer(1, 16))
        story.append(Paragraph(FOOTER, styles["FooterStyle"]))
        story.append(Paragraph(f"Generated {stamp} · extractor {escape(str(extractor))}", styles["FooterStyle"]))

        doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
        pdf_bytes = buffer.getvalue()
        logger.info(
            "Blueprint assessment PDF built document_id=%s status=%s bytes=%s pages_text=%s",
            document.get("id"),
            status,
            len(pdf_bytes),
            len(page_text),
        )
        return pdf_bytes
    except Exception:
        logger.exception("Failed to build Blueprint Assessment PDF document_id=%s", (document or {}).get("id"))
        raise
