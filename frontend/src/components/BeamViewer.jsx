import React, { Suspense, useMemo, useRef } from "react";
import { Canvas } from "@react-three/fiber";
import { Environment, Html, Line, OrbitControls } from "@react-three/drei";
import * as THREE from "three";

const inchesToFeet = (value = 0) => value / 12;
const plantGreen = "#2F9E44";
const steelGray = "#97A0AE";

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
    dimensions: source.dimensions || {},
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

function Shell({ spec, beam, highlighted, onSurfacePick, onBeamSelect }) {
  const geometry = useMemo(() => new THREE.ExtrudeGeometry(spec.shape, { depth: spec.length, bevelEnabled: false }), [spec]);
  return (
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
      <meshStandardMaterial color={steelGray} roughness={0.82} metalness={0.06} emissive={highlighted ? "#1F6FEB" : "#000000"} emissiveIntensity={highlighted ? 0.28 : 0} />
    </mesh>
  );
}

function HardwarePill({ position, color, label }) {
  return (
    <Html position={position} distanceFactor={18}>
      <div style={{ background: "rgba(10,12,16,0.92)", color, border: `1px solid ${color}`, padding: "2px 6px", fontSize: 9, fontFamily: "JetBrains Mono, monospace", whiteSpace: "nowrap" }}>
        {label}
      </div>
    </Html>
  );
}

function LiftLoops({ beam, spec, onHardwareSelect }) {
  const radius = Math.max(spec.width * 0.085, 0.12);
  return (spec.blueprint.lift_loops || []).map((item, index) => {
    const payload = { id: `lift-loop-${index}`, type: "Lift loop", beamMark: beam.mark, spec: item };
    return (
      <group key={payload.id} position={[0, spec.depth + radius * 0.85, item.x_ft]}>
        <mesh rotation={[Math.PI / 2, 0, 0]} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
          <torusGeometry args={[radius, radius * 0.24, 10, 36, Math.PI]} />
          <meshStandardMaterial color={plantGreen} roughness={0.45} metalness={0.35} />
        </mesh>
      </group>
    );
  });
}

function SideInserts({ beam, spec, onHardwareSelect }) {
  return (spec.blueprint.inserts || []).map((item, index) => {
    const side = item.side === "right" ? 1 : -1;
    const radius = Math.max(inchesToFeet(item.diameter_in || 2) / 2, spec.width * 0.04);
    const x = side * (spec.width / 2 + radius * 0.35);
    const payload = { id: `insert-${index}`, type: "Side insert", beamMark: beam.mark, spec: item };
    return (
      <mesh key={payload.id} position={[x, spec.depth * 0.7, item.x_ft]} rotation={[0, 0, Math.PI / 2]} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
        <cylinderGeometry args={[radius, radius, spec.width * 0.18, 16]} />
        <meshStandardMaterial color="#D97706" roughness={0.55} metalness={0.25} />
      </mesh>
    );
  });
}

function CylindricalOpenings({ beam, spec, items, type, color, y, onHardwareSelect }) {
  return (items || []).map((item, index) => {
    const radius = Math.max(inchesToFeet(item.diameter_in || 2) / 2, 0.08);
    const payload = { id: `${type}-${index}`, type, beamMark: beam.mark, spec: item };
    return (
      <group key={payload.id} position={[0, y, item.x_ft]}>
        <mesh rotation={[0, 0, Math.PI / 2]} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
          <cylinderGeometry args={[radius, radius, spec.width * 1.04, 18]} />
          <meshStandardMaterial color={color} roughness={0.85} metalness={0.1} />
        </mesh>
      </group>
    );
  });
}

function HoldDowns({ beam, spec, onHardwareSelect }) {
  if (beam.twin_type !== "i_beam") return null;
  const width = Math.max(spec.width * 0.18, 0.32);
  const height = Math.max(spec.depth * 0.38, 0.65);
  return (spec.blueprint.hold_downs || []).map((item, index) => {
    const payload = { id: `hold-down-${index}`, type: "Hold-down", beamMark: beam.mark, spec: item };
    return (
      <group key={payload.id} position={[0, spec.depth + height / 2 + 0.02, item.x_ft]}>
        <mesh onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
          <boxGeometry args={[width, height, width * 0.4]} />
          <meshStandardMaterial color="#8B5E34" roughness={0.55} metalness={0.2} />
        </mesh>
        <mesh position={[0, -height / 2, 0]}>
          <boxGeometry args={[spec.width * 0.72, 0.08, width * 0.55]} />
          <meshStandardMaterial color="#6B7280" roughness={0.65} metalness={0.12} />
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
      <mesh key={payload.id} position={[0, spec.depth * 0.45, z]} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
        <boxGeometry args={[spec.width * 1.04, spec.depth * 0.7, length]} />
        <meshStandardMaterial color="#111111" opacity={0.5} transparent roughness={1} />
      </mesh>
    );
  });
}

