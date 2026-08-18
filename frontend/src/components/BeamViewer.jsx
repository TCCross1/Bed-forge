import React, { useMemo, useState, Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, ContactShadows } from "@react-three/drei";
import * as THREE from "three";
import { hardwareColor, inchesToFt, strandPathPoints } from "../lib/beamSpec";
import { COMPACT_HARDWARE_KINDS } from "../lib/bedLayout";
import { MarkedEndMarker, UnmarkedEndMarker } from "./MarkedEndMarker";

function iBeamShape(geo) {
  const s = new THREE.Shape();
  const h = inchesToFt(geo.depth_in);
  const tw = inchesToFt(geo.top_flange_width_in) / 2;
  const bw = inchesToFt(geo.bot_flange_width_in) / 2;
  const tt = inchesToFt(geo.top_flange_thick_in);
  const bt = inchesToFt(geo.bot_flange_thick_in);
  const wt = inchesToFt(geo.web_thick_in) / 2;
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

function boxBeamShape(geo) {
  const s = new THREE.Shape();
  const h = inchesToFt(geo.depth_in);
  const w = inchesToFt(geo.width_in) / 2;
  const wall = 0.25;
  s.moveTo(-w, 0);
  s.lineTo(w, 0);
  s.lineTo(w, h);
  s.lineTo(-w, h);
  s.closePath();
  const hole = new THREE.Path();
  hole.moveTo(-w + wall, wall);
  hole.lineTo(w - wall, wall);
  hole.lineTo(w - wall, h - wall);
  hole.lineTo(-w + wall, h - wall);
  hole.closePath();
  s.holes.push(hole);
  return s;
}

function BeamBody({ geo, onPick, bodyColor = "#9aa0aa", highlighted = false }) {
  const length = geo.length_ft;
  const shape = useMemo(
    () => (geo.twin_type === "box_beam" ? boxBeamShape(geo) : iBeamShape(geo)),
    [geo]
  );
  const geometry = useMemo(
    () => new THREE.ExtrudeGeometry(shape, { depth: length, bevelEnabled: false }),
    [shape, length]
  );
  return (
    <mesh
      geometry={geometry}
      castShadow
      receiveShadow
      onClick={(e) => {
        e.stopPropagation();
        if (onPick) onPick(e.point);
      }}
      onPointerOver={() => { document.body.style.cursor = "crosshair"; }}
      onPointerOut={() => { document.body.style.cursor = "auto"; }}
    >
      <meshStandardMaterial
        color={bodyColor}
        roughness={highlighted ? 0.45 : 0.86}
        metalness={highlighted ? 0.18 : 0.04}
        emissive={highlighted ? bodyColor : "#000000"}
        emissiveIntensity={highlighted ? 0.28 : 0}
      />
    </mesh>
  );
}

function StrandRun({ strand, length, holdDowns }) {
  const points = useMemo(() => {
    return strandPathPoints(strand, length, holdDowns, 48).map((p) => new THREE.Vector3(p.x, p.y, p.z));
  }, [strand, length, holdDowns]);
  const curve = useMemo(() => new THREE.CatmullRomCurve3(points), [points]);
  const draped = strand.draped || strand.detensioning === "draped";
  return (
    <mesh>
      <tubeGeometry args={[curve, 32, 0.022, 6, false]} />
      <meshStandardMaterial
        color={draped ? "#7E57C2" : "#5C6BC0"}
        metalness={0.6}
        roughness={0.35}
      />
    </mesh>
  );
}

function HardwareMesh({ item, geo, selected, measurement, onSelect }) {
  const color = selected ? "#FFFFFF" : hardwareColor(item.kind, measurement);
  const z = item.position?.station_ft || 0;
  const x = inchesToFt(item.position?.offset_in);
  const y = inchesToFt(item.position?.height_from_soffit_in);
  const depth = inchesToFt(geo.depth_in);
  const kind = item.kind;
  const z2 = item.end_station_ft != null ? item.end_station_ft : z + 0.4;
  const span = Math.max(0.3, z2 - z);

  const handle = (e) => {
    e.stopPropagation();
    if (onSelect) onSelect(item);
  };

  if (kind === "bituminous_zone") {
    const bw = inchesToFt(geo.bot_flange_width_in);
    return (
      <mesh position={[0, 0.04, z + span / 2]} onClick={handle}>
        <boxGeometry args={[bw * 0.92, 0.08, span]} />
        <meshStandardMaterial color="#111111" roughness={0.95} />
      </mesh>
    );
  }
  if (kind === "lift_loop") {
    return (
      <group position={[x, depth + 0.15, z]} onClick={handle}>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.18, 0.035, 8, 16, Math.PI]} />
          <meshStandardMaterial color={color} metalness={0.7} roughness={0.3} emissive={selected ? color : "#000"} emissiveIntensity={selected ? 0.4 : 0} />
        </mesh>
      </group>
    );
  }
  if (kind === "insert") {
    return (
      <mesh position={[x, y, z]} onClick={handle}>
        <cylinderGeometry args={[0.06, 0.06, 0.12, 10]} />
        <meshStandardMaterial color={color} metalness={0.5} roughness={0.4} emissive={selected ? color : "#000"} emissiveIntensity={selected ? 0.35 : 0} />
      </mesh>
    );
  }
  if (kind === "drain" || kind === "tube" || kind === "downspout" || kind === "tie_rod") {
    const r = kind === "downspout" ? 0.16 : 0.09;
    return (
      <mesh position={[x, y, z]} rotation={[0, 0, Math.PI / 2]} onClick={handle}>
        <cylinderGeometry args={[r, r, kind === "tube" || kind === "tie_rod" ? inchesToFt(geo.web_thick_in) + 0.4 : 0.35, 12]} />
        <meshStandardMaterial color={color} metalness={0.2} roughness={0.5} emissive={selected ? color : "#000"} emissiveIntensity={selected ? 0.35 : 0} />
      </mesh>
    );
  }
  if (kind === "hold_down") {
    return (
      <mesh position={[x, 0.12, z]} onClick={handle}>
        <boxGeometry args={[0.35, 0.18, 0.35]} />
        <meshStandardMaterial color={color} metalness={0.6} roughness={0.35} />
      </mesh>
    );
  }
  if (kind === "bearing_plate") {
    const bw = inchesToFt(geo.bot_flange_width_in);
    return (
      <mesh position={[0, -0.04, z]} onClick={handle}>
        <boxGeometry args={[bw * 0.9, 0.06, 0.7]} />
        <meshStandardMaterial color={color} metalness={0.8} roughness={0.25} />
      </mesh>
    );
  }
  if (kind === "diaphragm") {
    return (
      <mesh position={[inchesToFt(geo.web_thick_in) / 2 + 0.08, y, z]} onClick={handle}>
        <boxGeometry args={[0.08, 0.7, 0.7]} />
        <meshStandardMaterial color={color} metalness={0.55} roughness={0.4} />
      </mesh>
    );
  }
  if (kind === "projecting_rebar") {
    return (
      <group position={[0, y, z]} onClick={handle}>
        {[-0.15, -0.05, 0.05, 0.15].map((dx) => (
          <mesh key={dx} position={[dx, 0, 0.4]}>
            <cylinderGeometry args={[0.03, 0.03, 0.8, 8]} />
            <meshStandardMaterial color={color} metalness={0.5} roughness={0.45} />
          </mesh>
        ))}
      </group>
    );
  }
  if (kind === "grout_groove" || kind === "shear_key") {
    const w = inchesToFt(geo.width_in);
    return (
      <mesh position={[w / 2 - 0.04, y, z + span / 2]} onClick={handle}>
        <boxGeometry args={[0.08, 0.12, span]} />
        <meshStandardMaterial color={color} />
      </mesh>
    );
  }
  return (
    <mesh position={[x, y, z]} onClick={handle}>
      <boxGeometry args={[0.16, 0.16, 0.16]} />
      <meshStandardMaterial color={color} />
    </mesh>
  );
}

