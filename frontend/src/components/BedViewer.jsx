import React, { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { SpecBeam } from "./BeamViewer";
import { TwinBadge } from "./MarkedEndMarker";
import { fallbackSpec, plannerLaneWidthFt, plannerTwinType, statusColor } from "../lib/bedLayout";

function BedStructure({ lengthFt, widthFt }) {
  const width = Math.max(16, Number(widthFt) || 16);
  const headerDepth = 3.6;
  const bulkheadDepth = 3.2;
  const railH = 1.15;
  const railT = 0.48;
  return (
    <group>
      <mesh position={[0, -0.18, lengthFt / 2]} receiveShadow>
        <boxGeometry args={[width, 0.55, lengthFt]} />
        <meshStandardMaterial color="#3A4658" metalness={0.12} roughness={0.72} />
      </mesh>
      <mesh position={[0, 0.14, lengthFt / 2]}>
        <boxGeometry args={[Math.max(4, width * 0.28), 0.08, lengthFt]} />
        <meshStandardMaterial color="#2979FF" emissive="#2979FF" emissiveIntensity={0.22} />
      </mesh>
      <mesh position={[-(width / 2) + railT / 2, railH / 2, lengthFt / 2]}>
        <boxGeometry args={[railT, railH, lengthFt]} />
        <meshStandardMaterial color="#8FA1B6" metalness={0.3} roughness={0.45} />
      </mesh>
      <mesh position={[(width / 2) - railT / 2, railH / 2, lengthFt / 2]}>
        <boxGeometry args={[railT, railH, lengthFt]} />
        <meshStandardMaterial color="#8FA1B6" metalness={0.3} roughness={0.45} />
      </mesh>
      <mesh position={[0, 0.22, 5]}>
        <boxGeometry args={[width * 0.96, 0.14, 10]} />
        <meshStandardMaterial color="#2979FF" emissive="#2979FF" emissiveIntensity={0.5} />
      </mesh>
      <mesh position={[0, 2.35, headerDepth / 2]}>
        <boxGeometry args={[width + 2.4, 4.7, headerDepth]} />
        <meshStandardMaterial color="#2979FF" metalness={0.35} roughness={0.36} emissive="#2979FF" emissiveIntensity={0.24} />
      </mesh>
      <mesh position={[0, 2.15, lengthFt - bulkheadDepth / 2]}>
        <boxGeometry args={[width + 1.6, 4.3, bulkheadDepth]} />
        <meshStandardMaterial color="#C9A227" metalness={0.48} roughness={0.32} emissive="#C9A227" emissiveIntensity={0.16} />
      </mesh>
      <TwinBadge text="MARKED END · HEADER" color="#2979FF" position={[0, 5.6, headerDepth / 2]} />
      <TwinBadge text="BULKHEAD · DEAD END" color="#C9A227" position={[0, 5.2, lengthFt - bulkheadDepth / 2]} />
    </group>
  );
}

function LaidBeam({ row, active, onSelect }) {
  const spec = row.spec || fallbackSpec(row.beam || { length_ft: row.length_ft, twin_type: "i_beam", mark: row.beam?.mark });
  const length = spec.geometry.length_ft;
  const towardBulkhead = row.marked_end_toward === "bulkhead";
  const station = Number(row.station_ft) || 0;
  const color = statusColor(row.production_status);
  return (
    <group
      position={[0, 0.28, towardBulkhead ? station + length : station]}
      rotation={[0, towardBulkhead ? Math.PI : 0, 0]}
    >
      <SpecBeam
        spec={spec}
        compact
        bodyColor={color}
        highlighted={active}
        mark={(row.beam && row.beam.mark) || row.beam_id}
        onClick={() => onSelect && onSelect(row)}
      />
    </group>
  );
}

function IntermediateBulkhead({ z, widthFt }) {
  const width = Math.max(14, Number(widthFt) || 16);
  return (
    <mesh position={[0, 1.6, z]}>
      <boxGeometry args={[width * 0.88, 3.2, 0.55]} />
      <meshStandardMaterial color="#3A4254" metalness={0.2} roughness={0.7} />
    </mesh>
  );
}

function BedScene({ layout, onSelectBeam }) {
  const bed = layout.bed || {};
  const lengthFt = Number(bed.length_ft) || 300;
  const widthFt = plannerLaneWidthFt(plannerTwinType(layout));
  const rows = layout.assignments || [];
  return (
    <group>
      <BedStructure lengthFt={lengthFt} widthFt={widthFt} />
      {rows.map((row) => (
        <React.Fragment key={row.id}>
          <LaidBeam
            row={row}
            active={layout.active_beam_id && row.beam_id === layout.active_beam_id}
            onSelect={onSelectBeam}
          />
          {row.gap_after_ft > 0 && (
            <IntermediateBulkhead
              z={(row.end_station_ft || 0) + (row.gap_after_ft || 0) / 2}
              widthFt={widthFt}
            />
          )}
        </React.Fragment>
      ))}
    </group>
  );
}

export default function BedViewer({ layout, onSelectBeam, height = 420 }) {
  const laneW = plannerLaneWidthFt(plannerTwinType(layout));
  const viewLen = 90;
  const camX = Math.max(laneW * 1.35, 22);
  const camY = 22;
  const camZ = -18;
  return (
    <div style={{ width: "100%", height, background: "#0A0C10" }} data-testid="bed-twin-canvas">
      <Canvas
        camera={{ position: [camX, camY, camZ], fov: 36, near: 0.2, far: 115 }}
        dpr={[1, 1.5]}
        gl={{ antialias: true, powerPreference: "high-performance" }}
      >
        <Suspense fallback={null}>
          <color attach="background" args={["#0A0C10"]} />
          <ambientLight intensity={1.0} />
          <directionalLight position={[30, 50, 10]} intensity={0.85} />
          <directionalLight position={[-18, 22, -20]} intensity={0.3} />
          {layout && <BedScene layout={layout} onSelectBeam={onSelectBeam} />}
          <gridHelper args={[100, 20, "#1C2230", "#12151C"]} position={[0, -0.02, viewLen * 0.45]} />
          <OrbitControls target={[0, 1.1, 32]} enablePan enableZoom enableRotate makeDefault />
        </Suspense>
      </Canvas>
    </div>
  );
}
