import { productionStatus } from "./constants";

export const HEADER_SETBACK_FT = 8;
export const GAP_FT = 2.5;
export const COMPACT_HARDWARE_KINDS = ["lift_loop", "bearing_plate", "bituminous_zone", "hold_down", "projecting_rebar"];

/** Casting-lane soffit width in feet. I-beam beds are narrower than box beds. */
export function plannerLaneWidthFt(twinType) {
  return twinType === "box_beam" ? 22 : 16;
}

export function plannerTwinType(layout) {
  return (
    layout?.bed?.twin_type
    || layout?.assignments?.[0]?.beam?.twin_type
    || layout?.assignments?.[0]?.spec?.geometry?.twin_type
    || "i_beam"
  );
}

export function statusColor(status) {
  return productionStatus(status).color;
}

export function fallbackSpec(beam) {
  const length = Number(beam?.length_ft) || 90;
  const isBox = beam?.twin_type === "box_beam";
  const depth = isBox ? 27 : 45;
  const width = isBox ? 48 : 16;
  return {
    id: `fallback-${beam?.id || "beam"}`,
    status: "draft",
    marked_end_id: "ME",
    unmarked_end_id: "UE",
    product_name: beam?.mark || "Beam",
    geometry: {
      twin_type: isBox ? "box_beam" : "i_beam",
      length_ft: length,
      depth_in: depth,
      width_in: width,
      top_flange_width_in: isBox ? width : 16,
      top_flange_thick_in: 7,
      bot_flange_width_in: isBox ? width : 18,
      bot_flange_thick_in: 7,
      web_thick_in: 6,
    },
    strands: [],
    stirrup_zones: [],
    hardware: [
      { id: "ll-me", kind: "lift_loop", name: "Lift loop ME", position: { station_ft: length * 0.2, offset_in: 0, height_from_soffit_in: depth } },
      { id: "ll-ue", kind: "lift_loop", name: "Lift loop UE", position: { station_ft: length * 0.8, offset_in: 0, height_from_soffit_in: depth } },
      { id: "brg-me", kind: "bearing_plate", name: "Bearing ME", position: { station_ft: 0.75, offset_in: 0, height_from_soffit_in: 0 } },
      { id: "brg-ue", kind: "bearing_plate", name: "Bearing UE", position: { station_ft: length - 0.75, offset_in: 0, height_from_soffit_in: 0 } },
    ],
  };
}

export function dragPayload(beam) {
  return JSON.stringify({
    beam_id: beam.id,
    mark: beam.mark,
    length_ft: beam.length_ft,
    job_id: beam.job_id || null,
    pour_id: beam.pour_id || null,
  });
}

export function readDragPayload(event) {
  try {
    const raw = event.dataTransfer.getData("application/json") || event.dataTransfer.getData("text/plain");
    return raw ? JSON.parse(raw) : null;
  } catch (err) {
    console.error("[planner] drag payload parse failed", err);
    return null;
  }
}

export function isoToday() {
  const d = new Date();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${month}-${day}`;
}

export function addDays(iso, n) {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + n);
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${month}-${day}`;
}

export function weekStartMonday(iso) {
  const d = new Date(`${iso}T12:00:00`);
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const date = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${month}-${date}`;
}
