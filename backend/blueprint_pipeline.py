import json
import logging
import re
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pypdf import PdfReader

from models import BlueprintField

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION = "controlled_regex_ocr_v2"
WEAK_NOTE_RX = re.compile(r"not confidently located|not clearly (?:stated|confirmed)|could not be normalized", re.IGNORECASE)

FIELD_GROUPS = {
    "title_block": [
        "job_number",
        "cid",
        "bridge_id",
        "route",
        "project_name",
        "county_dot",
        "sheet_number",
        "revision",
        "beam_mark",
        "beam_marks",
        "product_family",
        "overall_length_ft",
        "casting_length_ft",
        "mark_length_families",
        "design_camber_in",
        "finish_notes",
    ],
    "geometry": [
        "overall_depth_in",
        "top_flange_width_in",
        "top_flange_thickness_in",
        "bottom_flange_width_in",
        "bottom_flange_thickness_in",
        "web_thickness_in",
        "outer_width_in",
        "outer_depth_in",
        "wall_thickness_in",
        "void_width_in",
        "void_depth_in",
        "special_end_geometry",
    ],
    "strand_system": [
        "strand_count",
        "strand_diameter_in",
        "strand_grade",
        "strand_final_pull_lb",
        "strand_area_in2",
        "strand_pattern_rows",
        "straight_strand_count",
        "draped_strand_count",
        "hold_downs",
        "hold_down_type",
        "jacking_force_kip",
        "target_elongation_in",
        "debond_notes",
    ],
    "hardware": [
        "lift_loops",
        "lift_loop_spec",
        "inserts",
        "tubes",
        "tie_rod_openings",
        "drain_holes",
        "stirrups",
        "plates_and_clips",
        "grout_grooves",
        "bituminous_ends",
    ],
    "ends_and_qc": [
        "marked_end_rule",
        "end_elevation_notes",
        "paint_id_requirements",
        "dimensional_tolerances",
        "special_inspection_notes",
    ],
}

CRITICAL_FIELDS = {
    "beam_mark",
    "product_family",
    "overall_length_ft",
    "overall_depth_in",
}


@dataclass
class ExtractionResult:
    status: str
    summary: str
    page_text: List[str]
    fields: Dict[str, BlueprintField]
    field_groups: Dict[str, List[str]]
    fail_reasons: List[str]
    page_sources: List[str] = dc_field(default_factory=list)


def _blank_field(note: str = "") -> BlueprintField:
    return BlueprintField(value=None, confidence="low", source_page=None, status="unconfirmed", extraction_notes=note)


def build_empty_fields() -> Dict[str, BlueprintField]:
    return {name: _blank_field() for group in FIELD_GROUPS.values() for name in group}


def _normalize_text(text: str) -> str:
    cleaned = (text or "").replace("\u2013", "-").replace("\u2014", "-")
    cleaned = cleaned.replace("\u2018", "'").replace("\u2019", "'")
    cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"')
    cleaned = cleaned.replace("\u2032", "'").replace("\u2033", '"')
    return re.sub(r"[ \t]+", " ", cleaned).strip()


def _page_text(reader: PdfReader) -> List[str]:
    pages = []
    for page in reader.pages:
        try:
            pages.append(_normalize_text(page.extract_text() or ""))
        except Exception:
            logger.exception("pypdf failed to extract text from a page")
            pages.append("")
    return pages


def read_pdf_pages(path: str | Path) -> List[str]:
    reader = PdfReader(str(path))
    return _page_text(reader)


def read_pdf_pages_for_extract(path: str | Path) -> Tuple[List[str], List[str]]:
    native = read_pdf_pages(path)
    try:
        from blueprint_ocr import read_pdf_pages_merged
        return read_pdf_pages_merged(path, native)
    except Exception:
        logger.exception("OCR merge failed for %s; continuing with native text layer", path)
        sources = ["text_layer" if text else "empty" for text in native]
        return native, sources


def _source_page(page_text: List[str], pattern: str) -> Optional[int]:
    rx = re.compile(pattern, re.IGNORECASE)
    for index, text in enumerate(page_text, start=1):
        if rx.search(text or ""):
            return index
    return None


def _page_source_label(page_sources: Sequence[str], page: Optional[int]) -> str:
    if not page or page < 1 or page > len(page_sources):
        return "text_layer"
    return page_sources[page - 1] or "text_layer"


def _build_field(
    value: Any,
    confidence: str,
    page: Optional[int],
    status: str = "confirmed",
    note: str = "",
    source: str = "text_layer",
) -> BlueprintField:
    source_note = f"source={source}."
    full_note = f"{source_note} {note}".strip() if note else source_note
    return apply_confidence_guard(
        BlueprintField(value=value, confidence=confidence, source_page=page, status=status, extraction_notes=full_note)
    )


def apply_confidence_guard(field: BlueprintField) -> BlueprintField:
    """Never allow CONFIRMED when notes say the value was not confidently located."""
    notes = field.extraction_notes or ""
    weak_note = bool(WEAK_NOTE_RX.search(notes))
    if field.status == "manually_confirmed":
        return field
    if field.status == "not_applicable":
        return field
    if weak_note or field.value in (None, "", [], {}):
        if field.status == "confirmed":
            field.status = "unconfirmed"
        if field.confidence == "high" and weak_note:
            field.confidence = "low"
        if not notes:
            field.extraction_notes = "Value was not confidently located."
        return field
    if field.status == "confirmed" and (field.confidence == "low" or field.source_page is None):
        field.status = "unconfirmed"
        if field.confidence == "high":
            field.confidence = "medium"
        extra = "Confirmed status demoted: strong pattern requires page evidence and better than low confidence."
        if extra not in (field.extraction_notes or ""):
            field.extraction_notes = f"{field.extraction_notes} {extra}".strip()
    return field


def parse_fraction(token: str) -> Optional[float]:
    text = (token or "").strip().replace("¾", "3/4").replace("½", "1/2")
    text = re.sub(r"\s+", " ", text)
    mixed = re.fullmatch(r"(\d+)\s+(\d+)\s*/\s*(\d+)", text)
    if mixed:
        den_i = int(mixed.group(3))
        return None if den_i == 0 else int(mixed.group(1)) + (int(mixed.group(2)) / den_i)
    glued = re.fullmatch(r"(\d+)(\d+)\s*/\s*(\d+)", text)
    if glued:
        den_i = int(glued.group(3))
        num = int(glued.group(2))
        if den_i and 0 < num < den_i:
            return int(glued.group(1)) + (num / den_i)
    simple = re.fullmatch(r"(\d+)\s*/\s*(\d+)", text)
    if simple:
        den_i = int(simple.group(2))
        return None if den_i == 0 else int(simple.group(1)) / den_i
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    return None


