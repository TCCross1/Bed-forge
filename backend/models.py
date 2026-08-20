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
    status: str = "open"  # open | hold | complete
    document_ids: List[str] = Field(default_factory=list)
    notes: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class JobCreate(BaseModel):
    job_number: str
    name: str
    customer: str
    state_spec: str = "AASHTO"


class JobPatch(BaseModel):
    name: Optional[str] = None
    customer: Optional[str] = None
    state_spec: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class OpenJobInput(BaseModel):
    job_id: str


class JobOverrideInput(BaseModel):
    note: str = Field(min_length=8, max_length=2000)
    manager_email: EmailStr
    manager_password: str = Field(min_length=1)


class StrandRollConfirm(BaseModel):
    heat_number: str
    reel_number: Optional[str] = None
    lot_number: Optional[str] = None
    pack_weight: Optional[str] = None
    pack_length: Optional[str] = None
    astm_standard: Optional[str] = None
    strand_grade: Optional[str] = None
    strand_type: Optional[str] = None
    nominal_diameter: Optional[str] = None
    area_in2: Optional[float] = None
    received_date: Optional[str] = None


class StrandRollAssign(BaseModel):
    bed_id: str


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
    spec_id: Optional[str] = None
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
    spec_id: Optional[str] = None
    twin_type: str = "i_beam"
    length_ft: float = 100.0
    position_on_bed: int = 1
    traceability: Dict[str, Any] = Field(default_factory=dict)
    blueprint_document_id: Optional[str] = None
    locked_blueprint_revision_id: Optional[str] = None


class BeamUpdate(BaseModel):
    status: Optional[str] = None
    qc_state: Optional[str] = None
    spec_id: Optional[str] = None
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
    extractor_version: str = "controlled_regex_ocr_v2"
    summary: str = ""
    page_text: List[str] = Field(default_factory=list)
    page_sources: List[str] = Field(default_factory=list)
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


class JobBeamSpec(BaseModel):
    """Per-mark Spec DNA stored with the job after blueprint lock/confirm."""
    id: str = Field(default_factory=new_id)
    job_id: Optional[str] = None
    job_number: str = ""
    beam_mark: str
    beam_id: Optional[str] = None
    document_id: Optional[str] = None
    locked_revision_id: Optional[str] = None
    product_family: str = "i_beam"
    product_type: Optional[str] = None
    identity: Dict[str, Any] = Field(default_factory=dict)
    geometry: Dict[str, Any] = Field(default_factory=dict)
    strand: Dict[str, Any] = Field(default_factory=dict)
    hardware: List[Dict[str, Any]] = Field(default_factory=list)
    stirrup_zones: List[Dict[str, Any]] = Field(default_factory=list)
    finishes: Dict[str, Any] = Field(default_factory=dict)
    qc: Dict[str, Any] = Field(default_factory=dict)
    missing_fields: List[str] = Field(default_factory=list)
    unconfirmed_fields: List[str] = Field(default_factory=list)
    blueprint: Dict[str, Any] = Field(default_factory=dict)
    status: str = "locked"
    section_source: str = "extracted"
    locked_at: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


LEVEL_TOLERANCE_IN = 0.125
ROLL_STATUSES = ["draft", "extracted", "confirmed", "assigned", "depleted"]
LOW_CONFIDENCE = 0.72


class UserAdminCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    name: str
    role: str = "qc_tech"


class UserAdminUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    disabled: Optional[bool] = None
    must_change_password: Optional[bool] = None


class OverrideRequest(BaseModel):
    kind: str
    target_id: str
    reason: str = Field(min_length=8)
    hours: int = 8


class SecuritySettingsUpdate(BaseModel):
    session_minutes: Optional[int] = None
    idle_minutes: Optional[int] = None
    ip_allowlist: Optional[List[str]] = None
    office_ip_enforced: Optional[bool] = None
    bind_device: Optional[bool] = None
    retention_days: Optional[int] = None
    camber_tolerance_in: Optional[float] = None
    length_tolerance_in: Optional[float] = None
    legal_hold: Optional[bool] = None
    ncr_cost_usd: Optional[float] = None
    scrap_cost_usd: Optional[float] = None
    bed_day_cost_usd: Optional[float] = None
    overtime_hold_usd: Optional[float] = None
    required_release_psi: Optional[float] = None
    maturity_su_psi: Optional[float] = None
    maturity_k_hours: Optional[float] = None


