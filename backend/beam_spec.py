"""BeamSpec — structured shop-drawing extraction for blueprint-accurate twins.

All linear stations are feet from the Marked End unless noted.
Heights are inches from soffit. Offsets are inches from beam centerline
(+ toward the right when looking from Marked End toward Unmarked End).
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from models import new_id, now_iso


DEFAULT_TOLERANCES_IN = {
    "length": 0.5,
    "lift_loop": 1.0,
    "insert": 0.5,
    "tube": 1.0,
    "drain": 1.0,
    "downspout": 1.0,
    "tie_rod": 0.5,
    "hold_down": 1.0,
    "stirrup": 1.0,
    "hoop": 1.0,
    "projecting_rebar": 0.5,
    "grout_groove": 0.5,
    "diaphragm": 1.0,
    "bearing_plate": 0.25,
    "bituminous_zone": 2.0,
    "strand": 0.25,
}


class StationRef(BaseModel):
    station_ft: float = 0.0
    offset_in: float = 0.0
    height_from_soffit_in: float = 0.0
    face: str = "top"
    page: Optional[int] = None
    source_note: str = ""


class HardwareItem(BaseModel):
    id: str = Field(default_factory=new_id)
    kind: str
    name: str
    type_code: str = ""
    quantity: int = 1
    size: str = ""
    material: str = ""
    position: StationRef = Field(default_factory=StationRef)
    end_station_ft: Optional[float] = None
    design_value: Optional[float] = None
    unit: str = "ft"
    notes: str = ""
    tolerance_in: float = 1.0


class StrandItem(BaseModel):
    id: str = Field(default_factory=new_id)
    number: int = 1
    size: str = "0.5in"
    detensioning: str = "straight"  # straight | draped
    area_in2: float = 0.153
    jacking_kip: float = 31.0
    soffit_in: float = 2.0
    drape_peak_in: Optional[float] = None
    hold_down_stations_ft: List[float] = Field(default_factory=list)
    debond_me_ft: float = 0.0
    debond_ue_ft: float = 0.0
    offset_in: float = 0.0
    notes: str = ""
    page: Optional[int] = None


class StirrupZone(BaseModel):
    id: str = Field(default_factory=new_id)
    from_ft: float = 0.0
    to_ft: float = 0.0
    spacing_in: float = 12.0
    bar_size: str = "#4"
    shape: str = "stirrup"
    notes: str = ""
    page: Optional[int] = None


class BeamGeometry(BaseModel):
    twin_type: str = "i_beam"
    length_ft: float = 73.333
    depth_in: float = 36.0
    width_in: float = 18.0
    top_flange_width_in: float = 12.0
    top_flange_thick_in: float = 6.0
    bot_flange_width_in: float = 18.0
    bot_flange_thick_in: float = 6.0
    web_thick_in: float = 6.0
    product_name: str = "KYTC PC I-Beam Type 2"


class BillItem(BaseModel):
    item: str
    quantity: float = 1
    unit: str = "EA"
    notes: str = ""


class BeamSpec(BaseModel):
    id: str = Field(default_factory=new_id)
    beam_id: Optional[str] = None
    job_id: Optional[str] = None
    pour_id: Optional[str] = None
    blueprint_id: Optional[str] = None
    catalog_id: str = ""
    source_agency: str = ""
    source_drawing: str = ""
    source_url: str = ""
    job_number: str = ""
    beam_mark: str = ""
    product_name: str = ""
    state_spec: str = "KYTC"
    geometry: BeamGeometry = Field(default_factory=BeamGeometry)
    marked_end_id: str = ""
    unmarked_end_id: str = ""
    strands: List[StrandItem] = Field(default_factory=list)
    hardware: List[HardwareItem] = Field(default_factory=list)
    stirrup_zones: List[StirrupZone] = Field(default_factory=list)
    bill_of_materials: List[BillItem] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    tolerances: Dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_TOLERANCES_IN))
    special_finishes: List[str] = Field(default_factory=list)
    status: str = "extracted"  # extracted | reviewed | locked
    extractor: str = "reference"
    extractor_confidence: float = 0.0
    review_notes: str = ""
    reviewed_by: str = ""
    locked_by: str = ""
    locked_at: Optional[str] = None
    source_pages: int = 1
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class Blueprint(BaseModel):
    id: str = Field(default_factory=new_id)
    beam_id: Optional[str] = None
    job_id: Optional[str] = None
    original_name: str = ""
    stored_name: str = ""
    content_type: str = ""
    size_bytes: int = 0
    page_count: int = 1
    status: str = "uploaded"  # uploaded | extracting | extracted | failed
    extractor: str = ""
    error: str = ""
    uploaded_by: str = ""
    created_at: str = Field(default_factory=now_iso)


class SpecMeasurement(BaseModel):
    id: str = Field(default_factory=new_id)
    spec_id: str
    beam_id: str = ""
    element_id: str
    element_kind: str = ""
    element_name: str = ""
    design_station_ft: float = 0.0
    measured_station_ft: Optional[float] = None
    measured_offset_in: Optional[float] = None
    measured_height_in: Optional[float] = None
    delta_in: Optional[float] = None
    tolerance_in: float = 1.0
    within_tolerance: Optional[bool] = None
    inspector: str = ""
    notes: str = ""
    created_at: str = Field(default_factory=now_iso)


class SpecMeasurementCreate(BaseModel):
    element_id: str
    measured_station_ft: Optional[float] = None
    measured_offset_in: Optional[float] = None
    measured_height_in: Optional[float] = None
    notes: str = ""


class BeamSpecPatch(BaseModel):
    geometry: Optional[BeamGeometry] = None
    marked_end_id: Optional[str] = None
    unmarked_end_id: Optional[str] = None
    strands: Optional[List[StrandItem]] = None
    hardware: Optional[List[HardwareItem]] = None
    stirrup_zones: Optional[List[StirrupZone]] = None
    notes: Optional[List[str]] = None
    special_finishes: Optional[List[str]] = None
    review_notes: Optional[str] = None
    beam_mark: Optional[str] = None
    product_name: Optional[str] = None
    status: Optional[str] = None


def compare_measurement(spec: BeamSpec, payload: SpecMeasurementCreate, inspector: str) -> SpecMeasurement:
    element = None
    kind = ""
    name = ""
    design_ft = 0.0
    tol = 1.0
    for item in spec.hardware:
        if item.id == payload.element_id:
            element = item
            kind = item.kind
            name = item.name
            design_ft = item.position.station_ft
            tol = item.tolerance_in or spec.tolerances.get(item.kind, 1.0)
            break
    if element is None:
        for s in spec.strands:
            if s.id == payload.element_id:
                kind = "strand"
                name = f"Strand {s.number}"
                design_ft = 0.0
                tol = spec.tolerances.get("strand", 0.25)
                break
    measured = payload.measured_station_ft
    delta = None
    within = None
    if measured is not None:
        delta = round(abs(measured - design_ft) * 12.0, 3)
        within = delta <= tol
    return SpecMeasurement(
        spec_id=spec.id,
        beam_id=spec.beam_id or "",
        element_id=payload.element_id,
        element_kind=kind,
        element_name=name,
        design_station_ft=design_ft,
        measured_station_ft=measured,
        measured_offset_in=payload.measured_offset_in,
        measured_height_in=payload.measured_height_in,
        delta_in=delta,
        tolerance_in=tol,
        within_tolerance=within,
        inspector=inspector,
        notes=payload.notes,
    )


def flatten_hardware(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(spec.get("hardware") or [])