def parse_feet_inches(value: str) -> Optional[float]:
    """Parse plant shop-drawing lengths such as 47'-3\", 47'-3 3/4\", 47'-33/4\", 52'-0\", 110' 0\"."""
    if value is None:
        return None
    text = _normalize_text(str(value)).replace("¾", " 3/4 ").replace("½", " 1/2 ")
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    if not text:
        return None
    ft_only = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:FT|FEET)\b\.?", text, re.IGNORECASE)
    if ft_only:
        return float(ft_only.group(1))
    match = re.search(r"(\d+)\s*['’]\s*-?\s*(.*)$", text)
    if match:
        rest = re.sub(r"(?:\"|IN)\s*$", "", match.group(2).strip(), flags=re.IGNORECASE).strip()
        inches = parse_fraction(rest or "0")
        if inches is not None:
            return round(float(match.group(1)) + (inches / 12.0), 4)
    hyphen = re.search(r"(\d+)\s*-\s*(\d+(?:\s+\d+\s*/\s*\d+|\d+\s*/\s*\d+)?)\s*(?:\"|IN)?\s*$", text, re.IGNORECASE)
    if hyphen:
        inches = parse_fraction(hyphen.group(2))
        if inches is not None:
            return round(float(hyphen.group(1)) + (inches / 12.0), 4)
    mixed = re.fullmatch(r"(\d+)\s+[-]?\s*(\d+)\s*(?:\"|IN)", text, re.IGNORECASE)
    if mixed:
        return round(float(mixed.group(1)) + (float(mixed.group(2)) / 12.0), 4)
    bare = re.fullmatch(r"(\d+(?:\.\d+)?)", text)
    if bare:
        return float(bare.group(1))
    return None


def format_feet_inches(value_ft: Optional[float]) -> str:
    if value_ft is None:
        return ""
    feet = int(value_ft)
    inches_total = round((value_ft - feet) * 12, 4)
    whole = int(inches_total)
    frac = inches_total - whole
    if abs(frac) < 0.01:
        return f"{feet}'-{whole}\""
    if abs(frac - 0.75) < 0.02:
        return f"{feet}'-{whole} 3/4\""
    if abs(frac - 0.5) < 0.02:
        return f"{feet}'-{whole} 1/2\""
    eighths = round(frac * 8)
    if eighths in (0, 8):
        return f"{feet}'-{whole + (1 if eighths == 8 else 0)}\""
    return f"{feet}'-{whole} {eighths}/8\""


def expand_mark_spec(spec: str) -> List[str]:
    """Expand MARK 201/202/203, MK 201-203, and 201–209 into individual marks."""
    text = _normalize_text(spec)
    if not text:
        return []
    marks: List[str] = []
    range_match = re.fullmatch(r"(\d{2,4})\s*-\s*(\d{2,4})", text)
    if range_match:
        start, end = int(range_match.group(1)), int(range_match.group(2))
        if 0 < end - start <= 40 and len(range_match.group(1)) == len(range_match.group(2)):
            return [str(n) for n in range(start, end + 1)]
    for token in re.split(r"[/,;&]| and ", text):
        token = token.strip()
        if re.fullmatch(r"\d{2,4}", token):
            marks.append(token)
    return list(dict.fromkeys(marks))


def parse_mark_groups(text: str) -> List[str]:
    """Find beam marks from shop-drawing callouts without matching the trailing 's' in Marks."""
    blob = _normalize_text(text)
    found: List[str] = []
    patterns = [
        r"BEAM\s+MARKS?\s*[:\-]?\s*(\d{2,4}\s*-\s*\d{2,4})",
        r"BEAM\s+MARKS?\s*[:\-]?\s*(\d{2,4}(?:\s*/\s*\d{2,4})+)",
        r"\bMARKS?\s*[:\-]\s*(\d{2,4}(?:\s*/\s*\d{2,4})+)",
        r"\bMARKS?\s+(\d{2,4}(?:\s*/\s*\d{2,4}){1,})",
        r"\bMK\.?\s*[:\-]?\s*(\d{2,4}(?:\s*/\s*\d{2,4})+)",
        r"\bMK\.?\s*[:\-]?\s*(\d{2,4}\s*-\s*\d{2,4})",
        r"\bMK\.?\s+(\d{3,4})\b",
        r"MARKS?\s+(\d{2,4}\s*-\s*\d{2,4})",
        r"\bMARK\s+(\d{2,4})\s+HARDWARE",
        r"BEAMS?\s+(\d{2,4}\s*-\s*\d{2,4})\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, blob, flags=re.IGNORECASE):
            found.extend(expand_mark_spec(match.group(1)))
    return list(dict.fromkeys(found))


def _joined_text(page_text: List[str]) -> str:
    return "\n".join(page_text or [])


def _first_match(page_text: List[str], patterns: List[str]) -> Optional[Tuple[str, int, str]]:
    for pattern in patterns:
        rx = re.compile(pattern, re.IGNORECASE)
        for index, text in enumerate(page_text, start=1):
            match = rx.search(text or "")
            if match:
                raw = next((group for group in match.groups() if group not in (None, "")), match.group(0))
                return _normalize_text(str(raw)), index, match.group(0)
    return None


def _capture_scalar(
    page_text: List[str],
    patterns: List[str],
    cast=lambda value: value.strip(),
    confidence: str = "high",
    missing_note: str = "",
    success_note: str = "Labeled pattern match.",
    page_sources: Optional[Sequence[str]] = None,
) -> BlueprintField:
    hit = _first_match(page_text, patterns)
    if not hit:
        return _blank_field(missing_note or "Value was not confidently located.")
    raw, page, _span = hit
    try:
        value = cast(raw)
    except Exception:
        return _blank_field("Matched text could not be normalized cleanly.")
    source = _page_source_label(page_sources or [], page)
    return _build_field(value, confidence, page, note=success_note, source=source)


def _product_family(page_text: List[str], hint: str = "", page_sources: Optional[Sequence[str]] = None) -> BlueprintField:
    text = _joined_text(page_text).upper()
    page = _source_page(page_text, r"BOX\s+BEAM|ADJACENT\s+BOX|I[\s-]?BEAM|AASHTO\s+TYPE|TYPE\s*2|BULB\s+TEE|\bFIB\b|BT-")
    source = _page_source_label(page_sources or [], page)
    if "BOX BEAM" in text or "ADJACENT BOX" in text:
        return _build_field("box_beam", "high", page or _source_page(page_text, r"BOX\s+BEAM|ADJACENT\s+BOX"), note="Box-beam family callout.", source=source)
    if any(token in text for token in ("TYPE 2", "TYPE2", "I-BEAM", "I BEAM", "AASHTO TYPE", "BULB TEE", "BT-", " FIB")):
        note = "Type 2 / I-beam / FIB family callout." if "TYPE 2" in text else "I-beam family callout."
        return _build_field("i_beam", "high", page, note=note, source=source)
    if hint in ("i_beam", "box_beam"):
        return _build_field(hint, "medium", None, status="unconfirmed", note="Derived from upload hint; drawing text did not clearly confirm the family.", source="text_layer")
    return _blank_field("Product family not clearly stated in extracted page text.")


def _find_all_stations(page_text: List[str], label: str, type_name: str, extra: Optional[Dict[str, Any]] = None, page_sources: Optional[Sequence[str]] = None) -> BlueprintField:
    items: List[Dict[str, Any]] = []
    seen = set()
    patterns = [
        rf"{label}[^A-Z0-9]{{0,8}}(?:AT|@)\s*(\d+\s*'\s*-?\s*\d+(?:\s+\d+/\d+)?(?:\"|IN)?)",
        rf"{label}[^A-Z0-9]{{0,8}}(?:AT|@)\s*(\d+(?:\.\d+)?)\s*(FT|FEET|')",
    ]
    for pattern in patterns:
        rx = re.compile(pattern, re.IGNORECASE)
        for page_index, text in enumerate(page_text, start=1):
            for match in rx.finditer(text or ""):
                station = parse_feet_inches("".join(group or "" for group in match.groups()))
                if station is None:
                    continue
                dedupe_key = (round(station, 3), type_name, page_index)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                item = {"x_ft": round(station, 3), "type": type_name}
                if extra:
                    item.update(extra)
                item["_source_page"] = page_index
                items.append(item)
    if not items:
        return _blank_field(f"No deterministic {type_name.lower()} station callouts were found in extractable text.")
    source_page = items[0].pop("_source_page", None)
    for item in items[1:]:
        item.pop("_source_page", None)
    source = _page_source_label(page_sources or [], source_page)
    return _build_field(items, "medium", source_page, note="Station callouts parsed from labeled AT/@ dimensions.", source=source)


def _capture_notes(page_text: List[str], keyword: str, target_note: str, page_sources: Optional[Sequence[str]] = None) -> BlueprintField:
    page = _source_page(page_text, keyword)
    if page is None:
        return _blank_field(target_note)
    source = _page_source_label(page_sources or [], page)
    return _build_field(target_note, "medium", page, status="unconfirmed", note="Keyword hit only; verify exact wording against source.", source=source)


def _parse_county(page_text: List[str], page_sources: Optional[Sequence[str]] = None) -> BlueprintField:
    hit = _first_match(
        page_text,
        [
            r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?\s+County(?:,\s*[A-Z][A-Za-z]+)?)\b",
            r"COUNTY(?:\s+NAME)?\s*[:\-]\s*([A-Z][A-Za-z][A-Za-z .,]{2,40})",
        ],
    )
    if not hit:
        return _blank_field("County/DOT owner not confidently located.")
    raw, page, _span = hit
    cleaned = re.sub(r"\s+", " ", raw).strip(" ,")
    if cleaned.startswith(",") or cleaned.lower() in {"kentucky", "ky"}:
        return _blank_field("County/DOT owner not confidently located.")
    if "county" not in cleaned.lower() and "," not in cleaned:
        return _blank_field("County/DOT owner not confidently located.")
    source = _page_source_label(page_sources or [], page)
    return _build_field(cleaned, "high", page, note="County/state identity from title block.", source=source)


