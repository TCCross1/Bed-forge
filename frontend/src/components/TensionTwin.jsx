import React, { Suspense, useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, OrthographicCamera, PerspectiveCamera } from "@react-three/drei";
import { MarkedEndMarker, UnmarkedEndMarker, TwinBadge } from "./MarkedEndMarker";
import * as THREE from "three";
import {
  holdDownColor, inchesToFt, isDraped, strandEndYIn, strandPathPoints, strandTensionColor,
} from "../lib/beamSpec";

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
        opacity={dimmed ? 0.12 : 0.28}
        roughness={0.9}
        metalness={0.04}
        depthWrite={false}
      />
    </mesh>
  );
}

function StrandPath({ strand, length, holdDowns, selected, onSelect, showLabel, endView }) {
  const color = strandTensionColor(strand);
  const x = inchesToFt(strand.x_in ?? strand.offset_in);
  const yEnd = inchesToFt(strandEndYIn(strand));
  const points = useMemo(() => {
    if (endView) return [new THREE.Vector3(x, yEnd, 0), new THREE.Vector3(x, yEnd, 0.12)];
    return strandPathPoints(strand, length, holdDowns, 56).map((p) => new THREE.Vector3(p.x, p.y, p.z));
  }, [endView, holdDowns, length, strand, x, yEnd]);
  const curve = useMemo(() => new THREE.CatmullRomCurve3(points), [points]);
  const draped = isDraped(strand);
  return (
    <group>
      {!endView && (
        <mesh
          onClick={(e) => {
            e.stopPropagation();
            onSelect({ kind: "strand", item: strand });
          }}
          onPointerOver={() => { document.body.style.cursor = "pointer"; }}
          onPointerOut={() => { document.body.style.cursor = "auto"; }}
        >
          <tubeGeometry args={[curve, Math.max(24, points.length), selected ? 0.055 : 0.038, 10, false]} />
          <meshStandardMaterial
            color={color}
            emissive={selected ? "#FFFFFF" : color}
            emissiveIntensity={selected ? 0.45 : draped ? 0.22 : 0.12}
            metalness={0.45}
            roughness={0.35}
          />
        </mesh>
      )}
      <mesh
        position={[x, yEnd, endView ? 0.08 : 0.04]}
        onClick={(e) => {
          e.stopPropagation();
          onSelect({ kind: "strand", item: strand });
        }}
        onPointerOver={() => { document.body.style.cursor = "pointer"; }}
        onPointerOut={() => { document.body.style.cursor = "auto"; }}
      >
        <sphereGeometry args={[selected ? 0.11 : 0.085, 16, 16]} />
        <meshStandardMaterial
          color={color}
          emissive={selected ? "#FFFFFF" : color}
          emissiveIntensity={selected ? 0.55 : 0.28}
          metalness={0.35}
          roughness={0.3}
        />
      </mesh>
      {endView && (
        <mesh
          position={[x, yEnd, 0.08]}
          onClick={(e) => {
            e.stopPropagation();
            onSelect({ kind: "strand", item: strand });
          }}
        >
          <sphereGeometry args={[0.16, 8, 8]} />
          <meshBasicMaterial transparent opacity={0} depthWrite={false} />
        </mesh>
      )}
      {showLabel && (
        <TwinBadge
          text={`${strand.number}${draped ? "D" : ""}`}
          color={color}
          compact
          position={[x, yEnd + 0.18, endView ? 0.12 : 0.2]}
        />
      )}
    </group>
  );
}

function holdDownClampXs(item) {
  const qty = Math.max(1, Number(item.quantity_at_station) || 1);
  const pitchIn = Number(item.offset_in);
  const pitch = inchesToFt(Number.isFinite(pitchIn) && Math.abs(pitchIn) > 0 ? Math.abs(pitchIn) : 2);
  if (qty <= 1) return [inchesToFt(Number.isFinite(pitchIn) ? pitchIn : 0)];
  return [-pitch, pitch];
}

