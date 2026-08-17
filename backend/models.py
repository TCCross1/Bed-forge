import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, EmailStr


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


# ---------- Auth ----------
class UserPublic(BaseModel):
    id: str
    email: str
    name: str
    role: str  # qc_tech | qc_supervisor | production | admin
    created_at: str


class RegisterInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str
    role: str = "qc_tech"


class LoginInput(BaseModel):
    email: EmailStr
    password: str


# ---------- Product Types ----------
class ProductType(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    category: str  # i_beam | box_beam
    depth_in: float
    width_in: float
    default_length_ft: float
    description: str = ""
    created_at: str = Field(default_factory=now_iso)


class ProductTypeCreate(BaseModel):
    name: str
    category: str
    depth_in: float
    width_in: float
    default_length_ft: float
    description: str = ""


# ---------- Jobs ----------
class Job(BaseModel):
    id: str = Field(default_factory=new_id)
    job_number: str
    name: str
    customer: str
    state_spec: str = "AASHTO"
    created_at: str = Field(default_factory=now_iso)


class JobCreate(BaseModel):
    job_number: str
    name: str
    customer: str
    state_spec: str = "AASHTO"


# ---------- Pours ----------
class Pour(BaseModel):
    id: str = Field(default_factory=new_id)
    job_id: str
    pour_number: str
    pour_date: str
    concrete_mix: str = ""
    status: str = "scheduled"  # scheduled | active | complete
    created_at: str = Field(default_factory=now_iso)


class PourCreate(BaseModel):
    job_id: str
    pour_number: str
    pour_date: str
    concrete_mix: str = ""
    status: str = "scheduled"


# ---------- Beds ----------
BED_STATES = ["idle", "setup", "tensioning", "casting", "curing", "stripping", "complete"]


class Bed(BaseModel):
    id: str = Field(default_factory=new_id)
    bed_number: int
    name: str
    length_ft: float = 300.0
    status: str = "idle"
    current_pour_id: Optional[str] = None
    active_beam_id: Optional[str] = None
    header_label: str = "HEADER / LIVE END"
    bulkhead_label: str = "BULKHEAD / DEAD END"
    updated_at: str = Field(default_factory=now_iso)
    created_at: str = Field(default_factory=now_iso)


class BedUpdate(BaseModel):
    status: Optional[str] = None
    current_pour_id: Optional[str] = None
    active_beam_id: Optional[str] = None


PRODUCTION_STATES = ["planned", "forming", "stressed", "poured", "cured", "released"]


class BedAssignment(BaseModel):
    """Authoritative order of a beam on a bed for a scheduled cycle."""
    id: str = Field(default_factory=new_id)
    bed_id: str
    beam_id: str
    job_id: Optional[str] = None
    pour_id: Optional[str] = None
    position_on_bed: int = 1
    station_ft: float = 0.0
    marked_end_toward: str = "header"  # header | bulkhead
    scheduled_date: str
    scheduled_end_date: Optional[str] = None
    actual_start: Optional[str] = None
    actual_end: Optional[str] = None
    production_status: str = "planned"
    notes: str = ""
    created_by: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class BedAssignmentCreate(BaseModel):
    bed_id: str
    beam_id: str
    job_id: Optional[str] = None
    pour_id: Optional[str] = None
    position_on_bed: Optional[int] = None
    marked_end_toward: str = "header"
    scheduled_date: str
    scheduled_end_date: Optional[str] = None
    production_status: Optional[str] = None
    notes: str = ""


class BedAssignmentUpdate(BaseModel):
    bed_id: Optional[str] = None
    position_on_bed: Optional[int] = None
    marked_end_toward: Optional[str] = None
    scheduled_date: Optional[str] = None
    scheduled_end_date: Optional[str] = None
    actual_start: Optional[str] = None
    actual_end: Optional[str] = None
    production_status: Optional[str] = None
    notes: Optional[str] = None


class BedReorder(BaseModel):
    date: str
    assignment_ids: List[str]


# ---------- Beams ----------
BEAM_QC_STATES = ["pending", "in_progress", "passed", "hold", "failed", "shipped"]


class Beam(BaseModel):
    id: str = Field(default_factory=new_id)
    mark: str
    bed_id: str
    pour_id: Optional[str] = None
    job_id: Optional[str] = None
    product_type_id: Optional[str] = None
    twin_type: str = "i_beam"  # i_beam | box_beam
    length_ft: float = 100.0
    position_on_bed: int = 1
    status: str = "casting"
    qc_state: str = "pending"
    production_status: str = "planned"
    created_at: str = Field(default_factory=now_iso)


class BeamCreate(BaseModel):
    mark: str
    bed_id: str
    pour_id: Optional[str] = None
    job_id: Optional[str] = None
    product_type_id: Optional[str] = None
    twin_type: str = "i_beam"
    length_ft: float = 100.0
    position_on_bed: int = 1
    production_status: str = "planned"


class BeamUpdate(BaseModel):
    status: Optional[str] = None
    qc_state: Optional[str] = None
    bed_id: Optional[str] = None
    position_on_bed: Optional[int] = None
    production_status: Optional[str] = None
    pour_id: Optional[str] = None
    job_id: Optional[str] = None


# ---------- Inspections (QIR sections) ----------
class Inspection(BaseModel):
    id: str = Field(default_factory=new_id)
    beam_id: str
    section: str  # layout | reinforcement | casting | concrete_testing | post_production | detailing
    status: str = "open"  # open | pass | fail | hold
    data: Dict[str, Any] = Field(default_factory=dict)
    inspector: str = ""
    notes: str = ""
    created_at: str = Field(default_factory=now_iso)


class InspectionCreate(BaseModel):
    beam_id: str
    section: str
    status: str = "open"
    data: Dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


# ---------- Tension Reports ----------
class TensionReport(BaseModel):
    id: str = Field(default_factory=new_id)
    bed_id: str
    pour_id: Optional[str] = None
    strand_size: str = "0.6in"
    strand_area_in2: float = 0.217
    modulus_ksi: float = 28500.0
    bed_length_ft: float = 400.0
    jacking_force_kip: float = 43.94
    num_strands: int = 1
    theoretical_elongation_in: float = 0.0
    measured_elongation_in: float = 0.0
    variance_pct: float = 0.0
    within_tolerance: bool = True
    created_at: str = Field(default_factory=now_iso)


class TensionCalcInput(BaseModel):
    strand_area_in2: float = 0.217
    modulus_ksi: float = 28500.0
    bed_length_ft: float = 400.0
    jacking_force_kip: float = 43.94
    measured_elongation_in: Optional[float] = None


class TensionReportCreate(TensionCalcInput):
    bed_id: str
    pour_id: Optional[str] = None
    strand_size: str = "0.6in"
    num_strands: int = 1


# ---------- Camber Readings (3-point) ----------
class CamberReading(BaseModel):
    id: str = Field(default_factory=new_id)
    beam_id: str
    design_camber_in: float = 0.0
    measured_camber_in: float = 0.0
    marked_end_in: float = 0.0
    midspan_in: float = 0.0
    unmarked_end_in: float = 0.0
    release_strength_psi: float = 0.0
    required_strength_psi: float = 0.0
    notes: str = ""
    inspector: str = ""
    reading_date: str = Field(default_factory=now_iso)
    created_at: str = Field(default_factory=now_iso)


class CamberReadingCreate(BaseModel):
    beam_id: str
    design_camber_in: float = 0.0
    measured_camber_in: float = 0.0
    marked_end_in: float = 0.0
    midspan_in: float = 0.0
    unmarked_end_in: float = 0.0
    release_strength_psi: float = 0.0
    required_strength_psi: float = 0.0
    notes: str = ""


# ---------- Finish Sheet ----------
class FinishSheet(BaseModel):
    id: str = Field(default_factory=new_id)
    beam_id: str
    pour_id: Optional[str] = None
    strand_cut_flush: bool = False
    strand_recessed: bool = False
    strand_grouted: bool = False
    strand_treatment_notes: str = ""
    hardware_complete: bool = False
    hardware_notes: str = ""
    surface_finish: str = "trowel"
    surface_pass: bool = False
    surface_notes: str = ""
    marked_end_id: str = ""
    marked_end_verified: bool = False
    lifting_devices_ok: bool = False
    voids_grouted: bool = False
    inspector: str = ""
    status: str = "open"
    notes: str = ""
    created_at: str = Field(default_factory=now_iso)


class FinishSheetCreate(BaseModel):
    beam_id: str
    pour_id: Optional[str] = None
    strand_cut_flush: bool = False
    strand_recessed: bool = False
    strand_grouted: bool = False
    strand_treatment_notes: str = ""
    hardware_complete: bool = False
    hardware_notes: str = ""
    surface_finish: str = "trowel"
    surface_pass: bool = False
    surface_notes: str = ""
    marked_end_id: str = ""
    marked_end_verified: bool = False
    lifting_devices_ok: bool = False
    voids_grouted: bool = False
    status: str = "open"
    notes: str = ""


# ---------- Pre-Delivery / Release ----------
class PreDelivery(BaseModel):
    id: str = Field(default_factory=new_id)
    beam_id: str
    dimensional_check: bool = False
    camber_verified: bool = False
    finish_complete: bool = False
    hardware_installed: bool = False
    marked_end_id_verified: bool = False
    cracks_documented: bool = False
    truck_number: str = ""
    destination: str = ""
    load_position: str = ""
    qc_signoff: str = ""
    production_signoff: str = ""
    carrier_signoff: str = ""
    released: bool = False
    release_at: Optional[str] = None
    inspector: str = ""
    notes: str = ""
    created_at: str = Field(default_factory=now_iso)


class PreDeliveryCreate(BaseModel):
    beam_id: str
    dimensional_check: bool = False
    camber_verified: bool = False
    finish_complete: bool = False
    hardware_installed: bool = False
    marked_end_id_verified: bool = False
    cracks_documented: bool = False
    truck_number: str = ""
    destination: str = ""
    load_position: str = ""
    qc_signoff: str = ""
    production_signoff: str = ""
    carrier_signoff: str = ""
    released: bool = False
    notes: str = ""


# ---------- Anomalies / Crack Map ----------
class Anomaly(BaseModel):
    id: str = Field(default_factory=new_id)
    beam_id: str
    type: str = "crack"  # crack | spall | honeycomb | chip | stain | other
    severity: str = "minor"  # minor | moderate | major
    position: Dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    length_in: float = 0.0
    note: str = ""
    photo_url: str = ""
    inspector: str = ""
    created_at: str = Field(default_factory=now_iso)


class AnomalyCreate(BaseModel):
    beam_id: str
    type: str = "crack"
    severity: str = "minor"
    position: Dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    length_in: float = 0.0
    note: str = ""
    photo_url: str = ""