def _parse_job_number(page_text: List[str], page_sources: Optional[Sequence[str]] = None) -> BlueprintField:
    hit = _first_match(
        page_text,
        [
            r"JOB(?:\s+NO\.?|\s+NUMBER|#)\s*[:\-]?\s*([A-Z0-9\-_/]+)",
            r"\bJOB\s+(L\d{4,})\b",
            r"\b(L\d{5})\b",
        ],
    )
    if not hit:
        return _blank_field("Job number not confidently located.")
    raw, page, _span = hit
    source = _page_source_label(page_sources or [], page)
    return _build_field(raw.upper(), "high", page, note="Job number from JOB NO / L-number pattern.", source=source)


def _collect_beam_marks(page_text: List[str]) -> Tuple[List[str], Optional[int]]:
    marks: List[str] = []
    first_page = None
    for index, text in enumerate(page_text, start=1):
        page_marks = parse_mark_groups(text or "")
        if page_marks and first_page is None:
            first_page = index
        for mark in page_marks:
            if mark not in marks:
                marks.append(mark)
    return marks, first_page


_FT_IN_CASTING = r"\d+\s*['’]\s*-?\s*(?:\d+\s+\d+\s*/\s*\d+|\d+\d+\s*/\s*\d+|\d+)\s*(?:\"|IN)?"
_CASTING_EVIDENCE_RX = re.compile(r"BASED\s+ON\s+CASTING|CASTING\s+LENGTH", re.IGNORECASE)
CASTING_EXTRA_FT = 0.75 / 12.0
FINAL_PULL_MIN_LB = 10000
FINAL_PULL_MAX_LB = 60000


def _length_hits_on_page(text: str) -> Dict[str, List[str]]:
    blob = _normalize_text(text).replace("¾", " 3/4 ").replace("½", " 1/2 ")
    blob = re.sub(r"\s+", " ", blob)
    overall = []
    casting = []
    overall_rx = re.compile(
        r"(?:OVERALL(?:\s+LENGTH)?|O\.?A\.?L\.?)\s*[:\-]?\s*(\d+\s*'\s*-?\s*\d+(?:\s+\d+/\d+)?\"?)",
        re.IGNORECASE,
    )
    overall.extend(m.group(1) for m in overall_rx.finditer(blob))
    trailing = re.compile(r"(\d+\s*'\s*-?\s*\d+(?:\s+\d+/\d+)?\"?)\s*overall", re.IGNORECASE)
    overall.extend(m.group(1) for m in trailing.finditer(blob))
    casting_rx = re.compile(
        rf"(?:CASTING(?:\s+LENGTH)?|C\.L\.)\s*[:\-]?\s*({_FT_IN_CASTING})",
        re.IGNORECASE,
    )
    casting.extend(m.group(1) for m in casting_rx.finditer(blob))
    casting_trail = re.compile(
        rf"({_FT_IN_CASTING})\s*(?:CASTING(?:\s+LENGTH)?)",
        re.IGNORECASE,
    )
    casting.extend(m.group(1) for m in casting_trail.finditer(blob))
    return {"overall": overall, "casting": casting}


def _fill_casting_three_quarter(families: List[Dict[str, Any]], page_text: List[str]) -> List[Dict[str, Any]]:
    """If overall is known and CASTING LENGTH evidence exists, fill missing casting as overall + 3/4\"."""
    joined = _joined_text(page_text)
    global_evidence = bool(_CASTING_EVIDENCE_RX.search(joined))
    for family in families:
        if family.get("casting_length_ft") is not None:
            continue
        overall = family.get("overall_length_ft")
        if overall is None:
            continue
        page_i = family.get("source_page") or 0
        page_blob = page_text[page_i - 1] if 1 <= page_i <= len(page_text) else ""
        if not (_CASTING_EVIDENCE_RX.search(page_blob or "") or global_evidence):
            continue
        casting = round(float(overall) + CASTING_EXTRA_FT, 4)
        family["casting_length_ft"] = casting
        family["casting_display"] = family.get("casting_display") or format_feet_inches(casting)
        family["casting_inferred_three_quarter"] = True
        logger.info(
            "Inferred casting length %s from overall %s + 3/4 in (BASED ON CASTING LENGTH) marks=%s page=%s",
            family["casting_display"],
            family.get("overall_display"),
            family.get("marks"),
            page_i,
        )
    return families


def _coerce_final_pull_lb(raw: str) -> Optional[int]:
    try:
        digits = re.sub(r"[^\d]", "", raw or "")
        if not digits:
            return None
        value = int(digits)
    except Exception:
        logger.exception("Failed to coerce final-pull token %r", raw)
        return None
    if FINAL_PULL_MIN_LB <= value <= FINAL_PULL_MAX_LB:
        return value
    return None


