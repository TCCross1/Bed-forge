import React, { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { plannerLaneWidthFt, plannerTwinType, statusColor } from "../lib/bedLayout";
import { bedState } from "../lib/constants";
import { MarkedEndMarker, TwinBadge } from "./MarkedEndMarker";

const BED_SPACING = 30;

function SimpleBeam({ row, x, active, onSelect }) {
  const length = Number(row.length_ft) || 80;
  const station = Number(row.station_ft) || 8;
  const color = statusColor(row.production_status);
  const towardBulkhead = row.marked_end_toward === "bulkhead";
  const meLocalZ = towardBulkhead ? length / 2 : -length / 2;
  const facing = towardBulkhead ? 1 : -1;
  const mark = (row.beam && row.beam.mark) || "BEAM";
  return (
    <group
      position={[x, 1.1, station + length / 2]}
      onClick={(e) => {
        e.stopPropagation();
        if (onSelect) onSelect(row);
      }}
    >
      <mesh>
        <boxGeometry args={[2.4, 2.0, length]} />
        <meshStandardMaterial
          color={color}
          emissive={active ? "#FFD600" : color}
          emissiveIntensity={active ? 0.45 : 0.08}
          roughness={0.55}
        />
      </mesh>
      <group position={[0, -1.0, 0]}>
        <MarkedEndMarker
          depthFt={2.0}
          widthFt={2.4}
          z={meLocalZ}
          facing={facing}
          compact
          label="ME"
          sublabel={mark}
        />
      </group>
    </group>
  );
}

function PlantBed({ layout, index, onSelectBed, onSelectBeam }) {
  const bed = layout.bed || {};
  const lengthFt = Number(bed.length_ft) || 300;
  const width = plannerLaneWidthFt(plannerTwinType(layout));
  const x = (index - 3.5) * BED_SPACING;
  const st = bedState(bed.status);
  const headerDepth = 3.4;
  return (
    <group
      onClick={(e) => {
        e.stopPropagation();
        if (onSelectBed) onSelectBed(bed);
      }}
    >
      <mesh position={[x, -0.22, lengthFt / 2]}>
        <boxGeometry args={[width, 0.44, lengthFt]} />
        <meshStandardMaterial color="#161B24" />
      </mesh>
      <mesh position={[x, 0.08, 3.5]}>
        <boxGeometry args={[width * 0.9, 0.1, 7]} />
        <meshStandardMaterial color="#2979FF" emissive="#2979FF" emissiveIntensity={0.28} />
      </mesh>
      <mesh position={[x, 2.2, headerDepth / 2]}>
        <boxGeometry args={[width + 2.2, 4.4, headerDepth]} />
        <meshStandardMaterial color="#2979FF" emissive="#2979FF" emissiveIntensity={0.14} />
      </mesh>
      <mesh position={[x, 2.0, lengthFt - 1.6]}>
        <boxGeometry args={[width + 1.6, 4.0, 3.2]} />
        <meshStandardMaterial color="#C9A227" emissive="#C9A227" emissiveIntensity={0.08} />
      </mesh>
      <TwinBadge text={`BED ${bed.bed_number} · MARKED END`} color="#2979FF" position={[x, 5.4, headerDepth / 2]} />
      <TwinBadge text={st.label || `BED ${bed.bed_number}`} color={st.color} compact position={[x, 5.8, 14]} />
      {(layout.assignments || []).map((row) => (
        <SimpleBeam
          key={row.id}
          row={row}
          x={x}
          active={layout.active_beam_id && row.beam_id === layout.active_beam_id}
          onSelect={onSelectBeam}
        />
      ))}
    </group>
  );
}

export default function PlantFloor({ plant, onSelectBed, onSelectBeam, height = 520 }) {
  const longest = Math.max(300, ...((plant?.beds || []).map((b) => Number(b.bed?.length_ft) || 300)));
  return (
    <div style={{ width: "100%", height, background: "#0A0C10" }} data-testid="plant-floor-canvas">
      <Canvas
        camera={{ position: [0, 110, -48], fov: 40 }}
        dpr={[1, 1.5]}
        gl={{ antialias: true, powerPreference: "high-performance" }}
      >
        <Suspense fallback={null}>
          <color attach="background" args={["#0A0C10"]} />
          <ambientLight intensity={0.95} />
          <directionalLight position={[30, 80, 10]} intensity={0.7} />
          {(plant?.beds || []).map((layout, index) => (
            <PlantBed
              key={layout.bed?.id || index}
              layout={layout}
              index={index}
              onSelectBed={onSelectBed}
              onSelectBeam={onSelectBeam}
            />
          ))}
          <gridHelper args={[Math.max(240, longest + 40), 36, "#1C2230", "#12151C"]} position={[0, 0, longest / 2]} />
          <OrbitControls target={[0, 0, longest / 2]} enablePan enableZoom enableRotate makeDefault />
        </Suspense>
      </Canvas>
    </div>
  );
}
