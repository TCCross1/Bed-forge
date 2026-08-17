import uuid
import secrets
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, EmailStr


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def new_qr_token() -> str:
    return secrets.token_hex(8)


# ---------- Auth ----------
class UserPublic(BaseModel):
    id: str
    email: str
    name: str
    role: str  # qc_tech | qc_supervisor | production | admin | executive
    disabled: bool = False
    must_change_password: bool = False
    created_at: str


class RegisterInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    name: str
    role: str = "qc_tech"


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class DemoLoginInput(BaseModel):
    role: str = "qc_tech"


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10)


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


# ---------- Fresh / plastic concrete at delivery (not cylinder crush) ----------
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


# ---------- Batch plant (mixer-side; links to Fresh Test + cylinders) ----------
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


class BatchIngredient(BaseModel):
    kind: str = "cement"  # cement | scm | coarse | sand | water | ice | admixture | other
    name: str = ""
    source: str = ""
    size: str = ""
    weight_lb: Optional[float] = None
    moisture_pct: Optional[float] = None
    dosage: Optional[float] = None
    dosage_unit: str = "oz/cwt"
    notes: str = ""


class BatchEnvironment(BaseModel):
    ambient_f: Optional[float] = None
    mix_temp_f: Optional[float] = None
    rh_pct: Optional[float] = None
    pressure_inhg: Optional[float] = None
    wind_mph: Optional[float] = None
    weather: str = ""
    solar_proxy: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    source: str = "manual"
    env_flag: str = ""
    captured_at: str = ""
    manual_override: bool = False


class BatchRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    status: str = "draft"  # draft | confirmed
    immutable: bool = False
    revision: int = 1
    parent_id: Optional[str] = None
    job_id: str
    pour_id: str
    bed_ids: List[str] = Field(default_factory=list)
    beam_ids: List[str] = Field(default_factory=list)
    batched_at: str = Field(default_factory=now_iso)
    mixer_operator: str = ""
    mix_code: str = ""
    mix_design_id: Optional[str] = None
    target_strength_psi: Optional[float] = None
    target_air_pct: Optional[float] = None
    target_slump_in: Optional[float] = None
    target_spread_in: Optional[float] = None
    target_temp_f: Optional[float] = None
    batch_size: Optional[float] = None
    batch_unit: str = "yd3"
    mixing_time_sec: Optional[float] = None
    sequence_notes: str = ""
    truck_id: str = ""
    deviations: str = ""
    ingredients: List[Dict[str, Any]] = Field(default_factory=list)
    environment: Dict[str, Any] = Field(default_factory=dict)
    cementitious_lb: Optional[float] = None
    water_lb: Optional[float] = None
    w_cm: Optional[float] = None
    fresh_test_ids: List[str] = Field(default_factory=list)
    cylinder_ids: List[str] = Field(default_factory=list)
    confirmed_by: str = ""
    confirmed_at: Optional[str] = None
    created_by: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class BatchRecordCreate(BaseModel):
    job_id: str
    pour_id: str
    bed_ids: List[str] = Field(default_factory=list)
    beam_ids: List[str] = Field(default_factory=list)
    batched_at: Optional[str] = None
    mixer_operator: str = ""
    mix_code: str = ""
    mix_design_id: Optional[str] = None
    target_strength_psi: Optional[float] = None
    target_air_pct: Optional[float] = None
    target_slump_in: Optional[float] = None
    target_spread_in: Optional[float] = None
    target_temp_f: Optional[float] = None
    batch_size: Optional[float] = None
    batch_unit: str = "yd3"
    mixing_time_sec: Optional[float] = None
    sequence_notes: str = ""
    truck_id: str = ""
    deviations: str = ""
    ingredients: List[Dict[str, Any]] = Field(default_factory=list)
    environment: Dict[str, Any] = Field(default_factory=dict)
    fresh_test_ids: List[str] = Field(default_factory=list)
    cylinder_ids: List[str] = Field(default_factory=list)
    copy_from_id: Optional[str] = None


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
    qr_token: str = Field(default_factory=new_qr_token)
    qr_created_at: str = Field(default_factory=now_iso)
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


