import React, { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { SpecBeam } from "./BeamViewer";
import { TwinBadge } from "./MarkedEndMarker";
import { fallbackSpec, statusColor } from "../lib/bedLayout";

function BedStructure({ lengthFt, headerLabel, bulkheadLabel }) {
  const width = 8;
  return (
    <group>
      <mesh position={[0, -0.25, lengthFt / 2]} receiveShadow>
        <boxGeometry args={[width, 0.5, lengthFt]} />
        <meshStandardMaterial color="#161B24" metalness={0.15} roughness={0.82} />
      </mesh>
      <mesh position={[0, 2.2, 0.6]}>
        <boxGeometry args={[width + 1.2, 4.4, 1.2]} />
        <meshStandardMaterial color="#2979FF" metalness={0.35} roughness={0.4} emissive="#2979FF" emissiveIntensity={0.12} />
      </mesh>
      <mesh position={[0, 2.2, lengthFt - 0.6]}>
        <boxGeometry args={[width + 1.2, 4.4, 1.2]} />
        <meshStandardMaterial color="#C9A227" metalness={0.45} roughness={0.35} emissive="#C9A227" emissiveIntensity={0.1} />
      </mesh>
      <TwinBadge text={headerLabel || "HEADER / LIVE END"} color="#2979FF" compact position={[0, 5.1, 0.6]} />
      <TwinBadge text={bulkheadLabel || "BULKHEAD / DEAD END"} color="#C9A227" compact position={[0, 5.1, lengthFt - 0.6]} />
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

function IntermediateBulkhead({ z }) {
  return (
    <mesh position={[0, 1.4, z]}>
      <boxGeometry args={[7.2, 2.8, 0.45]} />
      <meshStandardMaterial color="#3A4254" metalness={0.2} roughness={0.7} />
    </mesh>
  );
}

function BedScene({ layout, onSelectBeam }) {
  const bed = layout.bed || {};
  const lengthFt = Number(bed.length_ft) || 300;
  const rows = layout.assignments || [];
  return (
    <group>
      <BedStructure
        lengthFt={lengthFt}
        headerLabel={bed.header_label}
        bulkheadLabel={bed.bulkhead_label}
      />
      {rows.map((row) => (
        <React.Fragment key={row.id}>
          <LaidBeam
            row={row}
            active={layout.active_beam_id && row.beam_id === layout.active_beam_id}
            onSelect={onSelectBeam}
          />
          {row.gap_after_ft > 0 && (
            <IntermediateBulkhead z={(row.end_station_ft || 0) + (row.gap_after_ft || 0) / 2} />
          )}
        </React.Fragment>
      ))}
    </group>
  );
}

export default function BedViewer({ layout, onSelectBeam, height = 420 }) {
  const lengthFt = Number(layout?.bed?.length_ft) || 300;
  const camZ = Math.max(28, lengthFt * 0.12);
  const camX = 28;
  return (
    <div style={{ width: "100%", height, background: "#0A0C10" }} data-testid="bed-twin-canvas">
      <Canvas
        camera={{ position: [camX, 18, camZ], fov: 42 }}
        dpr={[1, 1.5]}
        gl={{ antialias: true, powerPreference: "high-performance" }}
      >
        <Suspense fallback={null}>
          <color attach="background" args={["#0A0C10"]} />
          <ambientLight intensity={0.9} />
          <directionalLight position={[40, 50, 20]} intensity={0.7} />
          <directionalLight position={[-20, 20, -10]} intensity={0.25} />
          {layout && <BedScene layout={layout} onSelectBeam={onSelectBeam} />}
          <gridHelper args={[Math.max(80, lengthFt + 20), 40, "#1C2230", "#12151C"]} position={[0, -0.02, lengthFt / 2]} />
          <OrbitControls target={[0, 2, lengthFt / 2]} enablePan enableZoom enableRotate makeDefault />
        </Suspense>
      </Canvas>
    </div>
  );
}