class FreshConcreteTest(BaseModel):
    id: str = Field(default_factory=new_id)
    job_id: str
    pour_id: str
    beam_ids: List[str] = Field(default_factory=list)
    bed_id: Optional[str] = None
    test_types: List[str] = Field(default_factory=lambda: ["spread"])
    mix_ticket: str = ""
    load_number: str = ""
    concrete_temp_f: Optional[float] = None
    air_content_pct: Optional[float] = None
    time_sampled: str = Field(default_factory=now_iso)
    spread_d1_in: Optional[float] = None
    spread_d2_in: Optional[float] = None
    spread_avg_in: Optional[float] = None
    t50_sec: Optional[float] = None
    visual_stability: Optional[str] = None
    spread_spec_min_in: Optional[float] = None
    spread_spec_max_in: Optional[float] = None
    slump_in: Optional[float] = None
    slump_spec_min_in: Optional[float] = None
    slump_spec_max_in: Optional[float] = None
    unconstrained_avg_in: Optional[float] = None
    jring_d1_in: Optional[float] = None
    jring_d2_in: Optional[float] = None
    jring_avg_in: Optional[float] = None
    blocking_delta_in: Optional[float] = None
    blocking_assessment: Optional[str] = None
    blocking_label: Optional[str] = None
    blocking_detail: Optional[str] = None
    jring_note: str = "standard J-ring"
    gate: str = "hold"
    notes: str = ""
    inspector: str = ""
    created_at: str = Field(default_factory=now_iso)


class FreshConcreteTestCreate(BaseModel):
    job_id: str
    pour_id: str
    beam_ids: List[str] = Field(default_factory=list)
    bed_id: Optional[str] = None
    test_types: List[str] = Field(default_factory=lambda: ["spread"])
    mix_ticket: str = ""
    load_number: str = ""
    concrete_temp_f: Optional[float] = None
    air_content_pct: Optional[float] = None
    time_sampled: Optional[str] = None
    spread_d1_in: Optional[float] = None
    spread_d2_in: Optional[float] = None
    t50_sec: Optional[float] = None
    visual_stability: Optional[str] = None
    spread_spec_min_in: Optional[float] = None
    spread_spec_max_in: Optional[float] = None
    slump_in: Optional[float] = None
    slump_spec_min_in: Optional[float] = None
    slump_spec_max_in: Optional[float] = None
    unconstrained_avg_in: Optional[float] = None
    jring_d1_in: Optional[float] = None
    jring_d2_in: Optional[float] = None
    jring_note: str = "standard J-ring"
    gate: str = "hold"
    notes: str = ""


class MixDesign(BaseModel):
    id: str = Field(default_factory=new_id)
    mix_code: str
    name: str = ""
    target_strength_psi: Optional[float] = None
    target_air_pct: Optional[float] = None
    target_slump_in: Optional[float] = None
    target_spread_in: Optional[float] = None
    target_temp_f: Optional[float] = None
    notes: str = ""
    ingredients: List[Dict[str, Any]] = Field(default_factory=list)
    created_by: str = ""
    created_at: str = Field(default_factory=now_iso)


class MixDesignCreate(BaseModel):
    mix_code: str
    name: str = ""
    target_strength_psi: Optional[float] = None
    target_air_pct: Optional[float] = None
    target_slump_in: Optional[float] = None
    target_spread_in: Optional[float] = None
    target_temp_f: Optional[float] = None
    notes: str = ""
    ingredients: List[Dict[str, Any]] = Field(default_factory=list)


class BatchRecordUpdate(BaseModel):
    job_id: Optional[str] = None
    pour_id: Optional[str] = None
    bed_ids: Optional[List[str]] = None
    beam_ids: Optional[List[str]] = None
    batched_at: Optional[str] = None
    mixer_operator: Optional[str] = None
    mix_code: Optional[str] = None
    mix_design_id: Optional[str] = None
    target_strength_psi: Optional[float] = None
    target_air_pct: Optional[float] = None
    target_slump_in: Optional[float] = None
    target_spread_in: Optional[float] = None
    target_temp_f: Optional[float] = None
    batch_size: Optional[float] = None
    batch_unit: Optional[str] = None
    mixing_time_sec: Optional[float] = None
    sequence_notes: Optional[str] = None
    truck_id: Optional[str] = None
    deviations: Optional[str] = None
    ingredients: Optional[List[Dict[str, Any]]] = None
    environment: Optional[Dict[str, Any]] = None
    fresh_test_ids: Optional[List[str]] = None
    cylinder_ids: Optional[List[str]] = None


class BatchAmendInput(BaseModel):
    reason: str = Field(min_length=8)
    patch: BatchRecordUpdate


class BatchLinkQcInput(BaseModel):
    fresh_test_ids: Optional[List[str]] = None
    cylinder_ids: Optional[List[str]] = None


