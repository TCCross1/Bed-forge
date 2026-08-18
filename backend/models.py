import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Literal
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
    blueprint: Dict[str, Any] = Field(default_factory=dict)
    default_locked_blueprint_revision_id: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class ProductTypeCreate(BaseModel):
    name: str
    category: str
    depth_in: float
    width_in: float
    default_length_ft: float
    description: str = ""
    blueprint: Dict[str, Any] = Field(default_factory=dict)
    default_locked_blueprint_revision_id: Optional[str] = None


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
    traceability: Dict[str, Any] = Field(default_factory=dict)
    blueprint_document_id: Optional[str] = None
    locked_blueprint_revision_id: Optional[str] = None
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
    traceability: Dict[str, Any] = Field(default_factory=dict)
    blueprint_document_id: Optional[str] = None
    locked_blueprint_revision_id: Optional[str] = None


class BeamUpdate(BaseModel):
    status: Optional[str] = None
    qc_state: Optional[str] = None
    traceability: Optional[Dict[str, Any]] = None
    blueprint_document_id: Optional[str] = None
    locked_blueprint_revision_id: Optional[str] = None


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


# ---------- Batch Plant ----------
class BatchRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    pour_id: str
    job_id: Optional[str] = None
    bed_ids: List[str] = Field(default_factory=list)
    beam_ids: List[str] = Field(default_factory=list)
    ticket_number: str
    mix_design: str
    ambient_temp_f: float = 70.0
    concrete_temp_f: float = 72.0
    humidity_pct: float = 50.0
    wind_mph: float = 4.0
    weather: str = "Clear"
    ingredients: List[Dict[str, Any]] = Field(default_factory=list)
    admixtures: List[Dict[str, Any]] = Field(default_factory=list)
    cylinders: List[Dict[str, Any]] = Field(default_factory=list)
    notes: str = ""
    created_by: str = ""
    created_at: str = Field(default_factory=now_iso)


class BatchRecordCreate(BaseModel):
    pour_id: str
    job_id: Optional[str] = None
    bed_ids: List[str] = Field(default_factory=list)
    beam_ids: List[str] = Field(default_factory=list)
    ticket_number: str
    mix_design: str
    ambient_temp_f: float = 70.0
    concrete_temp_f: float = 72.0
    humidity_pct: float = 50.0
    wind_mph: float = 4.0
    weather: str = "Clear"
    ingredients: List[Dict[str, Any]] = Field(default_factory=list)
    admixtures: List[Dict[str, Any]] = Field(default_factory=list)
    cylinders: List[Dict[str, Any]] = Field(default_factory=list)
    notes: str = ""


# ---------- NCR ----------
NCR_STATES = ["open", "investigation", "corrective_action", "verification", "closed"]


class NCR(BaseModel):
    id: str = Field(default_factory=new_id)
    code: str
    title: str
    severity: str = "major"
    status: str = "open"
    beam_id: Optional[str] = None
    pour_id: Optional[str] = None
    batch_record_id: Optional[str] = None
    anomaly_ids: List[str] = Field(default_factory=list)
    inspection_id: Optional[str] = None
    source_measurement: Dict[str, Any] = Field(default_factory=dict)
    investigation: str = ""
    corrective_action: str = ""
    verification: str = ""
    owner: str = ""
    linked_photo_urls: List[str] = Field(default_factory=list)
    audit_trail: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class NCRCreate(BaseModel):
    title: str
    severity: str = "major"
    beam_id: Optional[str] = None
    pour_id: Optional[str] = None
    batch_record_id: Optional[str] = None
    anomaly_ids: List[str] = Field(default_factory=list)
    inspection_id: Optional[str] = None
    source_measurement: Dict[str, Any] = Field(default_factory=dict)
    investigation: str = ""
    corrective_action: str = ""
    verification: str = ""
    owner: str = ""
    linked_photo_urls: List[str] = Field(default_factory=list)


