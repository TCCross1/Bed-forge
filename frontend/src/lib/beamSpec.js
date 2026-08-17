/** Kind colors for the blueprint-accurate twin. */
export const ELEMENT_COLORS = {
  lift_loop: "#C9A227",
  insert: "#2979FF",
  tube: "#00B8D4",
  drain: "#00E676",
  downspout: "#69F0AE",
  tie_rod: "#FFD600",
  hold_down: "#FF8A3D",
  stirrup: "#8B5A2B",
  hoop: "#A67C52",
  projecting_rebar: "#B87333",
  grout_groove: "#4B5563",
  shear_key: "#6B7280",
  diaphragm: "#90A4AE",
  bearing_plate: "#78909C",
  bituminous_zone: "#111111",
  strand: "#5C6BC0",
  strand_draped: "#7E57C2",
};

export const KIND_LABELS = {
  lift_loop: "Lift loop",
  insert: "Insert",
  tube: "Tube / sleeve",
  drain: "Drain hole",
  downspout: "Downspout",
  tie_rod: "Tie-rod opening",
  hold_down: "Hold-down",
  stirrup: "Stirrup",
  hoop: "Rebar hoop",
  projecting_rebar: "Projecting rebar",
  grout_groove: "Grout groove",
  shear_key: "Shear key",
  diaphragm: "Diaphragm hardware",
  bearing_plate: "Bearing plate",
  bituminous_zone: "Bituminous / debond",
  strand: "Strand",
};

export function hardwareColor(kind, measurement) {
  if (measurement?.within_tolerance === false) return "#FF3366";
  if (measurement?.within_tolerance === true) return "#00E676";
  return ELEMENT_COLORS[kind] || "#2979FF";
}

export function latestMeasurements(list) {
  const map = {};
  (list || []).forEach((m) => {
    map[m.element_id] = m;
  });
  return map;
}

export function inchesToFt(inches) {
  return (Number(inches) || 0) / 12;
}
