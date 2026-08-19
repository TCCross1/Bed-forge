import React, { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { Html, Line, OrbitControls } from "@react-three/drei";
import * as THREE from "three";

const inchesToFeet = (value = 0) => value / 12;
const concreteBase = "#C5CBD4";
const concreteEdge = "#EEF3F8";
const steelGray = "#8A93A1";
const steelBright = "#D4DBE6";
const brassGold = "#E3C565";
const asphaltBlack = "#1A1A1A";
const runningDimensionColor = "#22D3EE";
const elevationDimensionColor = "#050505";
const overallDimensionColor = "#CBD5E1";
const strandStraightColor = "#C9D2DE";
const strandDrapedColor = "#2DD4BF";
const holdDownBronze = "#C47A2C";
const holdDownClamp = "#F0A85C";

function TwinCanvasFallback({ message = "Digital Twin unavailable on this device." }) {
  return (
    <div className="w-full h-full flex items-center justify-center p-6 bg-[#0A0C10] text-center">
      <div className="max-w-md border border-border rounded-sm bg-card/90 px-5 py-4">
        <div className="font-display font-bold uppercase tracking-wider text-sm text-white">3D Viewer Fallback</div>
        <div className="mt-2 text-sm text-muted-foreground font-mono">{message}</div>
      </div>
    </div>
  );
}

class TwinCanvasErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.error("Digital Twin renderer failed", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

function CanvasContextMonitor({ onContextLost }) {
  const { gl } = useThree();

  useEffect(() => {
    const canvas = gl?.domElement;
    if (!canvas) return undefined;

    const handleContextLost = (event) => {
      event.preventDefault();
      onContextLost?.();
    };

    canvas.addEventListener("webglcontextlost", handleContextLost, false);
    return () => canvas.removeEventListener("webglcontextlost", handleContextLost, false);
  }, [gl, onContextLost]);

  return null;
}

function formatFeet(value = 0) {
  const numeric = Number(value) || 0;
  const sign = numeric < 0 ? "-" : "";
  const totalInches = Math.round(Math.abs(numeric) * 12);
  const feet = Math.floor(totalInches / 12);
  const inches = totalInches % 12;
  return `${sign}${feet}'-${inches}"`;
}

function formatInches(value = 0, digits = 0) {
  return `${Number(value).toFixed(digits)} in`;
}

function formatStation(value = 0) {
  return `STA ${Number(value).toFixed(1)}`;
}

function hasSpecDna(beam) {
  return Boolean(beam?.beam_spec || beam?.blueprint_source?.spec_id || (beam?.blueprint_source?.status === "locked" && beam?.product_type?.blueprint));
}

function familySectionEnvelope(family, depth) {
  if (family === "box_beam") {
    return {
      outer_width_in: 42,
      outer_depth_in: depth || 30,
      wall_thickness_in: 4,
      void_width_in: 24,
      void_depth_in: 16,
    };
  }
  const envelopes = {
    36: { bottom_flange_width_in: 18, bottom_flange_thickness_in: 6, web_thickness_in: 6, top_flange_width_in: 12, top_flange_thickness_in: 6, overall_depth_in: 36 },
    45: { bottom_flange_width_in: 28, bottom_flange_thickness_in: 8, web_thickness_in: 7, top_flange_width_in: 16, top_flange_thickness_in: 7, overall_depth_in: 45 },
    54: { bottom_flange_width_in: 32, bottom_flange_thickness_in: 8.5, web_thickness_in: 7, top_flange_width_in: 20, top_flange_thickness_in: 7.5, overall_depth_in: 54 },
    72: { bottom_flange_width_in: 26, bottom_flange_thickness_in: 9, web_thickness_in: 8, top_flange_width_in: 42, top_flange_thickness_in: 8, overall_depth_in: 72 },
  };
  return envelopes[Math.round(Number(depth) || 0)] || envelopes[36];
}

function normalizeBlueprint(beam) {
  const specDriven = hasSpecDna(beam);
  const source = beam?.beam_spec?.blueprint || beam?.product_type?.blueprint || {};
  const family = beam?.twin_type === "box_beam" ? "box_beam" : "i_beam";
  const extracted = source.cross_section || {};
  const depth = extracted.overall_depth_in || extracted.outer_depth_in || beam?.product_type?.depth_in || (family === "box_beam" ? 30 : 36);
  const width = extracted.top_flange_width_in || extracted.outer_width_in || beam?.product_type?.width_in || (family === "box_beam" ? 42 : 12);
  const length = Math.max(Number(source.length || source.dimensions?.overall_length_ft || beam?.length_ft || beam?.product_type?.default_length_ft || 10), 4);
  const envelope = familySectionEnvelope(family, depth);
  const crossSection = family === "box_beam"
    ? { ...envelope, ...extracted, outer_depth_in: extracted.outer_depth_in || depth, outer_width_in: extracted.outer_width_in || width }
    : { ...envelope, ...extracted, overall_depth_in: extracted.overall_depth_in || depth };

  if (specDriven) {
    const stirrups = source.stirrups && typeof source.stirrups === "object" ? { ...source.stirrups } : {};
    const specZones = beam?.beam_spec?.stirrup_zones;
    if ((!Array.isArray(stirrups.zones) || !stirrups.zones.length) && Array.isArray(specZones) && specZones.length) {
      stirrups.zones = specZones;
    }
    return {
      cross_section: crossSection,
      lift_loops: Array.isArray(source.lift_loops) ? source.lift_loops : [],
      inserts: Array.isArray(source.inserts) ? source.inserts : [],
      tubes: Array.isArray(source.tubes) ? source.tubes : [],
      tie_rod_openings: Array.isArray(source.tie_rod_openings) ? source.tie_rod_openings : [],
      drain_holes: Array.isArray(source.drain_holes) ? source.drain_holes : [],
      hold_downs: Array.isArray(source.hold_downs) ? source.hold_downs : [],
      bituminous_ends: Array.isArray(source.bituminous_ends) ? source.bituminous_ends : [],
      strand_pattern: source.strand_pattern || { start_y_in: 5, row_spacing_in: 4.5, rows: [] },
      strand_system: source.strand_system || beam?.beam_spec?.strand || null,
      strand_draped: Boolean(source.strand_draped || beam?.beam_spec?.strand?.draped),
      strand_end_treatment: source.strand_end_treatment || beam?.beam_spec?.strand?.end_treatments?.marked_end || null,
      strand_pattern_source: source.strand_pattern_source || beam?.beam_spec?.strand?.pattern_source || "unconfirmed",
      stirrups,
      marked_end: source.marked_end || { end: "start", label: "MARKED END", color: "#F4F7FB" },
      grout_grooves: Array.isArray(source.grout_grooves) ? source.grout_grooves : [],
      drape_profile: source.drape_profile || null,
      dimensions: {
        overall_length_ft: length,
        overall_depth_in: depth,
        overall_width_in: width,
        ...(source.dimensions || {}),
      },
      length,
      specDriven: true,
      missing_fields: beam?.beam_spec?.missing_fields || [],
    };
  }

  const base = family === "box_beam"
    ? {
        cross_section: {
          outer_width_in: width,
          outer_depth_in: depth,
          wall_thickness_in: 4,
          void_width_in: Math.max(width - 14, 16),
          void_depth_in: Math.max(depth - 10, 14),
        },
        grout_grooves: [{ x_ft: length * 0.24 }, { x_ft: length * 0.76 }],
      }
    : {
        cross_section: {
          bottom_flange_width_in: Math.max(width * 1.7, width + 10),
          bottom_flange_thickness_in: 8,
          web_thickness_in: 7,
          top_flange_width_in: width,
          top_flange_thickness_in: 7,
          overall_depth_in: depth,
        },
        drape_profile: {
          low_points_ft: [length * 0.25, length * 0.5, length * 0.75],
          sag_in: 7,
        },
      };

  return {
    cross_section: { ...base.cross_section, ...extracted },
    lift_loops: source.lift_loops || [{ x_ft: length * 0.18 }, { x_ft: length * 0.82 }],
    inserts: source.inserts || [{ x_ft: length * 0.25, side: "left", embed: "plate" }, { x_ft: length * 0.75, side: "right", embed: "plate" }],
    tubes: source.tubes || [{ x_ft: length * 0.38, diameter_in: 3 }, { x_ft: length * 0.62, diameter_in: 3 }],
    tie_rod_openings: source.tie_rod_openings || [{ x_ft: length * 0.33, diameter_in: 2.5 }, { x_ft: length * 0.67, diameter_in: 2.5 }],
    drain_holes: source.drain_holes || [{ x_ft: length * 0.08, diameter_in: 2 }, { x_ft: length * 0.92, diameter_in: 2 }],
    hold_downs: source.hold_downs || [{ x_ft: length * 0.22 }, { x_ft: length * 0.5 }, { x_ft: length * 0.78 }],
    bituminous_ends: source.bituminous_ends || [{ end: "start", length_in: 18 }, { end: "end", length_in: 18 }],
    strand_pattern: source.strand_pattern || { start_y_in: 5, row_spacing_in: 4.5, rows: [{ count: 4, spacing_in: 4 }, { count: 4, spacing_in: 4, draped: true }] },
    stirrups: source.stirrups || { start_ft: 2, end_ft: Math.max(length - 2, 4), spacing_in: 24, cover_in: 2.5 },
    marked_end: source.marked_end || { end: "start", label: "MARKED END", color: "#F4F7FB" },
    grout_grooves: source.grout_grooves || base.grout_grooves || [],
    drape_profile: source.drape_profile || base.drape_profile || null,
    strand_system: source.strand_system || null,
    strand_draped: Boolean(source.strand_draped || source.drape_profile || base.drape_profile),
    strand_end_treatment: source.strand_end_treatment || { type: "cut_flush_bituminous", label: "Cut flush + bituminous" },
    strand_pattern_source: source.strand_pattern_source || "invented",
    dimensions: {
      overall_length_ft: length,
      overall_depth_in: depth,
      overall_width_in: width,
      ...(source.dimensions || {}),
    },
    length,
    specDriven: false,
    missing_fields: [],
  };
}

function buildIBeam(crossSection) {
  const bottomWidth = inchesToFeet(crossSection.bottom_flange_width_in);
  const bottomThickness = inchesToFeet(crossSection.bottom_flange_thickness_in);
  const webThickness = inchesToFeet(crossSection.web_thickness_in);
  const topWidth = inchesToFeet(crossSection.top_flange_width_in);
  const topThickness = inchesToFeet(crossSection.top_flange_thickness_in);
  const depth = inchesToFeet(crossSection.overall_depth_in);
  const bottomSlopeRun = Math.min(inchesToFeet(crossSection.bottom_transition_in || 4), Math.max((bottomWidth - webThickness) / 2 - 0.04, 0.06));
  const bottomSlopeRise = Math.min(inchesToFeet(crossSection.bottom_transition_rise_in || 4.5), Math.max(depth * 0.16, 0.12));
  const topSlopeRun = Math.min(inchesToFeet(crossSection.top_transition_in || 5), Math.max((topWidth - webThickness) / 2 - 0.04, 0.06));
  const topSlopeDrop = Math.min(inchesToFeet(crossSection.top_transition_drop_in || 4.5), Math.max(depth * 0.14, 0.12));
  const shape = new THREE.Shape();
  shape.moveTo(-bottomWidth / 2, 0);
  shape.lineTo(bottomWidth / 2, 0);
  shape.lineTo(bottomWidth / 2, bottomThickness);
  shape.lineTo(webThickness / 2 + bottomSlopeRun, bottomThickness);
  shape.lineTo(webThickness / 2, bottomThickness + bottomSlopeRise);
  shape.lineTo(webThickness / 2, depth - topThickness - topSlopeDrop);
  shape.lineTo(webThickness / 2 + topSlopeRun, depth - topThickness);
  shape.lineTo(topWidth / 2, depth - topThickness);
  shape.lineTo(topWidth / 2, depth);
  shape.lineTo(-topWidth / 2, depth);
  shape.lineTo(-topWidth / 2, depth - topThickness);
  shape.lineTo(-webThickness / 2 - topSlopeRun, depth - topThickness);
  shape.lineTo(-webThickness / 2, depth - topThickness - topSlopeDrop);
  shape.lineTo(-webThickness / 2, bottomThickness + bottomSlopeRise);
  shape.lineTo(-webThickness / 2 - bottomSlopeRun, bottomThickness);
  shape.lineTo(-bottomWidth / 2, bottomThickness);
  shape.closePath();
  return { shape, width: bottomWidth, depth, topWidth };
}

function buildBoxBeam(crossSection) {
  const outerWidth = inchesToFeet(crossSection.outer_width_in);
  const outerDepth = inchesToFeet(crossSection.outer_depth_in);
  const wall = inchesToFeet(crossSection.wall_thickness_in);
  const innerWidth = inchesToFeet(crossSection.void_width_in);
  const innerDepth = inchesToFeet(crossSection.void_depth_in);
  const topChamfer = Math.min(inchesToFeet(crossSection.top_chamfer_in || 2.5), Math.max(outerWidth * 0.08, 0.08));
  const voidHaunch = Math.min(inchesToFeet(crossSection.void_haunch_in || 2), Math.max((innerWidth * 0.16), 0.08));
  const bottomSlab = wall;
  const topSlab = Math.max(outerDepth - innerDepth - bottomSlab, wall * 0.9);
  const shape = new THREE.Shape();
  shape.moveTo(-outerWidth / 2, 0);
  shape.lineTo(outerWidth / 2, 0);
  shape.lineTo(outerWidth / 2, outerDepth - topChamfer);
  shape.lineTo(outerWidth / 2 - topChamfer, outerDepth);
  shape.lineTo(-outerWidth / 2 + topChamfer, outerDepth);
  shape.lineTo(-outerWidth / 2, outerDepth - topChamfer);
  shape.closePath();
  const hole = new THREE.Path();
  hole.moveTo(-innerWidth / 2, bottomSlab);
  hole.lineTo(innerWidth / 2, bottomSlab);
  hole.lineTo(innerWidth / 2, outerDepth - topSlab - voidHaunch);
  hole.lineTo(innerWidth / 2 - voidHaunch, outerDepth - topSlab);
  hole.lineTo(-innerWidth / 2 + voidHaunch, outerDepth - topSlab);
  hole.lineTo(-innerWidth / 2, outerDepth - topSlab - voidHaunch);
  hole.closePath();
  shape.holes.push(hole);
  return { shape, width: outerWidth, depth: outerDepth };
}

function useBeamSpec(beam) {
  return useMemo(() => {
    const blueprint = normalizeBlueprint(beam);
    const section = beam?.twin_type === "box_beam"
      ? buildBoxBeam(blueprint.cross_section)
      : buildIBeam(blueprint.cross_section);
    return {
      blueprint,
      length: blueprint.length,
      width: section.width,
      depth: section.depth,
      topWidth: section.topWidth,
      shape: section.shape,
      label: beam?.product_type?.name || beam?.mark || "Beam",
    };
  }, [beam]);
}

function clickHardware(event, payload, onHardwareSelect) {
  event.stopPropagation();
  onHardwareSelect?.(payload);
}

function CalloutTag({ position, color, label }) {
  return (
    <Html position={position} distanceFactor={16}>
      <div style={{ background: "rgba(10,12,16,0.96)", color, border: `1px solid ${color}`, padding: "3px 7px", fontSize: 10, fontFamily: "JetBrains Mono, monospace", whiteSpace: "nowrap", boxShadow: "0 0 0 1px rgba(255,255,255,0.04)" }}>
        {label}
      </div>
    </Html>
  );
}

function Shell({ spec, beam, highlighted, onSurfacePick, onBeamSelect, pourMode = "post_pour" }) {
  const geometry = useMemo(() => new THREE.ExtrudeGeometry(spec.shape, { depth: spec.length, bevelEnabled: false }), [spec]);
  const edges = useMemo(() => new THREE.EdgesGeometry(geometry, 25), [geometry]);
  const prePour = pourMode === "pre_pour";
  return (
    <group>
      <mesh
        castShadow={!prePour}
        receiveShadow={!prePour}
        geometry={geometry}
        onClick={(event) => {
          event.stopPropagation();
          onSurfacePick?.(event.point);
          onBeamSelect?.(beam);
        }}
      >
        {prePour ? (
          <meshBasicMaterial color="#5EEAD4" transparent opacity={0} depthWrite={false} side={THREE.DoubleSide} />
        ) : (
          <meshPhysicalMaterial
            color={concreteBase}
            roughness={0.78}
            metalness={0.05}
            clearcoat={0.22}
            clearcoatRoughness={0.62}
            reflectivity={0.18}
            emissive={highlighted ? "#0F3A4A" : "#0B0D10"}
            emissiveIntensity={highlighted ? 0.16 : 0.04}
          />
        )}
      </mesh>
      <lineSegments geometry={edges}>
        <lineBasicMaterial color={prePour ? "#5EEAD4" : (highlighted ? "#B8E8F0" : concreteEdge)} transparent opacity={prePour ? 1 : 0.78} />
      </lineSegments>
    </group>
  );
}

function SectionRevealLines({ beam, spec }) {
  if (beam.twin_type === "box_beam") {
    const wall = inchesToFeet(spec.blueprint.cross_section.wall_thickness_in || 4);
    const voidWidth = inchesToFeet(spec.blueprint.cross_section.void_width_in || 24);
    const topSlab = Math.max(spec.depth - inchesToFeet(spec.blueprint.cross_section.void_depth_in || 16) - wall, wall);
    return (
      <group>
        {[-1, 1].map((side) => (
          <React.Fragment key={side}>
            <Line points={[[side * (spec.width / 2 - wall), wall, 0.08], [side * (spec.width / 2 - wall), wall, spec.length - 0.08]]} color="#738091" lineWidth={0.8} />
            <Line points={[[side * (voidWidth / 2), spec.depth - topSlab, 0.08], [side * (voidWidth / 2), spec.depth - topSlab, spec.length - 0.08]]} color="#8A95A5" lineWidth={0.8} />
          </React.Fragment>
        ))}
      </group>
    );
  }

  const topThickness = inchesToFeet(spec.blueprint.cross_section.top_flange_thickness_in || 7);
  const bottomThickness = inchesToFeet(spec.blueprint.cross_section.bottom_flange_thickness_in || 8);
  const webThickness = inchesToFeet(spec.blueprint.cross_section.web_thickness_in || 7);
  const bottomWidth = inchesToFeet(spec.blueprint.cross_section.bottom_flange_width_in || 24);
  return (
    <group>
      <Line points={[[-bottomWidth / 2, bottomThickness, 0.08], [bottomWidth / 2, bottomThickness, 0.08]]} color="#7E8B9C" lineWidth={0.8} />
      <Line points={[[-bottomWidth / 2, bottomThickness, spec.length - 0.08], [bottomWidth / 2, bottomThickness, spec.length - 0.08]]} color="#7E8B9C" lineWidth={0.8} />
      {[-1, 1].map((side) => (
        <Line
          key={side}
          points={[[side * (webThickness / 2), bottomThickness, spec.length * 0.08], [side * (webThickness / 2), spec.depth - topThickness, spec.length * 0.92]]}
          color="#8A95A5"
          lineWidth={0.8}
        />
      ))}
    </group>
  );
}

function LiftLoops({ beam, spec, onHardwareSelect }) {
  return (spec.blueprint.lift_loops || []).map((item, index) => {
    const station = stationValue(item);
    if (station == null) return null;
    const radius = Math.max(inchesToFeet(item.diameter_in || 0) / 2, spec.width * 0.2, 0.38);
    const legHeight = Math.max(radius * 1.35, 0.55);
    const spread = Math.max(radius * 0.58, 0.22);
    const cable = Math.max(radius * 0.08, 0.035);
    const arch = [
      [-spread, 0, 0],
      [-spread * 0.86, legHeight * 0.54, 0],
      [0, legHeight, 0],
      [spread * 0.86, legHeight * 0.54, 0],
      [spread, 0, 0],
    ];
    const payload = { id: `lift-loop-${index}`, type: "Lift loop", beamMark: beam.mark, spec: item };
    return (
      <group key={payload.id} position={[0, spec.depth + 0.05, station]} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
        <Line points={arch} color={steelBright} lineWidth={3.4} />
        {[-spread, spread].map((offset) => (
          <React.Fragment key={offset}>
            <mesh position={[offset, 0.11, 0]}>
              <cylinderGeometry args={[cable, cable, 0.24, 12]} />
              <meshStandardMaterial color={steelBright} roughness={0.34} metalness={0.72} />
            </mesh>
            <mesh position={[offset, -0.02, 0]}>
              <cylinderGeometry args={[cable * 1.55, cable * 1.55, 0.08, 16]} />
              <meshStandardMaterial color="#465160" roughness={0.5} metalness={0.36} />
            </mesh>
          </React.Fragment>
        ))}
      </group>
    );
  });
}

function SideInserts({ beam, spec, onHardwareSelect }) {
  return (spec.blueprint.inserts || []).map((item, index) => {
    const station = stationValue(item);
    if (station == null) return null;
    const side = item.side === "right" ? 1 : -1;
    const radius = Math.max(inchesToFeet(item.diameter_in || 2) / 2, spec.width * 0.038);
    const x = side * (spec.width / 2 + radius * 0.28);
    const payload = { id: `insert-${index}`, type: "Side insert", beamMark: beam.mark, spec: item };
    return (
      <group key={payload.id} position={[x, spec.depth * 0.7, station]} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
        <mesh position={[-side * radius * 0.32, 0, 0]}>
          <boxGeometry args={[radius * 0.55, radius * 1.8, radius * 1.8]} />
          <meshStandardMaterial color="#525B67" roughness={0.55} metalness={0.42} />
        </mesh>
        <mesh rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[radius, radius, spec.width * 0.14, 18]} />
          <meshStandardMaterial color="#D18C1B" roughness={0.34} metalness={0.52} />
        </mesh>
        <mesh position={[side * radius * 0.52, 0, 0]} rotation={[0, Math.PI / 2, 0]}>
          <cylinderGeometry args={[radius * 0.88, radius * 0.88, radius * 0.5, 6]} />
          <meshStandardMaterial color="#A9B3C0" roughness={0.32} metalness={0.74} />
        </mesh>
        <mesh position={[side * radius * 0.86, 0, 0]} rotation={[0, Math.PI / 2, 0]}>
          <cylinderGeometry args={[radius * 0.36, radius * 0.36, radius * 0.18, 16]} />
          <meshStandardMaterial color="#202632" roughness={0.62} metalness={0.24} />
        </mesh>
      </group>
    );
  });
}

function CylindricalOpenings({ beam, spec, items, type, color, y, onHardwareSelect }) {
  return (items || []).map((item, index) => {
    const station = stationValue(item);
    if (station == null) return null;
    const radius = Math.max(inchesToFeet(item.diameter_in || 2) / 2, 0.08);
    const isDrain = type.toLowerCase().includes("drain");
    const isTie = type.toLowerCase().includes("tie");
    const payload = { id: `${type}-${index}`, type, beamMark: beam.mark, spec: item };
    return (
      <group key={payload.id} position={[0, y, station]} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
        <mesh rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[radius, radius, spec.width * 1.02, 22]} />
          <meshStandardMaterial color={color} roughness={0.78} metalness={0.1} />
        </mesh>
        {[-spec.width / 2, spec.width / 2].map((x) => (
          <mesh key={x} position={[x, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
            <cylinderGeometry args={[radius * 1.05, radius * 1.05, 0.04, 18]} />
            <meshStandardMaterial color="#0F172A" roughness={0.7} metalness={0.12} />
          </mesh>
        ))}
        {[-spec.width / 2, spec.width / 2].map((x) => (
          <mesh key={`${x}-trim`} position={[x * 0.98, 0, 0]}>
            <boxGeometry args={[0.03, radius * 2.25, radius * 2.25]} />
            <meshStandardMaterial color="#D2D8E0" roughness={0.46} metalness={0.58} />
          </mesh>
        ))}
        {isDrain && [-1, 1].map((side) => (
          <group key={`spout-${side}`} position={[side * (spec.width / 2 + radius * 0.9), -radius * 1.9, 0]}>
            <mesh rotation={[Math.PI / 2, 0, 0]}>
              <cylinderGeometry args={[radius * 0.45, radius * 0.45, radius * 2.8, 14]} />
              <meshStandardMaterial color="#4D5966" roughness={0.48} metalness={0.45} />
            </mesh>
          </group>
        ))}
        {isTie && [-1, 1].map((side) => (
          <group key={`nut-${side}`} position={[side * (spec.width / 2 + 0.08), 0, 0]} rotation={[0, Math.PI / 2, 0]}>
            <mesh>
              <cylinderGeometry args={[radius * 1.35, radius * 1.35, 0.14, 6]} />
              <meshStandardMaterial color="#A9B3C0" roughness={0.34} metalness={0.72} />
            </mesh>
            <mesh position={[0, 0, side * 0.08]}>
              <cylinderGeometry args={[radius * 0.58, radius * 0.58, 0.16, 16]} />
              <meshStandardMaterial color="#1A1F28" roughness={0.62} metalness={0.18} />
            </mesh>
          </group>
        ))}
      </group>
    );
  });
}

function HoldDowns({ beam, spec, onHardwareSelect, stations, parametric = false }) {
  if (beam.twin_type !== "i_beam") return null;
  const resolved = stations || (spec.blueprint.hold_downs || []).map((item) => stationValue(item)).filter((value) => value != null);
  const layout = strandLayout(spec, beam);
  const holdY = inchesToFeet(layout.path.hold_down_elevation_in || 5);
  const width = Math.max(spec.width * 0.42, 0.62);
  const height = Math.max(inchesToFeet(12), spec.depth * 0.24);
  return resolved.map((station, index) => {
    const payload = {
      id: `hold-down-${parametric ? "p-" : ""}${index}`,
      type: parametric ? "Hold-down (parametric)" : "Hold-down",
      beamMark: beam.mark,
      spec: { x_ft: station, type: layout.holdDownType, parametric, source: layout.path.source },
    };
    return (
      <group key={payload.id} position={[0, holdY, station]} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
        <mesh>
          <boxGeometry args={[spec.width * 0.48, height * 0.2, width]} />
          <meshStandardMaterial color={holdDownBronze} roughness={0.34} metalness={0.58} />
        </mesh>
        {[-width * 0.3, width * 0.3].map((x) => (
          <mesh key={x} position={[x, height * 0.32, 0]}>
            <boxGeometry args={[0.12, height, width * 0.3]} />
            <meshStandardMaterial color={holdDownClamp} roughness={0.3} metalness={0.64} />
          </mesh>
        ))}
        <mesh position={[0, height * 0.46, 0]} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.08, 0.08, spec.width * 0.4, 12]} />
          <meshStandardMaterial color={brassGold} roughness={0.26} metalness={0.72} />
        </mesh>
      </group>
    );
  });
}