class BedAssignment(BaseModel):
    id: str = Field(default_factory=new_id)
    bed_id: str
    beam_id: str
    job_id: Optional[str] = None
    pour_id: Optional[str] = None
    position_on_bed: int = 1
    station_ft: float = 0.0
    marked_end_toward: str = "header"
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


class QrLabelRequest(BaseModel):
    pour_id: Optional[str] = None
    job_id: Optional[str] = None
    beam_ids: Optional[List[str]] = None


class ARMeasurement(BaseModel):
    id: str = Field(default_factory=new_id)
    beam_id: Optional[str] = None
    bed_id: Optional[str] = None
    purpose: str = "level"
    point_a: Dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    point_b: Dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    distance_ft: float = 0.0
    delta_height_in: float = 0.0
    level: bool = False
    forced: bool = False
    confidence: float = 0.0
    sample_count: int = 12
    lidar: bool = False
    engine: str = "web"
    device_class: str = "field"
    device_model: str = ""
    warning: str = ""
    note: str = ""
    photo_data: str = ""
    element_id: Optional[str] = None
    run_id: Optional[str] = None
    station_index: Optional[int] = None
    origin_label: str = ""
    device_id: str = ""
    scale_factor: Optional[float] = None
    created_by: str = ""
    created_at: str = Field(default_factory=now_iso)


class ARMeasurementCreate(BaseModel):
    beam_id: Optional[str] = None
    bed_id: Optional[str] = None
    purpose: str = "level"
    point_a: Dict[str, float]
    point_b: Dict[str, float]
    distance_ft: Optional[float] = None
    delta_height_in: Optional[float] = None
    level: Optional[bool] = None
    forced: bool = False
    confidence: float = 0.0
    sample_count: int = 12
    lidar: bool = False
    engine: str = "web"
    device_class: str = "field"
    device_model: str = ""
    warning: str = ""
    note: str = ""
    photo_data: str = ""
    element_id: Optional[str] = None
    run_id: Optional[str] = None
    station_index: Optional[int] = None
    origin_label: str = ""
    device_id: str = ""


class TapeShotIn(BaseModel):
    station_index: int = 1
    point_b: Dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    distance_ft: Optional[float] = None
    station_ft: Optional[float] = None
    delta_height_in: Optional[float] = None
    level: Optional[bool] = None
    forced: bool = False
    confidence: float = 0.0
    sample_count: int = 12
    note: str = ""
    element_id: Optional[str] = None
    warning: str = ""


class TapeRunCreate(BaseModel):
    beam_id: Optional[str] = None
    bed_id: Optional[str] = None
    purpose: str = "tape"
    origin_label: str = "header"
    point_a: Dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    shots: List[TapeShotIn] = Field(default_factory=list)
    engine: str = "web"
    device_class: str = "field"
    device_model: str = ""
    lidar: bool = False
    note: str = ""
    device_id: str = ""


class TapeRunPreview(BaseModel):
    beam_id: Optional[str] = None
    shots: List[TapeShotIn] = Field(default_factory=list)


class DeviceRegistration(BaseModel):
    id: str = Field(default_factory=new_id)
    platform: str = "ios"
    device_class: str = "field"
    push_token: str = ""
    model: str = ""
    user_id: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class DeviceRegistrationCreate(BaseModel):
    platform: str = "web"
    device_class: str = "field"
    push_token: str = ""
    model: str = ""


class TapeCalibrationCreate(BaseModel):
    device_id: str = ""
    known_length_ft: float
    measured_length_ft: float
    engine: str = "web"
    lidar: bool = False
    device_class: str = "field"
    device_model: str = ""
    note: str = ""


class NCRTransition(BaseModel):
    status: str
    note: str = ""
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    verification_by: Optional[str] = None
    verification_how: Optional[str] = None
    signoff: Optional[str] = None


class StrandRollPhoto(BaseModel):
    id: str = Field(default_factory=new_id)
    kind: str = "tag"
    filename: str = ""
    url: str = ""
    content_type: str = "image/jpeg"
    captured_at: str = Field(default_factory=now_iso)


class StrandRoll(BaseModel):
    id: str = Field(default_factory=new_id)
    reel_number: str = ""
    heat_number: str = ""
    lot_number: str = ""
    pack_weight: str = ""
    pack_length: str = ""
    astm_standard: str = ""
    strand_grade: str = ""
    strand_type: str = "Low-Relaxation"
    nominal_diameter: str = ""
    area_in2: Optional[float] = None
    cert_values: Dict[str, Any] = Field(default_factory=dict)
    photos: List[StrandRollPhoto] = Field(default_factory=list)
    mtc_url: str = ""
    received_date: str = ""
    status: str = "draft"
    extractor: str = ""
    extractor_confidence: float = 0.0
    field_confidence: Dict[str, float] = Field(default_factory=dict)
    raw_text: str = ""
    notes: str = ""
    logged_by: str = ""
    logged_at: str = Field(default_factory=now_iso)
    confirmed_by: str = ""
    confirmed_at: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class StrandRollAssignment(BaseModel):
    id: str = Field(default_factory=new_id)
    roll_id: str
    bed_id: str
    pour_id: Optional[str] = None
    beam_ids: List[str] = Field(default_factory=list)
    allocated_length: Optional[float] = None
    logged_by: str = ""
    logged_at: str = Field(default_factory=now_iso)
    created_at: str = Field(default_factory=now_iso)


