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

export const STRAND_TENSION_COLORS = {
  pending: "#8B949E",
  pass: "#00E676",
  fail: "#FF3366",
  na: "#2979FF",
};

export const HOLD_DOWN_STATUS_COLORS = {
  pending: "#8B949E",
  installed: "#2979FF",
  stressed: "#FFD600",
  released: "#00BCD4",
  inspected: "#00E676",
  verified: "#00E676",
  issue: "#FF3366",
};

export function strandTensionStatus(strand) {
  if (strand?.na) return "na";
  if (strand?.measured_elongation == null && strand?.measured_elongation_in == null) return "pending";
  if (strand?.within_tolerance === true || strand?.status === "pass") return "pass";
  if (strand?.within_tolerance === false || strand?.status === "fail") return "fail";
  return strand?.status || "pending";
}

export function strandTensionColor(strand) {
  return STRAND_TENSION_COLORS[strandTensionStatus(strand)] || STRAND_TENSION_COLORS.pending;
}

export function holdDownColor(item) {
  return HOLD_DOWN_STATUS_COLORS[item?.status] || HOLD_DOWN_STATUS_COLORS.pending;
}

export function isDraped(strand) {
  return Boolean(strand?.draped || strand?.detensioning === "draped");
}

export function strandEndYIn(strand) {
  if (isDraped(strand)) return Number(strand.drape_peak_in ?? strand.y_in ?? strand.soffit_in ?? 0);
  return Number(strand.y_in ?? strand.soffit_in ?? 0);
}

export function strandHoldYIn(strand) {
  if (isDraped(strand)) {
    const hold = Number(strand.hold_down_y_in ?? strand.soffit_in);
    if (Number.isFinite(hold)) return hold;
  }
  return strandEndYIn(strand);
}

export function drapeKeyStations(strand, lengthFt, holdDowns) {
  const fromStrand = (strand?.hold_down_stations_ft || []).map(Number).filter((n) => Number.isFinite(n) && n > 0);
  if (fromStrand.length) return fromStrand.slice().sort((a, b) => a - b);
  const fromHd = (holdDowns || []).map((h) => Number(h.station_from_marked_end)).filter((n) => Number.isFinite(n) && n > 0);
  if (fromHd.length) return fromHd.slice().sort((a, b) => a - b);
  return [];
}

export function strandElevationIn(strand, zFt, lengthFt, holdDowns) {
  const yEnd = strandEndYIn(strand);
  if (!isDraped(strand)) return yEnd;
  const yHold = strandHoldYIn(strand);
  const length = Number(lengthFt) || 0;
  const stations = drapeKeyStations(strand, length, holdDowns);
  const keys = [[0, yEnd], ...stations.map((s) => [s, yHold]), [length, yEnd]];
  const z = Math.max(0, Math.min(length, Number(zFt) || 0));
  for (let i = 0; i < keys.length - 1; i += 1) {
    const [z0, y0] = keys[i];
    const [z1, y1] = keys[i + 1];
    if (z <= z1 || i === keys.length - 2) {
      if (z1 === z0) return y1;
      return y0 + ((z - z0) / (z1 - z0)) * (y1 - y0);
    }
  }
  return yEnd;
}

export function strandPathPoints(strand, lengthFt, holdDowns, steps = 48) {
  const x = inchesToFt(strand.x_in ?? strand.offset_in);
  const length = Number(lengthFt) || 0;
  const stations = drapeKeyStations(strand, length, holdDowns);
  const zs = new Set([0, length]);
  stations.forEach((s) => zs.add(s));
  for (let i = 0; i <= steps; i += 1) zs.add((i / steps) * length);
  return [...zs].sort((a, b) => a - b).map((z) => ({
    x,
    y: inchesToFt(strandElevationIn(strand, z, length, holdDowns)),
    z,
  }));
}

export const EMBED_KIND_KEYS = {
  lift_loop: "lift_loops",
  insert: "inserts",
  tube: "tubes",
  tie_rod: "tie_rod_openings",
  drain: "drain_holes",
  hold_down: "hold_downs",
  grout_groove: "grout_grooves",
  bituminous_zone: "bituminous_ends",
};

function finiteStation(value) {
  if (value == null || value === "") return null;
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) return null;
  return number;
}

function embedQuantity(item) {
  const quantity = Number(item?.quantity);
  if (Number.isFinite(quantity) && quantity >= 1) return Math.floor(quantity);
  return 1;
}