function BituminousEnds({ beam, spec, onHardwareSelect }) {
  return (spec.blueprint.bituminous_ends || []).map((item, index) => {
    const length = inchesToFeet(item.length_in || 18);
    const z = item.end === "end" ? spec.length - length / 2 : length / 2;
    const payload = { id: `bituminous-${index}`, type: "Bituminous pocket", beamMark: beam.mark, spec: item };
    return (
      <group key={payload.id} position={[0, spec.depth * 0.18, z]} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
        <mesh>
          <boxGeometry args={[spec.width * 0.96, spec.depth * 0.28, length]} />
          <meshStandardMaterial color={asphaltBlack} roughness={1} metalness={0} />
        </mesh>
        <mesh position={[0, spec.depth * 0.18, 0]}>
          <boxGeometry args={[spec.width * 0.82, 0.03, length]} />
          <meshStandardMaterial color="#2A2A2A" roughness={0.94} metalness={0.02} />
        </mesh>
      </group>
    );
  });
}

function GroutGrooves({ beam, spec, onHardwareSelect }) {
  if (beam.twin_type !== "box_beam") return null;
  return (spec.blueprint.grout_grooves || []).map((item, index) => {
    const station = stationValue(item);
    if (station == null) return null;
    const payload = { id: `grout-groove-${index}`, type: "Grout groove", beamMark: beam.mark, spec: item };
    return (
      <group key={payload.id} position={[0, spec.depth + 0.01, station]} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
        <mesh>
          <boxGeometry args={[spec.width * 0.84, 0.035, 0.24]} />
          <meshStandardMaterial color="#586272" roughness={0.76} metalness={0.05} />
        </mesh>
        <mesh position={[0, -0.02, 0]}>
          <boxGeometry args={[spec.width * 0.72, 0.018, 0.18]} />
          <meshStandardMaterial color="#2B313B" roughness={0.82} metalness={0.04} />
        </mesh>
      </group>
    );
  });
}

