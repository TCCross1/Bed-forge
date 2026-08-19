import React, { Suspense, useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { Html, Line, OrbitControls, PerspectiveCamera } from "@react-three/drei";
import * as THREE from "three";

const inchesToFeet = (value = 0) => (Number(value) || 0) / 12;
const concrete = "#AEB6C2";
const concreteDark = "#687383";
const wood = "#C99258";
const steel = "#B9C2CF";
const epoxy = "#7CFC00";
const brass = "#E3C565";

function formatCamber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? `${n.toFixed(2)} in` : "—";
}

function normalizeBlueprint(beam) {
  const depth = beam?.product_type?.depth_in || (beam?.twin_type === "box_beam" ? 30 : 48);
  const width = beam?.product_type?.width_in || (beam?.twin_type === "box_beam" ? 42 : 18);
  const length = Math.max(beam?.length_ft || beam?.product_type?.default_length_ft || 80, 10);
  const source = beam?.product_type?.blueprint || {};
  const cross = beam?.twin_type === "box_beam"
    ? {
        outer_width_in: width,
        outer_depth_in: depth,
        wall_thickness_in: 4,
        void_width_in: Math.max(width - 14, 16),
        void_depth_in: Math.max(depth - 10, 14),
      }
    : {
        bottom_flange_width_in: Math.max(width * 1.7, width + 10),
        bottom_flange_thickness_in: 8,
        web_thickness_in: 7,
        top_flange_width_in: width,
        top_flange_thickness_in: 7,
        overall_depth_in: depth,
      };
  return {
    cross_section: { ...cross, ...(source.cross_section || {}) },
    lift_loops: source.lift_loops || [],
    inserts: source.inserts || [],
    tubes: source.tubes || [],
    tie_rod_openings: source.tie_rod_openings || [],
    drain_holes: source.drain_holes || [],
    hold_downs: source.hold_downs || [],
    bituminous_ends: source.bituminous_ends || [],
    stirrups: source.stirrups || { start_ft: 2, end_ft: Math.max(length - 2, 4), spacing_in: 24 },
    strand_pattern: source.strand_pattern || { start_y_in: 5, row_spacing_in: 4.5, rows: [{ count: 4, spacing_in: 4 }, { count: 4, spacing_in: 4 }] },
    dimensions: { overall_length_ft: length, overall_depth_in: depth, ...(source.dimensions || {}) },
    length,
  };
}

function profilePoints(beam, blueprint) {
  const s = blueprint.cross_section || {};
  if (beam?.twin_type === "box_beam") {
    const w = inchesToFeet(s.outer_width_in || s.overall_width_in || 42) / 2;
    const h = inchesToFeet(s.outer_depth_in || s.overall_depth_in || 30);
    return [[-w, 0], [w, 0], [w, h], [-w, h]];
  }
  const bw = inchesToFeet(s.bottom_flange_width_in || 28) / 2;
  const bt = inchesToFeet(s.bottom_flange_thickness_in || 8);
  const web = inchesToFeet(s.web_thickness_in || 7) / 2;
  const tw = inchesToFeet(s.top_flange_width_in || 16) / 2;
  const tt = inchesToFeet(s.top_flange_thickness_in || 7);
  const h = inchesToFeet(s.overall_depth_in || 48);
  const br = Math.min(inchesToFeet(s.bottom_transition_in || 4), Math.max(bw - web - 0.04, 0.06));
  const tr = Math.min(inchesToFeet(s.top_transition_in || 5), Math.max(tw - web - 0.04, 0.06));
  const rise = Math.min(inchesToFeet(s.bottom_transition_rise_in || 4.5), Math.max(h * 0.14, 0.12));
  const drop = Math.min(inchesToFeet(s.top_transition_drop_in || 4.5), Math.max(h * 0.12, 0.12));
  return [
    [-bw, 0], [bw, 0], [bw, bt], [web + br, bt], [web, bt + rise],
    [web, h - tt - drop], [web + tr, h - tt], [tw, h - tt], [tw, h],
    [-tw, h], [-tw, h - tt], [-web - tr, h - tt], [-web, h - tt - drop],
    [-web, bt + rise], [-web - br, bt], [-bw, bt],
  ];
}