function HoldDownStation({ item, selected, onSelect, showLabel, geo }) {
  const z = Number(item.station_from_marked_end) || 0;
  const color = holdDownColor(item);
  const web = inchesToFt(geo?.web_thick_in || 6);
  const xs = holdDownClampXs(item);
  const handle = (e) => {
    e.stopPropagation();
    onSelect({ kind: "hold_down", item });
  };
  return (
    <group position={[0, 0, z]} onClick={handle}>
      <mesh
        position={[0, 0.55, 0]}
        onClick={handle}
        onPointerOver={() => { document.body.style.cursor = "pointer"; }}
        onPointerOut={() => { document.body.style.cursor = "auto"; }}
      >
        <boxGeometry args={[web + 1.1, 1.35, 0.75]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
      <mesh position={[0, 0.04, 0]}>
        <boxGeometry args={[web + 0.55, 0.08, 0.42]} />
        <meshStandardMaterial color={color} metalness={0.7} roughness={0.28} emissive={selected ? color : "#000"} emissiveIntensity={selected ? 0.4 : 0} />
      </mesh>
      {xs.map((ox) => (
        <group key={ox} position={[ox, 0, 0]}>
          <mesh position={[0, 0.55, 0]}>
            <cylinderGeometry args={[0.035, 0.035, 1.1, 10]} />
            <meshStandardMaterial color="#C9A227" metalness={0.82} roughness={0.22} />
          </mesh>
          <mesh position={[0, 0.22, 0]}>
            <boxGeometry args={[0.32, 0.06, 0.28]} />
            <meshStandardMaterial color={color} metalness={0.65} roughness={0.3} />
          </mesh>
        </group>
      ))}
      {showLabel && (
        <TwinBadge
          text={`${item.type_spec || "H-56-S"} · ${z}' ME`}
          color={color}
          compact
          position={[0, 1.35, 0]}
        />
      )}
    </group>
  );
}

function Scene({ spec, strands, holdDowns, view, selected, onSelect }) {
  const geo = spec.geometry;
  const length = Number(geo.length_ft) || 73;
  const endView = view === "end";
  const shellLen = endView ? 0.28 : length;
  return (
    <group>
      <BeamShell geo={geo} length={shellLen} dimmed={!endView} />
      {strands.map((strand) => (
        <StrandPath
          key={strand.id || strand.strand_id || strand.number}
          strand={strand}
          length={length}
          holdDowns={holdDowns}
          selected={selected?.kind === "strand" && (selected.item.id === strand.id || selected.item.number === strand.number)}
          onSelect={onSelect}
          showLabel={endView || (selected?.kind === "strand" && (selected.item.id === strand.id || selected.item.number === strand.number))}
          endView={endView}
        />
      ))}
      {!endView && holdDowns.map((item) => (
        <HoldDownStation
          key={item.id}
          item={item}
          geo={geo}
          selected={selected?.kind === "hold_down" && selected.item.id === item.id}
          onSelect={onSelect}
          showLabel
        />
      ))}
      <MarkedEndMarker
        depthFt={inchesToFt(geo.depth_in)}
        widthFt={inchesToFt(geo.top_flange_width_in || geo.width_in)}
        compact={endView}
        stripeFt={endView ? 0 : undefined}
        label={endView ? "ME · STRAND PATTERN" : (spec.marked_end_id || "MARKED END")}
      />
      {!endView && (
        <UnmarkedEndMarker
          depthFt={inchesToFt(geo.depth_in)}
          widthFt={inchesToFt(geo.top_flange_width_in || geo.width_in)}
          z={length}
          label={spec.unmarked_end_id || "UE"}
        />
      )}
    </group>
  );
}

export default function TensionTwin({
  spec,
  strands = [],
  holdDowns = [],
  view = "end",
  selected,
  onSelect,
  height = 520,
}) {
  const length = Number(spec?.geometry?.length_ft) || 73;
  const depth = inchesToFt(spec?.geometry?.depth_in || 36);
  const endView = view === "end";
  const target = endView
    ? [0, depth * 0.45, 0.1]
    : [0, depth * 0.45, length * 0.5];
  const perspPos = [Math.max(14, length * 0.22), Math.max(7, depth * 2.2), length * 0.08];

  return (
    <div style={{ width: "100%", height, background: "#0A0C10" }} data-testid="tension-twin-canvas" data-view={view}>
      <Canvas dpr={[1, 1.5]} gl={{ antialias: true, powerPreference: "high-performance" }}>
        <Suspense fallback={null}>
          <color attach="background" args={["#0A0C10"]} />
          {endView ? (
            <OrthographicCamera makeDefault position={[0, depth * 0.5, -6]} zoom={height >= 480 ? 118 : 96} near={0.1} far={80} />
          ) : (
            <PerspectiveCamera makeDefault position={perspPos} fov={42} />
          )}
          <ambientLight intensity={0.95} />
          <directionalLight position={[12, 16, 8]} intensity={0.75} />
          <directionalLight position={[-8, 8, -6]} intensity={0.3} />
          {spec && (
            <Scene
              spec={spec}
              strands={strands}
              holdDowns={holdDowns}
              view={view}
              selected={selected}
              onSelect={onSelect}
            />
          )}
          <OrbitControls
            target={target}
            enablePan
            enableZoom
            enableRotate={!endView}
            makeDefault
          />
        </Suspense>
      </Canvas>
    </div>
  );
}
