"""BeamSpec — structured shop-drawing extraction for blueprint-accurate twins.

All linear stations are feet from the Marked End unless noted.
Heights are inches from soffit. Offsets are inches from beam centerline
(+ toward the right when looking from Marked End toward Unmarked End).
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator

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


HOLD_DOWN_STATES = ["pending", "installed", "stressed", "released", "inspected", "verified", "issue"]
DEFAULT_MODULUS_KSI = 28500.0


class StrandItem(BaseModel):
    id: str = Field(default_factory=new_id)
    strand_id: str = ""
    number: int = 1
    row: int = 0
    column: int = 0
    size: str = "0.5in"
    detensioning: str = "straight"  # straight | draped
    draped: bool = False
    area_in2: float = 0.153
    jacking_kip: float = 31.0
    soffit_in: float = 2.0
    offset_in: float = 0.0
    x_in: Optional[float] = None
    y_in: Optional[float] = None
    drape_peak_in: Optional[float] = None
    hold_down_y_in: Optional[float] = None
    hold_down_stations_ft: List[float] = Field(default_factory=list)
    debond_me_ft: float = 0.0
    debond_ue_ft: float = 0.0
    modulus_ksi: float = DEFAULT_MODULUS_KSI
    theoretical_elongation: Optional[float] = None
    measured_elongation: Optional[float] = None
    jacking_force: Optional[float] = None
    variance_pct: Optional[float] = None
    within_tolerance: Optional[bool] = None
    na: bool = False
    recorded_by: str = ""
    recorded_at: Optional[str] = None
    notes: str = ""
    page: Optional[int] = None

    @model_validator(mode="after")
    def sync_pattern_fields(self):
        if not self.strand_id:
            self.strand_id = self.id
        if self.detensioning == "draped":
            self.draped = True
        elif self.draped:
            self.detensioning = "draped"
        if self.x_in is None:
            self.x_in = self.offset_in
        else:
            self.offset_in = self.x_in
        if self.draped:
            if self.drape_peak_in is None:
                self.drape_peak_in = self.y_in if self.y_in is not None else self.soffit_in
            if self.y_in is None:
                self.y_in = self.drape_peak_in
            if self.hold_down_y_in is None:
                self.hold_down_y_in = self.soffit_in
        elif self.y_in is None:
            self.y_in = self.soffit_in
        else:
            self.soffit_in = self.y_in
        return self


class HoldDownItem(BaseModel):
    id: str = Field(default_factory=new_id)
    station_from_marked_end: float = 0.0
    height: float = 2.5
    offset_in: float = 0.0
    type_spec: str = "I-beam hold-down"
    quantity_at_station: int = 1
    orientation: str = "transverse"
    status: str = "pending"
    notes: str = ""
    verified_by: str = ""
    verified_at: Optional[str] = None
    page: Optional[int] = None


class StrandTensionCapture(BaseModel):
    measured_elongation_in: Optional[float] = None
    jacking_force_kip: Optional[float] = None
    bed_length_ft: Optional[float] = None
    na: bool = False
    notes: str = ""


class HoldDownCapture(BaseModel):
    status: str = "pending"
    notes: str = ""


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
    hold_downs: List[HoldDownItem] = Field(default_factory=list)
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
    hold_downs: Optional[List[HoldDownItem]] = None
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


def _as_dict(strand: Any) -> Dict[str, Any]:
    if isinstance(strand, dict):
        return strand
    if hasattr(strand, "model_dump"):
        return strand.model_dump()
    return {}


def is_draped(strand: Any) -> bool:
    data = _as_dict(strand)
    return bool(data.get("draped") or data.get("detensioning") == "draped")


def strand_end_y_in(strand: Any) -> float:
    """Height from soffit at the marked-end strand pattern (shop-drawing end view)."""
    data = _as_dict(strand)
    if is_draped(strand):
        return float(data.get("drape_peak_in") or data.get("y_in") or data.get("soffit_in") or 0)
    if data.get("y_in") is not None:
        return float(data["y_in"])
    return float(data.get("soffit_in") or 0)


def strand_hold_y_in(strand: Any) -> float:
    """Height from soffit at hold-down stations (depressed drape)."""
    data = _as_dict(strand)
    if is_draped(strand):
        if data.get("hold_down_y_in") is not None:
            return float(data["hold_down_y_in"])
        return float(data.get("soffit_in") or 2.0)
    return strand_end_y_in(strand)


def drape_key_stations_ft(strand: Any, length_ft: float = 0.0, hold_downs: Optional[List[Any]] = None) -> List[float]:
    data = _as_dict(strand)
    raw = [float(s) for s in (data.get("hold_down_stations_ft") or []) if s is not None]
    stations = sorted(s for s in raw if s > 0)
    if stations:
        return stations
    extra = []
    for item in hold_downs or []:
        rec = _as_dict(item)
        st = rec.get("station_from_marked_end")
        if st is not None:
            extra.append(float(st))
    extra = sorted(s for s in extra if s > 0)
    if extra:
        return extra
    length = float(length_ft or 0)
    if length > 0:
        return [round(length * 0.40, 3), round(length * 0.60, 3)]
    return []


def drape_elevation_in(strand: Any, z_ft: float, length_ft: float, hold_downs: Optional[List[Any]] = None) -> float:
    """Elevation (in from soffit) of a strand at station z_ft from Marked End.

    Straight strands are constant. Draped strands are HIGH at both ends (end-view
    pattern) and LOW at each hold-down — piecewise linear through those stations.
    """
    y_end = strand_end_y_in(strand)
    if not is_draped(strand):
        return y_end
    y_hold = strand_hold_y_in(strand)
    length = float(length_ft or 0)
    stations = drape_key_stations_ft(strand, length, hold_downs)
    keys = [(0.0, y_end)] + [(st, y_hold) for st in stations] + [(length, y_end)]
    z = max(0.0, min(length, float(z_ft or 0)))
    for i in range(len(keys) - 1):
        z0, y0 = keys[i]
        z1, y1 = keys[i + 1]
        if z <= z1 or i == len(keys) - 2:
            if z1 == z0:
                return y1
            return y0 + (z - z0) / (z1 - z0) * (y1 - y0)
    return y_end


def assign_strand_grid(strands: List[StrandItem]) -> List[StrandItem]:
    """Assign row/column from the shop-drawing END VIEW (x, end-y)."""
    if not strands:
        return strands
    heights = sorted({round(strand_end_y_in(s), 2) for s in strands})
    height_row = {h: i + 1 for i, h in enumerate(heights)}
    by_row: Dict[int, List[StrandItem]] = {}
    for strand in strands:
        y_end = round(strand_end_y_in(strand), 2)
        strand.row = height_row.get(y_end, 1)
        strand.x_in = float(strand.x_in if strand.x_in is not None else strand.offset_in)
        strand.offset_in = strand.x_in
        if strand.draped or strand.detensioning == "draped":
            if strand.drape_peak_in is None:
                strand.drape_peak_in = y_end
            strand.y_in = float(strand.drape_peak_in)
            if strand.hold_down_y_in is None:
                strand.hold_down_y_in = float(strand.soffit_in or 2.0)
        else:
            strand.y_in = float(strand.y_in if strand.y_in is not None else strand.soffit_in)
            strand.soffit_in = strand.y_in
        if not strand.strand_id:
            strand.strand_id = strand.id
        by_row.setdefault(strand.row, []).append(strand)
    for row_strands in by_row.values():
        ordered = sorted(row_strands, key=lambda s: float(s.x_in if s.x_in is not None else s.offset_in))
        for col, strand in enumerate(ordered, start=1):
            strand.column = col
    return strands


def hold_downs_from_hardware(hardware: List[Any]) -> List[HoldDownItem]:
    items = []
    for raw in hardware or []:
        kind = raw.get("kind") if isinstance(raw, dict) else getattr(raw, "kind", "")
        if kind != "hold_down":
            continue
        if isinstance(raw, dict):
            pos = raw.get("position") or {}
            station = float(pos.get("station_ft") or raw.get("station_from_marked_end") or 0)
            height = float(pos.get("height_from_soffit_in") or raw.get("height") or 2.5)
            offset = float(pos.get("offset_in") or raw.get("offset_in") or 0)
            type_spec = raw.get("type_code") or raw.get("size") or raw.get("name") or "I-beam hold-down"
            qty = int(raw.get("quantity") or 1)
            notes = raw.get("notes") or ""
            hid = raw.get("id") or new_id()
            page = pos.get("page")
        else:
            pos = raw.position
            station = float(pos.station_ft)
            height = float(pos.height_from_soffit_in)
            offset = float(pos.offset_in)
            type_spec = raw.type_code or raw.size or raw.name or "I-beam hold-down"
            qty = int(raw.quantity or 1)
            notes = raw.notes or ""
            hid = raw.id
            page = pos.page
        items.append(HoldDownItem(
            id=hid,
            station_from_marked_end=station,
            height=height,
            offset_in=offset,
            type_spec=type_spec,
            quantity_at_station=max(qty, 1),
            orientation="transverse",
            notes=notes,
            page=page,
        ))
    return items


def ensure_tension_geometry(spec: BeamSpec) -> BeamSpec:
    assign_strand_grid(spec.strands)
    if not spec.hold_downs:
        spec.hold_downs = hold_downs_from_hardware(spec.hardware)
    return spec


def strand_status_key(strand: Dict[str, Any]) -> str:
    if strand.get("na"):
        return "na"
    if strand.get("measured_elongation") is None:
        return "pending"
    if strand.get("within_tolerance") is True:
        return "pass"
    if strand.get("within_tolerance") is False:
        return "fail"
    return "pending"


def hold_down_done(item: Dict[str, Any]) -> bool:
    return item.get("status") in ("verified", "inspected", "released")
