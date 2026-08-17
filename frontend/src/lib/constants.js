export const ROLE_LABELS = {
  admin: "Admin",
  qc_supervisor: "QC Supervisor",
  qc_tech: "QC Tech",
  production: "Production",
};

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
