/** Strand-roll field map, confidence helpers, and offline photo queue. */

export const ROLL_FIELDS = [
  { key: "heat_number", label: "Heat Number", critical: true },
  { key: "reel_number", label: "Reel / Pack / Coil" },
  { key: "lot_number", label: "Lot / Production No." },
  { key: "pack_weight", label: "Pack Weight" },
  { key: "pack_length", label: "Pack Length" },
  { key: "astm_standard", label: "ASTM Standard" },
  { key: "strand_grade", label: "Strand Grade" },
  { key: "strand_type", label: "Strand Type" },
  { key: "nominal_diameter", label: "Nominal Diameter" },
  { key: "area_in2", label: "Area (in²)" },
  { key: "received_date", label: "Received Date" },
];

export const LOW_CONFIDENCE = 0.72;
export const QUEUE_KEY = "bf_strand_roll_queue";

export function isLowConfidence(roll, key) {
  const score = Number(roll?.field_confidence?.[key]);
  if (Number.isFinite(score)) return score < LOW_CONFIDENCE;
  return (roll?.low_confidence_fields || []).includes(key);
}

export function loadQueue() {
  try {
    const raw = JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
    return Array.isArray(raw) ? raw : [];
  } catch (err) {
    console.error("[rolls] queue parse failed", err);
    return [];
  }
}

export function saveQueue(items) {
  try {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(items.slice(0, 5)));
  } catch (err) {
    console.error("[rolls] queue save failed", err);
  }
}

export function enqueueRollJob(job) {
  const next = [...loadQueue(), { ...job, queued_at: new Date().toISOString() }];
  saveQueue(next);
  return next;
}

export function dequeueRollJob(id) {
  const next = loadQueue().filter((item) => item.id !== id);
  saveQueue(next);
  return next;
}

export function dataUrlToFile(dataUrl, filename, kind) {
  const [meta, body] = String(dataUrl || "").split(",");
  const mime = (meta.match(/data:(.*?);/) || [])[1] || "image/jpeg";
  const binary = atob(body || "");
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  const file = new File([bytes], filename || `${kind || "tag"}.jpg`, { type: mime });
  return file;
}
