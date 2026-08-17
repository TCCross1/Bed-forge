import React, { useMemo, useRef, Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Environment, Html, Line } from "@react-three/drei";
import * as THREE from "three";

const inchesToFeet = (value = 0) => value / 12;

function createDefaultBlueprint(beam) {
  const depth = beam?.product_type?.depth_in || (beam?.twin_type === "box_beam" ? 30 : 48);
  const width = beam?.product_type?.width_in || (beam?.twin_type === "box_beam" ? 42 : 18);
  if (beam?.twin_type === "box_beam") {
    return {
      cross_section: {
        outer_width_in: width,
        outer_depth_in: depth,
        wall_thickness_in: 4,
        void_width_in: Math.max(width - 12, 16),
        void_depth_in: Math.max(depth - 10, 14),
      },
      lift_loops: [{ x_ft: beam.length_ft * 0.18 }, { x_ft: beam.length_ft * 0.82 }],
      inserts: [{ x_ft: beam.length_ft * 0.25, side: "left" }, { x_ft: beam.length_ft * 0.75, side: "right" }],
      tubes: [{ x_ft: beam.length_ft * 0.4, diameter_in: 3 }, { x_ft: beam.length_ft * 0.6, diameter_in: 3 }],
      drain_holes: [{ x_ft: beam.length_ft * 0.08, diameter_in: 2 }, { x_ft: beam.length_ft * 0.92, diameter_in: 2 }],
      hold_downs: [{ x_ft: beam.length_ft * 0.2 }, { x_ft: beam.length_ft * 0.8 }],
      bituminous_ends: [{ end: "start", length_in: 18 }, { end: "end", length_in: 18 }],
      strand_pattern: { start_y_in: 5, row_spacing_in: 4, rows: [{ count: 4, spacing_in: 8 }, { count: 4, spacing_in: 8 }] },
      stirrups: { start_ft: 2, end_ft: Math.max(beam.length_ft - 2, 4), spacing_in: 24, cover_in: 2.5 },
    };
  }
  return {
    cross_section: {
      bottom_flange_width_in: Math.max(width * 1.8, width + 10),
      bottom_flange_thickness_in: 8,
      web_thickness_in: 7,
      top_flange_width_in: width,
      top_flange_thickness_in: 7,
      overall_depth_in: depth,
    },
    lift_loops: [{ x_ft: beam.length_ft * 0.18 }, { x_ft: beam.length_ft * 0.82 }],
    inserts: [{ x_ft: beam.length_ft * 0.25, side: "left" }, { x_ft: beam.length_ft * 0.75, side: "right" }],
    tubes: [{ x_ft: beam.length_ft * 0.4, diameter_in: 3 }, { x_ft: beam.length_ft * 0.6, diameter_in: 3 }],
    drain_holes: [{ x_ft: beam.length_ft * 0.08, diameter_in: 2 }, { x_ft: beam.length_ft * 0.92, diameter_in: 2 }],
    hold_downs: [{ x_ft: beam.length_ft * 0.2 }, { x_ft: beam.length_ft * 0.8 }],
    bituminous_ends: [{ end: "start", length_in: 18 }, { end: "end", length_in: 18 }],
    strand_pattern: { start_y_in: 5, row_spacing_in: 4.5, rows: [{ count: 4, spacing_in: 4 }, { count: 4, spacing_in: 4 }] },
    stirrups: { start_ft: 2, end_ft: Math.max(beam.length_ft - 2, 4), spacing_in: 24, cover_in: 2.5 },
  };
}