function Stirrups({ zones, geo }) {
  const stations = useMemo(() => {
    const list = [];
    (zones || []).forEach((zone) => {
      const spacing = Math.max(inchesToFt(zone.spacing_in), 0.2);
      for (let z = zone.from_ft; z <= zone.to_ft; z += spacing) {
        list.push({ z, hoop: zone.shape === "hoop" });
      }
    });
    return list;
  }, [zones]);
  const depth = inchesToFt(geo.depth_in);
  const web = inchesToFt(geo.web_thick_in);
  return (
    <group>
      {stations.map((item, i) => (
        <mesh key={`${item.z}-${i}`} position={[0, depth / 2, item.z]}>
          <boxGeometry args={[web + 0.2, depth * 0.7, 0.03]} />
          <meshStandardMaterial
            color={item.hoop ? "#A67C52" : "#8B5A2B"}
            metalness={0.4}
            roughness={0.55}
            transparent
            opacity={0.55}
          />
        </mesh>
      ))}
    </group>
  );
}

export function SpecBeam({
  spec,
  compact = false,
  bodyColor = "#9aa0aa",
  highlighted = false,
  onClick,
  mark,
  selectedId,
  onSelectHardware,
  measurementMap = {},
  anomalies = [],
  pickPos,
  onPick,
}) {
  const geo = spec.geometry;
  const length = geo.length_ft;
  const depth = inchesToFt(geo.depth_in);
  const hardware = compact
    ? (spec.hardware || []).filter((item) => COMPACT_HARDWARE_KINDS.includes(item.kind))
    : (spec.hardware || []);

  return (
    <group
      onClick={(e) => {
        e.stopPropagation();
        if (onClick) onClick(e);
      }}
    >
      <BeamBody geo={geo} onPick={onPick || onClick} bodyColor={bodyColor} highlighted={highlighted} />
      {!compact && (spec.strands || []).map((s) => (
        <StrandRun key={s.id} strand={s} length={length} holdDowns={spec.hold_downs} />
      ))}
      {!compact && <Stirrups zones={spec.stirrup_zones} geo={geo} />}
      {hardware.map((item) => (
        <HardwareMesh
          key={item.id}
          item={item}
          geo={geo}
          selected={selectedId === item.id}
          measurement={measurementMap[item.id]}
          onSelect={onSelectHardware}
        />
      ))}
      {pickPos && (
        <mesh position={[pickPos.x, pickPos.y, pickPos.z]}>
          <sphereGeometry args={[0.1, 12, 12]} />
          <meshBasicMaterial color="#2979FF" />
        </mesh>
      )}
      {(anomalies || []).map((a) => {
        const color = a.severity === "major" ? "#FF3366" : a.severity === "moderate" ? "#FFD600" : "#2979FF";
        return (
          <mesh key={a.id} position={[a.position?.z || 0.4, (a.position?.y || 1) * 0.3, Math.min(Math.max(a.position?.x || 0, 0), length)]}>
            <sphereGeometry args={[0.12, 12, 12]} />
            <meshBasicMaterial color={color} />
          </mesh>
        );
      })}
      <MarkedEndMarker
        depthFt={depth}
        widthFt={inchesToFt(geo.top_flange_width_in || geo.width_in)}
        compact={compact}
        label={compact ? "ME" : (spec.marked_end_id || "MARKED END")}
        sublabel={compact ? (mark || spec.beam_mark || "") : ""}
      />
      <UnmarkedEndMarker
        depthFt={depth}
        widthFt={inchesToFt(geo.top_flange_width_in || geo.width_in)}
        z={Number(length) || 0}
        compact={compact}
        label={spec.unmarked_end_id || "UE"}
      />
    </group>
  );
}

