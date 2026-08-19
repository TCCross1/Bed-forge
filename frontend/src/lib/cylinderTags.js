/** Cylinder tag math — keep in sync with backend/cylinder_tags.py */

export const MAX_SLOTS = 10;
export const MAX_BEAMS = 30;
export const BEAMS_PER_LABEL = 6;
export const STATUS_READY = "READY TO PRINT";
export const STATUS_INCOMPLETE = "INCOMPLETE";
export const STATUS_UNUSED = "NOT USED";

export function todayISO() {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

export function emptySlot(index, qcTech = "", pourDate = "") {
  return {
    slot: index,
    use_today: index === 1,
    qc_tech: qcTech || "",
    job_number: "",
    job_id: "",
    expected_beam_count: 0,
    pour_number: "",
    pour_id: "",
    pour_date: pourDate || todayISO(),
    cylinder_tags_needed: 0,
    beam_marks: Array.from({ length: MAX_BEAMS }, () => ""),
  };
}

export function emptyRun(qcTech = "", runDate = "") {
  const date = runDate || todayISO();
  return {
    run_date: date,
    job_count: 1,
    notes: "",
    slots: Array.from({ length: MAX_SLOTS }, (_, i) => emptySlot(i + 1, qcTech, date)),
  };
}

export function cleanBeams(marks) {
  return (marks || []).map((m) => String(m || "").trim()).filter(Boolean).slice(0, MAX_BEAMS);
}

export function labelsPerCylinder(count) {
  const n = Number(count) || 0;
  if (n <= 0) return 0;
  return Math.ceil(n / BEAMS_PER_LABEL);
}

export function slotStatus(slot) {
  if (!slot?.use_today) return STATUS_UNUSED;
  const beams = cleanBeams(slot.beam_marks);
  if (!String(slot.job_number || "").trim() || !String(slot.qc_tech || "").trim() || !beams.length || Number(slot.cylinder_tags_needed) < 1) {
    return STATUS_INCOMPLETE;
  }
  return STATUS_READY;
}

export function summarizeSlot(slot, cumulativeBefore = 0) {
  const beams = cleanBeams(slot?.beam_marks);
  const status = slotStatus(slot);
  const per = status === STATUS_UNUSED ? 0 : labelsPerCylinder(beams.length);
  const needed = Number(slot?.cylinder_tags_needed) || 0;
  const physical = status === STATUS_READY ? per * needed : 0;
  return {
    slot: slot?.slot,
    use_today: Boolean(slot?.use_today),
    qc_tech: slot?.qc_tech || "",
    job_number: slot?.job_number || "",
    pour_number: slot?.pour_number || "",
    pour_date: slot?.pour_date || "",
    expected_beam_count: Number(slot?.expected_beam_count) || 0,
    entered_beam_count: beams.length,
    beam_list: beams,
    cylinder_tags_needed: needed,
    labels_per_cylinder: per,
    physical_labels: physical,
    cumulative_labels: cumulativeBefore + physical,
    status,
  };
}

export function summarizeRun(run) {
  const count = Math.max(1, Math.min(MAX_SLOTS, Number(run?.job_count) || 1));
  const summaries = [];
  let cumulative = 0;
  for (let i = 0; i < MAX_SLOTS; i += 1) {
    const slot = { ...(run?.slots?.[i] || emptySlot(i + 1)), slot: i + 1 };
    if (i >= count) slot.use_today = false;
    const summary = summarizeSlot(slot, cumulative);
    cumulative = summary.cumulative_labels;
    summaries.push(summary);
  }
  const ready = summaries.filter((s) => s.status === STATUS_READY).length;
  const incomplete = summaries.filter((s) => s.status === STATUS_INCOMPLETE).length;
  return {
    summaries,
    total_physical_labels: cumulative,
    ready_jobs: ready,
    incomplete_jobs: incomplete,
    print_ready: ready > 0 && incomplete === 0,
  };
}

export function statusColor(status) {
  if (status === STATUS_READY) return "#00E676";
  if (status === STATUS_INCOMPLETE) return "#FFD600";
  return "#8B93A7";
}

export function padBeams(marks) {
  const next = Array.from({ length: MAX_BEAMS }, () => "");
  cleanBeams(marks).forEach((mark, i) => {
    next[i] = mark;
  });
  return next;
}