function Stirrups({ beam, spec, onHardwareSelect }) {
  const stirrup = useMemo(() => spec.blueprint.stirrups || {}, [spec.blueprint.stirrups]);
  const stations = useMemo(() => {
    const makeRange = (startFt, endFt, spacingIn) => {
      const start = Math.max(0.15, Math.min(startFt ?? 0.15, spec.length - 0.15));
      const end = Math.max(start, Math.min(endFt ?? spec.length - 0.15, spec.length - 0.15));
      const spacing = Math.max(inchesToFeet(spacingIn || stirrup.spacing_in || 24), 0.25);
      const count = Math.max(Math.floor(Math.max(end - start, 0) / spacing) + 1, 1);
      const range = Array.from({ length: count }).map((_, index) => Math.min(start + index * spacing, end));
      const last = range[range.length - 1];
      if (end - last > spacing * 0.35) range.push(end);
      return range;
    };
    const zones = Array.isArray(stirrup.zones) ? stirrup.zones : [];
    const hasCallout = zones.length > 0 || stirrup.spacing_in != null;
    if (!hasCallout) return [];
    const rawStations = zones.length
      ? zones.flatMap((zone) => makeRange(zone.from_ft, zone.to_ft, zone.spacing_in))
      : makeRange(stirrup.start_ft ?? 0.2, stirrup.end_ft ?? spec.length - 0.2, stirrup.spacing_in);
    return rawStations
      .filter((station) => station >= 0 && station <= spec.length)
      .sort((a, b) => a - b)
      .filter((station, index, rows) => index === 0 || Math.abs(station - rows[index - 1]) > 0.04);
  }, [stirrup, spec.length]);
  const loopRef = useRef();
  const legARef = useRef();
  const legBRef = useRef();
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const pairXs = useMemo(() => {
    const spread = Math.max(spec.width * 0.24, 0.42);
    return [-spread, spread];
  }, [spec.width]);
  const loopRadius = Math.max(spec.width * 0.055, 0.13);
  const legHeight = Math.max(spec.depth * 0.22, 0.58);
  useEffect(() => {
    let instance = 0;
    stations.forEach((z) => {
      pairXs.forEach((x) => {
        dummy.position.set(x, spec.depth + legHeight, z);
        dummy.rotation.set(0, 0, 0);
        dummy.updateMatrix();
        loopRef.current?.setMatrixAt(instance, dummy.matrix);
        dummy.position.set(x - loopRadius, spec.depth + legHeight / 2, z);
        dummy.rotation.set(0, 0, 0);
        dummy.updateMatrix();
        legARef.current?.setMatrixAt(instance, dummy.matrix);
        dummy.position.set(x + loopRadius, spec.depth + legHeight / 2, z);
        dummy.updateMatrix();
        legBRef.current?.setMatrixAt(instance, dummy.matrix);
        instance += 1;
      });
    });
    [loopRef, legARef, legBRef].forEach((ref) => {
      if (ref.current) ref.current.instanceMatrix.needsUpdate = true;
    });
  }, [stations, pairXs, spec.depth, legHeight, loopRadius, dummy]);
  if (!stations.length) return null;
  const payload = { id: "epoxy-stirrups", type: beam.twin_type === "box_beam" ? "Epoxy rebar hoop" : "Epoxy stirrup loop", beamMark: beam.mark, spec: { count: stations.length * 2, start_ft: stations[0], end_ft: stations[stations.length - 1], spacing_in: stirrup.spacing_in || 24 } };
  const instanceCount = stations.length * pairXs.length;
  return (
    <group onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
      <instancedMesh ref={loopRef} args={[null, null, instanceCount]} frustumCulled={false}>
        <torusGeometry args={[loopRadius, 0.026, 8, 18, Math.PI]} />
        <meshStandardMaterial color="#7CFC00" roughness={0.82} metalness={0.04} />
      </instancedMesh>
      <instancedMesh ref={legARef} args={[null, null, instanceCount]} frustumCulled={false}>
        <boxGeometry args={[0.042, legHeight, 0.042]} />
        <meshStandardMaterial color="#7CFC00" roughness={0.82} metalness={0.04} />
      </instancedMesh>
      <instancedMesh ref={legBRef} args={[null, null, instanceCount]} frustumCulled={false}>
        <boxGeometry args={[0.042, legHeight, 0.042]} />
        <meshStandardMaterial color="#7CFC00" roughness={0.82} metalness={0.04} />
      </instancedMesh>
    </group>
  );
}

function strandLayout(spec, beam) {
  const blueprint = spec.blueprint || {};
  const system = blueprint.strand_system || beam?.beam_spec?.strand || {};
  const pattern = system.pattern || blueprint.strand_pattern || {};
  const rows = Array.isArray(pattern.rows) ? pattern.rows : [];
  const path = system.path_model || {};
  const drape = blueprint.drape_profile || {};
  const holdType = String(system.hold_down_type || blueprint.hold_down_type || "");
  const draped = Boolean(system.draped || blueprint.strand_draped || /H-56-S|H56S/i.test(holdType));
  const drapedCount = Number(drape.draped_count || 0) || 0;
  const depthIn = spec.depth * 12;
  const endElev = Number(path.end_elevation_in || drape.end_elevation_in) || Math.max(10.5, depthIn * 0.42);
  const holdElev = Number(path.hold_down_elevation_in || drape.hold_down_elevation_in) || 2.5;
  let stations = (path.hold_down_stations_ft || drape.low_points_ft || [])
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value));
  if (draped && !stations.length && spec.length) {
    stations = [Math.round(spec.length * 500) / 1000];
  }
  const treatment = (system.end_treatments || {}).marked_end || blueprint.strand_end_treatment || { type: "unspecified", label: "Unspecified" };
  let items = [];
  if (rows.length) {
    const startY = pattern.start_y_in || 5;
    const rowSpacing = pattern.row_spacing_in || 4.5;
    let remainingDraped = drapedCount;
    rows.forEach((row, rowIndex) => {
      const spacing = row.spacing_in || 4;
      const count = Math.min(row.count || 0, 16);
      const totalWidth = spacing * Math.max(count - 1, 0);
      const lastRow = rowIndex === rows.length - 1;
      const isDrapedRow = Boolean(row.draped) || (draped && (row.draped !== false) && (drapedCount ? remainingDraped >= count && lastRow : lastRow && rows.length > 1));
      if (drapedCount && isDrapedRow) remainingDraped -= count;
      Array.from({ length: count }).forEach((_, strandIndex) => {
        const xIn = -totalWidth / 2 + strandIndex * spacing;
        const yIn = isDrapedRow ? endElev : (startY + rowIndex * rowSpacing);
        items.push({
          x: inchesToFeet(xIn),
          y: inchesToFeet(yIn),
          xIn,
          yIn,
          holdYIn: isDrapedRow ? holdElev : yIn,
          draped: Boolean(draped && (isDrapedRow || (rows.length === 1 && drapedCount === 0))),
        });
      });
    });
    if (draped && drapedCount === 0 && rows.length === 1) {
      items = items.map((item) => ({ ...item, draped: true, y: inchesToFeet(endElev), yIn: endElev, holdYIn: holdElev }));
    }
  } else if (draped || path.source === "parametric_midspan" || path.source === "extracted_stations") {
    items = [-5, -1.7, 1.7, 5].map((xIn) => ({
      x: inchesToFeet(xIn),
      y: inchesToFeet(2.5),
      xIn,
      yIn: 2.5,
      holdYIn: 2.5,
      draped: false,
      representative: true,
    })).concat([-2, 2].map((xIn) => ({
      x: inchesToFeet(xIn),
      y: inchesToFeet(endElev),
      xIn,
      yIn: endElev,
      holdYIn: holdElev,
      draped: true,
      representative: true,
    })));
  }
  return {
    items: items.slice(0, 32),
    draped,
    stations,
    path: {
      ...drape,
      ...path,
      hold_down_elevation_in: holdElev,
      end_elevation_in: endElev,
      hold_down_stations_ft: stations,
      source: path.source || drape.source || (draped && stations.length ? "parametric_midspan" : "none"),
    },
    patternSource: items.some((item) => item.representative) ? "unconfirmed" : (system.pattern_source || blueprint.strand_pattern_source || (rows.length ? "extracted" : "unconfirmed")),
    treatment,
    diameterIn: Number(system.diameter_in) || 0.5,
    holdDownType: system.hold_down_type || blueprint.hold_down_type,
    notes: system.notes || path.notes || drape.notes || [],
  };
}

function strandPath(item, spec, stations) {
  const start = [item.x, item.y, 0];
  const finish = [item.x, item.y, spec.length];
  if (!item.draped || !stations.length) {
    return [start, finish];
  }
  const holdY = inchesToFeet(item.holdYIn);
  const points = [start];
  stations.forEach((station, index) => {
    const previous = index === 0 ? 0 : stations[index - 1];
    const approach = previous + (station - previous) * 0.72;
    points.push([item.x, (item.y + holdY) / 2, approach]);
    points.push([item.x, holdY, station]);
  });
  const last = stations[stations.length - 1];
  points.push([item.x, (item.y + holdY) / 2, last + (spec.length - last) * 0.28]);
  points.push(finish);
  return points;
}

function StrandCable({ path, radius, color }) {
  const pathKey = (path || []).map((point) => point.join(",")).join("|");
  const geometry = useMemo(() => {
    const points = (path || []).map(([x, y, z]) => new THREE.Vector3(x, y, z));
    if (points.length < 2) return null;
    const curve = new THREE.CatmullRomCurve3(points, false, "catmullrom", 0.08);
    return new THREE.TubeGeometry(curve, Math.min(56, Math.max(18, points.length * 10)), radius, 7, false);
  }, [pathKey, path, radius]);
  useEffect(() => () => geometry?.dispose?.(), [geometry]);
  if (!geometry) return null;
  return (
    <mesh geometry={geometry} castShadow>
      <meshStandardMaterial color={color} roughness={0.22} metalness={0.84} />
    </mesh>
  );
}

function StrandEndTreatment({ type, x, y, z, radius, outward }) {
  if (type === "cut_flush_bituminous") {
    return (
      <group position={[x, y, z]}>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[radius * 1.7, radius * 1.7, 0.05, 14]} />
          <meshStandardMaterial color={asphaltBlack} roughness={0.96} metalness={0.02} />
        </mesh>
        <mesh rotation={[Math.PI / 2, 0, 0]} position={[0, 0, outward * 0.02]}>
          <cylinderGeometry args={[radius * 1.2, radius * 1.2, 0.03, 12]} />
          <meshStandardMaterial color="#2A2A2A" roughness={1} metalness={0} />
        </mesh>
      </group>
    );
  }
  if (type === "bent_90") {
    const hook = Math.max(0.32, radius * 8);
    return (
      <group position={[x, y, z]}>
        <mesh position={[0, 0, outward * hook * 0.22]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[radius * 1.08, radius * 1.08, hook * 0.44, 10]} />
          <meshStandardMaterial color={brassGold} roughness={0.26} metalness={0.8} />
        </mesh>
        <mesh position={[0, hook * 0.3, outward * hook * 0.44]}>
          <cylinderGeometry args={[radius * 1.08, radius * 1.08, hook * 0.6, 10]} />
          <meshStandardMaterial color={brassGold} roughness={0.26} metalness={0.8} />
        </mesh>
      </group>
    );
  }
  return (
    <group position={[x, y, z]}>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[radius * 1.45, radius * 1.25, 0.1, 12]} />
          <meshStandardMaterial color={steelGray} roughness={0.28} metalness={0.78} />
      </mesh>
    </group>
  );
}

