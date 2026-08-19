import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../lib/api";
import Layout, { PageHeader } from "../components/Layout";
import BeamTwinViewer, { BedTwinViewer } from "../components/BeamViewer";
import { bedState, qcState } from "../lib/constants";
import { toast } from "sonner";
import { Layers3, Loader2, MapPin, Ruler, ScanLine, Box, Construction, Lock, AlertTriangle } from "lucide-react";

function SpecRows({ spec }) {
  return Object.entries(spec || {}).map(([key, value]) => (
    <div key={key} className="flex items-center justify-between gap-3 text-xs font-mono">
      <span className="text-muted-foreground uppercase tracking-wider">{key.replace(/_/g, " ")}</span>
      <span className="text-white text-right">{typeof value === "object" ? JSON.stringify(value) : String(value)}</span>
    </div>
  ));
}

function stationList(items = []) {
  return items.length ? items.map((item) => `${Number(item.x_ft || 0).toFixed(1)}'`).join(" · ") : "—";
}

const LAYER_OPTIONS = [
  ["dimensions", "Dimensions"],
  ["hardware", "Hardware"],
  ["strands", "Strands"],
  ["stirrups", "Stirrups"],
  ["anomalies", "Anomalies"],
];

function LayerChip({ active, label, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`min-h-9 px-3 rounded-sm border text-[11px] font-mono uppercase tracking-wider transition-colors duration-100 ${
        active ? "border-primary bg-primary/15 text-primary" : "border-border bg-background text-muted-foreground hover:border-primary/60 hover:text-white"
      }`}
    >
      {label}
    </button>
  );
}

