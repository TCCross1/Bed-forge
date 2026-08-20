"""Prestressed cylinder tag generator — 6 beams per physical label.

Matches the plant spreadsheet rules:
- unused / empty cells never print
- more than 6 beams → continuation pages (PAGE n OF m)
- 13 beams = 3 labels per cylinder
"""
import io
import logging
import math
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_SLOTS = 10
MAX_BEAMS = 30
BEAMS_PER_LABEL = 6
STATUS_READY = "READY TO PRINT"
STATUS_INCOMPLETE = "INCOMPLETE"
STATUS_UNUSED = "NOT USED"


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def clean_beams(marks: Optional[List[Any]]) -> List[str]:
    out = []
    for mark in marks or []:
        text = clean_text(mark)
        if text:
            out.append(text)
        if len(out) >= MAX_BEAMS:
            break
    return out


def labels_per_cylinder(beam_count: int) -> int:
    if beam_count <= 0:
        return 0
    return int(math.ceil(beam_count / float(BEAMS_PER_LABEL)))


def physical_labels(beam_count: int, cylinder_tags_needed: int) -> int:
    needed = max(int(cylinder_tags_needed or 0), 0)
    return labels_per_cylinder(beam_count) * needed


def empty_slot(index: int, qc_tech: str = "", pour_date: str = "") -> dict:
    return {
        "slot": int(index),
        "use_today": False,
        "qc_tech": qc_tech or "",
        "job_number": "",
        "job_id": None,
        "expected_beam_count": 0,
        "pour_number": "",
        "pour_id": None,
        "pour_date": pour_date or "",
        "cylinder_tags_needed": 0,
        "beam_marks": [""] * MAX_BEAMS,
    }


def empty_run(qc_tech: str = "", run_date: str = "") -> dict:
    return {
        "run_date": run_date or "",
        "job_count": 1,
        "slots": [empty_slot(i, qc_tech, run_date) for i in range(1, MAX_SLOTS + 1)],
    }


def normalize_slot(raw: dict, index: int) -> dict:
    src = raw or {}
    beams = list(src.get("beam_marks") or [])
    while len(beams) < MAX_BEAMS:
        beams.append("")
    beams = [clean_text(b) for b in beams[:MAX_BEAMS]]
    expected = src.get("expected_beam_count") or 0
    needed = src.get("cylinder_tags_needed") or 0
    try:
        expected = int(expected)
    except (TypeError, ValueError):
        expected = 0
    try:
        needed = int(needed)
    except (TypeError, ValueError):
        needed = 0
    use_today = bool(src.get("use_today"))
    return {
        "slot": int(src.get("slot") or index),
        "use_today": use_today,
        "qc_tech": clean_text(src.get("qc_tech")),
        "job_number": clean_text(src.get("job_number")),
        "job_id": src.get("job_id") or None,
        "expected_beam_count": max(expected, 0),
        "pour_number": clean_text(src.get("pour_number")),
        "pour_id": src.get("pour_id") or None,
        "pour_date": clean_text(src.get("pour_date")),
        "cylinder_tags_needed": max(needed, 0),
        "beam_marks": beams,
    }


def slot_status(slot: dict) -> str:
    if not slot.get("use_today"):
        return STATUS_UNUSED
    beams = clean_beams(slot.get("beam_marks"))
    if (
        not slot.get("job_number")
        or not slot.get("qc_tech")
        or not beams
        or int(slot.get("cylinder_tags_needed") or 0) < 1
    ):
        return STATUS_INCOMPLETE
    return STATUS_READY


def summarize_slot(slot: dict, cumulative_before: int = 0) -> dict:
    beams = clean_beams(slot.get("beam_marks"))
    entered = len(beams)
    status = slot_status(slot)
    per = labels_per_cylinder(entered) if status != STATUS_UNUSED else 0
    needed = int(slot.get("cylinder_tags_needed") or 0)
    physical = per * needed if status == STATUS_READY else 0
    return {
        "slot": slot.get("slot"),
        "use_today": bool(slot.get("use_today")),
        "qc_tech": slot.get("qc_tech") or "",
        "job_number": slot.get("job_number") or "",
        "job_id": slot.get("job_id"),
        "pour_number": slot.get("pour_number") or "",
        "pour_id": slot.get("pour_id"),
        "pour_date": slot.get("pour_date") or "",
        "expected_beam_count": int(slot.get("expected_beam_count") or 0),
        "entered_beam_count": entered,
        "beam_list": beams,
        "cylinder_tags_needed": needed,
        "labels_per_cylinder": per,
        "physical_labels": physical,
        "cumulative_labels": cumulative_before + physical,
        "status": status,
    }


