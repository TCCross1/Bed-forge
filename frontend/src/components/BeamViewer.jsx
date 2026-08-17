import React, { useRef, useMemo, Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Environment, Html } from "@react-three/drei";
import * as THREE from "three";

// I-beam cross-section (approx AASHTO girder) extruded along length
function IBeamGeometry({ length = 8 }) {
  const shape = useMemo(() => {
    const s = new THREE.Shape();
    const w = 1.2, fh = 0.35, wt = 0.35, h = 2.2;
    s.moveTo(-w, 0);
    s.lineTo(w, 0);
    s.lineTo(w, fh);
    s.lineTo(wt, fh + 0.3);
    s.lineTo(wt, h - fh - 0.3);
    s.lineTo(w * 0.75, h - fh);
    s.lineTo(w * 0.75, h);
    s.lineTo(-w * 0.75, h);
    s.lineTo(-w * 0.75, h - fh);
    s.lineTo(-wt, h - fh - 0.3);
    s.lineTo(-wt, fh + 0.3);
    s.lineTo(-w, fh);
    s.closePath();
    return s;
  }, []);
  const geo = useMemo(
    () => new THREE.ExtrudeGeometry(shape, { depth: length, bevelEnabled: false }),
    [shape, length]
  );
  return <primitive object={geo} attach="geometry" />;
}

function BoxBeamGeometry({ length = 8 }) {
  const shape = useMemo(() => {
    const s = new THREE.Shape();
    const w = 1.5, h = 1.1;
    s.moveTo(-w, 0);
    s.lineTo(w, 0);
    s.lineTo(w, h);
    s.lineTo(-w, h);
    s.closePath();
    const hole = new THREE.Path();
    const iw = w - 0.25, ih = h - 0.25;
    hole.moveTo(-iw, 0.25);
    hole.lineTo(iw, 0.25);
    hole.lineTo(iw, ih);
    hole.lineTo(-iw, ih);
    hole.closePath();
    s.holes.push(hole);
    return s;
  }, []);
  const geo = useMemo(
    () => new THREE.ExtrudeGeometry(shape, { depth: length, bevelEnabled: false }),
    [shape, length]
  );
  return <primitive object={geo} attach="geometry" />;
}

function Beam({ twinType, length, anomalies, onPick }) {
  const mesh = useRef();
  return (
    <group position={[0, -1, -length / 2]}>
      <mesh
        ref={mesh}
        castShadow
        onClick={(e) => {
          e.stopPropagation();
          if (onPick) onPick(e.point);
        }}
      >
        {twinType === "box_beam" ? (
          <BoxBeamGeometry length={length} />
        ) : (
          <IBeamGeometry length={length} />
        )}
        <meshStandardMaterial color="#9aa0aa" roughness={0.85} metalness={0.05} />
      </mesh>

      {(anomalies || []).map((a) => {
        const z = Math.min(Math.max((a.position?.x || 0) / 10, 0), length);
        const y = (a.position?.y || 1) * 0.6;
        const color =
          a.severity === "major" ? "#FF3366" : a.severity === "moderate" ? "#FFD600" : "#2979FF";
        return (
          <mesh key={a.id} position={[1.25, y, z]}>
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
      })}
    </group>
  );
}

export default function BeamViewer({ twinType = "i_beam", length = 10, anomalies = [], onPick }) {
  const scaled = Math.max(4, Math.min(length / 10, 16));
  return (
    <div style={{ width: "100%", height: "100%", background: "#0A0C10" }} data-testid="beam-3d-canvas">
      <Canvas camera={{ position: [7, 4, 9], fov: 45 }} shadows>
        <Suspense fallback={null}>
          <ambientLight intensity={0.9} />
          <directionalLight position={[8, 10, 6]} intensity={0.7} />
          <directionalLight position={[-8, 6, -6]} intensity={0.4} />
          <Beam twinType={twinType} length={scaled} anomalies={anomalies} onPick={onPick} />
          <gridHelper args={[40, 40, "#222631", "#151922"]} position={[0, -1.05, 0]} />
          <Environment preset="warehouse" />
          <OrbitControls enablePan enableZoom enableRotate makeDefault />
        </Suspense>
      </Canvas>
    </div>
  );
}