function SpecScene({ spec, anomalies, pickPos, onPick, selectedId, onSelectHardware, measurementMap, bodyColor, compact }) {
  return (
    <SpecBeam
      spec={spec}
      compact={compact}
      bodyColor={bodyColor}
      anomalies={anomalies}
      pickPos={pickPos}
      onPick={onPick}
      selectedId={selectedId}
      onSelectHardware={onSelectHardware}
      measurementMap={measurementMap}
    />
  );
}

function FallbackBeam({ twinType, length, pickPos, onPick }) {
  const scaled = Math.max(4, Math.min(length / 10, 16));
  const geo = {
    twin_type: twinType,
    length_ft: scaled,
    depth_in: 36,
    width_in: 18,
    top_flange_width_in: 12,
    top_flange_thick_in: 6,
    bot_flange_width_in: 18,
    bot_flange_thick_in: 6,
    web_thick_in: 6,
  };
  return (
    <group position={[0, 0, -scaled / 2]}>
      <BeamBody geo={geo} onPick={onPick} />
      <MarkedEndMarker depthFt={inchesToFt(geo.depth_in)} widthFt={inchesToFt(geo.top_flange_width_in)} label="ME" />
      <UnmarkedEndMarker depthFt={inchesToFt(geo.depth_in)} widthFt={inchesToFt(geo.top_flange_width_in)} z={scaled} label="UE" />
      {pickPos && (
        <mesh position={[pickPos.x, pickPos.y, pickPos.z + scaled / 2]}>
          <sphereGeometry args={[0.1, 12, 12]} />
          <meshBasicMaterial color="#2979FF" />
        </mesh>
      )}
    </group>
  );
}

