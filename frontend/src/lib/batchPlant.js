/** Batch plant helpers — w/cm live, last mix recall, role gates. Never auto-apply AI dosages. */

export const LAST_BATCH_KEY = "bf_last_batch_identity";
export const LAST_MIX_KEY = "bf_last_mix_code";

export const DEFAULT_INGREDIENTS = [
  { kind: "cement", name: "Type III cement", source: "", size: "", weight_lb: "", moisture_pct: "", dosage: "", dosage_unit: "lb", notes: "" },
  { kind: "scm", name: "Fly ash", source: "", size: "", weight_lb: "", moisture_pct: "", dosage: "", dosage_unit: "lb", notes: "" },
  { kind: "scm", name: "Slag", source: "", size: "", weight_lb: "", moisture_pct: "", dosage: "", dosage_unit: "lb", notes: "" },
  { kind: "coarse", name: "Coarse #67", source: "", size: "#67", weight_lb: "", moisture_pct: "", dosage: "", dosage_unit: "lb", notes: "" },
  { kind: "sand", name: "Sand", source: "", size: "", weight_lb: "", moisture_pct: "", dosage: "", dosage_unit: "lb", notes: "" },
  { kind: "water", name: "Batch water", source: "", size: "", weight_lb: "", moisture_pct: "", dosage: "", dosage_unit: "lb", notes: "" },
  { kind: "ice", name: "Ice / chilled water", source: "", size: "", weight_lb: "", moisture_pct: "", dosage: "", dosage_unit: "lb", notes: "" },
  { kind: "admixture", name: "AEA", source: "", size: "", weight_lb: "", moisture_pct: "", dosage: "", dosage_unit: "oz/cwt", notes: "" },
  { kind: "admixture", name: "HRWR", source: "", size: "", weight_lb: "", moisture_pct: "", dosage: "", dosage_unit: "oz/cwt", notes: "" },
  { kind: "admixture", name: "Retarder", source: "", size: "", weight_lb: "", moisture_pct: "", dosage: "", dosage_unit: "oz/cwt", notes: "" },
  { kind: "admixture", name: "Accelerator", source: "", size: "", weight_lb: "", moisture_pct: "", dosage: "", dosage_unit: "oz/cwt", notes: "" },
  { kind: "admixture", name: "Corrosion inhibitor", source: "", size: "", weight_lb: "", moisture_pct: "", dosage: "", dosage_unit: "oz/cwt", notes: "" },
];

export const BATCH_DRAFT_ROLES = ["production", "admin", "executive"];
export const BATCH_CONFIRM_ROLES = ["admin", "executive"];

export function canDraftBatch(role) {
  return BATCH_DRAFT_ROLES.includes(role);
}

export function canConfirmBatch(role) {
  return BATCH_CONFIRM_ROLES.includes(role);
}