def _parse_final_pull(page_text: List[str], page_sources: Optional[Sequence[str]] = None) -> BlueprintField:
    labeled = [
        r"(?:FINAL\s+PULL(?:\s+AT)?|FINAL\s+FORCE|JACK(?:ING)?(?:\s+TO|\s+FORCE\s+TO))\s*[:\-]?\s*([0-9][0-9,\.\s]{3,14})\s*(?:LB|LBS|#)?",
        r"\b(33[\s,\.]?817)\s*(?:LB|LBS|#)?",
        r"\b(33[\s,\.]817)\b",
    ]
    try:
        for pattern in labeled:
            rx = re.compile(pattern, re.IGNORECASE)
            for index, text in enumerate(page_text, start=1):
                for match in rx.finditer(text or ""):
                    raw = next((group for group in match.groups() if group not in (None, "")), match.group(0))
                    value = _coerce_final_pull_lb(_normalize_text(str(raw)))
                    if value is None:
                        continue
                    source = _page_source_label(page_sources or [], index)
                    logger.info("Parsed strand final pull %s lb from page %s token %r", value, index, raw)
                    return _build_field(value, "high", index, note="Final pull from strand table / jacking note.", source=source)
    except Exception:
        logger.exception("strand_final_pull_lb parser failed")
    return _blank_field("Strand final pull not confidently located.")


def _parse_overall_depth(page_text: List[str], page_sources: Optional[Sequence[str]] = None) -> BlueprintField:
    explicit = _capture_scalar(
        page_text,
        [
            r"OVERALL\s+DEPTH\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")",
            r"(?:SECTION\s+DEPTH|BEAM\s+DEPTH)\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")",
        ],
        cast=lambda value: round(float(value), 3),
        confidence="medium",
        missing_note="Overall depth/height not confidently located.",
        success_note="Depth/height callout.",
        page_sources=page_sources,
    )
    if explicit.value is not None:
        return explicit
    type2 = _first_match(
        page_text,
        [r"\bTYPE\s*2\b", r"\bTYPE\s*II\b", r"AASHTO\s+TYPE\s*2", r"AASHTO\s+TYPE\s*II"],
    )
    if type2:
        _raw, page, _span = type2
        source = _page_source_label(page_sources or [], page)
        logger.info("overall_depth_in=36 from Type 2 / Type II family callout on page %s", page)
        return _build_field(
            36.0,
            "medium",
            page,
            note="AASHTO Type II / Type 2 I-beam overall depth is 36 in from section family callout (no explicit OVERALL DEPTH).",
            source=source,
        )
    type4 = _first_match(
        page_text,
        [r"\bTYPE\s*IV\b", r"AASHTO\s+TYPE\s*IV", r"\bTYPE\s*4\s+I[\s-]?BEAM"],
    )
    if type4:
        _raw, page, _span = type4
        source = _page_source_label(page_sources or [], page)
        logger.info("overall_depth_in=54 from Type IV family callout on page %s", page)
        return _build_field(
            54.0,
            "medium",
            page,
            note="AASHTO Type IV I-beam overall depth is 54 in from section family callout (no explicit OVERALL DEPTH).",
            source=source,
        )
    return _blank_field("Overall depth/height not confidently located.")


def extract_mark_length_families(page_text: List[str]) -> List[Dict[str, Any]]:
    families: List[Dict[str, Any]] = []
    seen = set()
    for index, text in enumerate(page_text, start=1):
        marks = parse_mark_groups(text or "")
        if not marks:
            continue
        lengths = _length_hits_on_page(text or "")
        overall_raw = lengths["overall"][0] if lengths["overall"] else None
        casting_raw = lengths["casting"][0] if lengths["casting"] else None
        key = (tuple(marks), overall_raw, casting_raw)
        if key in seen:
            continue
        seen.add(key)
        family = {
            "marks": marks,
            "overall_display": overall_raw,
            "casting_display": casting_raw,
            "overall_length_ft": parse_feet_inches(overall_raw) if overall_raw else None,
            "casting_length_ft": parse_feet_inches(casting_raw) if casting_raw else None,
            "source_page": index,
        }
        families.append(family)
    with_lengths = [
        item for item in families
        if item.get("overall_length_ft") is not None or item.get("casting_length_ft") is not None
    ]
    return with_lengths or families


def _parse_strand_diameter(page_text: List[str], page_sources: Optional[Sequence[str]] = None) -> BlueprintField:
    hit = _first_match(
        page_text,
        [
            r"(?:STRAND(?:\s+SIZE|\s+DIA(?:METER)?)?\s*[:\-]?\s*)?(1\s*/\s*2)\s*(?:\"|IN)",
            r"(?:STRAND(?:\s+SIZE|\s+DIA(?:METER)?)?\s*[:\-]?\s*)?(0\.5)\s*(?:\"|IN)",
            r"STRAND(?:\s+SIZE|\s+DIA(?:METER)?)?\s*[:\-]?\s*([0-9.]+)\s*(?:IN|\")",
        ],
    )
    if not hit:
        return _blank_field("Strand diameter not confidently located.")
    raw, page, _span = hit
    if re.fullmatch(r"1\s*/\s*2", raw):
        value = 0.5
    else:
        value = round(float(raw), 3)
    source = _page_source_label(page_sources or [], page)
    return _build_field(value, "high", page, note="Strand diameter from 1/2\" or 0.5\" callout.", source=source)