function buildIBeamShape(crossSection) {
  const bottomWidth = inchesToFeet(crossSection.bottom_flange_width_in);
  const bottomThickness = inchesToFeet(crossSection.bottom_flange_thickness_in);
  const webThickness = inchesToFeet(crossSection.web_thickness_in);
  const topWidth = inchesToFeet(crossSection.top_flange_width_in);
  const topThickness = inchesToFeet(crossSection.top_flange_thickness_in);
  const depth = inchesToFeet(crossSection.overall_depth_in);
  const s = new THREE.Shape();
  s.moveTo(-bottomWidth / 2, 0);
  s.lineTo(bottomWidth / 2, 0);
  s.lineTo(bottomWidth / 2, bottomThickness);
  s.lineTo(webThickness / 2, bottomThickness);
  s.lineTo(webThickness / 2, depth - topThickness);
  s.lineTo(topWidth / 2, depth - topThickness);
  s.lineTo(topWidth / 2, depth);
  s.lineTo(-topWidth / 2, depth);
  s.lineTo(-topWidth / 2, depth - topThickness);
  s.lineTo(-webThickness / 2, depth - topThickness);
  s.lineTo(-webThickness / 2, bottomThickness);
  s.lineTo(-bottomWidth / 2, bottomThickness);
  s.closePath();
  return { shape: s, width: bottomWidth, depth, topWidth };
}

function buildBoxBeamShape(crossSection) {
  const outerWidth = inchesToFeet(crossSection.outer_width_in);
  const outerDepth = inchesToFeet(crossSection.outer_depth_in);
  const wall = inchesToFeet(crossSection.wall_thickness_in);
  const innerWidth = inchesToFeet(crossSection.void_width_in);
  const innerDepth = inchesToFeet(crossSection.void_depth_in);
  const s = new THREE.Shape();
  s.moveTo(-outerWidth / 2, 0);
  s.lineTo(outerWidth / 2, 0);
  s.lineTo(outerWidth / 2, outerDepth);
  s.lineTo(-outerWidth / 2, outerDepth);
  s.closePath();
  const hole = new THREE.Path();
  hole.moveTo(-innerWidth / 2, wall);
  hole.lineTo(innerWidth / 2, wall);
  hole.lineTo(innerWidth / 2, wall + innerDepth);
  hole.lineTo(-innerWidth / 2, wall + innerDepth);
  hole.closePath();
  s.holes.push(hole);
  return { shape: s, width: outerWidth, depth: outerDepth };
}

function useBeamSpec(beam) {
  return useMemo(() => {
    const blueprint = beam?.product_type?.blueprint && Object.keys(beam.product_type.blueprint).length
      ? beam.product_type.blueprint
      : createDefaultBlueprint(beam);
    const length = Math.max(beam?.length_ft || beam?.product_type?.default_length_ft || 80, 10);
    const crossSection = blueprint.cross_section || {};
    const section = beam?.twin_type === "box_beam"
      ? buildBoxBeamShape(crossSection)
      : buildIBeamShape(crossSection);
    return {
      blueprint,
      crossSection,
      length,
      width: section.width,
      depth: section.depth,
      topWidth: section.topWidth,
      shape: section.shape,
    };
  }, [beam]);
}

function BeamShell({ spec, onPick }) {
  const geometry = useMemo(
    () => new THREE.ExtrudeGeometry(spec.shape, { depth: spec.length, bevelEnabled: false }),
    [spec.length, spec.shape],
  );
  return (
    <mesh castShadow receiveShadow geometry={geometry} onClick={onPick}>
      <meshStandardMaterial color="#9aa0aa" roughness={0.85} metalness={0.06} />
    </mesh>
  );
}

function LiftLoops({ spec, onPick }) {
  const radius = Math.max(spec.width * 0.08, 0.12);
  return (spec.blueprint.lift_loops || []).map((loop, index) => (
    <mesh
      key={`loop-${index}`}
      position={[0, spec.depth + radius * 0.8, loop.x_ft]}
      rotation={[Math.PI / 2, 0, 0]}
      onClick={onPick}
    >
      <torusGeometry args={[radius, radius * 0.2, 10, 32, Math.PI]} />
      <meshStandardMaterial color="#d9dde6" roughness={0.4} metalness={0.45} />
    </mesh>
  ));
}

