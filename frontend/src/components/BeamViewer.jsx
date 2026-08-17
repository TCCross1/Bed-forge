import React, { Suspense, useMemo, useRef } from "react";
import { Canvas } from "@react-three/fiber";
import { Environment, Html, Line, OrbitControls } from "@react-three/drei";
import * as THREE from "three";

const inchesToFeet = (value = 0) => value / 12;
const concreteBase = "#B7BEC7";
const concreteEdge = "#D8DEE5";
const steelGray = "#7D8795";
const steelBright = "#B9C2CF";
const brassGold = "#E3C565";
const asphaltBlack = "#1A1A1A";

function formatFeet(value = 0, digits = 1) {
  return `${Number(value).toFixed(digits)} ft`;
}

function formatInches(value = 0, digits = 0) {
  return `${Number(value).toFixed(digits)} in`;
}

function normalizeBlueprint(beam) {
  const depth = beam?.product_type?.depth_in || (beam?.twin_type === "box_beam" ? 30 : 48);
  const width = beam?.product_type?.width_in || (beam?.twin_type === "box_beam" ? 42 : 18);
  const length = Math.max(beam?.length_ft || beam?.product_type?.default_length_ft || 80, 10);
  const source = beam?.product_type?.blueprint || {};

  const base = beam?.twin_type === "box_beam"
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
    cross_section: { ...base.cross_section, ...(source.cross_section || {}) },
    lift_loops: source.lift_loops || [{ x_ft: length * 0.18 }, { x_ft: length * 0.82 }],
    inserts: source.inserts || [{ x_ft: length * 0.25, side: "left", embed: "plate" }, { x_ft: length * 0.75, side: "right", embed: "plate" }],
    tubes: source.tubes || [{ x_ft: length * 0.38, diameter_in: 3 }, { x_ft: length * 0.62, diameter_in: 3 }],
    tie_rod_openings: source.tie_rod_openings || [{ x_ft: length * 0.33, diameter_in: 2.5 }, { x_ft: length * 0.67, diameter_in: 2.5 }],
    drain_holes: source.drain_holes || [{ x_ft: length * 0.08, diameter_in: 2 }, { x_ft: length * 0.92, diameter_in: 2 }],
    hold_downs: source.hold_downs || [{ x_ft: length * 0.22 }, { x_ft: length * 0.5 }, { x_ft: length * 0.78 }],
    bituminous_ends: source.bituminous_ends || [{ end: "start", length_in: 18 }, { end: "end", length_in: 18 }],
    strand_pattern: source.strand_pattern || { start_y_in: 5, row_spacing_in: 4.5, rows: [{ count: 4, spacing_in: 4 }, { count: 4, spacing_in: 4 }] },
    stirrups: source.stirrups || { start_ft: 2, end_ft: Math.max(length - 2, 4), spacing_in: 24, cover_in: 2.5 },
    marked_end: source.marked_end || { end: "start", label: "MARKED END", color: "#F4F7FB" },
    grout_grooves: source.grout_grooves || base.grout_grooves || [],
    drape_profile: source.drape_profile || base.drape_profile || null,
    dimensions: {
      overall_length_ft: length,
      overall_depth_in: depth,
      overall_width_in: width,
      ...(source.dimensions || {}),
    },
    length,
  };
}