function num(value) {
  if (value === "" || value == null) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function waterCementitiousRatio(ingredients = []) {
  let cem = 0;
  let water = 0;
  ingredients.forEach((item) => {
    const w = num(item.weight_lb) || 0;
    const kind = String(item.kind || "").toLowerCase();
    if (kind === "cement" || kind === "scm") cem += w;
    if (kind === "water" || kind === "ice") water += w;
  });
  if (cem <= 0) return null;
  return Math.round((water / cem) * 10000) / 10000;
}

export function emptyBatchForm() {
  return {
    mix_code: "",
    mix_design_id: "",
    mixer_operator: "",
    target_strength_psi: "",
    target_air_pct: "",
    target_slump_in: "",
    target_spread_in: "",
    target_temp_f: "",
    batch_size: "",
    batch_unit: "yd3",
    mixing_time_sec: "",
    sequence_notes: "",
    truck_id: "",
    deviations: "",
    ingredients: DEFAULT_INGREDIENTS.map((row) => ({ ...row })),
    environment: {
      ambient_f: "",
      mix_temp_f: "",
      rh_pct: "",
      pressure_inhg: "",
      wind_mph: "",
      weather: "",
      solar_proxy: "",
      env_flag: "",
      source: "manual",
      manual_override: false,
      captured_at: "",
    },
  };
}

export function formFromRecord(rec) {
  const base = emptyBatchForm();
  if (!rec) return base;
  return {
    ...base,
    mix_code: rec.mix_code || "",
    mix_design_id: rec.mix_design_id || "",
    mixer_operator: rec.mixer_operator || "",
    target_strength_psi: rec.target_strength_psi ?? "",
    target_air_pct: rec.target_air_pct ?? "",
    target_slump_in: rec.target_slump_in ?? "",
    target_spread_in: rec.target_spread_in ?? "",
    target_temp_f: rec.target_temp_f ?? "",
    batch_size: rec.batch_size ?? "",
    batch_unit: rec.batch_unit || "yd3",
    mixing_time_sec: rec.mixing_time_sec ?? "",
    sequence_notes: rec.sequence_notes || "",
    truck_id: rec.truck_id || "",
    deviations: rec.deviations || "",
    ingredients: (rec.ingredients || []).length ? rec.ingredients.map((row) => ({ ...row })) : base.ingredients,
    environment: { ...base.environment, ...(rec.environment || {}) },
  };
}

export function payloadFromForm(form, identity) {
  const n = (v) => (v === "" || v == null ? null : Number.isFinite(Number(v)) ? Number(v) : null);
  const ingredients = (form.ingredients || []).map((row) => ({
    ...row,
    weight_lb: n(row.weight_lb),
    moisture_pct: n(row.moisture_pct),
    dosage: n(row.dosage),
  }));
  const env = { ...(form.environment || {}) };
  ["ambient_f", "mix_temp_f", "rh_pct", "pressure_inhg", "wind_mph", "lat", "lon"].forEach((k) => {
    env[k] = n(env[k]);
  });
  return {
    job_id: identity.jobId,
    pour_id: identity.pourId,
    bed_ids: identity.bedIds || (identity.bedId ? [identity.bedId] : []),
    beam_ids: identity.beamIds || [],
    mix_code: form.mix_code || "",
    mix_design_id: form.mix_design_id || null,
    mixer_operator: form.mixer_operator || "",
    target_strength_psi: n(form.target_strength_psi),
    target_air_pct: n(form.target_air_pct),
    target_slump_in: n(form.target_slump_in),
    target_spread_in: n(form.target_spread_in),
    target_temp_f: n(form.target_temp_f),
    batch_size: n(form.batch_size),
    batch_unit: form.batch_unit || "yd3",
    mixing_time_sec: n(form.mixing_time_sec),
    sequence_notes: form.sequence_notes || "",
    truck_id: form.truck_id || "",
    deviations: form.deviations || "",
    ingredients,
    environment: env,
  };
}

export function saveLastBatchIdentity({ jobId, pourId, mixCode }) {
  try {
    localStorage.setItem(LAST_BATCH_KEY, JSON.stringify({ jobId: jobId || "", pourId: pourId || "" }));
    if (mixCode) localStorage.setItem(LAST_MIX_KEY, mixCode);
  } catch (err) {
    console.error("[batch] last identity save failed", err);
  }
}

export function readLastBatchIdentity() {
  try {
    return {
      ...(JSON.parse(localStorage.getItem(LAST_BATCH_KEY) || "null") || {}),
      mixCode: localStorage.getItem(LAST_MIX_KEY) || "",
    };
  } catch (err) {
    console.error("[batch] last identity read failed", err);
    return {};
  }
}

export function emptyIntelligenceQuery(form = {}) {
  return {
    mix_code: form.mix_design || form.mix_code || "",
    required_release_psi: form.required_release_psi || 4500,
    required_7d_psi: form.required_7d_psi || "",
    required_28d_psi: form.required_28d_psi || "",
    target_air_pct: form.target_air_pct || 6,
    target_slump_in: form.target_slump_in || 5.5,
    ambient_f: form.ambient_temp_f || form.ambient_f || "",
    rh_pct: form.humidity_pct || form.rh_pct || "",
  };
}

export function formatEnvelopeLine(row) {
  if (!row) return "";
  const unit = row.unit || "";
  return `${row.name}: ${row.min} / ${row.median} / ${row.max} ${unit}`.trim();
}

export function envelopeToTicketText(envelope) {
  const materials = envelope?.materials || [];
  const ingredients = materials.filter((row) => String(row.kind || "").toLowerCase() !== "admixture" && !String(row.unit || "").startsWith("oz"));
  const admixtures = materials.filter((row) => String(row.kind || "").toLowerCase() === "admixture" || String(row.unit || "").startsWith("oz"));
  return {
    ingredientsText: ingredients.map((row) => `${row.name}|${row.median}|${row.median}`).join("\n"),
    admixturesText: admixtures.map((row) => `${row.name}|${row.median}`).join("\n"),
  };
}

export { num as parseBatchNumber };