class QrLabelRequest(BaseModel):
    pour_id: Optional[str] = None
    job_id: Optional[str] = None
    beam_ids: Optional[List[str]] = None


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


class NCR(BaseModel):
    id: str = Field(default_factory=new_id)
    status: str = "open"
    severity: str = "minor"
    category: str = "visual"
    sub_type: str = ""
    description: str = ""
    containment: str = ""
    root_cause: str = ""
    corrective_action: str = ""
    preventive_action: str = ""
    verification_how: str = ""
    verification_by: str = ""
    signoff: str = ""
    assigned_to: str = ""
    assigned_role: str = ""
    beam_ids: List[str] = Field(default_factory=list)
    job_id: str = ""
    pour_id: str = ""
    bed_id: str = ""
    batch_id: str = ""
    mix_code: str = ""
    anomaly_id: str = ""
    source_type: str = "manual"
    source_id: str = ""
    twin_position: Dict[str, Any] = Field(default_factory=dict)
    photos: List[str] = Field(default_factory=list)
    discovered_by: str = ""
    created_by: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    closed_at: Optional[str] = None
    closed_by: str = ""
    history: List[Dict[str, Any]] = Field(default_factory=list)


class NCRCreate(BaseModel):
    beam_ids: List[str] = Field(default_factory=list)
    beam_id: Optional[str] = None
    job_id: str = ""
    pour_id: str = ""
    bed_id: str = ""
    batch_id: str = ""
    mix_code: str = ""
    anomaly_id: str = ""
    source_type: str = "manual"
    source_id: str = ""
    category: str = "visual"
    sub_type: str = ""
    severity: str = "minor"
    description: str = ""
    containment: str = ""
    twin_position: Dict[str, Any] = Field(default_factory=dict)
    photos: List[str] = Field(default_factory=list)
    assigned_to: str = ""
    assigned_role: str = ""


class NCRUpdate(BaseModel):
    description: Optional[str] = None
    containment: Optional[str] = None
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    preventive_action: Optional[str] = None
    verification_how: Optional[str] = None
    verification_by: Optional[str] = None
    signoff: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_role: Optional[str] = None
    category: Optional[str] = None
    sub_type: Optional[str] = None
    severity: Optional[str] = None
    batch_id: Optional[str] = None
    mix_code: Optional[str] = None
    beam_ids: Optional[List[str]] = None
    job_id: Optional[str] = None
    pour_id: Optional[str] = None
    bed_id: Optional[str] = None


class NCRTransition(BaseModel):
    status: str
    note: str = ""
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    verification_by: Optional[str] = None
    verification_how: Optional[str] = None
    signoff: Optional[str] = None


LEVEL_TOLERANCE_IN = 0.125  # 1/8"


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


# ---------- Strand roll mill traceability ----------
ROLL_STATUSES = ["draft", "extracted", "confirmed", "assigned", "depleted"]
LOW_CONFIDENCE = 0.72


class StrandRollPhoto(BaseModel):
    id: str = Field(default_factory=new_id)
    kind: str = "tag"  # tag | mtc
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


class StrandRollConfirm(BaseModel):
    reel_number: Optional[str] = None
    heat_number: Optional[str] = None
    lot_number: Optional[str] = None
    pack_weight: Optional[str] = None
    pack_length: Optional[str] = None
    astm_standard: Optional[str] = None
    strand_grade: Optional[str] = None
    strand_type: Optional[str] = None
    nominal_diameter: Optional[str] = None
    area_in2: Optional[float] = None
    cert_values: Optional[Dict[str, Any]] = None
    received_date: Optional[str] = None
    notes: Optional[str] = None


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


# ---------- Multi-company / white-label ----------
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


# ---------- Cylinder tag generator ----------
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
