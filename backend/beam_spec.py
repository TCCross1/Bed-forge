"""Job-specific beam Spec DNA materialized from locked/confirmed blueprint extraction.

Specs never invent plant hardware stations. Missing geometry may use a family
envelope for a renderable section only, and that is labeled on the Spec.
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence

from models import BlueprintField, JobBeamSpec, now_iso
from blueprint_pipeline import FIELD_GROUPS, _field_value, normalize_locked_blueprint, refresh_strand_engineering

logger = logging.getLogger(__name__)

# AASHTO I-beam envelopes used only when the print did not give flange/web dims.
FAMILY_SECTION_ENVELOPES = {
    ("i_beam", 36): {
        "overall_depth_in": 36,
        "top_flange_width_in": 12,
        "top_flange_thickness_in": 6,
        "bottom_flange_width_in": 18,
        "bottom_flange_thickness_in": 6,
        "web_thickness_in": 6,
    },
    ("i_beam", 45): {
        "overall_depth_in": 45,
        "top_flange_width_in": 16,
        "top_flange_thickness_in": 7,
        "bottom_flange_width_in": 28,
        "bottom_flange_thickness_in": 8,
        "web_thickness_in": 7,
    },
    ("i_beam", 54): {
        "overall_depth_in": 54,
        "top_flange_width_in": 20,
        "top_flange_thickness_in": 7.5,
        "bottom_flange_width_in": 32,
        "bottom_flange_thickness_in": 8.5,
        "web_thickness_in": 7,
    },
    ("i_beam", 72): {
        "overall_depth_in": 72,
        "top_flange_width_in": 42,
        "top_flange_thickness_in": 8,
        "bottom_flange_width_in": 26,
        "bottom_flange_thickness_in": 9,
        "web_thickness_in": 8,
    },
}

TWIN_DRIVER_KEYS = (
    "overall_length_ft",
    "casting_length_ft",
    "overall_depth_in",
    "top_flange_width_in",
    "web_thickness_in",
    "strand_diameter_in",
    "strand_final_pull_lb",
    "hold_downs",
    "lift_loops",
)


def _confirmed_value(fields: Dict[str, BlueprintField], key: str, default: Any = None) -> Any:
    return _field_value(fields, key, default)


def _mark_list(fields: Dict[str, BlueprintField]) -> List[str]:
    marks = _confirmed_value(fields, "beam_marks") or []
    if isinstance(marks, list) and marks:
        return [str(item) for item in marks]
    compact = _confirmed_value(fields, "beam_mark")
    if compact is None:
        return []
    if isinstance(compact, list):
        return [str(item) for item in compact]
    text = str(compact).strip()
    return [text] if text else []


def _family_for_mark(families: Sequence[Dict[str, Any]], mark: str) -> Optional[Dict[str, Any]]:
    for family in families or []:
        family_marks = [str(item) for item in (family.get("marks") or [])]
        if mark in family_marks:
            return family
    return None


def _apply_section_envelope(cross_section: Dict[str, Any], family: str) -> tuple[Dict[str, Any], str]:
    section = dict(cross_section or {})
    depth = section.get("overall_depth_in") or section.get("outer_depth_in")
    if family != "i_beam" or not isinstance(depth, (int, float)):
        filled = any(section.get(key) is not None for key in section)
        return section, "extracted" if filled else "missing"
    envelope = FAMILY_SECTION_ENVELOPES.get((family, int(round(float(depth)))))
    if not envelope:
        return section, "extracted"
    used_envelope = False
    for key, value in envelope.items():
        if section.get(key) in (None, ""):
            section[key] = value
            used_envelope = True
    if used_envelope:
        extracted_any = any(
            cross_section.get(key) not in (None, "")
            for key in envelope
            if key != "overall_depth_in"
        )
        return section, "mixed" if extracted_any else "family_envelope"
    return section, "extracted"


def _station_items(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _flatten_hardware(blueprint: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    mapping = (
        ("lift_loops", "lift_loop"),
        ("inserts", "insert"),
        ("tubes", "tube"),
        ("tie_rod_openings", "tie_rod"),
        ("drain_holes", "drain"),
        ("hold_downs", "hold_down"),
        ("grout_grooves", "grout_groove"),
    )
    for key, kind in mapping:
        for index, item in enumerate(_station_items(blueprint.get(key))):
            station = item.get("x_ft")
            if station is None:
                station = item.get("station_ft")
            items.append({
                "id": f"{kind}-{index}",
                "kind": kind,
                "name": item.get("type") or kind.replace("_", " "),
                "type_code": item.get("type") or "",
                "quantity": 1,
                "size": str(item.get("size") or item.get("diameter_in") or ""),
                "material": "",
                "position": {
                    "station_ft": station,
                    "offset_in": item.get("offset_in") or 0,
                    "height_from_soffit_in": item.get("height_from_soffit_in") or 0,
                    "face": item.get("side") or "top",
                },
                "notes": item.get("notes") or "",
                "tolerance_in": 0,
            })
    return items


def _stirrup_zones(blueprint: Dict[str, Any]) -> List[Dict[str, Any]]:
    stirrups = blueprint.get("stirrups") or {}
    if not isinstance(stirrups, dict) or not stirrups:
        return []
    start_ft = stirrups.get("start_ft")
    end_ft = stirrups.get("end_ft")
    spacing_in = stirrups.get("spacing_in")
    if start_ft is None and end_ft is None and spacing_in is None:
        return []
    return [{
        "id": "zone-1",
        "from_ft": start_ft,
        "to_ft": end_ft,
        "spacing_in": spacing_in,
        "bar_size": stirrups.get("bar_size") or "",
        "shape": stirrups.get("shape") or "",
        "notes": stirrups.get("notes") or "",
    }]


def _unconfirmed_keys(fields: Dict[str, BlueprintField]) -> List[str]:
    names = []
    for group in FIELD_GROUPS.values():
        names.extend(group)
    found = []
    for name in names:
        field = fields.get(name)
        if not field:
            continue
        if field.status == "unconfirmed":
            found.append(name)
    return found


def _missing_drivers(fields: Dict[str, BlueprintField], blueprint: Dict[str, Any]) -> List[str]:
    missing = []
    for key in TWIN_DRIVER_KEYS:
        field = fields.get(key)
        if field and field.status in ("confirmed", "manually_confirmed") and field.value not in (None, "", [], {}):
            continue
        if key in ("hold_downs", "lift_loops") and _station_items(blueprint.get(key)):
            continue
        if key == "overall_length_ft" and blueprint.get("length"):
            continue
        if key == "overall_depth_in" and (blueprint.get("cross_section") or {}).get("overall_depth_in"):
            continue
        if key == "casting_length_ft" and blueprint.get("casting_length_ft") is not None:
            continue
        missing.append(key)
    return missing


def materialize_job_beam_specs(
    fields: Dict[str, BlueprintField],
    *,
    document: Optional[Dict[str, Any]] = None,
    revision: Optional[Dict[str, Any]] = None,
    beam_ids_by_mark: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Build one Spec per extracted mark / length family. Does not invent stations."""
    document = document or {}
    revision = revision or {}
    beam_ids_by_mark = beam_ids_by_mark or {}
    try:
        normalized = copy.deepcopy(revision.get("normalized_blueprint") or normalize_locked_blueprint(fields))
        marks = _mark_list(fields)
        if not marks:
            compact = revision.get("beam_mark") or document.get("beam_mark_hint")
            marks = [str(compact)] if compact else ["UNCONFIRMED"]
        families = _confirmed_value(fields, "mark_length_families") or normalized.get("mark_length_families") or []
        family_name = _confirmed_value(fields, "product_family", revision.get("product_family") or "i_beam")
        unconfirmed = _unconfirmed_keys(fields)
        specs: List[Dict[str, Any]] = []
        for mark in marks:
            blueprint = copy.deepcopy(normalized)
            family = _family_for_mark(families, mark) if isinstance(families, list) else None
            if family:
                overall = family.get("overall_length_ft")
                casting = family.get("casting_length_ft")
                if overall is not None:
                    blueprint["length"] = overall
                    blueprint.setdefault("dimensions", {})["overall_length_ft"] = overall
                if casting is not None:
                    blueprint["casting_length_ft"] = casting
                    blueprint.setdefault("dimensions", {})["casting_length_ft"] = casting
            blueprint["beam_mark"] = mark
            blueprint["product_family"] = family_name
            section, section_source = _apply_section_envelope(blueprint.get("cross_section") or {}, family_name)
            blueprint["cross_section"] = section
            blueprint = refresh_strand_engineering(fields, blueprint)
            missing = _missing_drivers(fields, blueprint)
            if section_source == "family_envelope":
                missing = [item for item in missing if item not in {"top_flange_width_in", "web_thickness_in"}]
                missing.append("section_flanges_web_from_family_envelope")
            identity = {
                "job_number": _confirmed_value(fields, "job_number") or document.get("project_name_hint"),
                "beam_mark": mark,
                "county": _confirmed_value(fields, "county_dot"),
                "cid": _confirmed_value(fields, "cid") or blueprint.get("cid"),
                "bridge_id": _confirmed_value(fields, "bridge_id") or blueprint.get("bridge_id"),
                "route": _confirmed_value(fields, "route") or blueprint.get("route"),
                "product_family": family_name,
                "product_type": "Type 2 I-Beam" if family_name == "i_beam" and int(round(float(section.get("overall_depth_in") or 0) or 0)) == 36 else None,
            }
            geometry = {
                "twin_type": family_name,
                "length_ft": blueprint.get("length"),
                "casting_length_ft": blueprint.get("casting_length_ft"),
                "depth_in": section.get("overall_depth_in") or section.get("outer_depth_in"),
                "width_in": section.get("top_flange_width_in") or section.get("outer_width_in"),
                "top_flange_width_in": section.get("top_flange_width_in"),
                "top_flange_thick_in": section.get("top_flange_thickness_in"),
                "bot_flange_width_in": section.get("bottom_flange_width_in"),
                "bot_flange_thick_in": section.get("bottom_flange_thickness_in"),
                "web_thick_in": section.get("web_thickness_in"),
                "product_name": identity.get("product_type") or family_name,
                "section_source": section_source,
            }
            tension = blueprint.get("tension_reference") or {}
            strand = dict(blueprint.get("strand_system") or {})
            if not strand:
                strand = {
                    "diameter_in": tension.get("strand_diameter_in"),
                    "grade": blueprint.get("strand_grade") or tension.get("strand_grade"),
                    "pattern": blueprint.get("strand_pattern"),
                    "draped": bool(blueprint.get("strand_draped") or blueprint.get("drape_profile")),
                    "hold_down_type": blueprint.get("hold_down_type"),
                    "jacking_force_kip": tension.get("jacking_force_kip"),
                    "final_pull_lb": blueprint.get("strand_final_pull_lb") or tension.get("strand_final_pull_lb"),
                }
            finishes = {
                "bituminous_ends": blueprint.get("bituminous_ends") or [],
                "marked_end": blueprint.get("marked_end"),
                "surface_finish": _confirmed_value(fields, "finish_notes"),
            }
            qc = {
                "strengths_psi": None,
                "notes": "PSI / cylinder strengths are included only when present on the print.",
            }
            spec = JobBeamSpec(
                job_id=document.get("job_id"),
                job_number=identity.get("job_number") or "",
                beam_mark=mark,
                beam_id=beam_ids_by_mark.get(mark),
                document_id=document.get("id") or revision.get("document_id"),
                locked_revision_id=revision.get("id"),
                product_family=family_name,
                product_type=identity.get("product_type"),
                identity=identity,
                geometry=geometry,
                strand=strand,
                hardware=_flatten_hardware(blueprint),
                stirrup_zones=_stirrup_zones(blueprint),
                finishes=finishes,
                qc=qc,
                missing_fields=missing,
                unconfirmed_fields=unconfirmed,
                blueprint=blueprint,
                status="locked" if revision.get("id") else "extracted",
                section_source=section_source,
                locked_at=revision.get("locked_at") or now_iso(),
            )
            specs.append(spec.model_dump())
        logger.info(
            "Materialized %s beam specs document_id=%s marks=%s",
            len(specs),
            document.get("id"),
            [item["beam_mark"] for item in specs],
        )
        return specs
    except Exception:
        logger.exception("Failed to materialize beam specs document_id=%s", (document or {}).get("id"))
        raise