function embedStation(item) {
  if (!item || typeof item !== "object") return null;
  const position = item.position && typeof item.position === "object" ? item.position : {};
  return finiteStation(item.x_ft) ?? finiteStation(item.station_ft) ?? finiteStation(item.station_from_marked_end) ?? finiteStation(position.station_ft);
}

function bituminousStation(item, lengthFt) {
  const stationed = embedStation(item);
  if (stationed != null) return stationed;
  const end = String(item?.end || "").trim().toLowerCase();
  const pocketIn = finiteStation(item?.length_in);
  const pocketFt = (pocketIn || 0) / 12;
  const span = finiteStation(lengthFt);
  if (end === "end" || end === "ue" || end === "unmarked") {
    if (span == null) return null;
    return Math.max(span - (pocketFt ? pocketFt / 2 : 0), 0);
  }
  if (end === "start" || end === "me" || end === "marked") {
    return pocketFt ? pocketFt / 2 : 0;
  }
  return null;
}

function normalizeEmbed(kind, item, index, copyIndex, lengthFt) {
  const position = item.position && typeof item.position === "object" ? item.position : {};
  const station = kind === "bituminous_zone" ? bituminousStation(item, lengthFt) : embedStation(item);
  const typeCode = item.type_code || item.type || "";
  return {
    id: item.id || `${kind}-${index}-${copyIndex}`,
    kind,
    name: item.name || typeCode || kind.replace(/_/g, " "),
    type_code: typeCode,
    size: String(item.size || item.diameter_in || ""),
    station_ft: station,
    position_unconfirmed: station == null,
    face: String(item.face || item.side || position.face || ""),
    side: item.side || "",
    offset_in: item.offset_in ?? position.offset_in ?? 0,
    height_from_soffit_in: item.height_from_soffit_in ?? position.height_from_soffit_in ?? null,
    diameter_in: item.diameter_in ?? null,
    end: item.end,
    length_in: item.length_in,
    notes: item.notes || "",
  };
}

export function collectEmbeddedHardware(beam, kind) {
  const fromApi = beam?.embedded_hardware?.[kind];
  if (Array.isArray(fromApi) && fromApi.length) return fromApi;
  const spec = beam?.beam_spec || {};
  const blueprint = spec.blueprint || beam?.product_type?.blueprint || {};
  const lengthFt = spec.geometry?.length_ft || blueprint.length || beam?.length_ft;
  const hardware = Array.isArray(spec.hardware) ? spec.hardware.filter((item) => item && item.kind === kind) : [];
  const blueprintKey = EMBED_KIND_KEYS[kind];
  const fromBlueprint = Array.isArray(blueprint[blueprintKey])
    ? blueprint[blueprintKey].filter((item) => item && typeof item === "object")
    : [];
  const source = hardware.length ? hardware : fromBlueprint;
  const items = [];
  source.forEach((item, index) => {
    const quantity = embedQuantity(item);
    for (let copyIndex = 0; copyIndex < quantity; copyIndex += 1) {
      items.push(normalizeEmbed(kind, item, index, copyIndex, lengthFt));
    }
  });
  return items;
}

export function unconfirmedParkingZ(lengthFt, index = 0, kindSlot = 0) {
  const length = Number(lengthFt) || 40;
  const cluster = Math.min(Math.max(length * 0.5, 3.5), Math.max(length - 3.5, 3.5));
  return cluster + index * 1.2 + kindSlot * 0.04;
}

export function embedFeatureCounts(beam, strandCount = 0) {
  const strands = Number(strandCount) || 0;
  return [
    ["Lift loops", collectEmbeddedHardware(beam, "lift_loop").length],
    ["Inserts", collectEmbeddedHardware(beam, "insert").length],
    ["Tubes", collectEmbeddedHardware(beam, "tube").length],
    ["Tie-rods", collectEmbeddedHardware(beam, "tie_rod").length],
    ["Drain holes", collectEmbeddedHardware(beam, "drain").length],
    ["Hold-downs", collectEmbeddedHardware(beam, "hold_down").length],
    ["Stirrup zones", Array.isArray(beam?.beam_spec?.stirrup_zones) ? beam.beam_spec.stirrup_zones.length : 0],
    ["Strand ends", strands > 0 ? strands * 2 : 0],
    ["Bituminous pockets", collectEmbeddedHardware(beam, "bituminous_zone").length],
  ];
}

export function embedStationList(items = []) {
  const stations = (items || [])
    .map((item) => item.station_ft ?? item.x_ft ?? item?.position?.station_ft)
    .filter((value) => value != null && value !== "");
  return stations.length ? stations.map((value) => `${Number(value).toFixed(1)}'`).join(" · ") : "unconfirmed";
}