function SideHardware({ spec, items, color, radiusScale = 0.06, y = null, onPick, kind = "insert" }) {
  return (items || []).map((item, index) => {
    const side = item.side === "right" ? 1 : -1;
    const radius = Math.max(inchesToFeet(item.diameter_in || 2) / 2, spec.width * radiusScale);
    const x = side * (spec.width / 2 + radius * 0.4);
    const yPos = y ?? Math.max(spec.depth * 0.55, spec.depth - radius * 3);
    return (
      <mesh
        key={`${kind}-${index}`}
        position={[x, yPos, item.x_ft]}
        rotation={[0, 0, Math.PI / 2]}
        onClick={onPick}
      >
        <cylinderGeometry args={[radius, radius, spec.width * 0.18, 18]} />
        <meshStandardMaterial color={color} roughness={0.55} metalness={0.3} />
      </mesh>
    );
  });
}

function WebTubes({ spec, onPick }) {
  return (spec.blueprint.tubes || []).map((tube, index) => {
    const radius = Math.max(inchesToFeet(tube.diameter_in || 3) / 2, 0.12);
    return (
      <group key={`tube-${index}`} position={[0, spec.depth * 0.52, tube.x_ft]}>
        <mesh rotation={[0, 0, Math.PI / 2]} onClick={onPick}>
          <cylinderGeometry args={[radius, radius, spec.width * 1.02, 24]} />
          <meshStandardMaterial color="#5e6a7d" roughness={0.7} metalness={0.15} />
        </mesh>
        <mesh onClick={onPick}>
          <cylinderGeometry args={[radius * 1.04, radius * 1.04, 0.05, 20]} />
          <meshStandardMaterial color="#0d1118" roughness={0.9} metalness={0} />
        </mesh>
      </group>
    );
  });
}

function DrainHoles({ spec, onPick }) {
  return (spec.blueprint.drain_holes || []).map((hole, index) => {
    const radius = Math.max(inchesToFeet(hole.diameter_in || 2) / 2, 0.08);
    return (
      <mesh
        key={`drain-${index}`}
        position={[0, radius * 2.2, hole.x_ft]}
        rotation={[0, 0, Math.PI / 2]}
        onClick={onPick}
      >
        <cylinderGeometry args={[radius, radius, spec.width * 1.04, 18]} />
        <meshStandardMaterial color="#0d1118" roughness={1} metalness={0} />
      </mesh>
    );
  });
}

function HoldDowns({ spec, onPick }) {
  const width = Math.max(spec.width * 0.2, 0.35);
  const height = Math.max(spec.depth * 0.35, 0.6);
  return (spec.blueprint.hold_downs || []).map((hold, index) => (
    <group key={`hold-${index}`} position={[0, spec.depth + height / 2 + 0.05, hold.x_ft]}>
      <mesh onClick={onPick}>
        <boxGeometry args={[width, height, width * 0.45]} />
        <meshStandardMaterial color="#c08f2d" roughness={0.55} metalness={0.2} />
      </mesh>
      <mesh position={[0, -height / 2, 0]} onClick={onPick}>
        <boxGeometry args={[spec.width * 0.7, 0.08, width * 0.6]} />
        <meshStandardMaterial color="#7d8694" roughness={0.55} metalness={0.2} />
      </mesh>
    </group>
  ));
}

function BituminousEnds({ spec }) {
  return (spec.blueprint.bituminous_ends || []).map((segment, index) => {
    const length = inchesToFeet(segment.length_in || 18);
    const z = segment.end === "end" ? spec.length - length / 2 : length / 2;
    return (
      <mesh key={`bit-${index}`} position={[0, spec.depth * 0.5, z]}>
        <boxGeometry args={[spec.width * 1.04, spec.depth * 1.02, length]} />
        <meshStandardMaterial color="#111111" transparent opacity={0.42} roughness={1} />
      </mesh>
    );
  });
}