function GroutGrooves({ beam, spec, onHardwareSelect }) {
  if (beam.twin_type !== "box_beam") return null;
  return (spec.blueprint.grout_grooves || []).map((item, index) => {
    const payload = { id: `grout-groove-${index}`, type: "Grout groove", beamMark: beam.mark, spec: item };
    return (
      <mesh key={payload.id} position={[0, spec.depth + 0.01, item.x_ft]} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
        <boxGeometry args={[spec.width * 0.78, 0.035, 0.18]} />
        <meshStandardMaterial color="#5B6472" roughness={0.7} metalness={0.08} />
      </mesh>
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
  const count = Math.max(Math.floor((Math.max(end - start, 0)) / spacing) + 1, 0);
  return Array.from({ length: count }).map((_, index) => {
    const z = Math.min(start + index * spacing, end);
    const payload = { id: `stirrup-${index}`, type: beam.twin_type === "box_beam" ? "Rebar hoop" : "Rebar stirrup", beamMark: beam.mark, spec: { z_ft: z, cover_in: stirrup.cover_in || 2.5, spacing_in: stirrup.spacing_in || 24 } };
    return (
      <group key={payload.id} position={[0, cover, z]} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
        {[[0, 0, 0, width, 0.03, 0.03], [0, height, 0, width, 0.03, 0.03], [-width / 2, height / 2, 0, 0.03, height, 0.03], [width / 2, height / 2, 0, 0.03, height, 0.03]].map((part, i) => (
          <mesh key={i} position={[part[0], part[1], part[2]]}>
            <boxGeometry args={[part[3], part[4], part[5]]} />
            <meshStandardMaterial color="#51606F" roughness={0.7} metalness={0.2} />
          </mesh>
        ))}
      </group>
    );
  });
}

function strandRows(blueprint, spec) {
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
  const strands = strandRows(spec.blueprint, spec);
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
    points.push(new THREE.Vector3(strand.x, strand.y, spec.length));
    const payload = { id: `strand-${index}`, type: "Prestressing strand", beamMark: beam.mark, spec: { index: index + 1, draped: beam.twin_type === "i_beam", row_y_ft: strand.y } };
    return (
      <group key={payload.id} onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
        <Line points={points} color="#E3C565" lineWidth={1.5} />
        <mesh position={[strand.x, strand.y, 0]}>
          <sphereGeometry args={[0.05, 10, 10]} />
          <meshStandardMaterial color="#F3D26A" roughness={0.35} metalness={0.35} />
        </mesh>
        <mesh position={[strand.x, strand.y, spec.length]}>
          <sphereGeometry args={[0.05, 10, 10]} />
          <meshStandardMaterial color="#F3D26A" roughness={0.35} metalness={0.35} />
        </mesh>
      </group>
    );
  });
}

function MarkedEnd({ beam, spec, onHardwareSelect }) {
  const area = spec.blueprint.marked_end || {};
  const z = area.end === "end" ? spec.length - 0.25 : 0.25;
  const payload = { id: "marked-end", type: "Marked end", beamMark: beam.mark, spec: area };
  return (
    <group position={[0, spec.depth * 0.78, z]}>
      <mesh onClick={(event) => clickHardware(event, payload, onHardwareSelect)}>
        <boxGeometry args={[spec.width * 0.5, spec.depth * 0.2, 0.06]} />
        <meshStandardMaterial color="#F8FAFC" roughness={0.9} metalness={0.02} />
      </mesh>
      <HardwarePill position={[0, spec.depth * 0.1, 0]} color="#F8FAFC" label={area.label || "MARKED END"} />
    </group>
  );
}

function DimensionCallouts({ beam, spec }) {
  const depthIn = beam.product_type?.depth_in || Math.round(spec.depth * 12 * 10) / 10;
  const widthIn = beam.product_type?.width_in || Math.round(spec.width * 12 * 10) / 10;
  const items = [
    { key: "length", text: `L ${beam.length_ft} ft`, points: [[-spec.width * 0.55, spec.depth + 0.16, 0], [-spec.width * 0.55, spec.depth + 0.16, spec.length]], anchor: [-spec.width * 0.8, spec.depth + 0.5, spec.length / 2] },
    { key: "depth", text: `D ${depthIn} in`, points: [[spec.width * 0.58, 0, spec.length * 0.18], [spec.width * 0.58, spec.depth, spec.length * 0.18]], anchor: [spec.width * 0.95, spec.depth / 2, spec.length * 0.18] },
    { key: "width", text: `W ${widthIn} in`, points: [[-spec.width / 2, spec.depth + 0.18, spec.length * 0.14], [spec.width / 2, spec.depth + 0.18, spec.length * 0.14]], anchor: [0, spec.depth + 0.55, spec.length * 0.14] },
  ];
  return items.map((item) => (
    <group key={item.key}>
      <Line points={item.points} color="#66B5FF" lineWidth={1} />
      <Html position={item.anchor} distanceFactor={16}>
        <div style={{ background: "rgba(10,12,16,0.92)", border: "1px solid #66B5FF", color: "#D7EBFF", padding: "3px 7px", fontSize: 10, fontFamily: "JetBrains Mono, monospace", whiteSpace: "nowrap" }}>
          {item.text}
        </div>
      </Html>
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
      <CylindricalOpenings beam={beam} spec={spec} items={spec.blueprint.tubes} type="Tube" color="#51606F" y={spec.depth * 0.56} onHardwareSelect={onHardwareSelect} />
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
        <ambientLight intensity={0.68} />
        <hemisphereLight intensity={0.45} groundColor="#0e1016" />
        <directionalLight position={[18, 20, 12]} intensity={1} castShadow />
        <directionalLight position={[-16, 8, -8]} intensity={0.35} />
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
      <Scene camera={{ position: [cameraDistance * 0.58, spec.depth * 2.4, cameraDistance], fov: 36 }}>
        <BeamAssembly beam={safeBeam} anomalies={anomalies} onSurfacePick={onSurfacePick} onHardwareSelect={onHardwareSelect} showCallouts={showCallouts} highlighted />
        <gridHelper args={[Math.max(safeBeam.length_ft * 1.25, 50), Math.max(Math.round(safeBeam.length_ft / 4), 24), "#222631", "#151922"]} position={[0, -spec.depth / 2 - 0.08, 0]} />
      </Scene>
    </div>
  );
}

export function BedTwinViewer({ bed, selectedBeamId, onBeamSelect, onHardwareSelect, showCallouts = false }) {
  const beams = bed?.beams || [];
  const bedLength = Math.max(...beams.map((item) => item.length_ft || 0), bed?.length_ft || 120);
  const laneWidth = 7;
  const halfSpread = ((beams.length - 1) * laneWidth) / 2;
  return (
    <div style={{ width: "100%", height: "100%", background: "#0A0C10" }}>
      <Scene camera={{ position: [22, 16, Math.max(bedLength * 0.65, 90)], fov: 34 }}>
        <mesh position={[0, -0.55, 0]} receiveShadow>
          <boxGeometry args={[Math.max(beams.length * laneWidth + 8, 20), 0.8, bedLength + 20]} />
          <meshStandardMaterial color="#303641" roughness={0.95} metalness={0.02} />
        </mesh>
        {Array.from({ length: beams.length + 1 }).map((_, index) => (
          <Line key={index} points={[[ -halfSpread - laneWidth / 2 + index * laneWidth, -0.1, -bedLength / 2 ], [ -halfSpread - laneWidth / 2 + index * laneWidth, -0.1, bedLength / 2 ]]} color="#475062" lineWidth={1} />
        ))}
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
            <Html position={[0, 3.8, 0]} distanceFactor={20}>
              <div style={{ background: item.id === selectedBeamId ? "#1F6FEB" : "rgba(12,14,19,0.92)", color: "#F8FAFC", border: "1px solid rgba(248,250,252,0.2)", padding: "4px 8px", fontSize: 10, fontFamily: "JetBrains Mono, monospace", whiteSpace: "nowrap", cursor: "pointer" }} onClick={() => onBeamSelect?.(item)}>
                {item.mark} · POS {item.position_on_bed}
              </div>
            </Html>
          </group>
        ))}
        <Html position={[0, 1.1, -bedLength / 2 - 6]} distanceFactor={18}>
          <div style={{ background: "rgba(10,12,16,0.92)", border: "1px solid #2F9E44", color: "#E5EDF5", padding: "6px 10px", fontSize: 11, fontFamily: "JetBrains Mono, monospace" }}>
            BED {bed?.bed_number} · {bed?.name} · {beams.length} BEAMS
          </div>
        </Html>
        <gridHelper args={[Math.max(bedLength + 40, 180), 40, "#222631", "#151922"]} position={[0, -0.95, 0]} />
      </Scene>
    </div>
  );
}