def _chunk_beams(beams: List[str]) -> List[List[str]]:
    if not beams:
        return []
    parts = []
    for i in range(0, len(beams), BEAMS_PER_LABEL):
        chunk = beams[i:i + BEAMS_PER_LABEL]
        while len(chunk) < BEAMS_PER_LABEL:
            chunk.append("")
        parts.append(chunk)
    return parts


def print_rows_for_slot(slot: dict, label_start: int = 1) -> List[dict]:
    summary = summarize_slot(slot)
    if summary["status"] != STATUS_READY:
        return []
    beams = summary["beam_list"]
    chunks = _chunk_beams(beams)
    parts_total = len(chunks)
    needed = summary["cylinder_tags_needed"]
    rows = []
    label_no = label_start
    for copy in range(1, needed + 1):
        for part, chunk in enumerate(chunks, start=1):
            caption = f"PAGE {part} OF {parts_total}" if parts_total > 1 else ""
            row = {
                "label_number": label_no,
                "job_slot": slot["slot"],
                "qc_tech": slot.get("qc_tech") or "",
                "job_number": slot.get("job_number") or "",
                "pour_number": slot.get("pour_number") or "",
                "date": slot.get("pour_date") or "",
                "cylinder_copy": copy,
                "copies_total": needed,
                "part": part,
                "parts_total": parts_total,
                "part_caption": caption,
                "beam_list": beams,
                "physical_labels_for_job": summary["physical_labels"],
            }
            for i in range(BEAMS_PER_LABEL):
                row[f"beam_{i + 1}"] = chunk[i]
            rows.append(row)
            label_no += 1
    return rows


def cylinder_sets_for_slot(slot: dict, run_id: str) -> List[dict]:
    summary = summarize_slot(slot)
    if summary["status"] != STATUS_READY:
        return []
    beams = summary["beam_list"]
    needed = summary["cylinder_tags_needed"]
    job = summary["job_number"]
    pour = summary["pour_number"] or "POUR"
    sets = []
    for copy in range(1, needed + 1):
        set_id = f"{job}-{pour}-C{copy}"
        sets.append({
            "set_id": set_id,
            "run_id": run_id,
            "job_slot": slot["slot"],
            "job_number": job,
            "job_id": slot.get("job_id"),
            "pour_number": summary["pour_number"],
            "pour_id": slot.get("pour_id"),
            "pour_date": summary["pour_date"],
            "qc_tech": summary["qc_tech"],
            "cylinder_copy": copy,
            "copies_total": needed,
            "beam_marks": beams,
            "status": "cast",
            "crush_psi": None,
            "crush_date": None,
            "crush_age_days": None,
            "required_psi": None,
            "release_ok": None,
            "notes": "",
        })
    return sets


def build_run_payload(raw: dict) -> dict:
    src = raw or {}
    job_count = src.get("job_count") or 1
    try:
        job_count = int(job_count)
    except (TypeError, ValueError):
        job_count = 1
    job_count = max(1, min(MAX_SLOTS, job_count))
    incoming = list(src.get("slots") or [])
    slots = []
    for i in range(1, MAX_SLOTS + 1):
        found = next((s for s in incoming if int(s.get("slot") or 0) == i), None)
        if found is None and i - 1 < len(incoming):
            found = incoming[i - 1]
        slot = normalize_slot(found or empty_slot(i, src.get("qc_tech") or "", src.get("run_date") or ""), i)
        if i > job_count:
            slot["use_today"] = False
        slots.append(slot)

    summaries = []
    rows = []
    cumulative = 0
    for slot in slots:
        summary = summarize_slot(slot, cumulative)
        summaries.append(summary)
        if summary["status"] == STATUS_READY:
            rows.extend(print_rows_for_slot(slot, label_start=cumulative + 1))
            cumulative = summary["cumulative_labels"]
        else:
            summary["cumulative_labels"] = cumulative
            summaries[-1] = summary

    ready = sum(1 for s in summaries if s["status"] == STATUS_READY)
    incomplete = sum(1 for s in summaries if s["status"] == STATUS_INCOMPLETE)
    return {
        "run_date": clean_text(src.get("run_date")),
        "job_count": job_count,
        "slots": slots,
        "summaries": summaries,
        "print_rows": rows,
        "total_physical_labels": len(rows),
        "ready_jobs": ready,
        "incomplete_jobs": incomplete,
        "print_ready": ready > 0 and incomplete == 0,
    }