function useCamberedGeometry(beam, supportY, camberFt, visualScale) {
  return useMemo(() => {
    const blueprint = normalizeBlueprint(beam);
    const length = blueprint.length;
    const profile = profilePoints(beam, blueprint);
    const segs = 72;
    const verts = [];
    const indices = [];
    const camberAt = (z) => supportY + camberFt * visualScale * 4 * (z / length) * (1 - z / length);
    for (let i = 0; i <= segs; i += 1) {
      const z = (i / segs) * length;
      const lift = camberAt(z);
      profile.forEach(([x, y]) => verts.push(x, y + lift, z));
    }
    const n = profile.length;
    for (let i = 0; i < segs; i += 1) {
      for (let j = 0; j < n; j += 1) {
        const a = i * n + j;
        const b = i * n + ((j + 1) % n);
        const c = (i + 1) * n + ((j + 1) % n);
        const d = (i + 1) * n + j;
        indices.push(a, b, d, b, c, d);
      }
    }
    for (let j = 1; j < n - 1; j += 1) indices.push(0, j, j + 1);
    const end = segs * n;
    for (let j = 1; j < n - 1; j += 1) indices.push(end, end + j + 1, end + j);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(verts, 3));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    return { geometry, blueprint, length, depth: Math.max(...profile.map((p) => p[1])), width: Math.max(...profile.map((p) => Math.abs(p[0]))) * 2, camberAt };
  }, [beam, supportY, camberFt, visualScale]);
}

function Badge({ position, color = "#D8ECFF", children }) {
  return (
    <Html position={position} center distanceFactor={16}>
      <div className="px-2 py-1 border bg-[#070A10]/95 text-[10px] font-mono uppercase tracking-widest whitespace-nowrap" style={{ borderColor: color, color }}>
        {children}
      </div>
    </Html>
  );
}

function StationHardware({ blueprint, dims, visible = true }) {
  if (!visible) return null;
  const yAt = (z, extra = 0) => dims.camberAt(z) + dims.depth + extra;
  const sideY = (z) => dims.camberAt(z) + dims.depth * 0.55;
  const bottomY = (z) => dims.camberAt(z) + 0.16;
  return (
    <group>
      {(blueprint.lift_loops || []).map((item, index) => {
        const z = Number(item.x_ft) || 0;
        return (
          <group key={`lift-${index}`} position={[0, yAt(z, 0.22), z]}>
            <mesh rotation={[Math.PI / 2, 0, 0]}>
              <torusGeometry args={[0.28, 0.035, 8, 24, Math.PI]} />
              <meshStandardMaterial color={steel} metalness={0.55} roughness={0.28} />
            </mesh>
          </group>
        );
      })}
      {(blueprint.inserts || []).map((item, index) => {
        const z = Number(item.x_ft) || 0;
        const side = item.side === "right" ? 1 : -1;
        return (
          <group key={`insert-${index}`} position={[side * dims.width * 0.5, sideY(z), z]} rotation={[0, Math.PI / 2, 0]}>
            <mesh><cylinderGeometry args={[0.09, 0.09, 0.12, 6]} /><meshStandardMaterial color="#A9B3C0" metalness={0.7} roughness={0.34} /></mesh>
            <mesh position={[0, 0, 0.07]}><cylinderGeometry args={[0.04, 0.04, 0.08, 14]} /><meshStandardMaterial color="#202632" /></mesh>
          </group>
        );
      })}
      {[...(blueprint.tubes || []), ...(blueprint.tie_rod_openings || [])].map((item, index) => {
        const z = Number(item.x_ft) || 0;
        const radius = Math.max(inchesToFeet(item.diameter_in || 2.5) / 2, 0.08);
        return (
          <mesh key={`tube-${index}`} position={[0, sideY(z), z]} rotation={[0, Math.PI / 2, 0]}>
            <cylinderGeometry args={[radius, radius, dims.width * 1.12, 18]} />
            <meshStandardMaterial color="#202734" metalness={0.2} roughness={0.58} />
          </mesh>
        );
      })}
      {(blueprint.drain_holes || []).map((item, index) => {
        const z = Number(item.x_ft) || 0;
        return (
          <group key={`drain-${index}`} position={[0, bottomY(z), z]}>
            <mesh rotation={[0, Math.PI / 2, 0]}><cylinderGeometry args={[0.09, 0.09, dims.width * 0.9, 16]} /><meshStandardMaterial color="#455160" metalness={0.4} roughness={0.5} /></mesh>
            <mesh position={[dims.width * 0.45, -0.16, 0]} rotation={[Math.PI / 2, 0, 0]}><cylinderGeometry args={[0.05, 0.05, 0.34, 12]} /><meshStandardMaterial color="#4D5966" /></mesh>
          </group>
        );
      })}
    </group>
  );
}

