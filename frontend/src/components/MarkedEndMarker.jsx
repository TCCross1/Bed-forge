import React, { useEffect, useMemo } from "react";
import * as THREE from "three";
import { Billboard } from "@react-three/drei";

const ME = "#2979FF";
const UE = "#C9A227";

function finite(n, fallback) {
  const v = Number(n);
  return Number.isFinite(v) ? v : fallback;
}

function TwinBadge({ text, color = ME, position = [0, 0, 0], compact = false }) {
  const label = String(text || "ME");
  const texture = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 1024;
    canvas.height = 192;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#0A0C10";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = color;
    ctx.lineWidth = 10;
    ctx.strokeRect(8, 8, canvas.width - 16, canvas.height - 16);
    ctx.fillStyle = color;
    ctx.font = "700 84px 'JetBrains Mono', 'IBM Plex Mono', monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, canvas.width / 2, canvas.height / 2 + 4);
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.needsUpdate = true;
    return tex;
  }, [color, label]);

  useEffect(() => () => texture.dispose(), [texture]);

  const w = compact
    ? Math.min(3.2, 0.2 * label.length + 0.9)
    : Math.min(5.4, 0.26 * label.length + 1.15);
  const h = compact ? 0.4 : 0.52;
  return (
    <Billboard follow position={[finite(position[0], 0), finite(position[1], 0), finite(position[2], 0)]}>
      <mesh renderOrder={20} raycast={() => {}}>
        <planeGeometry args={[w, h]} />
        <meshBasicMaterial map={texture} transparent depthTest={false} />
      </mesh>
    </Billboard>
  );
}

/**
 * Always-on marked-end cue. Local +Z is along the beam toward the unmarked end.
 * `facing` is the world-local Z direction pointing OUT of the marked end (-1 = -Z).
 */
export function MarkedEndMarker({
  depthFt,
  widthFt = 1.6,
  z = 0,
  facing = -1,
  compact = false,
  label = "ME",
  sublabel = "",
  stripeFt,
}) {
  const depth = Math.max(0.4, finite(depthFt, 3));
  const width = Math.max(0.8, finite(widthFt, 1.6));
  const station = finite(z, 0);
  const dir = facing >= 0 ? 1 : -1;
  const plateW = Math.max(width, compact ? 1.35 : 1.6);
  const coneLen = compact ? 0.95 : 1.25;
  const coneRad = compact ? 0.28 : 0.36;
  const stripeLen = stripeFt == null ? (compact ? 2.2 : 3.2) : Math.max(0, finite(stripeFt, 0));
  const badge = sublabel ? `${sublabel} · ${label}` : label;
  return (
    <group position={[0, 0, station]}>
      <mesh position={[0, depth / 2, dir * 0.07]}>
        <boxGeometry args={[plateW + 0.18, depth + 0.2, 0.14]} />
        <meshStandardMaterial color={ME} emissive={ME} emissiveIntensity={0.62} metalness={0.25} roughness={0.35} />
      </mesh>
      {stripeLen > 0 && (
        <mesh position={[0, depth + 0.05, dir < 0 ? stripeLen / 2 : -stripeLen / 2]}>
          <boxGeometry args={[Math.min(plateW * 0.72, 1.35), 0.07, stripeLen]} />
          <meshStandardMaterial color={ME} emissive={ME} emissiveIntensity={0.5} />
        </mesh>
      )}
      <mesh
        position={[0, depth + (compact ? 0.42 : 0.55), dir * (compact ? 0.9 : 1.15)]}
        rotation={[dir > 0 ? Math.PI / 2 : -Math.PI / 2, 0, 0]}
      >
        <coneGeometry args={[coneRad, coneLen, 8]} />
        <meshStandardMaterial color={ME} emissive={ME} emissiveIntensity={0.7} metalness={0.2} roughness={0.3} />
      </mesh>
      <TwinBadge
        text={badge}
        color={ME}
        compact={compact}
        position={[0, depth + (compact ? 1.05 : 1.25), dir * 0.15]}
      />
    </group>
  );
}

export function UnmarkedEndMarker({ depthFt, widthFt = 1.6, z = 0, compact = false, label = "UE" }) {
  if (compact) return null;
  const depth = Math.max(0.4, finite(depthFt, 3));
  const plateW = Math.max(finite(widthFt, 1.6), 1.5);
  return (
    <group position={[0, 0, finite(z, 0)]}>
      <mesh position={[0, depth / 2, 0.06]}>
        <boxGeometry args={[plateW + 0.08, depth + 0.08, 0.1]} />
        <meshStandardMaterial color={UE} emissive={UE} emissiveIntensity={0.28} metalness={0.35} roughness={0.4} />
      </mesh>
      <TwinBadge text={label} color={UE} position={[0, depth + 0.85, 0]} />
    </group>
  );
}

export { TwinBadge };