class NCRUpdate(BaseModel):
    title: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    investigation: Optional[str] = None
    corrective_action: Optional[str] = None
    verification: Optional[str] = None
    owner: Optional[str] = None
    linked_photo_urls: Optional[List[str]] = None


# ---------- Licensing ----------
class LicenseState(BaseModel):
    id: str = "license"
    status: str = "trial"  # trial | active | expired
    tier: str = "trial"  # trial | standard | enterprise
    license_key: str = ""
    expires_at: str = ""
    feature_flags: Dict[str, bool] = Field(default_factory=dict)
    last_checked_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    created_at: str = Field(default_factory=now_iso)


class LicenseActivateInput(BaseModel):
    license_key: str = Field(min_length=12)
    tier: Literal["standard", "enterprise"] = "standard"
    expires_at: str


# ---------- Blueprint Intelligence ----------
BLUEPRINT_STATUSES = ["uploaded", "extracted", "needs_review", "locked", "insufficient_quality", "failed"]
BLUEPRINT_FIELD_STATUSES = ["confirmed", "unconfirmed", "manually_confirmed", "not_applicable"]
BLUEPRINT_CONFIDENCE = ["high", "medium", "low"]


class BlueprintField(BaseModel):
    value: Any = None
    confidence: str = "low"
    source_page: Optional[int] = None
    status: str = "unconfirmed"
    extraction_notes: str = ""


class BlueprintDocument(BaseModel):
    id: str = Field(default_factory=new_id)
    filename: str
    storage_path: str
    content_type: str = "application/pdf"
    file_size_bytes: int = 0
    page_count: int = 0
    status: str = "uploaded"
    job_id: Optional[str] = None
    beam_id: Optional[str] = None
    product_type_id: Optional[str] = None
    product_family_hint: str = ""
    beam_mark_hint: str = ""
    project_name_hint: str = ""
    latest_extraction_id: Optional[str] = None
    locked_revision_id: Optional[str] = None
    latest_summary: str = ""
    created_by: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class BlueprintExtraction(BaseModel):
    id: str = Field(default_factory=new_id)
    document_id: str
    status: str = "needs_review"
    extractor_version: str = "controlled_regex_v1"
    summary: str = ""
    page_text: List[str] = Field(default_factory=list)
    field_groups: Dict[str, List[str]] = Field(default_factory=dict)
    fields: Dict[str, BlueprintField] = Field(default_factory=dict)
    confirmed_count: int = 0
    unconfirmed_count: int = 0
    fail_reasons: List[str] = Field(default_factory=list)
    created_by: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class LockedBlueprintRevision(BaseModel):
    id: str = Field(default_factory=new_id)
    document_id: str
    extraction_id: str
    revision_number: int = 1
    status: str = "locked"
    product_family: str
    beam_mark: str
    normalized_blueprint: Dict[str, Any] = Field(default_factory=dict)
    source_fields: Dict[str, BlueprintField] = Field(default_factory=dict)
    beam_ids: List[str] = Field(default_factory=list)
    product_type_id: Optional[str] = None
    notes: str = ""
    locked_by: str = ""
    locked_at: str = Field(default_factory=now_iso)
    created_at: str = Field(default_factory=now_iso)


class BlueprintAuditEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    document_id: str
    event_type: str
    actor_name: str = ""
    actor_role: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)


class BlueprintFieldPatch(BaseModel):
    value: Any = None
    confidence: Optional[str] = None
    source_page: Optional[int] = None
    status: Optional[str] = None
    extraction_notes: Optional[str] = None


class BlueprintExtractionPatch(BaseModel):
    fields: Dict[str, BlueprintFieldPatch] = Field(default_factory=dict)


class BlueprintLockInput(BaseModel):
    beam_ids: List[str] = Field(default_factory=list)
    product_type_id: Optional[str] = None
    notes: str = ""
