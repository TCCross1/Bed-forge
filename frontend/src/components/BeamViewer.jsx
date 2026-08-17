import React, { useRef, useMemo, useState, Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Environment, Html, ContactShadows } from "@react-three/drei";
import * as THREE from "three";

function IBeamGeometry({ length = 8 }) {
  const shape = useMemo(() => {
    const s = new THREE.Shape();
    const w = 1.2;
    const fh = 0.35;
    const wt = 0.35;
    const h = 2.2;
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
    const w = 1.5;
    const h = 1.1;
    s.moveTo(-w, 0);
    s.lineTo(w, 0);
    s.lineTo(w, h);
    s.lineTo(-w, h);
    s.closePath();
    const hole = new THREE.Path();
    const iw = w - 0.25;
    const ih = h - 0.25;
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

function severityColor(severity) {
  if (severity === "major") return "#FF3366";
  if (severity === "moderate") return "#FFD600";
  return "#2979FF";
}

function Beam({ twinType, length, anomalies, pickPos, onPick }) {
  const mesh = useRef();

  return (
    <group position={[0, -1, -length / 2]}>
      <mesh
        ref={mesh}
        castShadow
        receiveShadow
        onClick={(e) => {
          e.stopPropagation();
          if (onPick) onPick(e.point, e.face);
        }}
        onPointerOver={() => {
          document.body.style.cursor = "crosshair";
        }}
        onPointerOut={() => {
          document.body.style.cursor = "auto";
        }}
      >
        {twinType === "box_beam" ? (
          <BoxBeamGeometry length={length} />
        ) : (
          <IBeamGeometry length={length} />
        )}
        <meshStandardMaterial color="#9aa0aa" roughness={0.85} metalness={0.05} />
      </mesh>

      {pickPos && (
        <mesh position={[pickPos.x, pickPos.y + 1, pickPos.z + length / 2]}>
          <sphereGeometry args={[0.12, 16, 16]} />
          <meshBasicMaterial color="#2979FF" />
        </mesh>
      )}

      {(anomalies || []).map((a) => {
        const z = Math.min(Math.max((a.position?.x || 0) / 10, 0), length);
        const y = (a.position?.y || 1) * 0.6;
        const x = a.position?.z || 1.25;
        const color = severityColor(a.severity);
        return (
          <mesh key={a.id} position={[x, y, z]}>
            <sphereGeometry args={[0.14, 16, 16]} />
            <meshBasicMaterial color={color} />
            <Html distanceFactor={12} position={[0, 0.3, 0]}>
              <div
                style={{
                  background: "#0F1218",
                  border: `1px solid ${color}`,
                  color,
                  fontSize: 9,
                  padding: "2px 5px",
                  fontFamily: "JetBrains Mono, monospace",
                  whiteSpace: "nowrap",
                  transform: "translateX(-50%)",
                }}
              >
                {(a.type || "MARK").toUpperCase()}
              </div>
            </Html>
          </mesh>
        );
      })}
    </group>
  );
}

export default function BeamViewer({ twinType = "i_beam", length = 10, anomalies = [], onPick, pickPos }) {
  const scaled = Math.max(4, Math.min(length / 10, 16));
  const [localPick, setLocalPick] = useState(null);
  const marker = pickPos || localPick;

  const handlePick = (point) => {
    setLocalPick(point);
    if (onPick) onPick(point);
  };

  return (
    <div style={{ width: "100%", height: "100%", background: "#0A0C10" }} data-testid="beam-3d-canvas">
      <Canvas camera={{ position: [7, 4, 9], fov: 45 }} shadows>
        <Suspense fallback={null}>
          <color attach="background" args={["#0A0C10"]} />
          <ambientLight intensity={0.95} />
          <directionalLight position={[8, 10, 6]} intensity={0.65} />
          <directionalLight position={[-8, 6, -6]} intensity={0.35} />
          <Beam
            twinType={twinType}
            length={scaled}
            anomalies={anomalies}
            pickPos={marker}
            onPick={handlePick}
          />
          <gridHelper args={[40, 40, "#1C2230", "#12151C"]} position={[0, -1.05, 0]} />
          <ContactShadows position={[0, -1.05, 0]} opacity={0.35} scale={40} blur={2.2} far={8} />
          <Environment preset="warehouse" />
          <OrbitControls enablePan enableZoom enableRotate makeDefault />
        </Suspense>
      </Canvas>
    </div>
  );
}