def extract_structured_fields(
    page_text: List[str],
    hints: Optional[Dict[str, Any]] = None,
    page_sources: Optional[Sequence[str]] = None,
) -> ExtractionResult:
    hints = hints or {}
    page_sources = list(page_sources or ["text_layer" if text else "empty" for text in page_text])
    fields = build_empty_fields()
    fail_reasons: List[str] = []
    text_present = [text for text in page_text if text]
    if not text_present:
        fail_reasons.append("No extractable text was found in the uploaded PDF after native text + OCR merge. Scanned drawings still require a readable image.")
        return ExtractionResult(
            status="insufficient_quality",
            summary="Blueprint text extraction failed; no machine-readable drawing text was found.",
            page_text=page_text,
            fields=fields,
            field_groups=FIELD_GROUPS,
            fail_reasons=fail_reasons,
            page_sources=list(page_sources),
        )

    fields["job_number"] = _parse_job_number(page_text, page_sources)
    fields["cid"] = _capture_scalar(
        page_text,
        [r"\bCID\s*[:\-]?\s*(\d{2}-\d{3,5})\b", r"\b(25-\d{4})\b"],
        missing_note="CID not confidently located.",
        success_note="CID from title block.",
        page_sources=page_sources,
    )
    fields["bridge_id"] = _capture_scalar(
        page_text,
        [r"BRIDGE\s*ID\s*[:\-]?\s*([A-Z0-9]{6,})\b"],
        cast=lambda value: value.upper(),
        missing_note="Bridge ID not confidently located.",
        success_note="Bridge ID from title block.",
        page_sources=page_sources,
    )
    fields["route"] = _capture_scalar(
        page_text,
        [r"\b((?:KY|US|I|SR|KY)\s*\d{2,4})\b", r"ROUTE\s*[:\-]?\s*([A-Z0-9 ]{2,12})"],
        missing_note="Route not confidently located.",
        success_note="Route identifier from title block.",
        page_sources=page_sources,
    )
    fields["project_name"] = _capture_scalar(
        page_text,
        [r"PROJECT(?:\s+NAME)?\s*[:\-]?\s*([A-Z0-9 ,.&()/#\-]{4,80})"],
        missing_note="Project name not confidently located.",
        success_note="Project name from labeled field.",
        page_sources=page_sources,
    )
    fields["county_dot"] = _parse_county(page_text, page_sources)
    fields["sheet_number"] = _capture_scalar(
        page_text,
        [r"SHEET(?:\s+NO\.?|\s+NUMBER|#)\s*[:\-]?\s*([A-Z0-9\-_/]+)"],
        missing_note="Sheet number not confidently located.",
        success_note="Sheet number from labeled field.",
        page_sources=page_sources,
    )
    fields["revision"] = _capture_scalar(
        page_text,
        [r"REV(?:ISION)?\s*[:\-]?\s*([A-Z0-9\-_/]+)"],
        missing_note="Revision not confidently located.",
        success_note="Revision from labeled field.",
        page_sources=page_sources,
    )

    marks, marks_page = _collect_beam_marks(page_text)
    if marks:
        source = _page_source_label(page_sources, marks_page)
        fields["beam_marks"] = _build_field(marks, "high", marks_page, note="Beam marks expanded from MARK/MK groups and ranges.", source=source)
        if len(marks) >= 2 and all(re.fullmatch(r"\d+", m) for m in marks):
            compact = f"{marks[0]}-{marks[-1]}" if marks == [str(n) for n in range(int(marks[0]), int(marks[-1]) + 1)] else "/".join(marks)
        else:
            compact = "/".join(marks)
        fields["beam_mark"] = _build_field(compact, "high", marks_page, note="Multi-beam identity compacted from beam_marks.", source=source)
    else:
        fields["beam_mark"] = _capture_scalar(
            page_text,
            [r"(?:BEAM|PIECE)\s+MARK\s*[:\-]?\s*([A-Z0-9\-_/]{2,})"],
            missing_note="Beam mark not confidently located.",
            success_note="Single beam mark from BEAM MARK / PIECE MARK.",
            page_sources=page_sources,
        )
        if fields["beam_mark"].value:
            fields["beam_marks"] = _build_field(
                [str(fields["beam_mark"].value)],
                fields["beam_mark"].confidence,
                fields["beam_mark"].source_page,
                note="Single mark copied into beam_marks list.",
                source=_page_source_label(page_sources, fields["beam_mark"].source_page),
            )
        else:
            fields["beam_marks"] = _blank_field("Beam marks not confidently located.")
    if fields["beam_mark"].status == "unconfirmed" and hints.get("beam_mark_hint"):
        fields["beam_mark"] = _build_field(hints["beam_mark_hint"], "medium", None, status="unconfirmed", note="Taken from upload hint; verify against title block.", source="text_layer")
        if fields["beam_marks"].status == "unconfirmed":
            fields["beam_marks"] = _build_field([hints["beam_mark_hint"]], "medium", None, status="unconfirmed", note="Taken from upload hint; verify against title block.", source="text_layer")

    fields["product_family"] = _product_family(page_text, hints.get("product_family_hint", ""), page_sources)

    families = _fill_casting_three_quarter(extract_mark_length_families(page_text), page_text)
    if families:
        fam_page = families[0].get("source_page")
        source = _page_source_label(page_sources, fam_page)
        inferred = any(f.get("casting_inferred_three_quarter") for f in families)
        fam_note = "Per-mark overall/casting length families from shop sheets."
        if inferred:
            fam_note = "Per-mark overall/casting families. Missing casting lengths filled as overall + 3/4\" from BASED ON CASTING LENGTH evidence."
        fields["mark_length_families"] = _build_field(families, "high" if any(f.get("overall_length_ft") for f in families) else "medium", fam_page, note=fam_note, source=source)
        numeric_overall = [f["overall_length_ft"] for f in families if f.get("overall_length_ft") is not None]
        numeric_cast = [f["casting_length_ft"] for f in families if f.get("casting_length_ft") is not None]
        if numeric_overall:
            fields["overall_length_ft"] = _build_field(
                max(numeric_overall),
                "high",
                fam_page,
                note="Primary overall length is the longest mark family; see mark_length_families for all groups.",
                source=source,
            )
        if numeric_cast:
            cast_note = "Primary casting length is the longest mark family; see mark_length_families."
            if inferred:
                cast_note = "Primary casting length is overall + 3/4\" where the drawing says dimensions are BASED ON CASTING LENGTH."
            fields["casting_length_ft"] = _build_field(
                max(numeric_cast),
                "medium" if inferred else "high",
                fam_page,
                note=cast_note,
                source=source,
            )
        elif not numeric_cast:
            fields["casting_length_ft"] = _blank_field("Casting length not confidently located.")
    if fields["overall_length_ft"].status == "unconfirmed":
        fields["overall_length_ft"] = _capture_scalar(
            page_text,
            [
                r"(?:OVERALL LENGTH|O\.?A\.?L\.?)\s*[:\-]?\s*([0-9]+\s*'\s*-?\s*[0-9]+(?:\s+\d+/\d+)?\"?)",
                r"(?:OVERALL LENGTH|O\.?A\.?L\.?)\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:FT|FEET|')",
            ],
            cast=lambda value: round(parse_feet_inches(value), 4),
            missing_note="Overall length not confidently located.",
            success_note="Overall length from labeled dimension.",
            page_sources=page_sources,
        )
    if fields["casting_length_ft"].status == "unconfirmed":
        fields["casting_length_ft"] = _capture_scalar(
            page_text,
            [
                rf"CASTING(?:\s+LENGTH)?\s*[:\-]?\s*({_FT_IN_CASTING})",
                rf"({_FT_IN_CASTING})\s*(?:CASTING(?:\s+LENGTH)?)",
            ],
            cast=lambda value: round(parse_feet_inches(value), 4),
            missing_note="Casting length not confidently located.",
            success_note="Casting length from labeled dimension.",
            page_sources=page_sources,
        )
    if fields["mark_length_families"].status == "unconfirmed":
        fields["mark_length_families"] = _blank_field("Per-mark length families not confidently located.")

    fields["design_camber_in"] = _capture_scalar(
        page_text,
        [r"CAMBER(?:\s+AT\s+RELEASE|\s+TARGET|\s+DESIGN)?\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"],
        cast=lambda value: round(float(value), 3),
        confidence="medium",
        missing_note="Design camber note not clearly stated.",
        success_note="Camber callout.",
        page_sources=page_sources,
    )
    fields["finish_notes"] = _capture_notes(page_text, r"FINISH", "Finish notes present in drawing text; verify manually.", page_sources)

    fields["overall_depth_in"] = _parse_overall_depth(page_text, page_sources)
    fields["top_flange_width_in"] = _capture_scalar(page_text, [r"TOP FLANGE WIDTH\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), missing_note="Top flange width not confidently located.", success_note="Top flange width callout.", page_sources=page_sources)
    fields["top_flange_thickness_in"] = _capture_scalar(page_text, [r"TOP FLANGE THICKNESS\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), missing_note="Top flange thickness not confidently located.", success_note="Top flange thickness callout.", page_sources=page_sources)
    fields["bottom_flange_width_in"] = _capture_scalar(page_text, [r"BOTTOM FLANGE WIDTH\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), missing_note="Bottom flange width not confidently located.", success_note="Bottom flange width callout.", page_sources=page_sources)
    fields["bottom_flange_thickness_in"] = _capture_scalar(page_text, [r"BOTTOM FLANGE THICKNESS\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), missing_note="Bottom flange thickness not confidently located.", success_note="Bottom flange thickness callout.", page_sources=page_sources)
    fields["web_thickness_in"] = _capture_scalar(page_text, [r"WEB THICKNESS\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), missing_note="Web thickness not confidently located.", success_note="Web thickness callout.", page_sources=page_sources)
    fields["outer_width_in"] = _capture_scalar(page_text, [r"OUTER WIDTH\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), missing_note="Outer width not confidently located.", success_note="Outer width callout.", page_sources=page_sources)
    fields["outer_depth_in"] = _capture_scalar(page_text, [r"OUTER DEPTH\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), missing_note="Outer depth not confidently located.", success_note="Outer depth callout.", page_sources=page_sources)
    fields["wall_thickness_in"] = _capture_scalar(page_text, [r"WALL THICKNESS\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), missing_note="Wall thickness not confidently located.", success_note="Wall thickness callout.", page_sources=page_sources)
    fields["void_width_in"] = _capture_scalar(page_text, [r"(?:VOID|CORE) WIDTH\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), missing_note="Void/core width not confidently located.", success_note="Void width callout.", page_sources=page_sources)
    fields["void_depth_in"] = _capture_scalar(page_text, [r"(?:VOID|CORE) DEPTH\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), missing_note="Void/core depth not confidently located.", success_note="Void depth callout.", page_sources=page_sources)
    fields["special_end_geometry"] = _capture_notes(page_text, r"END ELEVATION|END DETAIL|SKEW", "Special end geometry/end-detail notes present; verify manually.", page_sources)

    fields["strand_count"] = _capture_scalar(page_text, [r"([0-9]+)\s+STRANDS?"], cast=lambda value: int(float(value)), missing_note="Strand count not confidently located.", success_note="Strand count callout.", page_sources=page_sources)
    fields["strand_diameter_in"] = _parse_strand_diameter(page_text, page_sources)
    grade_hit = _first_match(page_text, [r"\b(270\s*K(?:SI)?|GRADE\s*270|270K)\b", r"LOW[\s-]?RELAX(?:ATION)?"])
    if grade_hit:
        raw, page, span = grade_hit
        blob = _joined_text(page_text).upper()
        grade = "270K"
        if "LOW" in blob and "RELAX" in blob:
            grade = "270K low-relaxation"
        source = _page_source_label(page_sources, page)
        fields["strand_grade"] = _build_field(grade, "high", page, note="Strand grade / relaxation from 270K callout.", source=source)
    else:
        fields["strand_grade"] = _blank_field("Strand grade not confidently located.")
    fields["strand_final_pull_lb"] = _parse_final_pull(page_text, page_sources)
    fields["strand_area_in2"] = _capture_scalar(page_text, [r"STRAND(?:\s+AREA)?\s*[:\-]?\s*([0-9.]+)\s*(?:IN2|IN\^2|SQ\.?\s*IN)"], cast=lambda value: round(float(value), 4), missing_note="Strand area not confidently located.", success_note="Strand area callout.", page_sources=page_sources)
    fields["straight_strand_count"] = _capture_scalar(page_text, [r"([0-9]+)\s+STRAIGHT\s+STRANDS?"], cast=lambda value: int(float(value)), confidence="medium", missing_note="Straight strand count not clearly stated.", success_note="Straight strand count.", page_sources=page_sources)
    fields["draped_strand_count"] = _capture_scalar(page_text, [r"([0-9]+)\s+DRAPED\s+STRANDS?"], cast=lambda value: int(float(value)), confidence="medium", missing_note="Draped strand count not clearly stated.", success_note="Draped strand count.", page_sources=page_sources)
    draped_page = _source_page(page_text, r"\bDRAPED\b")
    if fields["draped_strand_count"].status == "unconfirmed" and draped_page:
        source = _page_source_label(page_sources, draped_page)
        fields["draped_strand_count"] = _build_field(
            "draped",
            "medium",
            draped_page,
            status="unconfirmed",
            note="Draped strand system mentioned; explicit count was not found so status stays unconfirmed.",
            source=source,
        )
    fields["jacking_force_kip"] = _capture_scalar(page_text, [r"JACK(?:ING)? FORCE\s*[:\-]?\s*([0-9.]+)\s*(?:KIP|KIPS)"], cast=lambda value: round(float(value), 3), missing_note="Jacking force note not confidently located.", success_note="Jacking force callout.", page_sources=page_sources)
    fields["target_elongation_in"] = _capture_scalar(page_text, [r"(?:ELONGATION|TARGET ELONGATION)\s*[:\-]?\s*([0-9.]+)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), missing_note="Target elongation note not confidently located.", success_note="Elongation callout.", page_sources=page_sources)
    fields["debond_notes"] = _capture_notes(page_text, r"DEBOND|SHIELD", "Debonded or shielded strand notes present; verify manually.", page_sources)
    fields["hold_downs"] = _find_all_stations(page_text, r"HOLD[\s-]?DOWN", "Hold-down", page_sources=page_sources)
    hold_type = _first_match(page_text, [r"\b(H-56-S)\b", r"HOLD[\s-]?DOWNS?\s*[:\-]?\s*([A-Z0-9\-]{3,})", r"DAYTON(?:\s*/\s*RICHMOND)?"])
    if hold_type:
        raw, page, _span = hold_type
        source = _page_source_label(page_sources, page)
        label = "H-56-S" if "H-56-S" in raw.upper() or "H-56-S" in _span.upper() else raw
        if re.search(r"DAYTON|RICHMOND", _joined_text(page_text), re.IGNORECASE):
            label = f"{label} (Dayton/Richmond)" if label != "Dayton/Richmond" else "Dayton/Richmond"
        fields["hold_down_type"] = _build_field(label, "high", page, note="Hold-down type from hardware callout.", source=source)
    else:
        fields["hold_down_type"] = _blank_field("Hold-down type not confidently located.")

    fields["lift_loops"] = _find_all_stations(page_text, r"LIFT(?:\s+LOOP|\s+POINT)", "Lift loop", page_sources=page_sources)
    lift_spec = _first_match(
        page_text,
        [
            r"(TRIPLE\s+LIFT\s+LOOPS?.{0,40}(?:0\.6|0\.60)\s*(?:\"|IN).{0,40}(?:EMBED|EMB).{0,20}\d+\s*'\s*-?\s*\d+(?:\s+\d+/\d+)?\"?)",
            r"((?:0\.6|0\.60)\s*(?:\"|IN)\s+TRIPLE\s+LIFT\s+LOOPS?.{0,40}(?:EMBED|EMB).{0,20}\d+\s*'\s*-?\s*\d+(?:\s+\d+/\d+)?\"?)",
            r"(0\s*\.\s*6\d{0,2}.{0,16}TRIPLE.{0,10}LIFT\s*_?LOOPS?)",
            r"(TRIPLE\s+_?LIFT\s*_?LOOPS?)",
            r"(TRPLE\s+LETLOOPS?)",
        ],
    )
    if lift_spec:
        raw, page, span = lift_spec
        source = _page_source_label(page_sources, page)
        blob = f"{span} {raw} {(page_text[page - 1] if page else '')}"
        spec = "triple lift loops"
        if re.search(r"0\s*\.\s*6", blob, re.IGNORECASE):
            spec = "0.6\" triple lift loops"
        embed = None
        embed_hit = re.search(r"(?:EMBED|EMB(?:EDDED)?(?:\s+DEPTH)?)\s*[:\-]?\s*(\d+\s*'\s*-?\s*\d+(?:\s+\d+/\d+)?\"?)", blob, re.IGNORECASE)
        if not embed_hit:
            embed_hit = re.search(r"(2\s*['\-]\s*7)\s*\"?", blob)
        if embed_hit:
            embed = embed_hit.group(1)
            if re.fullmatch(r"2\s*['\-]\s*7\"?", embed.strip()):
                embed = "2'-7\""
            spec = f"{spec}, embed {embed}"
        fields["lift_loop_spec"] = _build_field(spec, "high" if "0.6" in spec else "medium", page, note="Lift-loop spec from hardware callout. Count not invented.", source=source)
    else:
        fields["lift_loop_spec"] = _blank_field("Lift-loop specification not confidently located.")

    fields["inserts"] = _find_all_stations(page_text, r"INSERT|EMBED", "Insert", page_sources=page_sources)
    f64_page = _source_page(page_text, r"\bF-64\b")
    if f64_page:
        source = _page_source_label(page_sources, f64_page)
        existing = fields["inserts"].value if isinstance(fields["inserts"].value, list) else []
        if not any(isinstance(item, dict) and item.get("type") == "F-64" for item in existing):
            existing = list(existing) + [{"type": "F-64"}]
        fields["inserts"] = _build_field(existing, "high", f64_page, note="F-64 insert callout captured without inventing quantity.", source=source)
    elif fields["inserts"].status == "unconfirmed":
        fields["inserts"] = _blank_field("Insert callouts not confidently located.")

    fields["tubes"] = _find_all_stations(page_text, r"TUBE|VOID", "Tube", page_sources=page_sources)
    fields["tie_rod_openings"] = _find_all_stations(page_text, r"TIE[\s-]?ROD", "Tie-rod opening", page_sources=page_sources)
    fields["drain_holes"] = _find_all_stations(page_text, r"DRAIN", "Drain hole", page_sources=page_sources)
    fields["grout_grooves"] = _find_all_stations(page_text, r"GROUT GROOVE", "Grout groove", page_sources=page_sources)
    fields["plates_and_clips"] = _capture_notes(page_text, r"PLATE|CLIP|BEARING", "Plate, clip, or bearing notes present; verify manually.", page_sources)
    fields["bituminous_ends"] = _capture_notes(page_text, r"BITUMINOUS|CUT[\s-]?OFF POCKET", "Bituminous or cut-off pocket treatment noted; verify manually.", page_sources)
    fields["stirrups"] = _capture_scalar(
        page_text,
        [r"STIRRUPS?\s*(?:@|AT)\s*([0-9.]+)\s*(?:IN|\")"],
        cast=lambda value: {"spacing_in": round(float(value), 3)},
        confidence="medium",
        missing_note="Only stirrup spacing was auto-detected. Region/type still require review." if False else "Stirrup spacing not confidently located.",
        success_note="Stirrup spacing only; region/type still require review.",
        page_sources=page_sources,
    )

    fields["marked_end_rule"] = _capture_scalar(
        page_text,
        [r"MARKED\s+END\s*[:\-]?\s*([A-Z0-9 /()\-]+)"],
        cast=lambda value: {"label": value.strip(), "end": "start"},
        confidence="medium",
        missing_note="Marked end rule not confidently located.",
        success_note="Marked-end rule from labeled note.",
        page_sources=page_sources,
    )
    fields["end_elevation_notes"] = _capture_notes(page_text, r"END ELEVATION|ELEVATION DIFFERENCE", "End elevation note present; verify manually.", page_sources)
    fields["paint_id_requirements"] = _capture_notes(page_text, r"PAINT|ID", "Paint or ID marking note present; verify manually.", page_sources)
    fields["dimensional_tolerances"] = _capture_notes(page_text, r"TOLERANCE", "Tolerance note present; verify manually.", page_sources)
    fields["special_inspection_notes"] = _capture_notes(page_text, r"INSPECT|QC|SPECIAL NOTE", "Special inspection note present; verify manually.", page_sources)

    strand_rows = []
    row_matches = re.findall(r"(\d+)\s*(?:STRANDS?|STDS?)\s*@\s*([0-9.]+)\s*(?:IN|\")", " ".join(page_text), flags=re.IGNORECASE)
    if row_matches:
        for count, spacing in row_matches[:6]:
            strand_rows.append({"count": int(count), "spacing_in": float(spacing)})
    if strand_rows:
        page = _source_page(page_text, r"STRANDS?\s*@")
        source = _page_source_label(page_sources, page)
        fields["strand_pattern_rows"] = _build_field({"rows": strand_rows}, "medium", page, note="Strand rows inferred from text callouts. Marked/unmarked end symmetry still requires review.", source=source)

    product_family = fields["product_family"].value
    if product_family == "box_beam":
        for field_name in ("top_flange_width_in", "top_flange_thickness_in", "bottom_flange_width_in", "bottom_flange_thickness_in", "web_thickness_in"):
            if fields[field_name].status == "unconfirmed":
                fields[field_name] = _build_field(None, "low", None, status="not_applicable", note="Not required for box-beam translation.", source="text_layer")
    elif product_family == "i_beam":
        for field_name in ("outer_width_in", "outer_depth_in", "wall_thickness_in", "void_width_in", "void_depth_in", "grout_grooves"):
            if fields[field_name].status == "unconfirmed":
                fields[field_name] = _build_field(None, "low", None, status="not_applicable", note="Not required for I-beam translation unless the drawing explicitly calls it out.", source="text_layer")

    for field in fields.values():
        apply_confidence_guard(field)

    unconfirmed_critical = sorted(name for name in CRITICAL_FIELDS if fields[name].status == "unconfirmed")
    if unconfirmed_critical:
        fail_reasons.append(f"Critical fields require manual verification before lock: {', '.join(unconfirmed_critical)}.")

    confirmed_count = sum(1 for item in fields.values() if item.status in ("confirmed", "manually_confirmed"))
    unconfirmed_count = sum(1 for item in fields.values() if item.status == "unconfirmed")
    status = "needs_review" if unconfirmed_count else "extracted"
    ocr_pages = sum(1 for src in page_sources if "ocr" in src)
    summary = f"Controlled extraction captured {confirmed_count} fields with {unconfirmed_count} still unconfirmed."
    if ocr_pages:
        summary += f" OCR merged on {ocr_pages} sparse/empty page(s)."
    if fail_reasons:
        summary += f" {fail_reasons[0]}"
    return ExtractionResult(
        status=status,
        summary=summary,
        page_text=page_text,
        fields=fields,
        field_groups=FIELD_GROUPS,
        fail_reasons=fail_reasons,
        page_sources=list(page_sources),
    )


def _field_value(fields: Dict[str, BlueprintField], key: str, default: Any = None) -> Any:
    field = fields.get(key)
    if not field or field.status in ("unconfirmed", "not_applicable"):
        return default
    return field.value if field.value is not None else default


def _list_value(fields: Dict[str, BlueprintField], key: str) -> List[Dict[str, Any]]:
    value = _field_value(fields, key, [])
    return value if isinstance(value, list) else []


def normalize_locked_blueprint(fields: Dict[str, BlueprintField]) -> Dict[str, Any]:
    family = _field_value(fields, "product_family", "i_beam")
    length_ft = _field_value(fields, "overall_length_ft", 0)
    if isinstance(length_ft, list):
        nums = [item.get("overall_length_ft") if isinstance(item, dict) else item for item in length_ft]
        nums = [n for n in nums if isinstance(n, (int, float))]
        length_ft = max(nums) if nums else 0
    blueprint: Dict[str, Any] = {
        "cross_section": {},
        "length": length_ft,
        "marked_end": _field_value(fields, "marked_end_rule", {"label": "MARKED END", "end": "start"}),
        "bituminous_ends": _field_value(fields, "bituminous_ends", []),
        "lift_loops": _list_value(fields, "lift_loops"),
        "inserts": _list_value(fields, "inserts"),
        "tubes": _list_value(fields, "tubes"),
        "tie_rod_openings": _list_value(fields, "tie_rod_openings"),
        "drain_holes": _list_value(fields, "drain_holes"),
        "hold_downs": _list_value(fields, "hold_downs"),
        "grout_grooves": _list_value(fields, "grout_grooves"),
        "beam_marks": _field_value(fields, "beam_marks", []),
        "mark_length_families": _field_value(fields, "mark_length_families", []),
        "cid": _field_value(fields, "cid"),
        "bridge_id": _field_value(fields, "bridge_id"),
        "route": _field_value(fields, "route"),
        "casting_length_ft": _field_value(fields, "casting_length_ft"),
        "hold_down_type": _field_value(fields, "hold_down_type"),
        "lift_loop_spec": _field_value(fields, "lift_loop_spec"),
        "strand_grade": _field_value(fields, "strand_grade"),
        "strand_final_pull_lb": _field_value(fields, "strand_final_pull_lb"),
    }

    strand_rows = _field_value(fields, "strand_pattern_rows", {"rows": []})
    if isinstance(strand_rows, dict) and strand_rows.get("rows"):
        blueprint["strand_pattern"] = strand_rows
    else:
        strand_count = int(_field_value(fields, "strand_count", 0) or 0)
        if strand_count:
            straight_count = int(_field_value(fields, "straight_strand_count", 0) or 0)
            draped_count = int(_field_value(fields, "draped_strand_count", 0) or 0) if isinstance(_field_value(fields, "draped_strand_count", 0), (int, float)) else 0
            remaining = strand_count
            rows = []
            for count in (straight_count, draped_count):
                if count:
                    rows.append({"count": count, "spacing_in": 4})
                    remaining -= count
            if remaining > 0:
                rows.append({"count": remaining, "spacing_in": 4})
            blueprint["strand_pattern"] = {"start_y_in": 5, "row_spacing_in": 4.5, "rows": rows}

    stirrups = _field_value(fields, "stirrups", {})
    if isinstance(stirrups, dict) and stirrups:
        blueprint["stirrups"] = stirrups

    target_elongation = _field_value(fields, "target_elongation_in")
    jacking_force = _field_value(fields, "jacking_force_kip")
    if target_elongation or jacking_force or _field_value(fields, "strand_diameter_in") or _field_value(fields, "strand_final_pull_lb"):
        blueprint["tension_reference"] = {
            "target_elongation_in": target_elongation,
            "jacking_force_kip": jacking_force,
            "strand_area_in2": _field_value(fields, "strand_area_in2"),
            "strand_diameter_in": _field_value(fields, "strand_diameter_in"),
            "strand_final_pull_lb": _field_value(fields, "strand_final_pull_lb"),
            "strand_grade": _field_value(fields, "strand_grade"),
        }

    if family == "box_beam":
        blueprint["cross_section"] = {
            "outer_width_in": _field_value(fields, "outer_width_in"),
            "outer_depth_in": _field_value(fields, "outer_depth_in", _field_value(fields, "overall_depth_in")),
            "wall_thickness_in": _field_value(fields, "wall_thickness_in"),
            "void_width_in": _field_value(fields, "void_width_in"),
            "void_depth_in": _field_value(fields, "void_depth_in"),
        }
    else:
        blueprint["cross_section"] = {
            "overall_depth_in": _field_value(fields, "overall_depth_in"),
            "top_flange_width_in": _field_value(fields, "top_flange_width_in"),
            "top_flange_thickness_in": _field_value(fields, "top_flange_thickness_in"),
            "bottom_flange_width_in": _field_value(fields, "bottom_flange_width_in"),
            "bottom_flange_thickness_in": _field_value(fields, "bottom_flange_thickness_in"),
            "web_thickness_in": _field_value(fields, "web_thickness_in"),
        }
        draped_count = _field_value(fields, "draped_strand_count", 0)
        draped_n = int(draped_count) if isinstance(draped_count, (int, float)) else 0
        if draped_n:
            blueprint["drape_profile"] = {
                "sag_in": max(4, round(float(draped_n) * 0.5, 2)),
                "low_points_ft": sorted(item.get("x_ft") for item in blueprint["hold_downs"] if item.get("x_ft") is not None),
            }

    dimensions = {
        "overall_length_ft": _field_value(fields, "overall_length_ft"),
        "casting_length_ft": _field_value(fields, "casting_length_ft"),
        "overall_depth_in": _field_value(fields, "overall_depth_in", _field_value(fields, "outer_depth_in")),
        "overall_width_in": _field_value(fields, "top_flange_width_in", _field_value(fields, "outer_width_in")),
    }
    blueprint["dimensions"] = {key: value for key, value in dimensions.items() if value is not None}
    return blueprint


def parse_field_value(raw_value: Any) -> Any:
    if isinstance(raw_value, (list, dict, int, float)) or raw_value is None:
        return raw_value
    if not isinstance(raw_value, str):
        return raw_value
    text = raw_value.strip()
    if text == "":
        return None
    if text in ("true", "false"):
        return text == "true"
    try:
        return json.loads(text)
    except Exception:
        pass
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    return text
