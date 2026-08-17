/** BedForge BeamSpec — shop-drawing extraction types. */

export interface StationRef {
  station_ft: number;
  offset_in: number;
  height_from_soffit_in: number;
  face: string;
  page?: number | null;
  source_note?: string;
}

export interface HardwareItem {
  id: string;
  kind: string;
  name: string;
  type_code: string;
  quantity: number;
  size: string;
  material: string;
  position: StationRef;
  end_station_ft?: number | null;
  notes: string;
  tolerance_in: number;
}

export interface StrandItem {
  id: string;
  number: number;
  size: string;
  detensioning: "straight" | "draped" | string;
  area_in2: number;
  jacking_kip: number;
  soffit_in: number;
  drape_peak_in?: number | null;
  hold_down_stations_ft: number[];
  debond_me_ft: number;
  debond_ue_ft: number;
  offset_in: number;
  notes: string;
}

export interface StirrupZone {
  id: string;
  from_ft: number;
  to_ft: number;
  spacing_in: number;
  bar_size: string;
  shape: string;
  notes: string;
}

export interface BeamGeometry {
  twin_type: "i_beam" | "box_beam" | string;
  length_ft: number;
  depth_in: number;
  width_in: number;
  top_flange_width_in: number;
  top_flange_thick_in: number;
  bot_flange_width_in: number;
  bot_flange_thick_in: number;
  web_thick_in: number;
  product_name: string;
}

export interface BeamSpec {
  id: string;
  beam_id?: string | null;
  job_id?: string | null;
  pour_id?: string | null;
  blueprint_id?: string | null;
  job_number: string;
  beam_mark: string;
  product_name: string;
  state_spec: string;
  geometry: BeamGeometry;
  marked_end_id: string;
  unmarked_end_id: string;
  strands: StrandItem[];
  hardware: HardwareItem[];
  stirrup_zones: StirrupZone[];
  notes: string[];
  special_finishes: string[];
  status: "extracted" | "reviewed" | "locked" | string;
  extractor: string;
  extractor_confidence: number;
  review_notes: string;
  reviewed_by: string;
  locked_by: string;
  locked_at?: string | null;
}

export interface SpecMeasurement {
  id: string;
  spec_id: string;
  element_id: string;
  element_kind: string;
  element_name: string;
  design_station_ft: number;
  measured_station_ft?: number | null;
  delta_in?: number | null;
  tolerance_in: number;
  within_tolerance?: boolean | null;
  inspector: string;
  notes: string;
}