class StrandRollAssignInput(BaseModel):
    bed_id: str
    pour_id: Optional[str] = None
    beam_ids: Optional[List[str]] = None
    allocated_length: Optional[float] = None


class CompanySettings(BaseModel):
    id: str = "plant"
    tenant_id: str = "default"
    company_name: str = "PRESTRESS SERVICES INDUSTRIES LLC"
    app_name: str = "BedForge QC"
    tag_header: str = ""
    logo_filename: str = ""
    logo_content_type: str = ""
    updated_by: str = ""
    updated_at: str = Field(default_factory=now_iso)
    created_at: str = Field(default_factory=now_iso)
    session_minutes: int = 480
    idle_minutes: int = 30
    ip_allowlist: List[str] = Field(default_factory=list)
    office_ip_enforced: bool = False
    bind_device: bool = False
    retention_days: int = 2555
    camber_tolerance_in: float = 0.125
    length_tolerance_in: float = 0.5
    legal_hold: bool = False
    ncr_cost_usd: float = 2500.0
    scrap_cost_usd: float = 8000.0
    bed_day_cost_usd: float = 3500.0
    overtime_hold_usd: float = 1800.0
    required_release_psi: float = 4000.0
    maturity_su_psi: float = 8500.0
    maturity_k_hours: float = 18.0


class CompanySettingsUpdate(BaseModel):
    company_name: Optional[str] = None
    app_name: Optional[str] = None
    tag_header: Optional[str] = None


class CylinderJobSlot(BaseModel):
    slot: int = 1
    use_today: bool = False
    qc_tech: str = ""
    job_number: str = ""
    job_id: Optional[str] = None
    expected_beam_count: int = 0
    pour_number: str = ""
    pour_id: Optional[str] = None
    pour_date: str = ""
    cylinder_tags_needed: int = 0
    beam_marks: List[str] = Field(default_factory=list)


class CylinderTagRunInput(BaseModel):
    run_date: Optional[str] = None
    job_count: int = 1
    slots: List[CylinderJobSlot] = Field(default_factory=list)
    notes: str = ""


class CylinderCrushInput(BaseModel):
    crush_psi: Optional[float] = None
    crush_date: Optional[str] = None
    crush_age_days: Optional[int] = None
    required_psi: Optional[float] = None
    release_ok: Optional[bool] = None
    notes: Optional[str] = None


class MaturitySampleCreate(BaseModel):
    pour_id: Optional[str] = None
    bed_id: Optional[str] = None
    beam_id: Optional[str] = None
    temp_f: float
    recorded_at: Optional[str] = None
    source: str = "probe"
    note: str = ""


class OwnerPackageCreate(BaseModel):
    pour_id: str
    include_excel: bool = True
    note: str = ""


class InstrumentReading(BaseModel):
    id: str = Field(default_factory=new_id)
    job_id: Optional[str] = None
    beam_id: Optional[str] = None
    bed_id: Optional[str] = None
    station: str = ""
    purpose: str = "length"
    source: str = "manual"
    device_name: str = ""
    measured_in: float
    target_in: Optional[float] = None
    tolerance_in: float = 0.125
    delta_in: Optional[float] = None
    within_tolerance: bool = True
    status: str = "pass"
    override_note: Optional[str] = None
    override_by: Optional[str] = None
    captured_by: str = ""
    captured_at: str = Field(default_factory=now_iso)
    created_at: str = Field(default_factory=now_iso)


class InstrumentReadingCreate(BaseModel):
    job_id: Optional[str] = None
    beam_id: Optional[str] = None
    bed_id: Optional[str] = None
    station: str = ""
    purpose: str = "length"
    source: str = "manual"
    device_name: str = ""
    measured_in: float
    target_in: Optional[float] = None
    tolerance_in: float = 0.125
    note: str = ""


class InstrumentReadingEvaluateInput(BaseModel):
    measured_in: float
    target_in: Optional[float] = None
    tolerance_in: float = 0.125


class InstrumentReadingOverride(BaseModel):
    note: str = Field(min_length=8, max_length=2000)