function Stirrups({ blueprint, dims }) {
  const st = blueprint.stirrups || {};
  const start = Number(st.start_ft ?? 2);
  const end = Math.min(Number(st.end_ft ?? dims.length - 2), dims.length - 1);
  const spacing = Math.max(inchesToFeet(st.spacing_in || 24), 1.5);
  const stations = [];
  for (let z = start; z <= end; z += spacing) stations.push(z);
  return (
    <group>
      {stations.map((z, index) => (
        <group key={index} position={[0, dims.camberAt(z) + dims.depth + 0.55, z]}>
          {[-dims.width * 0.18, dims.width * 0.18].map((x) => (
            <group key={x} position={[x, 0, 0]}>
              <mesh rotation={[Math.PI / 2, 0, 0]}><torusGeometry args={[0.16, 0.022, 6, 14, Math.PI]} /><meshStandardMaterial color={epoxy} roughness={0.82} /></mesh>
              <mesh position={[-0.16, -0.28, 0]}><boxGeometry args={[0.035, 0.56, 0.035]} /><meshStandardMaterial color={epoxy} roughness={0.82} /></mesh>
              <mesh position={[0.16, -0.28, 0]}><boxGeometry args={[0.035, 0.56, 0.035]} /><meshStandardMaterial color={epoxy} roughness={0.82} /></mesh>
            </group>
          ))}
        </group>
      ))}
    </group>
  );
}

function Strands({ blueprint, dims }) {
  const rows = blueprint.strand_pattern?.rows || [];
  const startY = inchesToFeet(blueprint.strand_pattern?.start_y_in || 5);
  const rowSpacing = inchesToFeet(blueprint.strand_pattern?.row_spacing_in || 4.5);
  const strands = rows.flatMap((row, rowIndex) => {
    const spacing = inchesToFeet(row.spacing_in || 4);
    const count = row.count || 0;
    const total = spacing * Math.max(count - 1, 0);
    return Array.from({ length: count }).map((_, i) => ({ x: -total / 2 + i * spacing, y: startY + rowIndex * rowSpacing }));
  });
  return strands.map((strand, index) => (
    <Line key={index} points={[[strand.x, dims.camberAt(0) + strand.y, 0], [strand.x, dims.camberAt(dims.length / 2) + strand.y, dims.length / 2], [strand.x, dims.camberAt(dims.length) + strand.y, dims.length]]} color={brass} lineWidth={1.2} />
  ));
}

function Supports({ dims, supportTop }) {
  const pillarW = Math.min(Math.max(dims.width * 1.2, 2.4), 4.2);
  const shimH = 0.08;
  return (
    <group>
      {[0, dims.length].map((z, idx) => (
        <group key={z} position={[0, 0, z]}>
          <mesh position={[0, supportTop / 2, 0]}>
            <boxGeometry args={[pillarW, supportTop, 2.2]} />
            <meshStandardMaterial color={concrete} roughness={0.86} metalness={0.02} />
          </mesh>
          <mesh position={[0, supportTop + shimH / 2, 0]}>
            <boxGeometry args={[pillarW * 0.74, shimH, 1.35]} />
            <meshStandardMaterial color={wood} roughness={0.72} metalness={0.02} />
          </mesh>
          <mesh position={[0, supportTop + shimH * 1.6, 0]}>
            <boxGeometry args={[pillarW * 0.62, shimH, 1.05]} />
            <meshStandardMaterial color="#E1B070" roughness={0.76} metalness={0.01} />
          </mesh>
          <Badge position={[0, supportTop + 0.34, idx === 0 ? -1.1 : 1.1]} color="#E1B070">wood shims</Badge>
        </group>
      ))}
      <mesh position={[0, -0.04, dims.length / 2]}>
        <boxGeometry args={[Math.max(dims.width * 2.6, 7), 0.06, dims.length + 7]} />
        <meshStandardMaterial color={concreteDark} roughness={0.95} metalness={0} />
      </mesh>
    </group>
  );
}

