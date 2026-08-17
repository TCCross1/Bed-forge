/** Plastic / fresh concrete ticket math — ASTM C1611 spread, C143 slump, C1621 J-ring. */

export const LAST_IDENTITY_KEY = "bf_fresh_identity";
export const DEMO_MARK = "L25390-B1";
export const ACTIVE_BED_STATES = ["tensioning", "casting"];
export const DEFAULT_TEST_TYPES = ["spread"];

export const BLOCKING_PASS_MAX_IN = 1.0;
export const BLOCKING_BORDERLINE_MAX_IN = 2.0;

export function parseInches(value) {
  if (value === "" || value == null) return null;
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  return number;
}

export function diameterAverage(d1, d2) {
  const vals = [parseInches(d1), parseInches(d2)].filter((v) => v != null);
  if (!vals.length) return null;
  return Math.round((vals.reduce((s, v) => s + v, 0) / vals.length) * 1000) / 1000;
}

export function blockingDelta(unconstrainedAvg, jringAvg) {
  const unconstrained = parseInches(unconstrainedAvg);
  const jring = parseInches(jringAvg);
  if (unconstrained == null || jring == null) return null;
  return Math.round((unconstrained - jring) * 1000) / 1000;
}

export function blockingAssessment(deltaIn) {
  const delta = parseInches(deltaIn);
  if (delta == null) return null;
  if (delta <= BLOCKING_PASS_MAX_IN) {
    return { code: "pass", label: "PASS", detail: "No visible blocking (0–1 in)", color: "#00E676" };
  }
  if (delta <= BLOCKING_BORDERLINE_MAX_IN) {
    return { code: "borderline", label: "BORDERLINE", detail: "Minimal to notable blocking (1–2 in)", color: "#FFD600" };
  }
  return { code: "blocking", label: "BLOCKING", detail: "Noticeable blocking (>2 in)", color: "#FF3366" };
}

export function applyComputedFields(data = {}) {
  const spreadAvg = diameterAverage(data.spread_d1_in, data.spread_d2_in);
  const jringAvg = diameterAverage(data.jring_d1_in, data.jring_d2_in);
  const unconstrained = parseInches(data.unconstrained_avg_in) != null
    ? parseInches(data.unconstrained_avg_in)
    : spreadAvg;
  const delta = blockingDelta(unconstrained, jringAvg);
  const assess = blockingAssessment(delta);
  return {
    ...data,
    spread_avg_in: spreadAvg,
    jring_avg_in: jringAvg,
    unconstrained_avg_in: unconstrained,
    blocking_delta_in: delta,
    blocking_assessment: assess?.code || null,
    blocking_label: assess?.label || null,
    blocking_detail: assess?.detail || null,
  };
}

export function saveLastIdentity({ jobId, pourId }) {
  try {
    localStorage.setItem(LAST_IDENTITY_KEY, JSON.stringify({ jobId: jobId || "", pourId: pourId || "" }));
  } catch (err) {
    console.error("[fresh] last identity save failed", err);
  }
}

export function readLastIdentity() {
  try {
    return JSON.parse(localStorage.getItem(LAST_IDENTITY_KEY) || "null") || {};
  } catch (err) {
    console.error("[fresh] last identity read failed", err);
    return {};
  }
}

function matchIdOrCode(list, raw, codeKey) {
  const needle = String(raw || "").trim();
  if (!needle) return null;
  return (list || []).find((row) => row.id === needle || String(row[codeKey] || "") === needle) || null;
}

function matchBeam(beams, raw) {
  const needle = String(raw || "").trim();
  if (!needle) return null;
  return (beams || []).find((b) => b.id === needle || b.mark === needle) || null;
}

export function pickIdentity({ jobs = [], pours = [], beams = [], beds = [], plant = null, query = {}, last = {} } = {}) {
  const queryBeam = matchBeam(beams, query.beam);
  let job = matchIdOrCode(jobs, query.job, "job_number")
    || (queryBeam && jobs.find((j) => j.id === queryBeam.job_id))
    || matchIdOrCode(jobs, last.jobId, "job_number");
  let pour = matchIdOrCode(pours, query.pour, "pour_number")
    || (queryBeam && pours.find((p) => p.id === queryBeam.pour_id))
    || (job && matchIdOrCode(pours.filter((p) => p.job_id === job.id), last.pourId, "pour_number"))
    || (job && (pours.find((p) => p.id === last.pourId && p.job_id === job.id)))
    || null;

  if (!job && last.jobId) job = jobs.find((j) => j.id === last.jobId) || null;
  if (!pour && last.pourId) {
    const remembered = pours.find((p) => p.id === last.pourId);
    if (remembered && (!job || remembered.job_id === job.id)) pour = remembered;
  }

  const demoBeam = beams.find((b) => b.mark === DEMO_MARK) || null;
  const activeBeds = (beds || []).filter((b) => ACTIVE_BED_STATES.includes(b.status));
  const plantBeds = plant?.beds || [];
  const activePlant = plantBeds.find((row) => ACTIVE_BED_STATES.includes(row.bed?.status));
  const plantBeamId = activePlant?.active_beam_id
    || activePlant?.assignments?.find((a) => a.beam?.mark === DEMO_MARK)?.beam_id
    || activePlant?.assignments?.[0]?.beam_id
    || demoBeam?.id;

  if (!queryBeam && !query.job && !query.pour) {
    if (!job && demoBeam) job = jobs.find((j) => j.id === demoBeam.job_id) || job;
    if (!pour && demoBeam) pour = pours.find((p) => p.id === demoBeam.pour_id) || pour;
    if (!job && plantBeamId) {
      const pb = beams.find((b) => b.id === plantBeamId);
      if (pb) {
        job = jobs.find((j) => j.id === pb.job_id) || job;
        pour = pours.find((p) => p.id === pb.pour_id) || pour;
      }
    }
  }

  if (!job && jobs[0]) job = jobs[0];
  if (job && !pour) {
    const jobPours = pours.filter((p) => p.job_id === job.id);
    pour = jobPours.find((p) => p.status === "active") || jobPours[0] || null;
  }
  if (pour && job && pour.job_id !== job.id) {
    job = jobs.find((j) => j.id === pour.job_id) || job;
  }

  const pourBeams = pour ? beams.filter((b) => b.pour_id === pour.id) : [];
  let beamIds = [];
  if (queryBeam && (!pour || queryBeam.pour_id === pour.id)) {
    beamIds = [queryBeam.id];
  } else if (pourBeams.length === 1) {
    beamIds = [pourBeams[0].id];
  } else {
    const activeIds = new Set(activeBeds.map((b) => b.id));
    const onActive = pourBeams.filter((b) => activeIds.has(b.bed_id));
    if (onActive.length) beamIds = onActive.map((b) => b.id);
    else if (demoBeam && pourBeams.some((b) => b.id === demoBeam.id)) beamIds = [demoBeam.id];
    else beamIds = [];
  }

  const selected = beams.filter((b) => beamIds.includes(b.id));
  const bedIds = [...new Set(selected.map((b) => b.bed_id).filter(Boolean))];
  const bedId = bedIds.length === 1 ? bedIds[0] : (query.bed || "");

  return {
    jobId: job?.id || "",
    pourId: pour?.id || "",
    beamIds,
    bedId,
  };
}

export function gateColor(gate) {
  if (gate === "pass") return "#00E676";
  if (gate === "fail") return "#FF3366";
  return "#FFD600";
}

export function stampNowIso() {
  return new Date().toISOString();
}

export function formatStamp(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  } catch (err) {
    return iso;
  }
}