function StrandSystem({ beam, spec, onHardwareSelect, pourMode, showPaths }) {
  const layout = useMemo(() => strandLayout(spec, beam), [spec, beam]);
  const radius = Math.max(inchesToFeet((layout.diameterIn || 0.5) * 3.1), 0.055);
  const prePour = pourMode === "pre_pour";
  const extractedHoldStations = (spec.blueprint.hold_downs || []).map((item) => stationValue(item)).filter((value) => value != null);
  const parametricStations = prePour
    ? layout.stations.filter((station) => !extractedHoldStations.some((value) => Math.abs(value - station) < 0.05))
    : [];
  if (!layout.items.length) return null;
  return (
    <group>
      {showPaths && layout.items.map((item, index) => {
        const path = strandPath(item, spec, layout.stations);
        const payload = {
          id: `strand-${index}`,
          type: item.draped ? "Draped prestressing strand" : "Straight prestressing strand",
          beamMark: beam.mark,
          spec: { index: index + 1, draped: item.draped, representative: Boolean(item.representative), y_in: item.yIn, path_source: layout.path.source },
        };
        return (
          <group key={payload.id} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
            <StrandCable path={path} radius={radius} color={item.draped ? strandDrapedColor : strandStraightColor} />
          </group>
        );
      })}
      {layout.items.map((item, index) => (
        <React.Fragment key={`tip-${index}`}>
          <StrandEndTreatment type={layout.treatment?.type || "unspecified"} x={item.x} y={item.y} z={-0.06} radius={radius} outward={-1} />
          <StrandEndTreatment type={layout.treatment?.type || "unspecified"} x={item.x} y={item.y} z={spec.length + 0.06} radius={radius} outward={1} />
        </React.Fragment>
      ))}
      {parametricStations.length > 0 && (
        <HoldDowns
          beam={beam}
          spec={spec}
          onHardwareSelect={onHardwareSelect}
          stations={parametricStations}
          parametric
        />
      )}
      {prePour && layout.patternSource === "unconfirmed" && (
        <Html position={[0, spec.depth * 0.55, spec.length * 0.5]} center distanceFactor={22} occlude={false}>
          <div style={{
            background: "rgba(10,12,16,0.92)",
            border: "1px solid #2DD4BF",
            color: "#5EEAD4",
            padding: "4px 8px",
            fontSize: 10,
            fontFamily: "JetBrains Mono, monospace",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            whiteSpace: "nowrap",
          }}>
            Strand pattern unconfirmed · {layout.path.source === "parametric_midspan" ? "parametric drape" : layout.path.source}
          </div>
        </Html>
      )}
    </group>
  );
}

function MarkedEnd({ beam, spec, onHardwareSelect }) {
  const area = spec.blueprint.marked_end || {};
  const color = area.color || "#F4F7FB";
  const z = area.end === "end" ? spec.length - 0.09 : 0.09;
  const payload = { id: "marked-end", type: "Marked end", beamMark: beam.mark, spec: area };
  return (
    <group position={[0, spec.depth * 0.82, z]}>
      <mesh onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
        <boxGeometry args={[spec.width * 0.62, spec.depth * 0.22, 0.06]} />
        <meshStandardMaterial color={color} roughness={0.92} metalness={0.01} />
      </mesh>
      <CalloutTag position={[0, spec.depth * 0.12, 0]} color={color} label={area.label || "MARKED END"} />
    </group>
  );
}

function calloutLine(points, color = "#73BCFF") {
  return <Line points={points} color={color} lineWidth={1} />;
}

function finiteNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function valueOrNull(...values) {
  for (const value of values) {
    const number = finiteNumber(value);
    if (number != null && number > 0) return number;
  }
  return null;
}

function angleDegrees(runFt, riseFt) {
  if (!runFt || !riseFt) return null;
  return Math.round((Math.atan2(riseFt, runFt) * 180 / Math.PI) * 10) / 10;
}

function DimensionLabel({ position, label, color = "#73BCFF" }) {
  return (
    <Html position={position} center distanceFactor={18} occlude={false}>
      <div style={{
        background: "rgba(6,8,13,0.96)",
        border: `1px solid ${color}`,
        color,
        padding: "2px 6px",
        fontSize: 9,
        lineHeight: 1.2,
        fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, monospace",
        letterSpacing: "0.08em",
        whiteSpace: "nowrap",
        boxShadow: "0 8px 24px rgba(0,0,0,0.28)",
      }}>
        {label}
      </div>
    </Html>
  );
}

function DimensionLine({ start, end, label, labelPosition, color = "#73BCFF", tick = 0.18, tickAxis = "y" }) {
  const tickVector = {
    x: [tick, 0, 0],
    y: [0, tick, 0],
    z: [0, 0, tick],
  }[tickAxis] || [0, tick, 0];
  const tickLine = (point, key) => (
    <Line
      key={key}
      points={[
        [point[0] - tickVector[0], point[1] - tickVector[1], point[2] - tickVector[2]],
        [point[0] + tickVector[0], point[1] + tickVector[1], point[2] + tickVector[2]],
      ]}
      color={color}
      lineWidth={1}
    />
  );
  return (
    <group>
      <Line points={[start, end]} color={color} lineWidth={1} />
      {tickLine(start, "start")}
      {tickLine(end, "end")}
      {label && <DimensionLabel position={labelPosition || [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2, (start[2] + end[2]) / 2]} label={label} color={color} />}
    </group>
  );
}

function MeasurementText({ position, label, color = "#D8ECFF", size = 10 }) {
  return (
    <Html position={position} center distanceFactor={18} occlude={false}>
      <span style={{
        color,
        fontSize: size,
        fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, monospace",
        fontWeight: 700,
        letterSpacing: "0.03em",
        whiteSpace: "nowrap",
        textShadow: "0 1px 2px rgba(0,0,0,0.95), 0 0 8px rgba(10,12,16,0.9)",
        pointerEvents: "none",
      }}>
        {label}
      </span>
    </Html>
  );
}

function ElevationMeasurementText({ position, label, size = 9 }) {
  return (
    <Html position={position} center distanceFactor={18} occlude={false}>
      <span style={{
        color: elevationDimensionColor,
        background: "rgba(245,247,250,0.94)",
        border: "1px solid rgba(5,5,5,0.72)",
        padding: "1px 4px",
        fontSize: size,
        fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, monospace",
        fontWeight: 800,
        letterSpacing: "0.02em",
        whiteSpace: "nowrap",
        boxShadow: "0 2px 10px rgba(0,0,0,0.32)",
        pointerEvents: "none",
      }}>
        {label}
      </span>
    </Html>
  );
}

function stationValue(item) {
  const raw = item?.x_ft ?? item?.station_ft ?? item?.station_from_marked_end;
  const value = finiteNumber(raw);
  return value != null && value >= 0 ? value : null;
}

function runningDimensionStations(spec) {
  const add = (rows, source, kind) => {
    (source || []).forEach((item, index) => {
      const station = stationValue(item);
      if (station == null) return;
      rows.push({ key: `${kind}-${index}`, kind, station });
    });
  };
  const rows = [];
  add(rows, spec.blueprint.lift_loops, "Lift");
  add(rows, spec.blueprint.inserts, "Insert");
  add(rows, spec.blueprint.tubes, "Tube");
  add(rows, spec.blueprint.tie_rod_openings, "Tie");
  add(rows, spec.blueprint.drain_holes, "Drain");
  add(rows, spec.blueprint.hold_downs, "Hold-down");
  const stirrup = spec.blueprint.stirrups || {};
  const stirrupStart = finiteNumber(stirrup.start_ft);
  if (stirrupStart != null) {
    rows.push({ key: "stirrup-start", kind: "Stirrup", station: stirrupStart });
  }
  const sorted = rows
    .filter((item) => item.station >= 0 && item.station <= spec.length)
    .sort((a, b) => a.station - b.station || a.kind.localeCompare(b.kind));
  return sorted.reduce((grouped, item) => {
    const previous = grouped[grouped.length - 1];
    if (previous && Math.abs(previous.station - item.station) < 0.05) {
      previous.kinds = [...new Set([...previous.kinds, item.kind])];
      previous.label = previous.kinds.map((kind) => kind.toUpperCase()).join(" / ");
      previous.key = `${previous.key}-${item.key}`;
    } else {
      grouped.push({ ...item, kinds: [item.kind], label: item.kind.toUpperCase() });
    }
    return grouped;
  }, []);
}

function elevationDimensionTargets(spec) {
  const centerElevation = (item, fallbackY) => {
    const heightIn = finiteNumber(item?.height_in ?? item?.height_from_soffit_in ?? item?.center_height_in);
    const y = heightIn != null && heightIn > 0 ? inchesToFeet(heightIn) : fallbackY;
    return Math.min(Math.max(y, 0.08), Math.max(spec.depth - 0.08, 0.08));
  };
  const targets = [];
  (spec.blueprint.inserts || []).forEach((item, index) => {
    const station = stationValue(item);
    if (station == null) return;
    targets.push({ key: `elev-insert-${index}`, station, y: centerElevation(item, spec.depth * 0.7), kind: "insert" });
  });
  (spec.blueprint.tubes || []).forEach((item, index) => {
    const station = stationValue(item);
    if (station == null) return;
    targets.push({ key: `elev-tube-${index}`, station, y: centerElevation(item, spec.depth * 0.56), kind: "tube" });
  });
  (spec.blueprint.tie_rod_openings || []).forEach((item, index) => {
    const station = stationValue(item);
    if (station == null) return;
    targets.push({ key: `elev-tie-${index}`, station, y: centerElevation(item, spec.depth * 0.42), kind: "tie" });
  });
  (spec.blueprint.drain_holes || []).forEach((item, index) => {
    const station = stationValue(item);
    if (station == null) return;
    targets.push({ key: `elev-drain-${index}`, station, y: centerElevation(item, 0.18), kind: "drain" });
  });
  const unique = [];
  targets
    .filter((item) => item.station >= 0 && item.station <= spec.length)
    .sort((a, b) => a.station - b.station || a.y - b.y)
    .forEach((item) => {
      const duplicate = unique.some((existing) => Math.abs(existing.station - item.station) < 0.05 && Math.abs(existing.y - item.y) < 0.05);
      if (!duplicate) unique.push(item);
    });
  return unique;
}

function EngineeringDimensions({ beam, spec, showOverall = true, showStations = true }) {
  const lengthFt = valueOrNull(spec.blueprint.dimensions?.overall_length_ft, beam.length_ft, spec.length);
  const stations = showStations ? runningDimensionStations(spec) : [];
  const sideX = -spec.width / 2 - 0.1;
  const tubeRowY = spec.depth * 0.56;
  const runLineY = Math.max(spec.depth * 0.34, tubeRowY - 0.52);
  const overallY = -0.48;
  const elevationTargets = showOverall ? elevationDimensionTargets(spec) : [];
  const finalStation = stations.length ? Math.max(...stations.map((item) => item.station)) : 0;
  return (
    <group>
      {showOverall && lengthFt && (
        <group>
          <Line points={[[0, overallY, 0], [0, overallY, spec.length]]} color={overallDimensionColor} lineWidth={1.4} />
          <Line points={[[-0.16, overallY, 0], [0.16, overallY, 0]]} color={overallDimensionColor} lineWidth={1.1} />
          <Line points={[[-0.16, overallY, spec.length], [0.16, overallY, spec.length]]} color={overallDimensionColor} lineWidth={1.1} />
          <MeasurementText position={[0, overallY - 0.32, spec.length / 2]} label={`OAL ${formatFeet(lengthFt)}`} color={overallDimensionColor} size={14} />
        </group>
      )}
      {showStations && stations.length > 0 && (
        <group>
          {finalStation > 0 && (
            <Line points={[[sideX, runLineY, 0], [sideX, runLineY, finalStation]]} color={runningDimensionColor} lineWidth={1.1} />
          )}
          <Line points={[[sideX - 0.16, runLineY, 0], [sideX + 0.16, runLineY, 0]]} color={runningDimensionColor} lineWidth={1} />
          <MeasurementText position={[sideX - 0.08, runLineY + 0.28, 0]} label={`ME 0'-0"`} color={runningDimensionColor} />
          {stations.map((item, index) => {
            const lane = index % 3;
            const side = index % 2 === 0 ? -1 : 1;
            const textY = runLineY + 0.28 + lane * 0.26;
            const labelX = sideX - 0.08 + (side > 0 ? 0 : -0.02);
            return (
              <group key={item.key}>
                <Line points={[[sideX - 0.18, runLineY, item.station], [sideX + 0.18, runLineY, item.station]]} color={runningDimensionColor} lineWidth={1} />
                <Line points={[[sideX, runLineY, item.station], [labelX, textY - 0.08, item.station]]} color={runningDimensionColor} lineWidth={0.6} />
                <MeasurementText position={[labelX, textY, item.station]} label={`ME→${item.label || item.kind} ${formatFeet(item.station)}`} color={runningDimensionColor} />
              </group>
            );
          })}
        </group>
      )}
      {elevationTargets.map((item, index) => {
        const x = sideX - 0.46 - (index % 3) * 0.18;
        const z = item.station;
        const tick = 0.14;
        return (
          <group key={item.key}>
            <Line points={[[x, 0, z], [x, item.y, z]]} color={elevationDimensionColor} lineWidth={1.1} />
            {[0, item.y].map((y) => (
              <Line key={`${item.key}-${y}`} points={[[x - tick, y, z], [x + tick, y, z]]} color={elevationDimensionColor} lineWidth={1.05} />
            ))}
            <Line points={[[x + tick, item.y, z], [sideX + 0.02, item.y, item.station]]} color={elevationDimensionColor} lineWidth={0.65} />
            <ElevationMeasurementText position={[x - 0.13, item.y + 0.16, z]} label={formatFeet(item.y)} />
          </group>
        );
      })}
    </group>
  );
}