function CamberScene({ beam, camberIn }) {
  const camber = Number.isFinite(Number(camberIn)) && Number(camberIn) > 0 ? Number(camberIn) : 1.5;
  const scale = Math.max(10, Math.min(28, 24 / Math.max(camber, 1)));
  const supportTop = 1.05;
  const shim = 0.16;
  const dims = useCamberedGeometry(beam, supportTop + shim, inchesToFeet(camber), scale);
  const midLift = inchesToFeet(camber) * scale;
  return (
    <group position={[0, 0, -dims.length / 2]}>
      <Supports dims={dims} supportTop={supportTop} />
      <mesh geometry={dims.geometry} castShadow receiveShadow>
        <meshStandardMaterial color="#B7BEC7" roughness={0.88} metalness={0.03} />
      </mesh>
      <lineSegments>
        <edgesGeometry args={[dims.geometry, 18]} />
        <lineBasicMaterial color="#D8DEE5" transparent opacity={0.34} />
      </lineSegments>
      <Stirrups blueprint={dims.blueprint} dims={dims} />
      <Strands blueprint={dims.blueprint} dims={dims} />
      <StationHardware blueprint={dims.blueprint} dims={dims} />
      <Line points={[[0, supportTop + shim + dims.depth + 0.6, 0], [0, supportTop + shim + dims.depth + 0.6 + midLift, dims.length / 2], [0, supportTop + shim + dims.depth + 0.6, dims.length]]} color="#73BCFF" lineWidth={2} />
      <Badge position={[0, supportTop + shim + dims.depth + 1 + midLift, dims.length / 2]} color="#73BCFF">camber {formatCamber(camber)} · exaggerated {Math.round(scale)}×</Badge>
      <Badge position={[-dims.width * 0.9, supportTop + shim + 0.3, 0]} color="#D8ECFF">marked end support</Badge>
      <Badge position={[dims.width * 0.9, supportTop + shim + 0.3, dims.length]} color="#D8ECFF">unmarked end support</Badge>
    </group>
  );
}

export default function CamberTwin({ beam, camberIn, height = 420 }) {
  if (!beam) {
    return <div className="h-full min-h-[320px] flex items-center justify-center text-sm font-mono text-muted-foreground">Select a beam to preview camber.</div>;
  }
  const length = Number(beam.length_ft || beam.product_type?.default_length_ft || 90);
  return (
    <div className="relative bg-[#0A0C10] border border-[#1C2230]" style={{ height }} data-testid="camber-twin-canvas">
      <Canvas dpr={[1, 1.5]} gl={{ antialias: true, powerPreference: "high-performance" }} shadows>
        <Suspense fallback={null}>
          <color attach="background" args={["#0A0C10"]} />
          <PerspectiveCamera makeDefault position={[Math.max(12, length * 0.18), 7.5, Math.max(16, length * 0.28)]} fov={42} />
          <ambientLight intensity={0.92} />
          <directionalLight position={[8, 12, 8]} intensity={0.85} castShadow />
          <directionalLight position={[-8, 4, -6]} intensity={0.25} />
          <CamberScene beam={beam} camberIn={camberIn} />
          <OrbitControls target={[0, 2.8, 0]} enablePan enableZoom enableRotate makeDefault />
        </Suspense>
      </Canvas>
      <div className="absolute left-3 bottom-3 px-3 py-2 border border-[#1C2230] bg-[#070A10]/90 text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
        Supports + shims are schematic. Camber arc is scaled for field visibility.
      </div>
    </div>
  );
}