function buildIBeam(crossSection) {
  const bottomWidth = inchesToFeet(crossSection.bottom_flange_width_in);
  const bottomThickness = inchesToFeet(crossSection.bottom_flange_thickness_in);
  const webThickness = inchesToFeet(crossSection.web_thickness_in);
  const topWidth = inchesToFeet(crossSection.top_flange_width_in);
  const topThickness = inchesToFeet(crossSection.top_flange_thickness_in);
  const depth = inchesToFeet(crossSection.overall_depth_in);
  const shape = new THREE.Shape();
  shape.moveTo(-bottomWidth / 2, 0);
  shape.lineTo(bottomWidth / 2, 0);
  shape.lineTo(bottomWidth / 2, bottomThickness);
  shape.lineTo(webThickness / 2, bottomThickness);
  shape.lineTo(webThickness / 2, depth - topThickness);
  shape.lineTo(topWidth / 2, depth - topThickness);
  shape.lineTo(topWidth / 2, depth);
  shape.lineTo(-topWidth / 2, depth);
  shape.lineTo(-topWidth / 2, depth - topThickness);
  shape.lineTo(-webThickness / 2, depth - topThickness);
  shape.lineTo(-webThickness / 2, bottomThickness);
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
  const shape = new THREE.Shape();
  shape.moveTo(-outerWidth / 2, 0);
  shape.lineTo(outerWidth / 2, 0);
  shape.lineTo(outerWidth / 2, outerDepth);
  shape.lineTo(-outerWidth / 2, outerDepth);
  shape.closePath();
  const hole = new THREE.Path();
  hole.moveTo(-innerWidth / 2, wall);
  hole.lineTo(innerWidth / 2, wall);
  hole.lineTo(innerWidth / 2, wall + innerDepth);
  hole.lineTo(-innerWidth / 2, wall + innerDepth);
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

function Shell({ spec, beam, highlighted, onSurfacePick, onBeamSelect }) {
  const geometry = useMemo(() => new THREE.ExtrudeGeometry(spec.shape, { depth: spec.length, bevelEnabled: false }), [spec]);
  const edges = useMemo(() => new THREE.EdgesGeometry(geometry, 25), [geometry]);
  return (
    <group>
      <mesh
        castShadow
        receiveShadow
        geometry={geometry}
        onClick={(event) => {
          event.stopPropagation();
          onSurfacePick?.(event.point);
          onBeamSelect?.(beam);
        }}
      >
        <meshPhysicalMaterial color={concreteBase} roughness={0.9} metalness={0.03} clearcoat={0.08} reflectivity={0.14} emissive={highlighted ? "#123762" : "#000000"} emissiveIntensity={highlighted ? 0.18 : 0} />
      </mesh>
      <lineSegments geometry={edges}>
        <lineBasicMaterial color={highlighted ? "#8FC5FF" : concreteEdge} transparent opacity={0.6} />
      </lineSegments>
    </group>
  );
}

function LiftLoops({ beam, spec, onHardwareSelect }) {
  const radius = Math.max(spec.width * 0.08, 0.12);
  return (spec.blueprint.lift_loops || []).map((item, index) => {
    const payload = { id: `lift-loop-${index}`, type: "Lift loop", beamMark: beam.mark, spec: item };
    return (
      <group key={payload.id} position={[0, spec.depth + radius * 0.85, item.x_ft]}>
        {[-0.09, 0.09].map((offset) => (
          <mesh key={offset} position={[offset, -radius * 0.72, 0]}>
            <cylinderGeometry args={[0.03, 0.03, radius * 1.18, 10]} />
            <meshStandardMaterial color={steelGray} roughness={0.35} metalness={0.65} />
          </mesh>
        ))}
        <mesh rotation={[Math.PI / 2, 0, 0]} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
          <torusGeometry args={[radius, radius * 0.18, 12, 42, Math.PI]} />
          <meshStandardMaterial color={steelBright} roughness={0.32} metalness={0.72} />
        </mesh>
      </group>
    );
  });
}

function SideInserts({ beam, spec, onHardwareSelect }) {
  return (spec.blueprint.inserts || []).map((item, index) => {
    const side = item.side === "right" ? 1 : -1;
    const radius = Math.max(inchesToFeet(item.diameter_in || 2) / 2, spec.width * 0.038);
    const x = side * (spec.width / 2 + radius * 0.28);
    const payload = { id: `insert-${index}`, type: "Side insert", beamMark: beam.mark, spec: item };
    return (
      <group key={payload.id} position={[x, spec.depth * 0.7, item.x_ft]} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
        <mesh position={[-side * radius * 0.32, 0, 0]}>
          <boxGeometry args={[radius * 0.55, radius * 1.8, radius * 1.8]} />
          <meshStandardMaterial color="#525B67" roughness={0.55} metalness={0.42} />
        </mesh>
        <mesh rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[radius, radius, spec.width * 0.14, 18]} />
          <meshStandardMaterial color="#D18C1B" roughness={0.34} metalness={0.52} />
        </mesh>
      </group>
    );
  });
}

