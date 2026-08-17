import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from pypdf import PdfReader

from models import BlueprintField

FIELD_GROUPS = {
    "title_block": [
        "job_number",
        "project_name",
        "county_dot",
        "sheet_number",
        "revision",
        "beam_mark",
        "product_family",
        "overall_length_ft",
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
        "strand_area_in2",
        "strand_pattern_rows",
        "straight_strand_count",
        "draped_strand_count",
        "hold_downs",
        "jacking_force_kip",
        "target_elongation_in",
        "debond_notes",
    ],
    "hardware": [
        "lift_loops",
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


def _blank_field(note: str = "") -> BlueprintField:
    return BlueprintField(value=None, confidence="low", source_page=None, status="unconfirmed", extraction_notes=note)


def build_empty_fields() -> Dict[str, BlueprintField]:
    return {field: _blank_field() for group in FIELD_GROUPS.values() for field in group}


def _normalize_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", (text or "")).strip()


def _page_text(reader: PdfReader) -> List[str]:
    pages = []
    for page in reader.pages:
        try:
            pages.append(_normalize_text(page.extract_text() or ""))
        except Exception:
            pages.append("")
    return pages


def read_pdf_pages(path: str | Path) -> List[str]:
    reader = PdfReader(str(path))
    return _page_text(reader)


def _source_page(page_text: List[str], pattern: str) -> Optional[int]:
    rx = re.compile(pattern, re.IGNORECASE)
    for index, text in enumerate(page_text, start=1):
        if rx.search(text or ""):
            return index
    return None


def _build_field(value: Any, confidence: str, page: Optional[int], status: str = "confirmed", note: str = "") -> BlueprintField:
    return BlueprintField(value=value, confidence=confidence, source_page=page, status=status, extraction_notes=note)


def _capture_scalar(page_text: List[str], patterns: List[str], cast=lambda value: value.strip(), confidence: str = "medium", note: str = "") -> BlueprintField:
    for pattern in patterns:
        rx = re.compile(pattern, re.IGNORECASE)
        for index, text in enumerate(page_text, start=1):
            match = rx.search(text or "")
            if match:
                raw = next((group for group in match.groups() if group is not None), match.group(0))
                try:
                    return _build_field(cast(raw), confidence, index, note=note)
                except Exception:
                    return _build_field(raw.strip(), "low", index, note="Matched text could not be normalized cleanly.")
    return _blank_field(note)


def _parse_feet_inches(value: str) -> Optional[float]:
    if value is None:
        return None
    text = value.strip().replace("”", '"').replace("“", '"').replace("’", "'")
    simple = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:FT|FEET|')", text, re.IGNORECASE)
    if simple:
        return float(simple.group(1))
    mixed = re.fullmatch(r"(\d+)\s*[- ]\s*(\d+)\s*(?:\"|IN)", text, re.IGNORECASE)
    if mixed:
        return float(mixed.group(1)) + (float(mixed.group(2)) / 12.0)
    ft_in = re.fullmatch(r"(\d+)\s*'\s*(\d+(?:\.\d+)?)\s*(?:\"|IN)?", text, re.IGNORECASE)
    if ft_in:
        return float(ft_in.group(1)) + (float(ft_in.group(2)) / 12.0)
    bare = re.fullmatch(r"(\d+(?:\.\d+)?)", text)
    if bare:
        return float(bare.group(1))
    return None


def _parse_number(value: str) -> Optional[float]:
    match = re.search(r"-?\d+(?:\.\d+)?", value or "")
    return float(match.group(0)) if match else None


def _product_family(page_text: List[str], hint: str = "") -> BlueprintField:
    text = " ".join(page_text).upper()
    if "BOX BEAM" in text or "ADJACENT BOX" in text:
        return _build_field("box_beam", "high", _source_page(page_text, r"BOX\s+BEAM|ADJACENT\s+BOX"))
    if any(token in text for token in ("I-BEAM", "I BEAM", "AASHTO TYPE", "BULB TEE", "BT-")):
        return _build_field("i_beam", "high", _source_page(page_text, r"I[\s-]?BEAM|AASHTO\s+TYPE|BULB\s+TEE|BT-"))
    if hint in ("i_beam", "box_beam"):
        return _build_field(hint, "medium", None, note="Derived from upload hint; drawing text did not clearly confirm the family.")
    return _blank_field("Product family not clearly stated in extracted page text.")


def _find_all_stations(page_text: List[str], label: str, type_name: str, extra: Optional[Dict[str, Any]] = None) -> BlueprintField:
    items: List[Dict[str, Any]] = []
    patterns = [
        rf"{label}[^A-Z0-9]{{0,8}}(?:AT|@)\s*(\d+\s*'\s*\d+(?:\.\d+)?(?:\"|IN)?)",
        rf"{label}[^A-Z0-9]{{0,8}}(?:AT|@)\s*(\d+(?:\.\d+)?)\s*(FT|FEET|')",
    ]
    for pattern in patterns:
        rx = re.compile(pattern, re.IGNORECASE)
        for page_index, text in enumerate(page_text, start=1):
            for match in rx.finditer(text or ""):
                station = _parse_feet_inches("".join(group or "" for group in match.groups()))
                if station is not None:
                    item = {"x_ft": round(station, 3), "type": type_name}
                    if extra:
                        item.update(extra)
                    if item not in items:
                        item["_source_page"] = page_index
                        items.append(item)
    if not items:
        return _blank_field(f"No deterministic {type_name.lower()} station callouts were found in extractable text.")
    source_page = items[0].pop("_source_page", None)
    for item in items[1:]:
        item.pop("_source_page", None)
    return _build_field(items, "medium", source_page)


def _capture_notes(page_text: List[str], keyword: str, target_note: str) -> BlueprintField:
    page = _source_page(page_text, keyword)
    if page is None:
        return _blank_field(target_note)
    return _build_field(target_note, "medium", page, note="Captured from keyword hit; verify exact wording against source.")


def extract_structured_fields(page_text: List[str], hints: Optional[Dict[str, Any]] = None) -> ExtractionResult:
    hints = hints or {}
    fields = build_empty_fields()
    fail_reasons: List[str] = []
    text_present = [text for text in page_text if text]
    if not text_present:
        fail_reasons.append("No extractable text was found in the uploaded PDF. Scanned or raster drawings require OCR before controlled extraction.")
        return ExtractionResult(
            status="insufficient_quality",
            summary="Blueprint text extraction failed; no machine-readable drawing text was found.",
            page_text=page_text,
            fields=fields,
            field_groups=FIELD_GROUPS,
            fail_reasons=fail_reasons,
        )

    fields["job_number"] = _capture_scalar(page_text, [r"JOB(?:\s+NO\.?|\s+NUMBER|#)\s*[:\-]?\s*([A-Z0-9\-_/]+)"], note="Job number not confidently located.")
    fields["project_name"] = _capture_scalar(page_text, [r"PROJECT(?:\s+NAME)?\s*[:\-]?\s*([A-Z0-9 ,.&()/#\-]+)"], note="Project name not confidently located.")
    fields["county_dot"] = _capture_scalar(page_text, [r"(?:COUNTY|DOT|DEPARTMENT OF TRANSPORTATION)\s*[:\-]?\s*([A-Z0-9 .,&()/#\-]+)"], note="County/DOT owner not confidently located.")
    fields["sheet_number"] = _capture_scalar(page_text, [r"SHEET(?:\s+NO\.?|\s+NUMBER|#)\s*[:\-]?\s*([A-Z0-9\-_/]+)"], note="Sheet number not confidently located.")
    fields["revision"] = _capture_scalar(page_text, [r"REV(?:ISION)?\s*[:\-]?\s*([A-Z0-9\-_/]+)"], note="Revision not confidently located.")
    fields["beam_mark"] = _capture_scalar(page_text, [r"(?:BEAM|PIECE)\s+MARK\s*[:\-]?\s*([A-Z0-9\-_/]+)", r"MARK\s*[:\-]?\s*([A-Z0-9\-_/]+)"], note="Beam mark not confidently located.")
    if fields["beam_mark"].status == "unconfirmed" and hints.get("beam_mark_hint"):
        fields["beam_mark"] = _build_field(hints["beam_mark_hint"], "medium", None, note="Taken from upload hint; verify against title block.")
    fields["product_family"] = _product_family(page_text, hints.get("product_family_hint", ""))

    fields["overall_length_ft"] = _capture_scalar(
        page_text,
        [
            r"(?:OVERALL LENGTH|O\.?A\.?L\.?)\s*[:\-]?\s*([0-9]+'\s*[0-9]+(?:\.\d+)?\"?)",
            r"(?:OVERALL LENGTH|O\.?A\.?L\.?)\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:FT|FEET|')",
        ],
        cast=lambda value: round(_parse_feet_inches(value), 3),
        confidence="high",
        note="Overall length not confidently located.",
    )
    fields["design_camber_in"] = _capture_scalar(page_text, [r"CAMBER(?:\s+AT\s+RELEASE|\s+TARGET|\s+DESIGN)?\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), confidence="medium", note="Design camber note not clearly stated.")
    fields["finish_notes"] = _capture_notes(page_text, r"FINISH", "Finish notes present in drawing text; verify manually.")

    fields["overall_depth_in"] = _capture_scalar(page_text, [r"(?:OVERALL DEPTH|DEPTH|HEIGHT)\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), confidence="medium", note="Overall depth/height not confidently located.")
    fields["top_flange_width_in"] = _capture_scalar(page_text, [r"TOP FLANGE WIDTH\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), confidence="medium", note="Top flange width not confidently located.")
    fields["top_flange_thickness_in"] = _capture_scalar(page_text, [r"TOP FLANGE THICKNESS\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), confidence="medium", note="Top flange thickness not confidently located.")
    fields["bottom_flange_width_in"] = _capture_scalar(page_text, [r"BOTTOM FLANGE WIDTH\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), confidence="medium", note="Bottom flange width not confidently located.")
    fields["bottom_flange_thickness_in"] = _capture_scalar(page_text, [r"BOTTOM FLANGE THICKNESS\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), confidence="medium", note="Bottom flange thickness not confidently located.")
    fields["web_thickness_in"] = _capture_scalar(page_text, [r"WEB THICKNESS\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), confidence="medium", note="Web thickness not confidently located.")
    fields["outer_width_in"] = _capture_scalar(page_text, [r"(?:OUTER|OVERALL) WIDTH\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), confidence="medium", note="Outer width not confidently located.")
    fields["outer_depth_in"] = _capture_scalar(page_text, [r"(?:OUTER|OVERALL) DEPTH\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), confidence="medium", note="Outer depth not confidently located.")
    fields["wall_thickness_in"] = _capture_scalar(page_text, [r"WALL THICKNESS\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), confidence="medium", note="Wall thickness not confidently located.")
    fields["void_width_in"] = _capture_scalar(page_text, [r"(?:VOID|CORE) WIDTH\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), confidence="medium", note="Void/core width not confidently located.")
    fields["void_depth_in"] = _capture_scalar(page_text, [r"(?:VOID|CORE) DEPTH\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), confidence="medium", note="Void/core depth not confidently located.")
    fields["special_end_geometry"] = _capture_notes(page_text, r"END ELEVATION|END DETAIL|SKEW", "Special end geometry/end-detail notes present; verify manually.")

    fields["strand_count"] = _capture_scalar(page_text, [r"([0-9]+)\s+STRANDS?"], cast=lambda value: int(float(value)), confidence="high", note="Strand count not confidently located.")
    fields["strand_diameter_in"] = _capture_scalar(page_text, [r"STRAND(?:\s+SIZE|\s+DIA(?:METER)?)?\s*[:\-]?\s*([0-9.]+)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), confidence="medium", note="Strand diameter not confidently located.")
    fields["strand_area_in2"] = _capture_scalar(page_text, [r"STRAND(?:\s+AREA)?\s*[:\-]?\s*([0-9.]+)\s*(?:IN2|IN\^2|SQ\.?\s*IN)"], cast=lambda value: round(float(value), 4), confidence="medium", note="Strand area not confidently located.")
    fields["straight_strand_count"] = _capture_scalar(page_text, [r"([0-9]+)\s+STRAIGHT\s+STRANDS?"], cast=lambda value: int(float(value)), confidence="medium", note="Straight strand count not clearly stated.")
    fields["draped_strand_count"] = _capture_scalar(page_text, [r"([0-9]+)\s+DRAPED\s+STRANDS?"], cast=lambda value: int(float(value)), confidence="medium", note="Draped strand count not clearly stated.")
    fields["jacking_force_kip"] = _capture_scalar(page_text, [r"JACK(?:ING)? FORCE\s*[:\-]?\s*([0-9.]+)\s*(?:KIP|KIPS)"], cast=lambda value: round(float(value), 3), confidence="medium", note="Jacking force note not confidently located.")
    fields["target_elongation_in"] = _capture_scalar(page_text, [r"(?:ELONGATION|TARGET ELONGATION)\s*[:\-]?\s*([0-9.]+)\s*(?:IN|\")"], cast=lambda value: round(float(value), 3), confidence="medium", note="Target elongation note not confidently located.")
    fields["debond_notes"] = _capture_notes(page_text, r"DEBOND|SHIELD", "Debonded or shielded strand notes present; verify manually.")
    fields["hold_downs"] = _find_all_stations(page_text, r"HOLD[\s-]?DOWN", "Hold-down")

    fields["lift_loops"] = _find_all_stations(page_text, r"LIFT(?:\s+LOOP|\s+POINT)", "Lift loop")
    fields["inserts"] = _find_all_stations(page_text, r"INSERT|EMBED", "Insert")
    fields["tubes"] = _find_all_stations(page_text, r"TUBE|VOID", "Tube")
    fields["tie_rod_openings"] = _find_all_stations(page_text, r"TIE[\s-]?ROD", "Tie-rod opening")
    fields["drain_holes"] = _find_all_stations(page_text, r"DRAIN", "Drain hole")
    fields["grout_grooves"] = _find_all_stations(page_text, r"GROUT GROOVE", "Grout groove")
    fields["plates_and_clips"] = _capture_notes(page_text, r"PLATE|CLIP|BEARING", "Plate, clip, or bearing notes present; verify manually.")
    fields["bituminous_ends"] = _capture_notes(page_text, r"BITUMINOUS|CUT[\s-]?OFF POCKET", "Bituminous or cut-off pocket treatment noted; verify manually.")
    fields["stirrups"] = _capture_scalar(
        page_text,
        [r"STIRRUPS?\s*(?:@|AT)\s*([0-9.]+)\s*(?:IN|\")"],
        cast=lambda value: {"spacing_in": round(float(value), 3)},
        confidence="medium",
        note="Only stirrup spacing was auto-detected. Region/type still require review.",
    )

    fields["marked_end_rule"] = _capture_scalar(
        page_text,
        [r"MARKED\s+END\s*[:\-]?\s*([A-Z0-9 /()\-]+)"],
        cast=lambda value: {"label": value.strip(), "end": "start"},
        confidence="medium",
        note="Marked end rule not confidently located.",
    )
    fields["end_elevation_notes"] = _capture_notes(page_text, r"END ELEVATION|ELEVATION DIFFERENCE", "End elevation note present; verify manually.")
    fields["paint_id_requirements"] = _capture_notes(page_text, r"PAINT|ID", "Paint or ID marking note present; verify manually.")
    fields["dimensional_tolerances"] = _capture_notes(page_text, r"TOLERANCE", "Tolerance note present; verify manually.")
    fields["special_inspection_notes"] = _capture_notes(page_text, r"INSPECT|QC|SPECIAL NOTE", "Special inspection note present; verify manually.")

    strand_rows = []
    row_matches = re.findall(r"(\d+)\s*(?:STRANDS?|STDS?)\s*@\s*([0-9.]+)\s*(?:IN|\")", " ".join(page_text), flags=re.IGNORECASE)
    if row_matches:
        for count, spacing in row_matches[:6]:
            strand_rows.append({"count": int(count), "spacing_in": float(spacing)})
    if strand_rows:
        fields["strand_pattern_rows"] = _build_field({"rows": strand_rows}, "medium", _source_page(page_text, r"STRANDS?\s*@"), note="Strand rows inferred from text callouts. Marked/unmarked end symmetry still requires review.")

    product_family = fields["product_family"].value
    if product_family == "box_beam":
        for field_name in ("top_flange_width_in", "top_flange_thickness_in", "bottom_flange_width_in", "bottom_flange_thickness_in", "web_thickness_in"):
            if fields[field_name].status == "unconfirmed":
                fields[field_name] = _build_field(None, "low", None, status="not_applicable", note="Not required for box-beam translation.")
    elif product_family == "i_beam":
        for field_name in ("outer_width_in", "outer_depth_in", "wall_thickness_in", "void_width_in", "void_depth_in", "grout_grooves"):
            if fields[field_name].status == "unconfirmed":
                fields[field_name] = _build_field(None, "low", None, status="not_applicable", note="Not required for I-beam translation unless the drawing explicitly calls it out.")

    unconfirmed_critical = sorted(field for field in CRITICAL_FIELDS if fields[field].status == "unconfirmed")
    if unconfirmed_critical:
        fail_reasons.append(f"Critical fields require manual verification before lock: {', '.join(unconfirmed_critical)}.")

    confirmed_count = sum(1 for field in fields.values() if field.status in ("confirmed", "manually_confirmed"))
    unconfirmed_count = sum(1 for field in fields.values() if field.status == "unconfirmed")
    status = "needs_review" if unconfirmed_count else "extracted"
    summary = f"Controlled extraction captured {confirmed_count} fields with {unconfirmed_count} still unconfirmed."
    if fail_reasons:
        summary += f" {fail_reasons[0]}"
    return ExtractionResult(status=status, summary=summary, page_text=page_text, fields=fields, field_groups=FIELD_GROUPS, fail_reasons=fail_reasons)


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
    }

    strand_rows = _field_value(fields, "strand_pattern_rows", {"rows": []})
    if isinstance(strand_rows, dict) and strand_rows.get("rows"):
        blueprint["strand_pattern"] = strand_rows
    else:
        strand_count = int(_field_value(fields, "strand_count", 0) or 0)
        if strand_count:
            straight_count = int(_field_value(fields, "straight_strand_count", 0) or 0)
            draped_count = int(_field_value(fields, "draped_strand_count", 0) or 0)
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
    if target_elongation or jacking_force:
        blueprint["tension_reference"] = {
            "target_elongation_in": target_elongation,
            "jacking_force_kip": jacking_force,
            "strand_area_in2": _field_value(fields, "strand_area_in2"),
            "strand_diameter_in": _field_value(fields, "strand_diameter_in"),
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
        draped_count = int(_field_value(fields, "draped_strand_count", 0) or 0)
        if draped_count:
            blueprint["drape_profile"] = {
                "sag_in": max(4, round(float(draped_count) * 0.5, 2)),
                "low_points_ft": sorted(item.get("x_ft") for item in blueprint["hold_downs"] if item.get("x_ft") is not None),
            }

    dimensions = {
        "overall_length_ft": _field_value(fields, "overall_length_ft"),
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
