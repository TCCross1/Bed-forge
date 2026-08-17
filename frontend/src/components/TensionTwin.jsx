import React, { Suspense, useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Html } from "@react-three/drei";
import * as THREE from "three";
import { holdDownColor, inchesToFt, strandTensionColor } from "../lib/beamSpec";

function iBeamShape(geo) {
  const s = new THREE.Shape();
  const h = inchesToFt(geo.depth_in);
  const tw = inchesToFt(geo.top_flange_width_in || geo.width_in) / 2;
  const bw = inchesToFt(geo.bot_flange_width_in || geo.width_in) / 2;
  const tt = inchesToFt(geo.top_flange_thick_in || 6);
  const bt = inchesToFt(geo.bot_flange_thick_in || 6);
  const wt = inchesToFt(geo.web_thick_in || 6) / 2;
  s.moveTo(-bw, 0);
  s.lineTo(bw, 0);
  s.lineTo(bw, bt);
  s.lineTo(wt, bt);
  s.lineTo(wt, h - tt);
  s.lineTo(tw, h - tt);
  s.lineTo(tw, h);
  s.lineTo(-tw, h);
  s.lineTo(-tw, h - tt);
  s.lineTo(-wt, h - tt);
  s.lineTo(-wt, bt);
  s.lineTo(-bw, bt);
  s.closePath();
  return s;
}

function boxShape(geo) {
  const s = new THREE.Shape();
  const h = inchesToFt(geo.depth_in);
  const w = inchesToFt(geo.width_in) / 2;
  s.moveTo(-w, 0);
  s.lineTo(w, 0);
  s.lineTo(w, h);
  s.lineTo(-w, h);
  s.closePath();
  return s;
}

function BeamShell({ geo, length, dimmed }) {
  const shape = useMemo(
    () => (geo.twin_type === "box_beam" ? boxShape(geo) : iBeamShape(geo)),
    [geo]
  );
  const geometry = useMemo(
    () => new THREE.ExtrudeGeometry(shape, { depth: length, bevelEnabled: false }),
    [shape, length]
  );
  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial
        color="#9aa0aa"
        transparent
        opacity={dimmed ? 0.18 : 0.28}
        roughness={0.9}
        metalness={0.04}
        depthWrite={false}
      />
    </mesh>
  );
}

function StrandCylinder({ strand, length, selected, onSelect, showLabel }) {
  const x = inchesToFt(strand.x_in ?? strand.offset_in);
  const y0 = inchesToFt(strand.y_in ?? strand.soffit_in);
  const draped = strand.draped || strand.detensioning === "draped";
  const peak = inchesToFt(strand.drape_peak_in || (y0 + 1.2));
  const color = strandTensionColor(strand);
  const points = useMemo(() => {
    const pts = [];
    const steps = draped ? 16 : 2;
    for (let i = 0; i <= steps; i += 1) {
      const t = i / steps;
      const z = t * length;
      let y = y0;
      if (draped) {
        const mid = 0.5 - t;
        y = y0 + (peak - y0) * (1 - 4 * mid * mid);
      }
      pts.push(new THREE.Vector3(x, y, z));
    }
    return pts;
  }, [draped, length, peak, x, y0]);
  const curve = useMemo(() => new THREE.CatmullRomCurve3(points), [points]);
  return (
    <group>
      <mesh
        onClick={(e) => {
          e.stopPropagation();
          onSelect({ kind: "strand", item: strand });
        }}
        onPointerOver={() => { document.body.style.cursor = "pointer"; }}
        onPointerOut={() => { document.body.style.cursor = "auto"; }}
      >
        <tubeGeometry args={[curve, 20, selected ? 0.09 : 0.07, 10, false]} />
        <meshStandardMaterial
          color={color}
          emissive={selected ? "#FFFFFF" : color}
          emissiveIntensity={selected ? 0.45 : 0.18}
          metalness={0.45}
          roughness={0.35}
        />
      </mesh>
      {showLabel && (
        <Html position={[x, y0 + 0.28, 0.15]} center>
          <div style={{
            color,
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10,
            fontWeight: 700,
            pointerEvents: "none",
            whiteSpace: "nowrap",
          }}>
            {strand.number}
          </div>
        </Html>
      )}
    </group>
  );
}