function hardwareCalloutItems(beam, spec) {
  const items = [];
  const pushStationed = (source, kind, color, anchorBuilder, labelBuilder) => {
    (source || []).forEach((item, index) => {
      const station = stationValue(item);
      if (station == null) return;
      items.push({ key: `${kind}-${index}`, category: kind, color, anchor: anchorBuilder(item, station), station, label: labelBuilder(item, station) });
    });
  };
  pushStationed(spec.blueprint.lift_loops, "Lift loop", "#DCE6F2", (_item, station) => [0, spec.depth + 0.35, station], (_item, station) => `LIFT ${formatStation(station)}`);
  (spec.blueprint.inserts || []).forEach((item, index) => {
    const station = stationValue(item);
    if (station == null) return;
    const side = item.side === "right" ? 1 : -1;
    items.push({ key: `insert-${index}`, category: "Insert", color: "#F4B652", anchor: [side * spec.width / 2, spec.depth * 0.7, station], station, label: `INSERT ${formatStation(station)}` });
  });
  pushStationed(spec.blueprint.tubes, "Tube", "#B1BCCB", (_item, station) => [0, spec.depth * 0.56, station], (_item, station) => `TUBE ${formatStation(station)}`);
  pushStationed(spec.blueprint.tie_rod_openings, "Tie-rod", "#AEB8C6", (_item, station) => [0, spec.depth * 0.42, station], (_item, station) => `TIE ${formatStation(station)}`);
  pushStationed(spec.blueprint.drain_holes, "Drain", "#9AA6B5", (_item, station) => [0, 0.18, station], (_item, station) => `DRAIN ${formatStation(station)}`);
  pushStationed(spec.blueprint.hold_downs, "Hold-down", "#DFA26A", (_item, station) => [0, spec.depth + 0.35, station], (_item, station) => `HOLD-DOWN ${formatStation(station)}`);
  pushStationed(spec.blueprint.grout_grooves, "Groove", "#C5D0DE", (_item, station) => [0, spec.depth + 0.1, station], (_item, station) => `GROOVE ${formatStation(station)}`);
  (spec.blueprint.bituminous_ends || []).forEach((item, index) => {
    const z = item.end === "end" ? spec.length - inchesToFeet(item.length_in || 18) / 2 : inchesToFeet(item.length_in || 18) / 2;
    items.push({ key: `bit-${index}`, category: "Bituminous", color: "#E5E7EB", anchor: [0, spec.depth * 0.18, z], station: z, label: `BITUMEN ${item.end?.toUpperCase() || "END"} ${formatInches(item.length_in || 18)}` });
  });
  return items.sort((a, b) => a.station - b.station);
}

function SmartHardwareCallouts({ beam, spec }) {
  const items = hardwareCalloutItems(beam, spec);
  if (!items.length) return null;
  const rows = 4;
  const minGap = Math.max(spec.length / Math.max(items.length, 1), 3.2);
  const placed = items.map((item, index) => {
    const side = index % 2 === 0 ? -1 : 1;
    const row = Math.floor(index / 2) % rows;
    const z = Math.min(Math.max(item.station, 1.5), Math.max(spec.length - 1.5, 1.5));
    const spreadZ = Math.min(Math.max(z + (row - 1.5) * Math.min(minGap * 0.22, 1.8), 0.8), spec.length - 0.8);
    const x = side * (spec.width * 1.65 + row * 0.35);
    const y = spec.depth + 0.75 + row * 0.22;
    return { ...item, tag: [x, y, spreadZ] };
  });
  return (
    <group>
      {placed.map((item) => (
        <group key={item.key}>
          <Line points={[item.anchor, [item.tag[0] * 0.78, item.tag[1] - 0.08, item.tag[2]], item.tag]} color={item.color} lineWidth={0.8} />
          <DimensionLabel position={item.tag} label={item.label} color={item.color} />
        </group>
      ))}
    </group>
  );
}

function DimensionCallouts({ beam, spec }) {
  const section = spec.blueprint.cross_section || {};
  const depthIn = beam.product_type?.depth_in || Math.round(spec.depth * 12 * 10) / 10;
  const widthIn = beam.product_type?.width_in || Math.round(spec.width * 12 * 10) / 10;
  const lifts = spec.blueprint.lift_loops || [];
  const drains = spec.blueprint.drain_holes || [];
  const inserts = spec.blueprint.inserts || [];
  const tubes = spec.blueprint.tubes || [];
  const holdDowns = spec.blueprint.hold_downs || [];
  const stirrupSpacing = spec.blueprint.stirrups?.spacing_in;
  const bituminous = spec.blueprint.bituminous_ends || [];
  const groutGrooves = spec.blueprint.grout_grooves || [];
  const items = [
    {
      key: "length",
      label: `OAL ${formatFeet(beam.length_ft)} · ${beam.mark}`,
      color: "#73BCFF",
      line: [[-spec.width * 0.64, spec.depth + 0.2, 0], [-spec.width * 0.64, spec.depth + 0.2, spec.length]],
      tag: [-spec.width * 0.9, spec.depth + 0.56, spec.length / 2],
    },
    {
      key: "depth",
      label: `DEPTH ${formatInches(depthIn)}`,
      color: "#73BCFF",
      line: [[spec.width * 0.62, 0, spec.length * 0.16], [spec.width * 0.62, spec.depth, spec.length * 0.16]],
      tag: [spec.width * 0.98, spec.depth / 2, spec.length * 0.16],
    },
    {
      key: "width",
      label: `WIDTH ${formatInches(widthIn)}`,
      color: "#73BCFF",
      line: [[-spec.width / 2, spec.depth + 0.2, spec.length * 0.1], [spec.width / 2, spec.depth + 0.2, spec.length * 0.1]],
      tag: [0, spec.depth + 0.6, spec.length * 0.1],
    },
  ];

  if (lifts.length) {
    const first = lifts[0]?.x_ft ?? 0;
    const last = lifts[lifts.length - 1]?.x_ft ?? first;
    items.push({
      key: "lift-loops",
      label: lifts.length > 1 ? `LIFT LOOPS ${formatFeet(first)} / ${formatFeet(last)}` : `LIFT LOOP ${formatFeet(first)}`,
      color: "#C9D4E1",
      line: [[0, spec.depth + 0.15, first], [0, spec.depth + 0.15, last]],
      tag: [spec.width * 0.42, spec.depth + 0.48, (first + last) / 2],
    });
  }

  if (inserts.length) {
    const first = inserts[0]?.x_ft ?? 0;
    const last = inserts[inserts.length - 1]?.x_ft ?? first;
    items.push({
      key: "inserts",
      label: `INSERTS ${formatStation(first)} / ${formatStation(last)}`,
      color: "#F4B652",
      line: [[-spec.width * 0.52, spec.depth * 0.72, first], [-spec.width * 0.52, spec.depth * 0.72, last]],
      tag: [-spec.width * 0.98, spec.depth * 0.88, (first + last) / 2],
    });
  }

  if (drains.length) {
    items.push({
      key: "drains",
      label: `DRAINS ${drains.map((item) => formatStation(item.x_ft)).join(" / ")}`,
      color: "#A5B0BE",
      line: [[spec.width * 0.5, 0.18, drains[0].x_ft], [spec.width * 0.5, 0.18, drains[drains.length - 1].x_ft]],
      tag: [spec.width * 0.98, 0.48, (drains[0].x_ft + drains[drains.length - 1].x_ft) / 2],
    });
  }

  if (tubes.length) {
    items.push({
      key: "tubes",
      label: `TUBES ${tubes.map((item) => formatStation(item.x_ft)).join(" / ")}`,
      color: "#B1BCCB",
      line: [[spec.width * 0.46, spec.depth * 0.56, tubes[0].x_ft], [spec.width * 0.46, spec.depth * 0.56, tubes[tubes.length - 1].x_ft]],
      tag: [spec.width * 0.98, spec.depth * 0.66, (tubes[0].x_ft + tubes[tubes.length - 1].x_ft) / 2],
    });
  }

  if (holdDowns.length) {
    items.push({
      key: "hold-downs",
      label: `HOLD-DOWNS ${holdDowns.length} PCS · ${formatStation(holdDowns[0].x_ft)}-${formatStation(holdDowns[holdDowns.length - 1].x_ft)}`,
      color: "#DFA26A",
      line: [[0, spec.depth + 0.34, holdDowns[0].x_ft], [0, spec.depth + 0.34, holdDowns[holdDowns.length - 1].x_ft]],
      tag: [0, spec.depth + 0.78, (holdDowns[0].x_ft + holdDowns[holdDowns.length - 1].x_ft) / 2],
    });
  }

  if (stirrupSpacing) {
    items.push({
      key: "stirrups",
      label: `STIRRUPS @ ${formatInches(stirrupSpacing)}`,
      color: "#91A0B2",
      line: [[-spec.width * 0.44, spec.depth * 0.4, spec.length * 0.5], [-spec.width * 0.26, spec.depth * 0.4, spec.length * 0.5]],
      tag: [-spec.width * 0.88, spec.depth * 0.52, spec.length * 0.5],
    });
  }

  if (bituminous.length) {
    items.push({
      key: "bituminous",
      label: `BITUMEN ${bituminous.map((item) => formatInches(item.length_in || 18)).join(" / ")}`,
      color: "#E5E7EB",
      line: [[0, spec.depth * 0.18, 0], [0, spec.depth * 0.18, inchesToFeet(bituminous[0]?.length_in || 18)]],
      tag: [spec.width * 0.52, spec.depth * 0.34, inchesToFeet(bituminous[0]?.length_in || 18) + 0.5],
    });
  }

  if (beam.twin_type === "box_beam") {
    items.push({
      key: "void",
      label: `VOID ${formatInches(section.void_width_in || widthIn - 12)} × ${formatInches(section.void_depth_in || depthIn - 10)}`,
      color: "#9DB0C4",
      line: [[0, spec.depth * 0.62, spec.length * 0.22], [0, spec.depth * 0.62, spec.length * 0.78]],
      tag: [0, spec.depth * 0.82, spec.length * 0.5],
    });
    if (groutGrooves.length) {
      items.push({
        key: "grout-grooves",
        label: `GROUT GROOVES ${groutGrooves.map((item) => formatStation(item.x_ft)).join(" / ")}`,
        color: "#C5D0DE",
        line: [[0, spec.depth + 0.06, groutGrooves[0].x_ft], [0, spec.depth + 0.06, groutGrooves[groutGrooves.length - 1].x_ft]],
        tag: [-spec.width * 0.52, spec.depth + 0.36, (groutGrooves[0].x_ft + groutGrooves[groutGrooves.length - 1].x_ft) / 2],
      });
    }
  } else {
    items.push({
      key: "section-web",
      label: `WEB ${formatInches(section.web_thickness_in || 7)} · TOP ${formatInches(section.top_flange_width_in || widthIn)} × ${formatInches(section.top_flange_thickness_in || 7)}`,
      color: "#C5D0DE",
      line: [[0, spec.depth * 0.76, spec.length * 0.23], [0, spec.depth * 0.76, spec.length * 0.77]],
      tag: [0, spec.depth + 0.18, spec.length * 0.5],
    });
    items.push({
      key: "section-bottom",
      label: `BOT FLG ${formatInches(section.bottom_flange_width_in || widthIn * 1.5)} × ${formatInches(section.bottom_flange_thickness_in || 8)}`,
      color: "#AAB5C4",
      line: [[0, spec.depth * 0.08, spec.length * 0.25], [0, spec.depth * 0.08, spec.length * 0.75]],
      tag: [0, 0.22, spec.length * 0.5],
    });
  }

  return items.map((item) => (
    <group key={item.key}>
      {calloutLine(item.line, item.color)}
      <CalloutTag position={item.tag} color={item.color} label={item.label} />
    </group>
  ));
}

function Anomalies({ anomalies, spec }) {
  return (anomalies || []).map((item) => {
    const z = Math.min(Math.max(item.position?.x || 0, 0), spec.length);
    const y = Math.min(Math.max(item.position?.y || spec.depth * 0.55, 0.2), spec.depth - 0.1);
    const x = Math.min(Math.max(item.position?.z || spec.width * 0.4, -spec.width / 2), spec.width / 2);
    const color = item.severity === "major" ? "#FF3366" : item.severity === "moderate" ? "#FFD600" : "#2979FF";
    return (
      <mesh key={item.id} position={[x, y, z]}>
        <sphereGeometry args={[0.14, 16, 16]} />
        <meshBasicMaterial color={color} />
        <Html position={[0, 0.28, 0]} distanceFactor={13}>
          <div style={{ background: "#12151C", border: `1px solid ${color}`, color, padding: "2px 5px", fontSize: 9, fontFamily: "JetBrains Mono, monospace", whiteSpace: "nowrap" }}>
            {item.type?.toUpperCase()}
          </div>
        </Html>
      </mesh>
    );
  });
}