def twin_beam_from_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Synthetic beam payload so the Digital Twin can render Spec DNA without seed geometry."""
    geometry = spec.get("geometry") or {}
    identity = spec.get("identity") or {}
    blueprint = spec.get("blueprint") or {}
    family = spec.get("product_family") or geometry.get("twin_type") or "i_beam"
    length = geometry.get("length_ft") or blueprint.get("length") or 0
    return {
        "id": spec.get("beam_id") or f"spec:{spec.get('id')}",
        "mark": spec.get("beam_mark"),
        "bed_id": None,
        "job_id": spec.get("job_id"),
        "twin_type": family,
        "length_ft": length,
        "position_on_bed": None,
        "status": "spec",
        "qc_state": "pending",
        "product_type": {
            "name": spec.get("product_type") or identity.get("product_type") or family,
            "category": family,
            "depth_in": geometry.get("depth_in"),
            "width_in": geometry.get("width_in"),
            "default_length_ft": length,
            "blueprint": blueprint,
        },
        "beam_spec": spec,
        "blueprint_source": {
            "status": "locked" if spec.get("status") == "locked" else "draft",
            "document_id": spec.get("document_id"),
            "revision_id": spec.get("locked_revision_id"),
            "beam_mark": spec.get("beam_mark"),
            "locked_at": spec.get("locked_at"),
            "critical_fields_complete": True,
            "spec_id": spec.get("id"),
            "section_source": spec.get("section_source") or geometry.get("section_source"),
        },
        "anomalies": [],
        "inspections": [],
        "camber_readings": [],
    }