function HoldDownClamp({ offsetX, color, selected, onClick }) {
  return (
    <group position={[offsetX, 0.02, 0]} onClick={onClick}>
      <mesh position={[0, 0.06, 0]}>
        <boxGeometry args={[1.6, 0.08, 0.55]} />
        <meshStandardMaterial color={color} metalness={0.7} roughness={0.28} emissive={selected ? color : "#000"} emissiveIntensity={selected ? 0.35 : 0} />
      </mesh>
      <mesh position={[0, 0.38, 0]}>
        <boxGeometry args={[0.1, 0.55, 0.45]} />
        <meshStandardMaterial color={color} metalness={0.65} roughness={0.3} />
      </mesh>
      <mesh position={[0, 0.68, 0]}>
        <boxGeometry args={[0.9, 0.08, 0.45]} />
        <meshStandardMaterial color={color} metalness={0.7} roughness={0.28} />
      </mesh>
      <mesh position={[0, 1.05, 0]}>
        <cylinderGeometry args={[0.09, 0.09, 0.7, 10]} />
        <meshStandardMaterial color="#C9A227" metalness={0.8} roughness={0.25} />
      </mesh>
    </group>
  );
}

function HoldDownStation({ item, selected, onSelect, showLabel }) {
  const z = Number(item.station_from_marked_end) || 0;
  const color = holdDownColor(item);
  const qty = Math.max(1, Number(item.quantity_at_station) || 1);
  const offsets = qty === 1 ? [inchesToFt(item.offset_in)] : [-0.55, 0.55].slice(0, qty);
  return (
    <group position={[0, inchesToFt(item.height) || 0, z]}>
      {offsets.map((ox) => (
        <HoldDownClamp
          key={`${item.id}-${ox}`}
          offsetX={ox}
          color={color}
          selected={selected}
          onClick={(e) => {
            e.stopPropagation();
            onSelect({ kind: "hold_down", item });
          }}
        />
      ))}
      {showLabel && (
        <Html position={[0, 1.6, 0]} center>
          <div style={{
            color,
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10,
            whiteSpace: "nowrap",
            pointerEvents: "none",
          }}>
            HD {z}' ME
          </div>
        </Html>
      )}
    </group>
  );
}

function Scene({ spec, strands, holdDowns, layer, selected, onSelect }) {
  const geo = spec.geometry;
  const length = Number(geo.length_ft) || 73;
  const showStrands = layer === "strands" || layer === "both";
  const showHold = layer === "hold_downs" || layer === "both";
  return (
    <group>
      <BeamShell geo={geo} length={length} dimmed={!showStrands} />
      <mesh position={[0, inchesToFt(geo.depth_in) / 2, 0.05]}>
        <boxGeometry args={[inchesToFt(geo.bot_flange_width_in || geo.width_in) + 0.4, inchesToFt(geo.depth_in) + 0.4, 0.08]} />
        <meshStandardMaterial color="#2979FF" transparent opacity={0.18} />
      </mesh>
      {showStrands && strands.map((strand) => (
        <StrandCylinder
          key={strand.id || strand.strand_id}
          strand={strand}
          length={Math.min(8, length * 0.12)}
          selected={selected?.kind === "strand" && (selected.item.id === strand.id)}
          onSelect={onSelect}
          showLabel={layer === "strands"}
        />
      ))}
      {showHold && holdDowns.map((item) => (
        <HoldDownStation
          key={item.id}
          item={item}
          selected={selected?.kind === "hold_down" && selected.item.id === item.id}
          onSelect={onSelect}
          showLabel={layer !== "strands"}
        />
      ))}
      <Html position={[0, inchesToFt(geo.depth_in) + 0.6, 0.2]} center>
        <div style={{ color: "#2979FF", fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>MARKED END</div>
      </Html>
    </group>
  );
}

export default function TensionTwin({
  spec,
  strands = [],
  holdDowns = [],
  layer = "both",
  selected,
  onSelect,
  height = 520,
}) {
  const length = Number(spec?.geometry?.length_ft) || 73;
  const cam = layer === "strands"
    ? { position: [0.2, 2.4, -7], target: [0, 1.2, 1.5] }
    : layer === "hold_downs"
      ? { position: [16, 10, length * 0.45], target: [0, 1, length * 0.5] }
      : { position: [14, 9, -6], target: [0, 1.5, length * 0.25] };

  return (
    <div style={{ width: "100%", height, background: "#0A0C10" }} data-testid="tension-twin-canvas">
      <Canvas camera={{ position: cam.position, fov: 42 }} dpr={[1, 1.5]} gl={{ antialias: true, powerPreference: "high-performance" }}>
        <Suspense fallback={null}>
          <color attach="background" args={["#0A0C10"]} />
          <ambientLight intensity={0.95} />
          <directionalLight position={[12, 16, 8]} intensity={0.75} />
          <directionalLight position={[-8, 8, -6]} intensity={0.3} />
          {spec && (
            <Scene
              spec={spec}
              strands={strands}
              holdDowns={holdDowns}
              layer={layer}
              selected={selected}
              onSelect={onSelect}
            />
          )}
          <OrbitControls target={cam.target} enablePan enableZoom enableRotate makeDefault />
        </Suspense>
      </Canvas>
    </div>
  );
}