function BeamAssembly({ beam, anomalies = [], onSurfacePick, onHardwareSelect, showCallouts = true, layers = {}, highlighted = false, onBeamSelect, pourMode = "post_pour" }) {
  const spec = useBeamSpec(beam);
  const activeLayers = {
    dimensions: showCallouts,
    stations: showCallouts,
    hardware: false,
    strands: false,
    stirrups: false,
    anomalies: true,
    ...layers,
  };
  const groupRef = useRef(null);
  const prePour = pourMode === "pre_pour";
  const surfacePick = (point) => {
    const localPoint = groupRef.current ? groupRef.current.worldToLocal(point.clone()) : point;
    onSurfacePick?.(localPoint, beam);
  };
  return (
    <group ref={groupRef} position={[0, -spec.depth / 2, -spec.length / 2]}>
      <Shell spec={spec} beam={beam} highlighted={highlighted} onSurfacePick={surfacePick} onBeamSelect={onBeamSelect} pourMode={pourMode} />
      {(prePour || activeLayers.dimensions) && <SectionRevealLines beam={beam} spec={spec} />}
      {!prePour && activeLayers.hardware && <BituminousEnds beam={beam} spec={spec} onHardwareSelect={onHardwareSelect} />}
      <StrandSystem beam={beam} spec={spec} onHardwareSelect={onHardwareSelect} pourMode={pourMode} showPaths={prePour && activeLayers.strands} />
      {activeLayers.stirrups && <Stirrups beam={beam} spec={spec} onHardwareSelect={onHardwareSelect} />}
      {(activeLayers.hardware || activeLayers.stirrups) && <LiftLoops beam={beam} spec={spec} onHardwareSelect={onHardwareSelect} />}
      {activeLayers.hardware && <SideInserts beam={beam} spec={spec} onHardwareSelect={onHardwareSelect} />}
      {activeLayers.hardware && <CylindricalOpenings beam={beam} spec={spec} items={spec.blueprint.tubes} type="Tube" color="#4F5968" y={spec.depth * 0.56} onHardwareSelect={onHardwareSelect} />}
      {activeLayers.hardware && <CylindricalOpenings beam={beam} spec={spec} items={spec.blueprint.tie_rod_openings} type="Tie-rod opening" color="#0F172A" y={spec.depth * 0.42} onHardwareSelect={onHardwareSelect} />}
      {activeLayers.hardware && <CylindricalOpenings beam={beam} spec={spec} items={spec.blueprint.drain_holes} type="Drain hole" color="#111827" y={0.18} onHardwareSelect={onHardwareSelect} />}
      {activeLayers.hardware && <HoldDowns beam={beam} spec={spec} onHardwareSelect={onHardwareSelect} />}
      {activeLayers.hardware && <GroutGrooves beam={beam} spec={spec} onHardwareSelect={onHardwareSelect} />}
      <MarkedEnd beam={beam} spec={spec} onHardwareSelect={onHardwareSelect} />
      {(activeLayers.dimensions || activeLayers.stations) && (
        <EngineeringDimensions beam={beam} spec={spec} showOverall={activeLayers.dimensions} showStations={activeLayers.stations} />
      )}
      {!prePour && activeLayers.hardware && <SmartHardwareCallouts beam={beam} spec={spec} />}
      {activeLayers.anomalies && <Anomalies anomalies={anomalies} spec={spec} />}
    </group>
  );
}

function Scene({ children, camera, target = ORBIT_TARGET }) {
  const [contextLost, setContextLost] = useState(false);

  if (contextLost) {
    return <TwinCanvasFallback message="The 3D canvas lost its graphics context. Reload the page or switch views to retry." />;
  }

  return (
    <TwinCanvasErrorBoundary fallback={<TwinCanvasFallback message="The 3D viewer could not start, but the Digital Twin page is still available." />}>
      <Canvas camera={camera} dpr={[1, 1.5]} shadows gl={{ antialias: true, powerPreference: "high-performance" }}>
        <Suspense fallback={<Html center><div style={{ color: "#A7B0BF", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 12, letterSpacing: "0.16em", textTransform: "uppercase" }}>Loading twin…</div></Html>}>
         <CanvasContextMonitor onContextLost={() => setContextLost(true)} />
         <color attach="background" args={["#07090D"]} />
        <ambientLight intensity={0.42} />
        <hemisphereLight intensity={0.4} color="#E8EEF6" groundColor="#16110C" />
        <directionalLight position={[16, 22, 10]} intensity={1.32} castShadow />
        <directionalLight position={[-12, 9, -6]} intensity={0.38} color="#9BE7FF" />
        <directionalLight position={[4, 8, -16]} intensity={0.28} color="#2DD4BF" />
        {children}
         <OrbitControls enablePan enableZoom enableRotate maxPolarAngle={Math.PI * 0.48} makeDefault target={target} />
        </Suspense>
      </Canvas>
    </TwinCanvasErrorBoundary>
  );
}


export function SpecBeam({ spec, compact = false, bodyColor = "#9aa0aa", highlighted = false, onClick, mark, anomalies = [], pickPos, onPick }) {
  const geo = spec?.geometry || {};
  const length = Math.max(Number(geo.length_ft) || 40, 4);
  const depth = inchesToFeet(Number(geo.depth_in) || 36);
  const width = inchesToFeet(Number(geo.width_in || geo.top_flange_width_in || geo.bot_flange_width_in) || 18);
  const hardware = compact ? [] : (spec?.hardware || []);
  const handleClick = (e) => {
    e.stopPropagation();
    if (onPick) onPick(e.point);
    if (onClick) onClick(e);
  };
  return (
    <group onClick={handleClick}>
      <mesh position={[0, depth / 2, length / 2]} castShadow receiveShadow>
        <boxGeometry args={[Math.max(width, 0.8), Math.max(depth, 0.8), length]} />
        <meshStandardMaterial color={bodyColor} roughness={0.82} metalness={highlighted ? 0.18 : 0.04} emissive={highlighted ? bodyColor : "#000000"} emissiveIntensity={highlighted ? 0.25 : 0} />
      </mesh>
      {hardware.map((item) => {
        const pos = item.position || {};
        return (
          <mesh key={item.id || item.name} position={[inchesToFeet(pos.offset_in || 0), inchesToFeet(pos.height_from_soffit_in || 8), pos.station_ft || 0]}>
            <sphereGeometry args={[0.12, 12, 12]} />
            <meshStandardMaterial color={brassGold} metalness={0.4} roughness={0.35} />
          </mesh>
        );
      })}
      {(anomalies || []).map((a) => {
        const color = a.severity === "major" ? "#FF3366" : a.severity === "moderate" ? "#FFD600" : "#2979FF";
        return (
          <mesh key={a.id} position={[a.position?.z || 0.4, (a.position?.y || 1) * 0.3, Math.min(Math.max(a.position?.x || 0, 0), length)]}>
            <sphereGeometry args={[0.12, 12, 12]} />
            <meshBasicMaterial color={color} />
          </mesh>
        );
      })}
      {pickPos && (
        <mesh position={[pickPos.x, pickPos.y, pickPos.z]}>
          <sphereGeometry args={[0.1, 12, 12]} />
          <meshBasicMaterial color="#2979FF" />
        </mesh>
      )}
      {!compact && <Html position={[0, depth + 0.5, 0]} center><div className="rounded-sm border border-border bg-black/70 px-2 py-1 text-[10px] font-mono text-white">ME · {mark || spec?.beam_mark || "Beam"}</div></Html>}
    </group>
  );
}