function StrandPattern({ spec, onPick }) {
  const pattern = spec.blueprint.strand_pattern || {};
  const rows = pattern.rows || [];
  const startY = inchesToFeet(pattern.start_y_in || 5);
  const rowSpacing = inchesToFeet(pattern.row_spacing_in || 4);
  return rows.flatMap((row, rowIndex) => {
    const count = row.count || 0;
    const spacing = inchesToFeet(row.spacing_in || 4);
    const strandRadius = Math.max(spec.width * 0.014, 0.05);
    const totalWidth = spacing * Math.max(count - 1, 0);
    return Array.from({ length: count }).map((_, strandIndex) => {
      const x = -totalWidth / 2 + strandIndex * spacing;
      return (
        <mesh
          key={`strand-${rowIndex}-${strandIndex}`}
          position={[x, startY + rowIndex * rowSpacing, spec.length / 2]}
          rotation={[Math.PI / 2, 0, 0]}
          onClick={onPick}
        >
          <cylinderGeometry args={[strandRadius, strandRadius, spec.length, 12]} />
          <meshStandardMaterial color="#f6d76b" roughness={0.4} metalness={0.35} />
        </mesh>
      );
    });
  });
}

function Stirrups({ spec, onPick }) {
  const stirrup = spec.blueprint.stirrups || {};
  const start = stirrup.start_ft ?? 2;
  const end = Math.min(stirrup.end_ft ?? spec.length - 2, spec.length - 1);
  const spacing = inchesToFeet(stirrup.spacing_in || 24);
  const cover = inchesToFeet(stirrup.cover_in || 2.5);
  const width = Math.max(spec.width - cover * 2, spec.width * 0.55);
  const height = Math.max(spec.depth - cover * 2, spec.depth * 0.65);
  const count = Math.max(Math.floor((Math.max(end - start, 0)) / spacing) + 1, 0);
  return Array.from({ length: count }).map((_, index) => {
    const z = Math.min(start + index * spacing, end);
    return (
      <group key={`stirrup-${index}`} position={[0, cover, z]}>
        <mesh onClick={onPick}>
          <boxGeometry args={[width, 0.03, 0.03]} />
          <meshStandardMaterial color="#5b6776" roughness={0.65} metalness={0.25} />
        </mesh>
        <mesh position={[0, height, 0]} onClick={onPick}>
          <boxGeometry args={[width, 0.03, 0.03]} />
          <meshStandardMaterial color="#5b6776" roughness={0.65} metalness={0.25} />
        </mesh>
        <mesh position={[-width / 2, height / 2, 0]} onClick={onPick}>
          <boxGeometry args={[0.03, height, 0.03]} />
          <meshStandardMaterial color="#5b6776" roughness={0.65} metalness={0.25} />
        </mesh>
        <mesh position={[width / 2, height / 2, 0]} onClick={onPick}>
          <boxGeometry args={[0.03, height, 0.03]} />
          <meshStandardMaterial color="#5b6776" roughness={0.65} metalness={0.25} />
        </mesh>
      </group>
    );
  });
}

function DimensionCallouts({ beam, spec }) {
  const labels = [
    {
      key: "length",
      value: `L = ${beam.length_ft} ft`,
      anchor: [-spec.width * 0.7, spec.depth + 0.5, spec.length / 2],
      points: [[-spec.width * 0.5, spec.depth + 0.12, 0], [-spec.width * 0.5, spec.depth + 0.12, spec.length]],
    },
    {
      key: "depth",
      value: `D = ${Math.round((beam.product_type?.depth_in || spec.depth * 12) * 10) / 10} in`,
      anchor: [spec.width * 0.9, spec.depth / 2, spec.length * 0.18],
      points: [[spec.width * 0.55, 0, spec.length * 0.18], [spec.width * 0.55, spec.depth, spec.length * 0.18]],
    },
    {
      key: "width",
      value: `W = ${Math.round((beam.product_type?.width_in || spec.width * 12) * 10) / 10} in`,
      anchor: [0, spec.depth + 0.7, spec.length * 0.16],
      points: [[-spec.width / 2, spec.depth + 0.2, spec.length * 0.16], [spec.width / 2, spec.depth + 0.2, spec.length * 0.16]],
    },
  ];
  return labels.map((label) => (
    <group key={label.key}>
      <Line points={label.points} color="#5fb3ff" lineWidth={1} />
      <Html position={label.anchor} distanceFactor={14}>
        <div style={{
          background: "rgba(10, 12, 16, 0.92)",
          border: "1px solid #5fb3ff",
          color: "#d8ebff",
          fontSize: 10,
          padding: "4px 8px",
          whiteSpace: "nowrap",
          fontFamily: "JetBrains Mono, monospace",
        }}>
          {label.value}
        </div>
      </Html>
    </group>
  ));
}

