export const ROLE_LABELS = {
  admin: "Plant Manager",
  executive: "Executive",
  qc_supervisor: "QC Supervisor",
  qc_tech: "QC Tech",
  production: "Production",
};

export const EXEC_ROLES = ["admin", "executive"];
export const isExec = (role) => EXEC_ROLES.includes(role);

export const BED_STATE_STYLES = {
  idle: { label: "IDLE", color: "#8B949E", dot: "#8B949E" },
  setup: { label: "SETUP", color: "#2979FF", dot: "#2979FF" },
  tensioning: { label: "TENSIONING", color: "#FFD600", dot: "#FFD600" },
  casting: { label: "CASTING", color: "#FFD600", dot: "#FFD600" },
  curing: { label: "CURING", color: "#2979FF", dot: "#2979FF" },
  stripping: { label: "STRIPPING", color: "#FFD600", dot: "#FFD600" },
  complete: { label: "COMPLETE", color: "#00E676", dot: "#00E676" },
};

export const QC_STATE_STYLES = {
  pending: { label: "PENDING", color: "#8B949E" },
  in_progress: { label: "IN PROGRESS", color: "#2979FF" },
  passed: { label: "PASSED", color: "#00E676" },
  hold: { label: "HOLD", color: "#FFD600" },
  failed: { label: "FAILED", color: "#FF3366" },
  shipped: { label: "SHIPPED", color: "#00E676" },
};

export const bedState = (s) => BED_STATE_STYLES[s] || BED_STATE_STYLES.idle;
export const qcState = (s) => QC_STATE_STYLES[s] || QC_STATE_STYLES.pending;

export const PRODUCTION_STATUS_STYLES = {
  planned: { label: "PLANNED", color: "#8B949E" },
  forming: { label: "FORMING", color: "#2979FF" },
  stressed: { label: "STRESSED", color: "#FFD600" },
  poured: { label: "POURED", color: "#FF9100" },
  cured: { label: "CURED", color: "#00BCD4" },
  released: { label: "RELEASED", color: "#00E676" },
};

export const productionStatus = (s) => PRODUCTION_STATUS_STYLES[s] || PRODUCTION_STATUS_STYLES.planned;

export const RELEASE_FORECAST_STYLES = {
  expected_pass: { label: "Expected Pass", color: "#00E676" },
  confirmed_pass: { label: "Crush Pass", color: "#00E676" },
  borderline: { label: "Borderline", color: "#FFD600" },
  fail_risk: { label: "Fail Risk", color: "#FF3366" },
  confirmed_fail: { label: "Crush Fail", color: "#FF3366" },
  unknown: { label: "No maturity", color: "#8B949E" },
};

export const releaseForecast = (s) => RELEASE_FORECAST_STYLES[s] || RELEASE_FORECAST_STYLES.unknown;

export const PLAN_ROLES = ["admin", "executive", "qc_supervisor", "production"];
export const canPlan = (role) => PLAN_ROLES.includes(role);