function CrossSectionInset({ beam }) {
  const spec = useBeamSpec(beam);
  const [position, setPosition] = useState(() => {
    if (typeof window === "undefined") return { x: 16, y: 420 };
    const saved = window.sessionStorage.getItem("bedforge-section-inset-position");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (Number.isFinite(parsed.x) && Number.isFinite(parsed.y)) return parsed;
      } catch {
        // Ignore stale session state.
      }
    }
    return { x: 16, y: Math.max(16, window.innerHeight - 244) };
  });
  const [viewState, setViewState] = useState(() => {
    if (typeof window === "undefined") return "normal";
    return window.sessionStorage.getItem("bedforge-section-inset-state") || "normal";
  });
  const dragRef = useRef(null);
  const section = spec.blueprint.cross_section || {};
  const isBox = beam?.twin_type === "box_beam";
  const depthIn = valueOrNull(section.overall_depth_in, section.outer_depth_in, beam?.product_type?.depth_in, spec.depth * 12);
  const topWidthIn = valueOrNull(section.top_flange_width_in, section.outer_width_in, beam?.product_type?.width_in, spec.topWidth * 12);
  const bottomWidthIn = valueOrNull(section.bottom_flange_width_in, section.outer_width_in, beam?.product_type?.width_in, spec.width * 12);
  const topThickIn = valueOrNull(section.top_flange_thickness_in, section.top_flange_thick_in);
  const bottomThickIn = valueOrNull(section.bottom_flange_thickness_in, section.bot_flange_thick_in);
  const webIn = valueOrNull(section.web_thickness_in, section.wall_thickness_in);
  const voidWidthIn = valueOrNull(section.void_width_in);
  const voidDepthIn = valueOrNull(section.void_depth_in);
  const wallIn = valueOrNull(section.wall_thickness_in);
  const bottomAngle = !isBox ? angleDegrees(inchesToFeet(valueOrNull(section.bottom_transition_in, 4) || 0), inchesToFeet(valueOrNull(section.bottom_transition_rise_in, 4.5) || 0)) : null;
  const topAngle = !isBox ? angleDegrees(inchesToFeet(valueOrNull(section.top_transition_in, 5) || 0), inchesToFeet(valueOrNull(section.top_transition_drop_in, 4.5) || 0)) : angleDegrees(1, 1);
  const layout = strandLayout(spec, beam);
  const lengthFt = valueOrNull(spec.blueprint.dimensions?.overall_length_ft, spec.length);
  const maxWidth = Math.max(bottomWidthIn || 0, topWidthIn || 0, section.outer_width_in || 0, 1);
  const maxDepth = Math.max(depthIn || 1, 1);
  const sx = 150 / maxWidth;
  const sy = 120 / maxDepth;
  const cx = 122;
  const baseY = 154;
  const x = (inches) => cx + (inches * sx);
  const y = (inches) => baseY - (inches * sy);
  const points = isBox
    ? [
        [x(-(bottomWidthIn || maxWidth) / 2), y(0)],
        [x((bottomWidthIn || maxWidth) / 2), y(0)],
        [x((bottomWidthIn || maxWidth) / 2), y(maxDepth - 2.5)],
        [x((bottomWidthIn || maxWidth) / 2 - 2.5), y(maxDepth)],
        [x(-(bottomWidthIn || maxWidth) / 2 + 2.5), y(maxDepth)],
        [x(-(bottomWidthIn || maxWidth) / 2), y(maxDepth - 2.5)],
      ]
    : [
        [x(-(bottomWidthIn || maxWidth) / 2), y(0)],
        [x((bottomWidthIn || maxWidth) / 2), y(0)],
        [x((bottomWidthIn || maxWidth) / 2), y(bottomThickIn || 0)],
        [x((webIn || maxWidth * 0.25) / 2 + 4), y(bottomThickIn || 0)],
        [x((webIn || maxWidth * 0.25) / 2), y((bottomThickIn || 0) + 4.5)],
        [x((webIn || maxWidth * 0.25) / 2), y(maxDepth - (topThickIn || 0) - 4.5)],
        [x((webIn || maxWidth * 0.25) / 2 + 5), y(maxDepth - (topThickIn || 0))],
        [x((topWidthIn || maxWidth) / 2), y(maxDepth - (topThickIn || 0))],
        [x((topWidthIn || maxWidth) / 2), y(maxDepth)],
        [x(-(topWidthIn || maxWidth) / 2), y(maxDepth)],
        [x(-(topWidthIn || maxWidth) / 2), y(maxDepth - (topThickIn || 0))],
        [x(-(webIn || maxWidth * 0.25) / 2 - 5), y(maxDepth - (topThickIn || 0))],
        [x(-(webIn || maxWidth * 0.25) / 2), y(maxDepth - (topThickIn || 0) - 4.5)],
        [x(-(webIn || maxWidth * 0.25) / 2), y((bottomThickIn || 0) + 4.5)],
        [x(-(webIn || maxWidth * 0.25) / 2 - 4), y(bottomThickIn || 0)],
        [x(-(bottomWidthIn || maxWidth) / 2), y(bottomThickIn || 0)],
      ];
  const poly = points.map(([px, py]) => `${px},${py}`).join(" ");
  const dim = (x1, y1, x2, y2, label, tx, ty) => (
    <g>
      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#73BCFF" strokeWidth="1" />
      <line x1={x1} y1={y1 - 4} x2={x1} y2={y1 + 4} stroke="#73BCFF" strokeWidth="1" />
      <line x1={x2} y1={y2 - 4} x2={x2} y2={y2 + 4} stroke="#73BCFF" strokeWidth="1" />
      <text x={tx} y={ty} fill="#D8ECFF" fontSize="9" textAnchor="middle">{label}</text>
    </g>
  );
  const minimized = viewState === "minimized";
  const maximized = viewState === "maximized";
  const panelWidth = minimized ? 196 : maximized ? 448 : 308;
  const panelHeight = minimized ? 34 : maximized ? 372 : 258;
  const clampPosition = useCallback((next) => {
    if (typeof window === "undefined") return next;
    return {
      x: Math.min(Math.max(8, next.x), Math.max(8, window.innerWidth - panelWidth - 8)),
      y: Math.min(Math.max(8, next.y), Math.max(8, window.innerHeight - panelHeight - 8)),
    };
  }, [panelHeight, panelWidth]);
  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    window.sessionStorage.setItem("bedforge-section-inset-position", JSON.stringify(position));
    return undefined;
  }, [position]);
  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    window.sessionStorage.setItem("bedforge-section-inset-state", viewState);
    setPosition((current) => clampPosition(current));
    return undefined;
  }, [viewState, panelWidth, panelHeight, clampPosition]);
  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const handlePointerMove = (event) => {
      if (!dragRef.current) return;
      const next = {
        x: event.clientX - dragRef.current.offsetX,
        y: event.clientY - dragRef.current.offsetY,
      };
      setPosition(clampPosition(next));
    };
    const stopDrag = () => {
      dragRef.current = null;
    };
    const handleResize = () => setPosition((current) => clampPosition(current));
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", stopDrag);
    window.addEventListener("pointercancel", stopDrag);
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", stopDrag);
      window.removeEventListener("pointercancel", stopDrag);
      window.removeEventListener("resize", handleResize);
    };
  }, [panelWidth, panelHeight, clampPosition]);
  const beginDrag = (event) => {
    event.preventDefault();
    dragRef.current = {
      offsetX: event.clientX - position.x,
      offsetY: event.clientY - position.y,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };
  const cycleSize = (event) => {
    event.stopPropagation();
    setViewState((current) => current === "maximized" ? "normal" : "maximized");
  };
  const toggleMinimized = (event) => {
    event.stopPropagation();
    setViewState((current) => current === "minimized" ? "normal" : "minimized");
  };
  return (
    <div
      data-testid="marked-end-inset"
      style={{
        position: "fixed",
        left: position.x,
        top: position.y,
        width: panelWidth,
        background: "linear-gradient(165deg, rgba(12,18,24,0.98) 0%, rgba(6,8,12,0.97) 55%, rgba(10,12,16,0.98) 100%)",
        border: "1px solid #2DD4BF55",
        boxShadow: "0 18px 48px rgba(0,0,0,0.55), 0 0 28px rgba(45,212,191,0.14), inset 0 1px 0 rgba(232,200,114,0.12)",
        pointerEvents: "auto",
        zIndex: 30,
        userSelect: "none",
      }}
    >
      <div
        onPointerDown={beginDrag}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          color: "#E8C872",
          fontSize: 12,
          fontWeight: 800,
          letterSpacing: "0.18em",
          fontFamily: "JetBrains Mono, monospace",
          padding: minimized ? "10px 12px" : "10px 12px 8px",
          cursor: "grab",
          touchAction: "none",
          borderBottom: minimized ? "none" : "1px solid #1F6F73",
          background: "linear-gradient(90deg, rgba(45,212,191,0.08), rgba(232,200,114,0.05) 40%, transparent)",
        }}
      >
        <span>MARKED END · TIP <span style={{ color: "#5EEAD4", marginLeft: 8, letterSpacing: "0.18em" }}>SPEC</span></span>
        <span style={{ display: "flex", gap: 5, letterSpacing: 0 }}>
          <button type="button" onPointerDown={(event) => event.stopPropagation()} onClick={cycleSize} aria-label={maximized ? "Restore section inset" : "Maximize section inset"} style={{ background: "#0C1218", border: "1px solid #2DD4BF66", color: "#D8ECFF", height: 24, minWidth: 24, cursor: "pointer" }}>{maximized ? "↙" : "↗"}</button>
          <button type="button" onPointerDown={(event) => event.stopPropagation()} onClick={toggleMinimized} aria-label={minimized ? "Restore section inset" : "Minimize section inset"} style={{ background: "#0C1218", border: "1px solid #2DD4BF66", color: "#D8ECFF", height: 24, minWidth: 24, cursor: "pointer" }}>{minimized ? "+" : "−"}</button>
        </span>
      </div>
      {!minimized && (
        <div style={{ padding: "10px 12px 12px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline", color: "#E2E8F0", fontFamily: "JetBrains Mono, monospace", marginBottom: 8 }}>
            <span style={{ color: "#E8C872", fontSize: 13, letterSpacing: "0.12em", fontWeight: 800 }}>OAL {lengthFt != null ? formatFeet(lengthFt) : "unconfirmed"}</span>
            <span style={{ fontSize: 12, letterSpacing: "0.1em" }}>DEPTH {depthIn != null ? formatInches(depthIn) : "unconfirmed"}</span>
          </div>
          <svg viewBox="0 0 260 176" width="100%" height={maximized ? 286 : 168} role="img" aria-label="Marked-end strand pattern and section">
            <defs>
              <pattern id="tech-grid" width="12" height="12" patternUnits="userSpaceOnUse">
                <path d="M 12 0 L 0 0 0 12" fill="none" stroke="#1F3A44" strokeWidth="0.6" />
              </pattern>
              <linearGradient id="steel-fill" x1="0" y1="1" x2="0" y2="0">
                <stop offset="0%" stopColor="#3A4554" />
                <stop offset="55%" stopColor="#1C242E" />
                <stop offset="100%" stopColor="#5EEAD422" />
              </linearGradient>
            </defs>
            <rect x="0" y="0" width="260" height="176" fill="#07090D" />
            <rect x="0" y="0" width="260" height="176" fill="url(#tech-grid)" />
            <rect x="8" y="8" width="244" height="160" fill="none" stroke="#E8C87233" strokeWidth="0.8" />
            <polygon points={poly} fill="url(#steel-fill)" stroke="#5EEAD4" strokeWidth="1.6" />
            {isBox && voidWidthIn && voidDepthIn && (
              <rect x={x(-voidWidthIn / 2)} y={y((wallIn || 4) + voidDepthIn)} width={voidWidthIn * sx} height={voidDepthIn * sy} fill="#05070A" stroke="#8FA1B6" />
            )}
            {layout.items.map((item, index) => (
              <g key={`strand-dot-${index}`}>
                <circle cx={x(item.xIn)} cy={y(item.yIn)} r={maximized ? 5.2 : 4.2} fill="none" stroke={item.draped ? "#5EEAD4" : "#E8C872"} strokeWidth="0.7" opacity="0.45" />
                <circle
                  cx={x(item.xIn)}
                  cy={y(item.yIn)}
                  r={maximized ? 3.6 : 2.9}
                  fill={item.draped ? strandDrapedColor : brassGold}
                  stroke="#0A0C10"
                  strokeWidth="0.7"
                />
              </g>
            ))}
            {bottomWidthIn && dim(x(-bottomWidthIn / 2), 166, x(bottomWidthIn / 2), 166, `${formatInches(bottomWidthIn)}`, cx, 174)}
            {topWidthIn && !isBox && dim(x(-topWidthIn / 2), 15, x(topWidthIn / 2), 15, `${formatInches(topWidthIn)} TOP`, cx, 10)}
            {depthIn && (
              <g>
                <line x1="232" y1={y(0)} x2="232" y2={y(depthIn)} stroke="#73BCFF" strokeWidth="1" />
                <line x1="228" y1={y(0)} x2="236" y2={y(0)} stroke="#73BCFF" strokeWidth="1" />
                <line x1="228" y1={y(depthIn)} x2="236" y2={y(depthIn)} stroke="#73BCFF" strokeWidth="1" />
                <text x="247" y="88" fill="#D8ECFF" fontSize="10" textAnchor="middle" transform="rotate(90 247 88)">{formatInches(depthIn)} DEPTH</text>
              </g>
            )}
            {webIn && !isBox && dim(x(-webIn / 2), 88, x(webIn / 2), 88, `${formatInches(webIn)} WEB`, cx, 82)}
            {topThickIn && <text x="22" y={y(depthIn - topThickIn / 2)} fill="#D8ECFF" fontSize="10">TOP {formatInches(topThickIn)}</text>}
            {bottomThickIn && <text x="18" y={y(bottomThickIn / 2)} fill="#D8ECFF" fontSize="10">BOT {formatInches(bottomThickIn)}</text>}
            {wallIn && isBox && <text x="24" y="92" fill="#D8ECFF" fontSize="10">WALL {formatInches(wallIn)}</text>}
            {topAngle && <text x="192" y="33" fill="#FFD166" fontSize="10">ANGLE {topAngle}°</text>}
            {bottomAngle && <text x="184" y="135" fill="#FFD166" fontSize="10">HAUNCH {bottomAngle}°</text>}
          </svg>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginTop: 8, color: "#94A3B8", fontFamily: "JetBrains Mono, monospace", fontSize: 11, letterSpacing: "0.1em", textTransform: "uppercase" }}>
            <span style={{ color: layout.patternSource === "unconfirmed" ? "#E8C872" : "#5EEAD4" }}>
              {layout.items.some((item) => item.draped) ? "Teal = draped" : "Pattern"} · {layout.patternSource}
            </span>
            <span>{layout.treatment?.label || layout.treatment?.type || "end unspecified"}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function DimensionColorLegend() {
  const item = (color, label) => (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span style={{ width: 18, height: 2, background: color, border: color === elevationDimensionColor ? "1px solid #F5F7FA" : "none", boxShadow: `0 0 10px ${color}66` }} />
      <span>{label}</span>
    </span>
  );
  return (
    <div
      className="absolute left-3.5 bottom-20 sm:bottom-3.5 z-10"
      style={{
      display: "flex",
      gap: 12,
      alignItems: "center",
      border: "1px solid #263244",
      background: "rgba(7,9,14,0.78)",
      padding: "6px 8px",
      color: "#C7D2E1",
      fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, monospace",
      fontSize: 10,
      letterSpacing: "0.12em",
      pointerEvents: "none",
    }}>
      {item(overallDimensionColor, "OVERALL")}
      {item(runningDimensionColor, "RUNNING")}
      {item(elevationDimensionColor, "ELEV")}
    </div>
  );
}

const VIEW_LIFT_MIN = -2;
const VIEW_LIFT_MAX = 12;
const VIEW_LIFT_DEFAULT = 6;
const ORBIT_TARGET = [0, VIEW_LIFT_DEFAULT, 0];

function invertLift(value) {
  return VIEW_LIFT_MIN + VIEW_LIFT_MAX - Number(value);
}

function ViewHeightControl({ value, onChange, align = "right" }) {
  const slider = (
    <input
      type="range"
      min={VIEW_LIFT_MIN}
      max={VIEW_LIFT_MAX}
      step={0.1}
      value={value}
      aria-valuemin={VIEW_LIFT_MIN}
      aria-valuemax={VIEW_LIFT_MAX}
      aria-valuenow={Number(value.toFixed(1))}
      aria-label="View height, raise or lower the beam"
      onChange={(event) => onChange(Number(event.target.value))}
      data-testid="twin-view-height-slider"
      className="accent-primary cursor-pointer"
    />
  );
  return (
    <>
      <div
        className={`hidden sm:flex absolute z-20 top-1/2 -translate-y-1/2 flex-col items-center gap-2 rounded-sm border border-primary/40 bg-[#0A0C10]/92 px-2 py-3 shadow-[0_0_24px_rgba(45,212,191,0.12)] ${align === "left" ? "left-3" : "right-3"}`}
        data-testid="twin-view-height"
      >
        <span className="text-[8px] font-mono uppercase tracking-[0.14em] text-primary text-center leading-tight">View height</span>
        <span className="text-[9px] font-mono uppercase tracking-[0.18em] text-primary [writing-mode:vertical-rl] rotate-180">Raise</span>
        <input
          type="range"
          min={VIEW_LIFT_MIN}
          max={VIEW_LIFT_MAX}
          step={0.1}
          value={invertLift(value)}
          aria-label="View height, raise or lower the beam"
          onChange={(event) => onChange(invertLift(event.target.value))}
          data-testid="twin-view-height-slider-vertical"
          className="h-[min(38vh,220px)] w-9 cursor-pointer accent-primary"
          style={{ writingMode: "vertical-lr" }}
        />
        <span className="text-[9px] font-mono uppercase tracking-[0.18em] text-muted-foreground [writing-mode:vertical-rl] rotate-180">Lower</span>
        <button
          type="button"
          onClick={() => onChange(VIEW_LIFT_DEFAULT)}
          className="mt-1 min-h-8 px-1.5 rounded-sm border border-border text-[9px] font-mono uppercase tracking-wider text-white hover:border-primary hover:text-primary"
        >
          {value.toFixed(1)} ft
        </button>
      </div>
      <div className="sm:hidden absolute z-20 left-3 right-3 bottom-3 rounded-sm border border-primary/40 bg-[#0A0C10]/94 px-3 py-2.5">
        <div className="flex items-center justify-between gap-3 mb-1.5">
          <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-primary">View height · Raise-Lower</span>
          <button
            type="button"
            onClick={() => onChange(VIEW_LIFT_DEFAULT)}
            className="min-h-8 px-2 rounded-sm border border-border text-[10px] font-mono text-white"
          >
            {value.toFixed(1)} ft
          </button>
        </div>
        {slider}
      </div>
    </>
  );
}