def build_pdf_bytes(print_rows: List[dict], company: dict, logo_path: Optional[str] = None) -> bytes:
    """High-contrast letter-page tags, 2 columns × 3 rows, actual size."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
    except ImportError as exc:
        logger.exception("reportlab missing — cannot build cylinder PDF")
        raise RuntimeError("PDF engine is not installed") from exc

    company = company or {}
    company_name = clean_text(company.get("company_name")) or "PRESTRESS SERVICES INDUSTRIES LLC"
    header = clean_text(company.get("tag_header")) or company_name
    buf = io.BytesIO()
    page_w, page_h = letter
    c = canvas.Canvas(buf, pagesize=letter)
    margin_x = 0.45 * inch
    margin_y = 0.5 * inch
    gap_x = 0.18 * inch
    gap_y = 0.18 * inch
    cols, rows_n = 2, 3
    tag_w = (page_w - (2 * margin_x) - gap_x) / cols
    tag_h = (page_h - (2 * margin_y) - (gap_y * (rows_n - 1))) / rows_n

    logo = None
    if logo_path:
        try:
            logo = ImageReader(logo_path)
        except Exception:
            logger.exception("cylinder PDF logo load failed")
            logo = None

    def draw_tag(x, y, row):
        c.setStrokeColorRGB(0, 0, 0)
        c.setFillColorRGB(1, 1, 1)
        c.setLineWidth(1.6)
        c.rect(x, y, tag_w, tag_h, stroke=1, fill=1)
        inner = 0.12 * inch
        tx = x + inner
        ty = y + tag_h - inner
        c.setFillColorRGB(0, 0, 0)
        if logo:
            try:
                c.drawImage(logo, tx, ty - 0.32 * inch, width=0.9 * inch, height=0.32 * inch, preserveAspectRatio=True, mask="auto")
                c.setFont("Helvetica-Bold", 8)
                c.drawRightString(x + tag_w - inner, ty - 0.14 * inch, header[:42])
            except Exception:
                logger.exception("cylinder PDF logo draw failed")
                c.setFont("Helvetica-Bold", 9)
                c.drawString(tx, ty - 0.16 * inch, header[:48])
        else:
            c.setFont("Helvetica-Bold", 9)
            c.drawString(tx, ty - 0.16 * inch, header[:48])
        ty -= 0.42 * inch
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(0.6)
        c.line(tx, ty, x + tag_w - inner, ty)
        ty -= 0.22 * inch
        job = clean_text(row.get("job_number"))
        pour = clean_text(row.get("pour_number"))
        c.setFont("Helvetica-Bold", 16)
        if job:
            c.drawString(tx, ty, f"JOB #  {job}")
        if pour:
            c.setFont("Helvetica-Bold", 12)
            c.drawRightString(x + tag_w - inner, ty, f"POUR #  {pour}")
        ty -= 0.28 * inch
        beams = [clean_text(row.get(f"beam_{i}")) for i in range(1, BEAMS_PER_LABEL + 1)]
        beams = [b for b in beams if b]
        c.setFont("Helvetica-Bold", 9)
        c.drawString(tx, ty, "BEAMS")
        ty -= 0.2 * inch
        c.setFont("Helvetica-Bold", 13)
        if beams:
            mid = max(1, math.ceil(len(beams) / 2.0))
            line1 = "   ".join(beams[:mid])
            line2 = "   ".join(beams[mid:])
            c.drawString(tx, ty, line1[:42])
            if line2:
                ty -= 0.2 * inch
                c.drawString(tx, ty, line2[:42])
        ty -= 0.26 * inch
        c.setLineWidth(0.6)
        c.line(tx, ty + 0.08 * inch, x + tag_w - inner, ty + 0.08 * inch)
        c.setFont("Helvetica", 9)
        qc = clean_text(row.get("qc_tech"))
        date = clean_text(row.get("date"))
        left = []
        if qc:
            left.append(f"QC  {qc}")
        if date:
            left.append(date)
        c.drawString(tx, ty - 0.08 * inch, "   |   ".join(left)[:48])
        caption = clean_text(row.get("part_caption"))
        if caption:
            c.setFont("Helvetica-Bold", 8)
            c.drawRightString(x + tag_w - inner, ty - 0.08 * inch, caption)
        copy = row.get("cylinder_copy")
        copies = row.get("copies_total")
        if copies and int(copies) > 1 and copy:
            c.setFont("Helvetica", 8)
            c.drawString(tx, y + inner, f"CYL {int(copy)} OF {int(copies)}")

    if not print_rows:
        c.setFont("Helvetica", 12)
        c.drawString(margin_x, page_h / 2, "No cylinder tags ready to print.")
        c.showPage()
    else:
        per_page = cols * rows_n
        for index, row in enumerate(print_rows):
            pos = index % per_page
            if pos == 0 and index > 0:
                c.showPage()
            col = pos % cols
            row_i = pos // cols
            x = margin_x + col * (tag_w + gap_x)
            y = page_h - margin_y - (row_i + 1) * tag_h - row_i * gap_y
            draw_tag(x, y, row)
        c.showPage()
    c.save()
    return buf.getvalue()