function CylindricalOpenings({ beam, spec, items, type, color, y, onHardwareSelect }) {
  return (items || []).map((item, index) => {
    const radius = Math.max(inchesToFeet(item.diameter_in || 2) / 2, 0.08);
    const payload = { id: `${type}-${index}`, type, beamMark: beam.mark, spec: item };
    return (
      <group key={payload.id} position={[0, y, item.x_ft]} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
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
      </group>
    );
  });
}

function HoldDowns({ beam, spec, onHardwareSelect }) {
  if (beam.twin_type !== "i_beam") return null;
  const width = Math.max(spec.width * 0.16, 0.28);
  const height = Math.max(spec.depth * 0.28, 0.52);
  return (spec.blueprint.hold_downs || []).map((item, index) => {
    const payload = { id: `hold-down-${index}`, type: "Hold-down", beamMark: beam.mark, spec: item };
    return (
      <group key={payload.id} position={[0, spec.depth + height / 2 + 0.03, item.x_ft]} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
        <mesh position={[0, -height / 2, 0]}>
          <boxGeometry args={[spec.width * 0.84, 0.08, width * 0.6]} />
          <meshStandardMaterial color="#565F6C" roughness={0.72} metalness={0.12} />
        </mesh>
        {[-width * 0.42, width * 0.42].map((x) => (
          <mesh key={x} position={[x, 0, 0]}>
            <boxGeometry args={[0.08, height, width * 0.32]} />
            <meshStandardMaterial color="#85592F" roughness={0.54} metalness={0.24} />
          </mesh>
        ))}
        <mesh position={[0, height * 0.24, 0]}>
          <boxGeometry args={[width * 1.32, 0.1, width * 0.42]} />
          <meshStandardMaterial color="#85592F" roughness={0.54} metalness={0.24} />
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
    const payload = { id: `grout-groove-${index}`, type: "Grout groove", beamMark: beam.mark, spec: item };
    return (
      <group key={payload.id} position={[0, spec.depth + 0.01, item.x_ft]} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
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
  const stirrup = spec.blueprint.stirrups || {};
  const start = stirrup.start_ft ?? 2;
  const end = Math.min(stirrup.end_ft ?? spec.length - 2, spec.length - 1);
  const spacing = inchesToFeet(stirrup.spacing_in || 24);
  const cover = inchesToFeet(stirrup.cover_in || 2.5);
  const width = Math.max(spec.width - cover * 2, spec.width * 0.55);
  const height = Math.max(spec.depth - cover * 2, spec.depth * 0.68);
  const count = Math.max(Math.floor(Math.max(end - start, 0) / spacing) + 1, 0);
  return Array.from({ length: count }).map((_, index) => {
    const z = Math.min(start + index * spacing, end);
    const payload = { id: `stirrup-${index}`, type: beam.twin_type === "box_beam" ? "Rebar hoop" : "Rebar stirrup", beamMark: beam.mark, spec: { z_ft: z, cover_in: stirrup.cover_in || 2.5, spacing_in: stirrup.spacing_in || 24 } };
    return (
      <group key={payload.id} position={[0, cover, z]} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
        {[[0, 0, 0, width, 0.028, 0.028], [0, height, 0, width, 0.028, 0.028], [-width / 2, height / 2, 0, 0.028, height, 0.028], [width / 2, height / 2, 0, 0.028, height, 0.028]].map((part, i) => (
          <mesh key={i} position={[part[0], part[1], part[2]]}>
            <boxGeometry args={[part[3], part[4], part[5]]} />
            <meshStandardMaterial color="#4E5966" roughness={0.72} metalness={0.22} />
          </mesh>
        ))}
      </group>
    );
  });
}

function strandRows(blueprint) {
  const pattern = blueprint.strand_pattern || {};
  const rows = pattern.rows || [];
  const startY = inchesToFeet(pattern.start_y_in || 5);
  const rowSpacing = inchesToFeet(pattern.row_spacing_in || 4.5);
  return rows.flatMap((row, rowIndex) => {
    const spacing = inchesToFeet(row.spacing_in || 4);
    const totalWidth = spacing * Math.max((row.count || 0) - 1, 0);
    return Array.from({ length: row.count || 0 }).map((_, strandIndex) => ({
      x: -totalWidth / 2 + strandIndex * spacing,
      y: startY + rowIndex * rowSpacing,
    }));
  });
}

function StrandPaths({ beam, spec, onHardwareSelect }) {
  const strands = strandRows(spec.blueprint);
  const sag = inchesToFeet(spec.blueprint.drape_profile?.sag_in || 0);
  const holdPoints = (spec.blueprint.hold_downs || []).map((item) => item.x_ft).sort((a, b) => a - b);
  return strands.map((strand, index) => {
    const points = [new THREE.Vector3(strand.x, strand.y, 0)];
    if (beam.twin_type === "i_beam" && holdPoints.length) {
      holdPoints.forEach((xFt, holdIndex) => {
        const isMiddle = holdIndex > 0 && holdIndex < holdPoints.length - 1;
        points.push(new THREE.Vector3(strand.x, strand.y - (isMiddle ? sag : sag * 0.6), xFt));
      });
    } else {
      points.push(new THREE.Vector3(strand.x, strand.y, spec.length / 2));
    }
    points.push(new THREE.Vector3(strand.x, strand.y, spec.length]);
    const payload = { id: `strand-${index}`, type: "Prestressing strand", beamMark: beam.mark, spec: { index: index + 1, draped: beam.twin_type === "i_beam", row_y_ft: strand.y } };
    return (
      <group key={payload.id} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
        <Line points={points} color={brassGold} lineWidth={1.5} />
        {[0, spec.length].map((z) => (
          <group key={z} position={[strand.x, strand.y, z]}>
            <mesh rotation={[Math.PI / 2, 0, 0]}>
              <cylinderGeometry args={[0.07, 0.07, 0.04, 14]} />
              <meshStandardMaterial color="#D2D8E0" roughness={0.38} metalness={0.68} />
            </mesh>
            <mesh>
              <sphereGeometry args={[0.048, 10, 10]} />
              <meshStandardMaterial color="#F3D26A" roughness={0.34} metalness={0.42} />
            </mesh>
          </group>
        ))}
      </group>
    );
  });
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

function DimensionCallouts({ beam, spec }) {
  const depthIn = beam.product_type?.depth_in || Math.round(spec.depth * 12 * 10) / 10;
  const widthIn = beam.product_type?.width_in || Math.round(spec.width * 12 * 10) / 10;
  const lifts = spec.blueprint.lift_loops || [];
  const drains = spec.blueprint.drain_holes || [];
  const inserts = spec.blueprint.inserts || [];
  const holdDowns = spec.blueprint.hold_downs || [];
  const stirrupSpacing = spec.blueprint.stirrups?.spacing_in;
  const bituminous = spec.blueprint.bituminous_ends || [];
  const items = [
    {
      key: "length",
      label: `OAL ${formatFeet(beam.length_ft)}`,
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
      label: `INSERTS ${formatFeet(first)} / ${formatFeet(last)}`,
      color: "#F4B652",
      line: [[-spec.width * 0.52, spec.depth * 0.72, first], [-spec.width * 0.52, spec.depth * 0.72, last]],
      tag: [-spec.width * 0.98, spec.depth * 0.88, (first + last) / 2],
    });
  }

  if (drains.length) {
    items.push({
      key: "drains",
      label: `DRAINS ${drains.map((item) => formatFeet(item.x_ft)).join(" / ")}`,
      color: "#A5B0BE",
      line: [[spec.width * 0.5, 0.18, drains[0].x_ft], [spec.width * 0.5, 0.18, drains[drains.length - 1].x_ft]],
      tag: [spec.width * 0.98, 0.48, (drains[0].x_ft + drains[drains.length - 1].x_ft) / 2],
    });
  }

  if (holdDowns.length) {
    items.push({
      key: "hold-downs",
      label: `HOLD-DOWNS ${holdDowns.length} PCS`,
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
      label: `BITUMEN ${bituminous.map((item) => formatInches(item.length_in || 18)).join(" EA END")}${bituminous.length > 1 ? " EA END" : ""}`,
      color: "#E5E7EB",
      line: [[0, spec.depth * 0.18, 0], [0, spec.depth * 0.18, inchesToFeet(bituminous[0]?.length_in || 18)]],
      tag: [spec.width * 0.52, spec.depth * 0.34, inchesToFeet(bituminous[0]?.length_in || 18) + 0.5],
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

function BeamAssembly({ beam, anomalies = [], onSurfacePick, onHardwareSelect, showCallouts = true, highlighted = false, onBeamSelect }) {
  const spec = useBeamSpec(beam);
  const groupRef = useRef(null);
  const surfacePick = (point) => {
    const localPoint = groupRef.current ? groupRef.current.worldToLocal(point.clone()) : point;
    onSurfacePick?.(localPoint, beam);
  };
  return (
    <group ref={groupRef} position={[0, -spec.depth / 2, -spec.length / 2]}>
      <Shell spec={spec} beam={beam} highlighted={highlighted} onSurfacePick={surfacePick} onBeamSelect={onBeamSelect} />
      <BituminousEnds beam={beam} spec={spec} onHardwareSelect={onHardwareSelect} />
      <StrandPaths beam={beam} spec={spec} onHardwareSelect={onHardwareSelect} />
      <Stirrups beam={beam} spec={spec} onHardwareSelect={onHardwareSelect} />
      <LiftLoops beam={beam} spec={spec} onHardwareSelect={onHardwareSelect} />
      <SideInserts beam={beam} spec={spec} onHardwareSelect={onHardwareSelect} />
      <CylindricalOpenings beam={beam} spec={spec} items={spec.blueprint.tubes} type="Tube" color="#4F5968" y={spec.depth * 0.56} onHardwareSelect={onHardwareSelect} />
      <CylindricalOpenings beam={beam} spec={spec} items={spec.blueprint.tie_rod_openings} type="Tie-rod opening" color="#0F172A" y={spec.depth * 0.42} onHardwareSelect={onHardwareSelect} />
      <CylindricalOpenings beam={beam} spec={spec} items={spec.blueprint.drain_holes} type="Drain hole" color="#111827" y={0.18} onHardwareSelect={onHardwareSelect} />
      <HoldDowns beam={beam} spec={spec} onHardwareSelect={onHardwareSelect} />
      <GroutGrooves beam={beam} spec={spec} onHardwareSelect={onHardwareSelect} />
      <MarkedEnd beam={beam} spec={spec} onHardwareSelect={onHardwareSelect} />
      {showCallouts && <DimensionCallouts beam={beam} spec={spec} />}
      <Anomalies anomalies={anomalies} spec={spec} />
    </group>
  );
}

function Scene({ children, camera }) {
  return (
    <Canvas camera={camera} shadows>
      <Suspense fallback={null}>
        <ambientLight intensity={0.78} />
        <hemisphereLight intensity={0.56} groundColor="#0e1016" />
        <directionalLight position={[18, 20, 12]} intensity={1.18} castShadow />
        <directionalLight position={[-16, 8, -8]} intensity={0.42} />
        <directionalLight position={[0, 10, -18]} intensity={0.3} />
        {children}
        <Environment preset="warehouse" />
        <OrbitControls enablePan enableZoom enableRotate maxPolarAngle={Math.PI * 0.48} makeDefault />
      </Suspense>
    </Canvas>
  );
}

export default function BeamTwinViewer({ beam, anomalies = [], onSurfacePick, onHardwareSelect, showCallouts = true }) {
  const safeBeam = beam || { twin_type: "i_beam", length_ft: 90, product_type: {}, mark: "Beam" };
  const spec = useBeamSpec(safeBeam);
  const cameraDistance = Math.max(safeBeam.length_ft * 0.34, 22);
  return (
    <div style={{ width: "100%", height: "100%", background: "#0A0C10" }} data-testid="beam-3d-canvas">
      <Scene camera={{ position: [cameraDistance * 0.56, spec.depth * 2.45, cameraDistance], fov: 34 }}>
        <BeamAssembly beam={safeBeam} anomalies={anomalies} onSurfacePick={onSurfacePick} onHardwareSelect={onHardwareSelect} showCallouts={showCallouts} highlighted />
        <mesh position={[0, -spec.depth / 2 - 0.14, 0]} receiveShadow>
          <boxGeometry args={[Math.max(spec.width * 4.2, 18), 0.16, Math.max(safeBeam.length_ft + 12, 34)]} />
          <meshStandardMaterial color="#20252F" roughness={0.96} metalness={0.04} />
        </mesh>
        <gridHelper args={[Math.max(safeBeam.length_ft * 1.25, 50), Math.max(Math.round(safeBeam.length_ft / 4), 24), "#2B313B", "#161B24"]} position={[0, -spec.depth / 2 - 0.05, 0]} />
      </Scene>
    </div>
  );
}

export function BedTwinViewer({ bed, selectedBeamId, onBeamSelect, onHardwareSelect, showCallouts = false }) {
  const beams = bed?.beams || [];
  const bedLength = Math.max(...beams.map((item) => item.length_ft || 0), bed?.length_ft || 120);
  const laneWidth = 7;
  const halfSpread = ((Math.max(beams.length, 1) - 1) * laneWidth) / 2;
  return (
    <div style={{ width: "100%", height: "100%", background: "#0A0C10", position: "relative" }}>
      <Scene camera={{ position: [22, 17, Math.max(bedLength * 0.66, 92)], fov: 33 }}>
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
        {beams.map((item, index) => (
          <group key={item.id} position={[-halfSpread + index * laneWidth, 0, 0]}>
            <BeamAssembly
              beam={item}
              anomalies={item.anomalies || []}
              onSurfacePick={null}
              onHardwareSelect={onHardwareSelect}
              showCallouts={showCallouts && item.id === selectedBeamId}
              highlighted={item.id === selectedBeamId}
              onBeamSelect={onBeamSelect}
            />
            <CalloutTag position={[0, 4.2, 0]} color={item.id === selectedBeamId ? "#8FC5FF" : "#E5EDF5"} label={`${item.mark} · POS ${String(item.position_on_bed).padStart(2, "0")}`} />
            <CalloutTag position={[0, 1.3, -bedLength / 2 - 2.2]} color="#8B949E" label={`LANE ${String(item.position_on_bed).padStart(2, "0")}`} />
          </group>
        ))}
        <CalloutTag position={[0, 1.35, -bedLength / 2 - 7]} color="#2F9E44" label={`BED ${bed?.bed_number} · ${bed?.name} · ${beams.length} BEAMS`} />
        <gridHelper args={[Math.max(bedLength + 40, 180), 40, "#222631", "#151922"]} position={[0, -1.02, 0]} />
      </Scene>
      <div
        style={{ position: "absolute", top: 16, right: 16, width: 280, background: "rgba(12,14,19,0.94)", border: "1px solid #222631", padding: 12, fontFamily: "JetBrains Mono, monospace" }}
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
              <div style={{ fontSize: 10, color: item.id === selectedBeamId ? "#8FC5FF" : "#8B949E", letterSpacing: "0.12em" }}>POS {String(item.position_on_bed).padStart(2, "0")}</div>
              <div style={{ fontSize: 12, fontWeight: 700 }}>{item.mark}</div>
              <div style={{ fontSize: 10, color: "#8B949E" }}>{item.product_type?.name || item.twin_type} · {formatFeet(item.length_ft)}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