function TwinVisualBar({ beam, spec, pourMode }) {
  const layout = strandLayout(spec, beam);
  const lengthFt = valueOrNull(spec.blueprint.dimensions?.overall_length_ft, beam.length_ft, spec.length);
  const job = beam?.beam_spec?.job_number || beam?.beam_spec?.identity?.job_number || "";
  const mark = beam?.mark || beam?.beam_spec?.beam_mark || "MARK";
  const prePour = pourMode === "pre_pour";
  const pathSource = layout.path?.source || "none";
  const pathLabel = layout.draped
    ? (pathSource === "extracted_stations" ? "DRAPED · SPEC STATIONS" : pathSource === "parametric_midspan" ? "DRAPED · PARAMETRIC" : "DRAPED")
    : "STRAIGHT";
  const cells = [
    { kicker: prePour ? "PRE-POUR" : "POST-POUR", value: prePour ? "CABLES / HOLD-DOWNS" : "CONCRETE / TIP PATTERN", accent: true },
    { kicker: job ? `${job} · MK ${mark}` : `MK ${mark}`, value: lengthFt != null ? `OAL ${formatFeet(lengthFt)}` : "OAL UNCONFIRMED" },
    { kicker: pathLabel, value: layout.holdDownType || (layout.draped ? "HOLD-DOWN UNCONFIRMED" : "NO HOLD-DOWNS") },
    { kicker: (layout.treatment?.label || "END UNSPECIFIED").toUpperCase(), value: layout.diameterIn ? `${layout.diameterIn}" STRAND` : "DIA UNCONFIRMED" },
  ];
  return (
    <div
      data-testid="twin-visual-bar"
      style={{
        position: "absolute",
        left: 12,
        right: 64,
        top: 12,
        zIndex: 20,
        pointerEvents: "none",
        display: "flex",
        flexWrap: "wrap",
        gap: 8,
      }}
    >
      {cells.map((cell) => (
        <div
          key={cell.kicker}
          style={{
            minHeight: 52,
            minWidth: 132,
            padding: "8px 12px",
            background: "linear-gradient(180deg, rgba(10,14,20,0.94) 0%, rgba(7,9,13,0.9) 100%)",
            border: cell.accent ? "1px solid rgba(45,212,191,0.55)" : "1px solid #243044",
            boxShadow: cell.accent ? "0 0 22px rgba(45,212,191,0.16)" : "0 10px 24px rgba(0,0,0,0.35)",
            color: "#E8EEF6",
            fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, monospace",
          }}
        >
          <div style={{ color: cell.accent ? "#5EEAD4" : "#E8C872", fontSize: 13, fontWeight: 800, letterSpacing: "0.12em" }}>{cell.kicker}</div>
          <div style={{ marginTop: 4, color: "#C7D2E1", fontSize: 12, letterSpacing: "0.08em" }}>{cell.value}</div>
        </div>
      ))}
    </div>
  );
}

export default function BeamTwinViewer({ beam, anomalies = [], onSurfacePick, onHardwareSelect, showCallouts = true, layers, pourMode = "post_pour" }) {
  const safeBeam = beam || { twin_type: "i_beam", length_ft: 90, product_type: {}, mark: "Beam" };
  const spec = useBeamSpec(safeBeam);
  const [viewLift, setViewLift] = useState(VIEW_LIFT_DEFAULT);
  const cameraDistance = Math.max(safeBeam.length_ft * 0.38, 24);
  const cameraHeight = Math.max(spec.depth * 0.55, 3.4);
  const camera = useMemo(
    () => ({ position: [cameraDistance * 0.28, VIEW_LIFT_DEFAULT + cameraHeight, cameraDistance * 0.96], fov: 32 }),
    [cameraDistance, cameraHeight],
  );
  const activeLayers = {
    dimensions: showCallouts,
    stations: showCallouts,
    hardware: false,
    strands: false,
    stirrups: false,
    anomalies: true,
    ...layers,
  };
  return (
    <div style={{ width: "100%", height: "100%", background: "#0A0C10", position: "relative" }} data-testid="beam-3d-canvas">
      <Scene
        camera={camera}
        target={ORBIT_TARGET}
      >
        <group position={[0, viewLift, 0]}>
          <BeamAssembly beam={safeBeam} anomalies={anomalies} onSurfacePick={onSurfacePick} onHardwareSelect={onHardwareSelect} showCallouts={showCallouts} layers={activeLayers} highlighted pourMode={pourMode} />
          <mesh position={[0, -spec.depth / 2 - 0.14, 0]} receiveShadow>
            <boxGeometry args={[Math.max(spec.width * 4.2, 18), 0.16, Math.max(safeBeam.length_ft + 12, 34)]} />
            <meshStandardMaterial color="#20252F" roughness={0.96} metalness={0.04} />
          </mesh>
          <gridHelper args={[Math.max(safeBeam.length_ft * 1.25, 50), Math.max(Math.round(safeBeam.length_ft / 4), 24), "#2B313B", "#161B24"]} position={[0, -spec.depth / 2 - 0.05, 0]} />
        </group>
      </Scene>
      <TwinVisualBar beam={safeBeam} spec={spec} pourMode={pourMode} />
      <ViewHeightControl value={viewLift} onChange={setViewLift} />
      {activeLayers.dimensions && <CrossSectionInset beam={safeBeam} />}
      {(activeLayers.dimensions || activeLayers.stations) && <DimensionColorLegend />}
    </div>
  );
}

function BedDimensionLayer({ bed, beams, bedLength, laneWidth, halfSpread }) {
  const bedWidth = Math.max(beams.length * laneWidth + 10, 22);
  const sorted = [...beams].sort((a, b) => (a.position_on_bed || 0) - (b.position_on_bed || 0));
  return (
    <group>
      <DimensionLine
        start={[-bedWidth / 2 - 1.2, 0.2, -bedLength / 2]}
        end={[-bedWidth / 2 - 1.2, 0.2, bedLength / 2]}
        label={`BED LENGTH ${formatFeet(bed?.length_ft || bedLength)}`}
        color="#73BCFF"
        tickAxis="x"
        tick={0.25}
      />
      <DimensionLine
        start={[-bedWidth / 2, 0.26, -bedLength / 2 - 2.4]}
        end={[bedWidth / 2, 0.26, -bedLength / 2 - 2.4]}
        label={`LANE WIDTH ${formatFeet(bedWidth, 1)}`}
        color="#73BCFF"
        tickAxis="z"
        tick={0.25}
      />
      {sorted.map((beam, index) => {
        const x = -halfSpread + index * laneWidth;
        const station = -bedLength / 2;
        const length = Math.min(beam.length_ft || bedLength, bedLength);
        return (
          <group key={`bed-dim-${beam.id}`}>
            <Line points={[[x, 0.35, station], [x, 0.35, station + length]]} color={beam.id === sorted[index]?.id ? "#8FC5FF" : "#516072"} lineWidth={1} />
            <DimensionLabel position={[x, 1.15 + (index % 3) * 0.28, -bedLength / 2 - 5 - (index % 2) * 1.8]} color="#C5D0DE" label={`POS ${String(beam.position_on_bed || index + 1).padStart(2, "0")} · STA 0+00 to ${formatFeet(length)}`} />
            {index > 0 && (
              <DimensionLine
                start={[x - laneWidth, 0.42, bedLength / 2 + 2.8 + (index % 2) * 1.1]}
                end={[x, 0.42, bedLength / 2 + 2.8 + (index % 2) * 1.1]}
                label={`SPACING ${formatFeet(laneWidth)}`}
                color="#91A0B2"
                tickAxis="z"
                tick={0.18}
              />
            )}
          </group>
        );
      })}
      {[-bedLength / 2, 0, bedLength / 2].map((z, index) => (
        <group key={`station-${z}`}>
          <Line points={[[-bedWidth / 2, 0.34, z], [bedWidth / 2, 0.34, z]]} color="#2F9E44" lineWidth={0.8} />
          <DimensionLabel position={[bedWidth / 2 + 1.4, 0.9, z]} color="#2F9E44" label={index === 0 ? "STA 0+00 / MARKED END" : index === 1 ? `MID ${formatFeet(bedLength / 2)}` : `STA ${formatFeet(bedLength)}`} />
        </group>
      ))}
    </group>
  );
}

export function BedTwinViewer({ bed, selectedBeamId, onBeamSelect, onHardwareSelect, showCallouts = false, layers, pourMode = "post_pour" }) {
  const beams = [...(bed?.beams || [])].sort((a, b) => (a.position_on_bed || 0) - (b.position_on_bed || 0));
  const bedLength = Math.max(...beams.map((item) => item.length_ft || 0), bed?.length_ft || 120);
  const laneWidth = 7;
  const halfSpread = ((Math.max(beams.length, 1) - 1) * laneWidth) / 2;
  const [viewLift, setViewLift] = useState(VIEW_LIFT_DEFAULT);
  const camera = useMemo(
    () => ({ position: [22, 12, Math.max(bedLength * 0.66, 92)], fov: 33 }),
    [bedLength],
  );
  const activeLayers = {
    dimensions: showCallouts,
    hardware: false,
    strands: false,
    stirrups: false,
    anomalies: true,
    ...layers,
  };
  return (
    <div style={{ width: "100%", height: "100%", background: "#0A0C10", position: "relative" }}>
      <Scene camera={camera} target={ORBIT_TARGET}>
        <group position={[0, viewLift, 0]}>
          <mesh position={[0, -0.65, 0]} receiveShadow>
            <boxGeometry args={[Math.max(beams.length * laneWidth + 10, 22), 1.0, bedLength + 24]} />
            <meshStandardMaterial color="#2D343E" roughness={0.96} metalness={0.03} />
          </mesh>
          {[-1, 1].map((side) => (
            <mesh key={side} position={[side * (Math.max(beams.length * laneWidth + 8, 20) / 2), 0.1, 0]}>
              <boxGeometry args={[0.28, 0.6, bedLength + 18]} />
              <meshStandardMaterial color="#495363" roughness={0.72} metalness={0.14} />
            </mesh>
          ))}
          {Array.from({ length: beams.length + 1 }).map((_, index) => (
            <Line key={index} points={[[-halfSpread - laneWidth / 2 + index * laneWidth, -0.08, -bedLength / 2], [-halfSpread - laneWidth / 2 + index * laneWidth, -0.08, bedLength / 2]]} color="#5D6878" lineWidth={1} />
          ))}
          <Line points={[[-halfSpread - laneWidth / 2, -0.02, 0], [halfSpread + laneWidth / 2, -0.02, 0]]} color="#2F9E44" lineWidth={1.2} />
          {activeLayers.dimensions && <CalloutTag position={[0, 1.55, -bedLength / 2 - 3.8]} color="#8FC5FF" label="HEAD / MARKED END" />}
          {activeLayers.dimensions && <CalloutTag position={[0, 1.55, bedLength / 2 + 3.2]} color="#8B949E" label="TAIL / STRAND END" />}
          {activeLayers.dimensions && <BedDimensionLayer bed={bed} beams={beams} bedLength={bedLength} laneWidth={laneWidth} halfSpread={halfSpread} />}
          {beams.map((item, index) => (
            <group key={item.id} position={[-halfSpread + index * laneWidth, 0, 0]}>
              <BeamAssembly
                beam={item}
                anomalies={item.anomalies || []}
                onSurfacePick={null}
                onHardwareSelect={onHardwareSelect}
                showCallouts={showCallouts && item.id === selectedBeamId}
                layers={{ ...activeLayers, dimensions: activeLayers.dimensions && item.id === selectedBeamId }}
                highlighted={item.id === selectedBeamId}
                onBeamSelect={onBeamSelect}
                pourMode={pourMode}
              />
              {(item.id === selectedBeamId || activeLayers.dimensions) && <CalloutTag position={[0, 4.2 + (index % 3) * 0.28, 0]} color={item.id === selectedBeamId ? "#8FC5FF" : "#E5EDF5"} label={`${item.mark} · POS ${String(item.position_on_bed).padStart(2, "0")} · ${formatFeet(item.length_ft)}`} />}
            </group>
          ))}
          {activeLayers.dimensions && <CalloutTag position={[0, 1.35, -bedLength / 2 - 7]} color="#2F9E44" label={`BED ${bed?.bed_number} · ${bed?.name} · ${beams.length} BEAMS`} />}
          <gridHelper args={[Math.max(bedLength + 40, 180), 40, "#222631", "#151922"]} position={[0, -1.02, 0]} />
        </group>
      </Scene>
      <ViewHeightControl value={viewLift} onChange={setViewLift} align="left" />
      <div
        style={{ position: "absolute", top: 16, right: 16, width: 280, maxWidth: "calc(100% - 5rem)", background: "rgba(12,14,19,0.94)", border: "1px solid #222631", padding: 12, fontFamily: "JetBrains Mono, monospace" }}
        data-testid="bed-sequence-panel"
      >
        <div style={{ color: "#FFFFFF", fontSize: 12, fontWeight: 700, letterSpacing: "0.16em", marginBottom: 10 }}>BED ORDER</div>
        <div style={{ display: "grid", gap: 8 }}>
          {beams.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onBeamSelect?.(item)}
              style={{
                minHeight: 40,
                width: "100%",
                border: `1px solid ${item.id === selectedBeamId ? "#2979FF" : "#303641"}`,
                background: item.id === selectedBeamId ? "rgba(41,121,255,0.12)" : "#12151C",
                color: "#E5EDF5",
                textAlign: "left",
                padding: "8px 10px",
                cursor: "pointer",
              }}
              data-testid={`bed-sequence-${item.position_on_bed}`}
            >
              <div style={{ fontSize: 10, color: item.id === selectedBeamId ? "#8FC5FF" : "#8B949E", letterSpacing: "0.12em" }}>POS {String(item.position_on_bed).padStart(2, "0")} · {item.qc_state?.replace(/_/g, " ")}</div>
              <div style={{ fontSize: 12, fontWeight: 700 }}>{item.mark}</div>
              <div style={{ fontSize: 10, color: "#8B949E" }}>{item.product_type?.name || item.twin_type} · {formatFeet(item.length_ft)}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
