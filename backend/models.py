import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
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
    state_spec: str = "AASHTO"  # controlling DOT/state tolerance spec
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
    length_ft: float = 400.0
    status: str = "idle"
    current_pour_id: Optional[str] = None
    updated_at: str = Field(default_factory=now_iso)
    created_at: str = Field(default_factory=now_iso)


class BedUpdate(BaseModel):
    status: Optional[str] = None
    current_pour_id: Optional[str] = None


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
    status: str = "casting"  # production status
    qc_state: str = "pending"
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


class BeamUpdate(BaseModel):
    status: Optional[str] = None
    qc_state: Optional[str] = None


# ---------- Inspections (QIR sections) ----------
class Inspection(BaseModel):
    id: str = Field(default_factory=new_id)
    beam_id: str
    section: str  # pre_pour | forms | strand | concrete | finish | camber | pre_delivery
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


# ---------- Camber Readings ----------
class CamberReading(BaseModel):
    id: str = Field(default_factory=new_id)
    beam_id: str
    design_camber_in: float = 0.0
    measured_camber_in: float = 0.0
    release_strength_psi: float = 0.0
    required_strength_psi: float = 0.0
    reading_date: str = Field(default_factory=now_iso)
    created_at: str = Field(default_factory=now_iso)


class CamberReadingCreate(BaseModel):
    beam_id: str
    design_camber_in: float = 0.0
    measured_camber_in: float = 0.0
    release_strength_psi: float = 0.0
    required_strength_psi: float = 0.0


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