export default function DigitalTwin() {
  const [params] = useSearchParams();
  const [beams, setBeams] = useState([]);
  const [beds, setBeds] = useState([]);
  const [selectedId, setSelectedId] = useState(params.get("beam") || "");
  const [beam, setBeam] = useState(null);
  const [bedTwin, setBedTwin] = useState(null);
  const [selectedBedId, setSelectedBedId] = useState("");
  const [selectedHardware, setSelectedHardware] = useState(null);
  const [pickPos, setPickPos] = useState(null);
  const [showCallouts, setShowCallouts] = useState(true);
  const [layers, setLayers] = useState({
    dimensions: true,
    hardware: false,
    strands: true,
    stirrups: true,
    anomalies: true,
  });
  const [mode, setMode] = useState("beam");
  const [form, setForm] = useState({ type: "crack", severity: "minor", note: "", length_in: 0 });

  useEffect(() => {
    api.get("/beams").then((r) => {
      setBeams(r.data);
      setSelectedId((current) => current || r.data[0]?.id || "");
      setSelectedBedId((current) => current || r.data[0]?.bed_id || "");
    });
    api.get("/beds").then((r) => setBeds(r.data));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    api.get(`/beams/${selectedId}`).then((r) => {
      setBeam(r.data);
      setSelectedBedId(r.data.bed_id);
    });
  }, [selectedId]);

  useEffect(() => {
    if (!selectedBedId) return;
    api.get(`/beds/${selectedBedId}/twin`).then((r) => setBedTwin(r.data));
  }, [selectedBedId, selectedId]);

  const saveAnomaly = async () => {
    if (!pickPos || !selectedId) {
      toast.error("Tap the beam shell to set the anomaly location first");
      return;
    }
    try {
      await api.post("/anomalies", {
        beam_id: selectedId,
        type: form.type,
        severity: form.severity,
        note: form.note,
        length_in: parseFloat(form.length_in) || 0,
        position: { x: +pickPos.z.toFixed(1), y: +pickPos.y.toFixed(2), z: +pickPos.x.toFixed(2) },
      });
      toast.success("Anomaly captured on twin");
      setPickPos(null);
      setForm({ type: "crack", severity: "minor", note: "", length_in: 0 });
      const beamRes = await api.get(`/beams/${selectedId}`);
      setBeam(beamRes.data);
      const bedRes = await api.get(`/beds/${beamRes.data.bed_id}/twin`);
      setBedTwin(bedRes.data);
    } catch {
      toast.error("Failed to save anomaly");
    }
  };

  const selectedBed = useMemo(() => beds.find((item) => item.id === selectedBedId), [beds, selectedBedId]);
  const beamState = beam ? qcState(beam.qc_state) : null;
  const bedStatus = selectedBed ? bedState(selectedBed.status) : null;
  const blueprint = beam?.product_type?.blueprint || {};
  const blueprintSource = beam?.blueprint_source || { status: "legacy_seed" };
  const draftTwinBlocked = blueprintSource.status === "draft";
  const strandCount = (blueprint.strand_pattern?.rows || []).reduce((sum, row) => sum + (row.count || 0), 0);
  const stirrupCount = (() => {
    const stirrups = blueprint.stirrups || {};
    const spacingFt = (stirrups.spacing_in || 24) / 12;
    const startFt = stirrups.start_ft ?? 0;
    const endFt = stirrups.end_ft ?? beam?.length_ft ?? 0;
    if (!spacingFt || endFt <= startFt) return 0;
    return Math.floor((endFt - startFt) / spacingFt) + 1;
  })();
  const featureCounts = [
    ["Lift loops", blueprint.lift_loops?.length || 0],
    ["Inserts", blueprint.inserts?.length || 0],
    ["Tubes", blueprint.tubes?.length || 0],
    ["Tie-rods", blueprint.tie_rod_openings?.length || 0],
    ["Drain holes", blueprint.drain_holes?.length || 0],
    ["Hold-downs", blueprint.hold_downs?.length || 0],
    ["Stirrups", stirrupCount],
    ["Strand ends", strandCount * 2],
    ["Bituminous pockets", blueprint.bituminous_ends?.length || 0],
  ];
  const quickDimensions = beam ? [
    ["OAL", `${beam.length_ft} ft`],
    ["Depth", `${blueprint.cross_section?.overall_depth_in || blueprint.cross_section?.outer_depth_in || beam.product_type?.depth_in || "—"} in`],
    ["Width", `${blueprint.cross_section?.top_flange_width_in || blueprint.cross_section?.outer_width_in || beam.product_type?.width_in || "—"} in`],
    beam.twin_type === "box_beam"
      ? ["Void", `${blueprint.cross_section?.void_width_in || "—"} × ${blueprint.cross_section?.void_depth_in || "—"} in`]
      : ["Top flange", `${blueprint.cross_section?.top_flange_width_in || "—"} × ${blueprint.cross_section?.top_flange_thickness_in || "—"} in`],
    beam.twin_type === "box_beam"
      ? ["Wall", `${blueprint.cross_section?.wall_thickness_in || "—"} in`]
      : ["Web / bottom flange", `${blueprint.cross_section?.web_thickness_in || "—"} in / ${blueprint.cross_section?.bottom_flange_width_in || "—"} × ${blueprint.cross_section?.bottom_flange_thickness_in || "—"} in`],
    ["Stirrups", blueprint.stirrups?.spacing_in ? `@ ${blueprint.stirrups.spacing_in} in from ${blueprint.stirrups.start_ft ?? 0}' to ${blueprint.stirrups.end_ft ?? beam.length_ft}'` : "—"],
  ] : [];
  const qcStations = beam ? [
    ["Lift loops", stationList(blueprint.lift_loops || [])],
    ["Inserts", stationList(blueprint.inserts || [])],
    ["Tubes", stationList(blueprint.tubes || [])],
    ["Drains", stationList(blueprint.drain_holes || [])],
    ["Hold-downs", stationList(blueprint.hold_downs || [])],
    ["Grooves", stationList(blueprint.grout_grooves || [])],
    ["Bituminous", (blueprint.bituminous_ends || []).length ? (blueprint.bituminous_ends || []).map((item) => `${item.end?.toUpperCase() || "END"} ${item.length_in || 0}"`).join(" · ") : "—"],
  ] : [];
  const activeLayers = useMemo(() => ({
    ...layers,
    dimensions: showCallouts && layers.dimensions,
    hardware: showCallouts && layers.hardware,
    strands: layers.strands,
    stirrups: layers.stirrups,
    anomalies: layers.anomalies,
  }), [layers, showCallouts]);

  return (
    <Layout>
      <PageHeader
        title="Digital Twin Viewer"
        subtitle="Production-grade beam and bed twins driven by product blueprint data"
        right={
          <div className="flex items-center gap-3">
            <button onClick={() => setShowCallouts((value) => !value)} className={`min-h-11 px-4 rounded-sm border text-xs font-mono uppercase tracking-wider ${showCallouts ? "border-primary text-primary" : "border-border text-muted-foreground"}`}>
              {showCallouts ? "Hide" : "Show"} Labels
            </button>
            <div className="flex border border-border rounded-sm overflow-hidden">
              {[["beam", Box, "Beam"], ["bed", Layers3, "Bed"]].map(([value, Icon, label]) => (
                <button key={value} onClick={() => setMode(value)} className={`min-h-11 px-4 flex items-center gap-2 text-xs font-mono uppercase tracking-wider ${mode === value ? "bg-primary text-white" : "bg-background text-muted-foreground"}`}>
                  <Icon className="w-4 h-4" /> {label}
                </button>
              ))}
            </div>
          </div>
        }
      />

      <div className="p-8 grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-card border border-border rounded-sm overflow-hidden flex flex-col" style={{ minHeight: 640 }}>
          <div className="px-5 py-3 border-b border-border flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <div className="flex flex-wrap items-center gap-3">
              <select value={selectedBedId} onChange={(e) => setSelectedBedId(e.target.value)} className="bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm">
                {beds.map((item) => <option key={item.id} value={item.id}>BED {item.bed_number} · {item.name}</option>)}
              </select>
              <select value={selectedId} onChange={(e) => setSelectedId(e.target.value)} className="bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm" data-testid="twin-beam-select">
                {beams.filter((item) => !selectedBedId || item.bed_id === selectedBedId).map((item) => <option key={item.id} value={item.id}>{item.mark} · {item.twin_type === "box_beam" ? "Box" : "I-Beam"}</option>)}
              </select>
            </div>
            <div className="flex items-center gap-2">
              {blueprintSource.status === "locked" && <span className="font-mono text-xs font-bold tracking-widest px-3 py-1 rounded-sm border border-primary/40 text-primary flex items-center gap-2"><Lock className="w-3.5 h-3.5" /> LOCKED BLUEPRINT</span>}
              {blueprintSource.status === "draft" && <span className="font-mono text-xs font-bold tracking-widest px-3 py-1 rounded-sm border border-[#FFD60055] text-[#FFD600] flex items-center gap-2"><AlertTriangle className="w-3.5 h-3.5" /> DRAFT EXTRACTION</span>}
              {bedStatus && <span className="font-mono text-xs font-bold tracking-widest px-3 py-1 rounded-sm" style={{ color: bedStatus.color, border: `1px solid ${bedStatus.color}55` }}>{bedStatus.label}</span>}
              {beamState && <span className="font-mono text-xs font-bold tracking-widest px-3 py-1 rounded-sm" style={{ color: beamState.color, border: `1px solid ${beamState.color}55` }}>{beamState.label}</span>}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-muted-foreground">Layers</span>
              {LAYER_OPTIONS.map(([key, label]) => (
                <LayerChip
                  key={key}
                  label={label}
                  active={!!activeLayers[key]}
                  onClick={() => setLayers((current) => ({ ...current, [key]: !current[key] }))}
                />
              ))}
            </div>
          </div>

          <div className="flex-1">
            {draftTwinBlocked ? (
              <div className="h-full flex items-center justify-center p-10">
                <div className="max-w-lg border border-[#FFD60055] bg-[#FFD60010] rounded-sm p-6 text-sm">
                  <div className="flex items-center gap-2 text-[#FFD600] font-display font-bold uppercase tracking-wider"><AlertTriangle className="w-5 h-5" /> Locked blueprint required</div>
                  <p className="text-muted-foreground mt-3">This beam is linked to a draft blueprint extraction. BedForge blocks production twin rendering until a reviewer verifies and locks the blueprint revision.</p>
                  <p className="text-muted-foreground mt-2">Once locked, geometry, strand rows, hold-downs, hardware, and inspection expectations will come only from the immutable revision.</p>
                </div>
              </div>
            ) : mode === "beam" && beam ? (
              <BeamTwinViewer
                beam={beam}
                anomalies={beam.anomalies || []}
                showCallouts={showCallouts}
                layers={activeLayers}
                onSurfacePick={(point) => {
                  setPickPos(point);
                  toast.info("Surface point marked for anomaly capture");
                }}
                onHardwareSelect={(item) => setSelectedHardware(item)}
              />
            ) : mode === "bed" && bedTwin ? (
              <BedTwinViewer
                bed={bedTwin}
                selectedBeamId={selectedId}
                showCallouts={showCallouts}
                layers={activeLayers}
                onBeamSelect={(item) => {
                  setSelectedId(item.id);
                  setMode("beam");
                }}
                onHardwareSelect={(item) => setSelectedHardware(item)}
              />
            ) : (
              <div className="h-full flex items-center justify-center text-muted-foreground"><Loader2 className="w-6 h-6 animate-spin" /></div>
            )}
          </div>
        </div>

        <div className="space-y-6">
          <div className="bg-card border border-border rounded-sm p-6">
            <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-4 flex items-center gap-2"><Ruler className="w-5 h-5 text-primary" /> Blueprint Callouts</h3>
            {beam ? (
              <div className="space-y-4 text-sm font-mono">
                <div className="grid grid-cols-2 gap-3">
                  <div className="border border-border rounded-sm px-3 py-2"><div className="text-xs uppercase tracking-widest text-muted-foreground">Beam</div><div className="mt-1 text-white">{beam.mark}</div></div>
                  <div className="border border-border rounded-sm px-3 py-2"><div className="text-xs uppercase tracking-widest text-muted-foreground">Product</div><div className="mt-1 text-white">{beam.product_type?.name || "—"}</div></div>
                  <div className="border border-border rounded-sm px-3 py-2"><div className="text-xs uppercase tracking-widest text-muted-foreground">Length</div><div className="mt-1 text-white">{beam.length_ft} ft</div></div>
                  <div className="border border-border rounded-sm px-3 py-2"><div className="text-xs uppercase tracking-widest text-muted-foreground">Marked End</div><div className="mt-1 text-white">{blueprint.marked_end?.label || "MARKED END"}</div></div>
                  <div className="border border-border rounded-sm px-3 py-2 col-span-2"><div className="text-xs uppercase tracking-widest text-muted-foreground">Blueprint source</div><div className="mt-1 text-white">{blueprintSource.status === "locked" ? `Locked revision ${blueprintSource.revision_id?.slice(0, 8)}` : blueprintSource.status.replace(/_/g, " ")}</div></div>
                </div>
                <div className="border border-border rounded-sm p-3">
                  <div className="text-xs uppercase tracking-widest text-muted-foreground mb-3 flex items-center gap-2"><ScanLine className="w-4 h-4" /> Embedded details</div>
                  <div className="grid grid-cols-2 gap-2">
                    {featureCounts.map(([label, count]) => (
                      <div key={label} className="flex items-center justify-between text-xs"><span className="text-muted-foreground">{label}</span><span className="text-white">{count}</span></div>
                    ))}
                  </div>
                </div>
                <div className="border border-border rounded-sm p-3">
                  <div className="text-xs uppercase tracking-widest text-muted-foreground mb-3">QC quick dimensions</div>
                  <div className="space-y-2">
                    {quickDimensions.map(([label, value]) => (
                      <div key={label} className="flex items-start justify-between gap-3 text-xs font-mono">
                        <span className="text-muted-foreground">{label}</span>
                        <span className="text-right text-white">{value}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="border border-border rounded-sm p-3">
                  <div className="text-xs uppercase tracking-widest text-muted-foreground mb-3">QC hardware stations</div>
                  <div className="space-y-2">
                    {qcStations.map(([label, value]) => (
                      <div key={label} className="flex items-start justify-between gap-3 text-xs font-mono">
                        <span className="text-muted-foreground">{label}</span>
                        <span className="text-right text-white">{value}</span>
                      </div>
                    ))}
                  </div>
                </div>
                {selectedBed && (
                  <div className="border border-border rounded-sm p-3">
                    <div className="text-xs uppercase tracking-widest text-muted-foreground mb-2">Bed order</div>
                    <div className="space-y-2">
                      {beams.filter((item) => item.bed_id === selectedBedId).sort((a, b) => (a.position_on_bed || 0) - (b.position_on_bed || 0)).map((item) => (
                        <div key={item.id} className={`flex items-center justify-between text-xs font-mono rounded-sm px-2 py-1 border ${item.id === selectedId ? "border-primary text-primary" : "border-border text-muted-foreground"}`}>
                          <span>POS {String(item.position_on_bed || 0).padStart(2, "0")}</span>
                          <span className={item.id === selectedId ? "text-white" : "text-white/80"}>{item.mark} · {item.length_ft} ft · {item.product_type?.name || item.twin_type}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : <div className="text-sm text-muted-foreground font-mono">Load a beam to inspect blueprint data.</div>}
          </div>

          <div className="bg-card border border-border rounded-sm p-6">
            <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-4 flex items-center gap-2"><Construction className="w-5 h-5 text-primary" /> Hardware Inspector</h3>
            {selectedHardware ? (
              <div className="space-y-3">
                <div className="border border-border rounded-sm px-3 py-2">
                  <div className="text-xs uppercase tracking-widest text-muted-foreground">Selected</div>
                  <div className="mt-1 font-mono text-white">{selectedHardware.type} · {selectedHardware.beamMark}</div>
                </div>
                <SpecRows spec={selectedHardware.spec} />
              </div>
            ) : (
              <div className="text-sm text-muted-foreground font-mono">Tap any loop, insert, tube, tie-rod, drain, strand, groove, pocket, or hold-down to inspect its spec.</div>
            )}
          </div>

          <div className="bg-card border border-border rounded-sm p-6">
            <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-4 flex items-center gap-2"><MapPin className="w-5 h-5 text-primary" /> Capture Anomaly</h3>
            <div className="space-y-4">
              <div className={`text-xs font-mono px-3 py-2 rounded-sm border ${pickPos ? "border-primary text-primary" : "border-border text-muted-foreground"}`} data-testid="pick-status">
                {pickPos ? `POINT SET · STA ${pickPos.z.toFixed(1)} FT · EL ${pickPos.y.toFixed(2)} FT` : "TAP THE BEAM SHELL TO SET LOCATION"}
              </div>
              <div>
                <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Type</label>
                <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className="mt-1 w-full bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm" data-testid="anomaly-type">
                  {["crack", "spall", "honeycomb", "chip", "stain", "other"].map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Severity</label>
                <select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })} className="mt-1 w-full bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm" data-testid="anomaly-severity">
                  {["minor", "moderate", "major"].map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Length (in)</label>
                <input type="number" value={form.length_in} onChange={(e) => setForm({ ...form, length_in: e.target.value })} className="mt-1 w-full bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm" data-testid="anomaly-length" />
              </div>
              <div>
                <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Note</label>
                <textarea value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} rows={2} className="mt-1 w-full bg-background border border-border rounded-sm px-3 py-2 font-mono text-sm" data-testid="anomaly-note" />
              </div>
              <button onClick={saveAnomaly} className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest rounded-sm hover:bg-white hover:text-black transition-colors duration-100" data-testid="save-anomaly">Save To Twin</button>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
}