export default function BeamViewer({
  spec = null,
  twinType = "i_beam",
  length = 10,
  anomalies = [],
  onPick,
  pickPos,
  selectedId,
  onSelectHardware,
  measurements = [],
  compact = false,
  bodyColor = "#9aa0aa",
}) {
  const [localPick, setLocalPick] = useState(null);
  const marker = pickPos || localPick;
  const measurementMap = useMemo(() => {
    const map = {};
    (measurements || []).forEach((m) => { map[m.element_id] = m; });
    return map;
  }, [measurements]);

  const handlePick = (point) => {
    setLocalPick(point);
    if (onPick) onPick(point);
  };

  const lengthFt = spec?.geometry?.length_ft || Math.max(4, Math.min(length / 10, 16));
  const depthFt = spec ? inchesToFt(spec.geometry.depth_in) : 3;
  const camZ = Math.max(8, lengthFt * 0.45);
  const camY = Math.max(4, depthFt * 3.5);
  const camX = Math.max(6, depthFt * 4);

  return (
    <div style={{ width: "100%", height: "100%", background: "#0A0C10" }} data-testid="beam-3d-canvas">
      <Canvas camera={{ position: [camX, camY, camZ], fov: 42 }} shadows>
        <Suspense fallback={<group />}>
          <color attach="background" args={["#0A0C10"]} />
          <ambientLight intensity={0.95} />
          <directionalLight position={[10, 12, 8]} intensity={0.7} />
          <directionalLight position={[-8, 6, -6]} intensity={0.35} />
          {spec ? (
            <SpecScene
              spec={spec}
              compact={compact}
              bodyColor={bodyColor}
              anomalies={anomalies}
              pickPos={marker}
              onPick={handlePick}
              selectedId={selectedId}
              onSelectHardware={onSelectHardware}
              measurementMap={measurementMap}
            />
          ) : (
            <FallbackBeam twinType={twinType} length={length} pickPos={marker} onPick={handlePick} />
          )}
          <gridHelper args={[Math.max(40, lengthFt + 10), 40, "#1C2230", "#12151C"]} position={[0, -0.02, lengthFt / 2]} />
          <ContactShadows position={[0, -0.02, lengthFt / 2]} opacity={0.3} scale={Math.max(40, lengthFt + 10)} blur={2.2} far={10} />
          <OrbitControls target={[0, depthFt / 2, lengthFt / 2]} enablePan enableZoom enableRotate makeDefault />
        </Suspense>
      </Canvas>
    </div>
  );
}