function AnomalyMarkers({ anomalies, spec }) {
  return (anomalies || []).map((a) => {
    const z = Math.min(Math.max((a.position?.x || 0) / 10, 0), spec.length);
    const y = Math.min(Math.max(a.position?.y || spec.depth * 0.55, 0.2), spec.depth - 0.1);
    const x = Math.min(Math.max(a.position?.z || spec.width * 0.42, -spec.width / 2), spec.width / 2);
    const color =
      a.severity === "major" ? "#FF3366" : a.severity === "moderate" ? "#FFD600" : "#2979FF";
    return (
      <mesh key={a.id} position={[x, y, z]}>
        <sphereGeometry args={[0.14, 16, 16]} />
        <meshBasicMaterial color={color} />
        <Html distanceFactor={12} position={[0, 0.3, 0]}>
          <div style={{
            background: "#12151C", border: `1px solid ${color}`, color,
            fontSize: 9, padding: "2px 5px", fontFamily: "JetBrains Mono, monospace",
            whiteSpace: "nowrap", transform: "translateX(-50%)",
          }}>
            {a.type?.toUpperCase()}
          </div>
        </Html>
      </mesh>
    );
  });
}

function Beam({ beam, anomalies, onPick }) {
  const spec = useBeamSpec(beam);
  const groupRef = useRef(null);
  const handlePick = (event) => {
    event.stopPropagation();
    const localPoint = groupRef.current ? groupRef.current.worldToLocal(event.point.clone()) : event.point;
    onPick?.(localPoint);
  };
  return (
    <group ref={groupRef} position={[0, -spec.depth / 2, -spec.length / 2]}>
      <BeamShell spec={spec} onPick={handlePick} />
      <BituminousEnds spec={spec} />
      <StrandPattern spec={spec} onPick={handlePick} />
      <Stirrups spec={spec} onPick={handlePick} />
      <LiftLoops spec={spec} onPick={handlePick} />
      <SideHardware spec={spec} items={spec.blueprint.inserts} color="#c84f4f" y={spec.depth * 0.7} onPick={handlePick} kind="insert" />
      <WebTubes spec={spec} onPick={handlePick} />
      <DrainHoles spec={spec} onPick={handlePick} />
      <HoldDowns spec={spec} onPick={handlePick} />
      <DimensionCallouts beam={beam} spec={spec} />
      <AnomalyMarkers anomalies={anomalies} spec={spec} />
    </group>
  );
}

export default function BeamViewer({ beam, anomalies = [], onPick }) {
  const safeBeam = beam || { twin_type: "i_beam", length_ft: 90, product_type: {} };
  const depth = inchesToFeet(safeBeam.product_type?.depth_in || (safeBeam.twin_type === "box_beam" ? 30 : 48));
  const cameraDistance = Math.max(safeBeam.length_ft * 0.35, 20);
  return (
    <div style={{ width: "100%", height: "100%", background: "#0A0C10" }} data-testid="beam-3d-canvas">
      <Canvas camera={{ position: [cameraDistance * 0.6, depth * 2.2, cameraDistance], fov: 38 }} shadows>
        <Suspense fallback={null}>
          <ambientLight intensity={0.72} />
          <hemisphereLight intensity={0.5} groundColor="#0e1016" />
          <directionalLight position={[12, 16, 10]} intensity={0.9} castShadow />
          <directionalLight position={[-16, 8, -8]} intensity={0.4} />
          <Beam beam={safeBeam} anomalies={anomalies} onPick={onPick} />
          <gridHelper args={[Math.max(safeBeam.length_ft * 1.2, 40), Math.max(Math.round(safeBeam.length_ft / 4), 20), "#222631", "#151922"]} position={[0, -depth / 2 - 0.08, 0]} />
          <Environment preset="warehouse" />
          <OrbitControls enablePan enableZoom enableRotate maxPolarAngle={Math.PI * 0.48} makeDefault />
        </Suspense>
      </Canvas>
    </div>
  );
}
