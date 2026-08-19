import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../lib/api";
import Layout, { PageHeader } from "../components/Layout";
import BeamTwinViewer, { BedTwinViewer } from "../components/BeamViewer";
import { bedState, qcState } from "../lib/constants";
import { toast } from "sonner";
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle } from "../components/ui/drawer";
import { Layers3, Loader2, MapPin, Ruler, ScanLine, Box, Construction, Lock, AlertTriangle, SlidersHorizontal } from "lucide-react";

function SpecRows({ spec }) {
  return Object.entries(spec || {}).map(([key, value]) => (
    <div key={key} className="flex items-center justify-between gap-3 text-xs font-mono">
      <span className="text-muted-foreground uppercase tracking-wider">{key.replace(/_/g, " ")}</span>
      <span className="text-white text-right">{typeof value === "object" ? JSON.stringify(value) : String(value)}</span>
    </div>
  ));
}

function stationList(items = []) {
  const stations = items.map((item) => item.x_ft ?? item.station_ft ?? item?.position?.station_ft).filter((value) => value != null && value !== "");
  return stations.length ? stations.map((value) => `${Number(value).toFixed(1)}'`).join(" · ") : "unconfirmed";
}

const LAYER_OPTIONS = [
  ["dimensions", "Dimensions"],
  ["stations", "Stations"],
  ["hardware", "Hardware"],
  ["strands", "Strands"],
  ["stirrups", "Stirrups / rebar"],
  ["anomalies", "Anomalies"],
];

function LayerChip({ active, label, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`min-h-9 px-3 rounded-sm border text-[11px] font-mono uppercase tracking-wider transition-colors duration-100 whitespace-nowrap ${
        active ? "border-primary bg-primary/15 text-primary" : "border-border bg-background text-muted-foreground hover:border-primary/60 hover:text-white"
      }`}
    >
      {label}
    </button>
  );
}

function TwinSelectors({ selectedSpecId, specs, onSpecChange, selectedBedId, beds, onBedChange, selectedId, beams, onBeamChange }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <select
        value={selectedSpecId}
        onChange={onSpecChange}
        className="bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm min-w-[12rem] flex-1"
        data-testid="twin-spec-select"
      >
        <option value="">{specs.length ? "Spec DNA — select mark" : "No locked Spec DNA yet"}</option>
        {specs.map((item) => (
          <option key={item.id} value={item.id}>
            {item.job_number || "JOB"} · MK {item.beam_mark} · {item.geometry?.length_ft ? `${Number(item.geometry.length_ft).toFixed(2)} ft` : "length unconfirmed"}
          </option>
        ))}
      </select>
      <select value={selectedBedId} onChange={onBedChange} className="bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm">
        {beds.map((item) => <option key={item.id} value={item.id}>BED {item.bed_number} · {item.name}</option>)}
      </select>
      <select value={selectedId} onChange={onBeamChange} className="bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm" data-testid="twin-beam-select">
        {beams.filter((item) => !selectedBedId || item.bed_id === selectedBedId).map((item) => <option key={item.id} value={item.id}>{item.mark} · {item.twin_type === "box_beam" ? "Box" : "I-Beam"}</option>)}
      </select>
    </div>
  );
}

function TwinLayerChips({ activeLayers, onToggle }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-muted-foreground mr-1">Layers</span>
      {LAYER_OPTIONS.map(([key, label]) => (
        <LayerChip key={key} label={label} active={!!activeLayers[key]} onClick={() => onToggle(key)} />
      ))}
    </div>
  );
}

function layersForPour(mode) {
  if (mode === "pre_pour") {
    return { dimensions: true, stations: true, hardware: true, strands: true, stirrups: true, anomalies: true };
  }
  return { dimensions: true, stations: true, hardware: true, strands: false, stirrups: false, anomalies: true };
}

export default function DigitalTwin() {
  const [params] = useSearchParams();
  const [beams, setBeams] = useState([]);
  const [beds, setBeds] = useState([]);
  const [specs, setSpecs] = useState([]);
  const [selectedId, setSelectedId] = useState(params.get("beam") || "");
  const [selectedSpecId, setSelectedSpecId] = useState(params.get("spec") || "");
  const [beam, setBeam] = useState(null);
  const [bedTwin, setBedTwin] = useState(null);
  const [selectedBedId, setSelectedBedId] = useState("");
  const [selectedHardware, setSelectedHardware] = useState(null);
  const [pickPos, setPickPos] = useState(null);
  const [showCallouts, setShowCallouts] = useState(true);
  const [pourMode, setPourMode] = useState("pre_pour");
  const [layers, setLayers] = useState(layersForPour("pre_pour"));
  const [mode, setMode] = useState("beam");
  const [controlsOpen, setControlsOpen] = useState(false);
  const [form, setForm] = useState({ type: "crack", severity: "minor", note: "", length_in: 0 });

  useEffect(() => {
    api.get("/beams").then((r) => {
      setBeams(r.data);
      setSelectedId((current) => current || r.data[0]?.id || "");
      setSelectedBedId((current) => current || r.data[0]?.bed_id || "");
    });
    api.get("/beds").then((r) => setBeds(r.data));
    api.get("/beam-specs").then((r) => {
      const list = Array.isArray(r.data) ? r.data : [];
      setSpecs(list);
      setSelectedSpecId((current) => current || (params.get("beam") ? "" : (list[0]?.id || "")));
    }).catch(() => setSpecs([]));
  }, []);

  useEffect(() => {
    if (selectedSpecId) {
      api.get(`/beam-specs/${selectedSpecId}/twin`).then((r) => {
        setBeam(r.data);
        if (r.data.bed_id) setSelectedBedId(r.data.bed_id);
      }).catch(() => toast.error("Failed to load Spec twin"));
      return;
    }
    if (!selectedId) return;
    api.get(`/beams/${selectedId}`).then((r) => {
      setBeam(r.data);
      if (r.data.bed_id) setSelectedBedId(r.data.bed_id);
    });
  }, [selectedId, selectedSpecId]);

  useEffect(() => {
    if (!selectedBedId) return;
    api.get(`/beds/${selectedBedId}/twin`).then((r) => setBedTwin(r.data));
  }, [selectedBedId, selectedId]);

  const setPour = (next) => {
    setPourMode(next);
    setLayers(layersForPour(next));
  };

  const saveAnomaly = async () => {
    if (!pickPos || !selectedId || String(selectedId).startsWith("spec:")) {
      toast.error(String(selectedId).startsWith("spec:") ? "Lock this Spec to a plant beam before capturing anomalies" : "Tap the beam shell to set the anomaly location first");
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
      if (beamRes.data.bed_id) {
        const bedRes = await api.get(`/beds/${beamRes.data.bed_id}/twin`);
        setBedTwin(bedRes.data);
      }
    } catch {
      toast.error("Failed to save anomaly");
    }
  };

  const selectedBed = useMemo(() => beds.find((item) => item.id === selectedBedId), [beds, selectedBedId]);
  const beamState = beam ? qcState(beam.qc_state) : null;
  const bedStatus = selectedBed ? bedState(selectedBed.status) : null;
  const blueprint = beam?.beam_spec?.blueprint || beam?.product_type?.blueprint || {};
  const beamSpec = beam?.beam_spec;
  const blueprintSource = beam?.blueprint_source || { status: "legacy_seed" };
  const draftTwinBlocked = blueprintSource.status === "draft" && !beamSpec;
  const specDnaActive = Boolean(beamSpec);
  const strandSystem = beamSpec?.strand || blueprint.strand_system || {};
  const strandCount = strandSystem.count || (blueprint.strand_pattern?.rows || []).reduce((sum, row) => sum + (row.count || 0), 0);
  const featureCounts = [
    ["Lift loops", blueprint.lift_loops?.length || 0],
    ["Inserts", blueprint.inserts?.length || 0],
    ["Tubes", blueprint.tubes?.length || 0],
    ["Tie-rods", blueprint.tie_rod_openings?.length || 0],
    ["Drain holes", blueprint.drain_holes?.length || 0],
    ["Hold-downs", blueprint.hold_downs?.length || 0],
    ["Stirrup zones", (beamSpec?.stirrup_zones || []).length],
    ["Strand ends", strandCount * 2],
    ["Bituminous pockets", Array.isArray(blueprint.bituminous_ends) ? blueprint.bituminous_ends.length : 0],
  ];
  const quickDimensions = beam ? [
    ["OAL", beam.length_ft != null ? `${beam.length_ft} ft` : "unconfirmed"],
    ["Casting", beamSpec?.geometry?.casting_length_ft != null ? `${beamSpec.geometry.casting_length_ft} ft` : "unconfirmed"],
    ["Depth", `${blueprint.cross_section?.overall_depth_in || blueprint.cross_section?.outer_depth_in || beam.product_type?.depth_in || "unconfirmed"}`],
    ["Width", `${blueprint.cross_section?.top_flange_width_in || blueprint.cross_section?.outer_width_in || beam.product_type?.width_in || "unconfirmed"}`],
    ["Section source", beamSpec?.section_source || blueprintSource.section_source || (specDnaActive ? "extracted" : "legacy seed")],
  ] : [];
  const qcStations = beam ? [
    ["Lift loops", stationList(blueprint.lift_loops || [])],
    ["Inserts", stationList(blueprint.inserts || [])],
    ["Tubes", stationList(blueprint.tubes || [])],
    ["Drains", stationList(blueprint.drain_holes || [])],
    ["Hold-downs", stationList(blueprint.hold_downs || [])],
    ["Grooves", stationList(blueprint.grout_grooves || [])],
  ] : [];
  const activeLayers = useMemo(() => ({
    ...layers,
    dimensions: showCallouts && layers.dimensions,
    stations: showCallouts && layers.stations,
    hardware: layers.hardware,
    strands: layers.strands,
    stirrups: layers.stirrups,
    anomalies: layers.anomalies,
  }), [layers, showCallouts]);

  const sidebar = (
    <div className="space-y-6">
      <div className="bg-card border border-border rounded-sm p-6">
        <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-4 flex items-center gap-2"><Ruler className="w-5 h-5 text-primary" /> Spec / Blueprint DNA</h3>
        {beam ? (
          <div className="space-y-4 text-sm font-mono">
            <div className="grid grid-cols-2 gap-3">
              <div className="border border-border rounded-sm px-3 py-2"><div className="text-xs uppercase tracking-widest text-muted-foreground">Beam</div><div className="mt-1 text-white">{beam.mark}</div></div>
              <div className="border border-border rounded-sm px-3 py-2"><div className="text-xs uppercase tracking-widest text-muted-foreground">Job</div><div className="mt-1 text-white">{beamSpec?.job_number || beamSpec?.identity?.job_number || "—"}</div></div>
              <div className="border border-border rounded-sm px-3 py-2"><div className="text-xs uppercase tracking-widest text-muted-foreground">Length</div><div className="mt-1 text-white">{beam.length_ft != null ? `${beam.length_ft} ft` : "unconfirmed"}</div></div>
              <div className="border border-border rounded-sm px-3 py-2"><div className="text-xs uppercase tracking-widest text-muted-foreground">Marked End</div><div className="mt-1 text-white">{blueprint.marked_end?.label || "MARKED END"}</div></div>
              <div className="border border-border rounded-sm px-3 py-2 col-span-2"><div className="text-xs uppercase tracking-widest text-muted-foreground">DNA source</div><div className="mt-1 text-white">{specDnaActive ? `Spec ${beamSpec.beam_mark} · ${blueprintSource.status}` : blueprintSource.status.replace(/_/g, " ")}</div></div>
            </div>
            {(beamSpec?.missing_fields || []).length > 0 && (
              <div className="border border-[#C9A22755] bg-[#C9A22712] rounded-sm p-3 text-xs text-[#E8C872]">
                Missing / unconfirmed on print: {(beamSpec.missing_fields || []).join(", ")}. Twin does not invent these stations.
              </div>
            )}
            <div className="border border-border rounded-sm p-3">
              <div className="text-xs uppercase tracking-widest text-muted-foreground mb-3 flex items-center gap-2"><ScanLine className="w-4 h-4" /> Embedded details</div>
              <div className="grid grid-cols-2 gap-2">
                {featureCounts.map(([label, count]) => (
                  <div key={label} className="flex items-center justify-between text-xs"><span className="text-muted-foreground">{label}</span><span className="text-white">{count}</span></div>
                ))}
              </div>
            </div>
            <div className="border border-border rounded-sm p-3">
              <div className="text-xs uppercase tracking-widest text-muted-foreground mb-3">QC dimensions</div>
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
              <div className="text-xs uppercase tracking-widest text-muted-foreground mb-3">Strand system</div>
              <div className="space-y-2">
                {[
                  ["Draped", strandSystem.draped ? "yes" : "no"],
                  ["Path", strandSystem.path_model?.source || "none"],
                  ["Pattern", strandSystem.pattern_source || "unconfirmed"],
                  ["Hold-down", strandSystem.hold_down_type || "unconfirmed"],
                  ["End treatment", strandSystem.end_treatments?.marked_end?.label || strandSystem.end_treatments?.marked_end?.type || "unspecified"],
                  ["Diameter", strandSystem.diameter_in != null ? `${strandSystem.diameter_in} in` : "unconfirmed"],
                  ["Grade", strandSystem.grade || "unconfirmed"],
                  ["Final pull", strandSystem.final_pull_lb != null ? `${strandSystem.final_pull_lb} lb` : "unconfirmed"],
                ].map(([label, value]) => (
                  <div key={label} className="flex items-start justify-between gap-3 text-xs font-mono">
                    <span className="text-muted-foreground">{label}</span>
                    <span className="text-right text-white">{String(value)}</span>
                  </div>
                ))}
              </div>
              {(strandSystem.path_model?.notes || []).length > 0 && (
                <div className="mt-3 text-[11px] leading-relaxed text-[#E8C872]">
                  {(strandSystem.path_model.notes || []).join(" ")}
                </div>
              )}
            </div>
            <div className="border border-border rounded-sm p-3">
              <div className="text-xs uppercase tracking-widest text-muted-foreground mb-3">Stations from marked end</div>
              <div className="space-y-2">
                {qcStations.map(([label, value]) => (
                  <div key={label} className="flex items-start justify-between gap-3 text-xs font-mono">
                    <span className="text-muted-foreground">{label}</span>
                    <span className="text-right text-white">{value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : <div className="text-sm text-muted-foreground font-mono">Load a beam or Spec to inspect DNA.</div>}
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
          <div className="text-sm text-muted-foreground font-mono">Tap any loop, insert, tube, strand, or hold-down to inspect its spec.</div>
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
  );

  return (
    <Layout>
      <PageHeader
        title="Digital Twin Viewer"
        subtitle="Job Spec DNA drives unique per-beam twins — Pre-Pour cage vs Post-Pour finish"
        right={
          <div className="flex flex-wrap items-center justify-end gap-2">
            <button type="button" onClick={() => setControlsOpen(true)} className="lg:hidden min-h-11 px-3 rounded-sm border border-primary text-primary text-xs font-mono uppercase tracking-wider flex items-center gap-2">
              <SlidersHorizontal className="w-4 h-4" /> Controls
            </button>
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

      <div className="p-4 sm:p-6 lg:p-8 grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
        <div className="lg:col-span-2 w-full bg-card border border-border rounded-sm overflow-hidden flex flex-col min-h-[480px] h-[calc(100vh-12.5rem)] max-h-[calc(100vh-11.5rem)] lg:sticky lg:top-24">
          <div className="px-4 sm:px-5 py-3 border-b border-border flex flex-col gap-3 shrink-0">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2" data-testid="pour-mode-toggle">
              {[["pre_pour", "Pre-Pour", "Cables / hold-downs / no concrete"], ["post_pour", "Post-Pour", "Concrete + tip pattern"]].map(([value, label, hint]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setPour(value)}
                  className={`min-h-12 rounded-sm border px-4 text-left transition-colors duration-100 ${
                    pourMode === value ? "border-primary bg-primary/15 shadow-[0_0_24px_rgba(45,212,191,0.18)]" : "border-border bg-background hover:border-primary/50"
                  }`}
                >
                  <div className={`font-display font-bold uppercase tracking-wider text-sm ${pourMode === value ? "text-primary" : "text-white"}`}>{label}</div>
                  <div className="text-[11px] font-mono text-muted-foreground mt-1">{hint}</div>
                </button>
              ))}
            </div>
            <div className="flex flex-col gap-4">
              <TwinSelectors
                selectedSpecId={selectedSpecId}
                specs={specs}
                onSpecChange={(e) => {
                  const next = e.target.value;
                  setSelectedSpecId(next);
                  if (!next) return;
                  const spec = specs.find((item) => item.id === next);
                  if (spec?.beam_id) setSelectedId(spec.beam_id);
                }}
                selectedBedId={selectedBedId}
                beds={beds}
                onBedChange={(e) => { setSelectedBedId(e.target.value); setSelectedSpecId(""); }}
                selectedId={selectedId}
                beams={beams}
                onBeamChange={(e) => { setSelectedId(e.target.value); setSelectedSpecId(""); }}
              />
              <div className="flex flex-wrap items-center gap-2">
                {blueprintSource.status === "locked" && <span className="font-mono text-xs font-bold tracking-widest px-3 py-1 rounded-sm border border-primary/40 text-primary flex items-center gap-2"><Lock className="w-3.5 h-3.5" /> {specDnaActive ? "SPEC DNA" : "LOCKED BLUEPRINT"}</span>}
                {blueprintSource.status === "draft" && <span className="font-mono text-xs font-bold tracking-widest px-3 py-1 rounded-sm border border-[#FFD60055] text-[#FFD600] flex items-center gap-2"><AlertTriangle className="w-3.5 h-3.5" /> DRAFT EXTRACTION</span>}
                {bedStatus && <span className="font-mono text-xs font-bold tracking-widest px-3 py-1 rounded-sm" style={{ color: bedStatus.color, border: `1px solid ${bedStatus.color}55` }}>{bedStatus.label}</span>}
                {beamState && <span className="font-mono text-xs font-bold tracking-widest px-3 py-1 rounded-sm" style={{ color: beamState.color, border: `1px solid ${beamState.color}55` }}>{beamState.label}</span>}
              </div>
              <div className="hidden md:block">
                <TwinLayerChips activeLayers={activeLayers} onToggle={(key) => setLayers((current) => ({ ...current, [key]: !current[key] }))} />
              </div>
              <p className="md:hidden text-[11px] font-mono text-muted-foreground">Open Controls for layer chips and DNA inspector</p>
            </div>
          </div>

          <div className="flex-1 min-h-[280px] sm:min-h-[360px] overflow-hidden">
            {draftTwinBlocked ? (
              <div className="h-full flex items-center justify-center p-10">
                <div className="max-w-lg border border-[#FFD60055] bg-[#FFD60010] rounded-sm p-6 text-sm">
                  <div className="flex items-center gap-2 text-[#FFD600] font-display font-bold uppercase tracking-wider"><AlertTriangle className="w-5 h-5" /> Locked blueprint required</div>
                  <p className="text-muted-foreground mt-3">This beam is linked to a draft blueprint extraction. Lock the revision in Blueprint Intelligence to materialize Spec DNA and render the twin.</p>
                </div>
              </div>
            ) : mode === "beam" && beam ? (
              <BeamTwinViewer
                beam={beam}
                anomalies={beam.anomalies || []}
                showCallouts={showCallouts}
                layers={activeLayers}
                pourMode={pourMode}
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
                pourMode={pourMode}
                onBeamSelect={(item) => {
                  setSelectedId(item.id);
                  setSelectedSpecId("");
                  setMode("beam");
                }}
                onHardwareSelect={(item) => setSelectedHardware(item)}
              />
            ) : (
              <div className="h-full flex items-center justify-center text-muted-foreground"><Loader2 className="w-6 h-6 animate-spin" /></div>
            )}
          </div>
        </div>

        <div className="hidden lg:block">{sidebar}</div>
      </div>

      <Drawer open={controlsOpen} onOpenChange={setControlsOpen}>
        <DrawerContent className="max-h-[85vh] overflow-y-auto bg-[#0A0C10] border-[#1C2230]">
          <DrawerHeader>
            <DrawerTitle className="font-display uppercase tracking-wider">Twin controls</DrawerTitle>
          </DrawerHeader>
          <div className="px-4 pb-8 space-y-6">
            <div className="md:hidden space-y-4">
              <TwinLayerChips activeLayers={activeLayers} onToggle={(key) => setLayers((current) => ({ ...current, [key]: !current[key] }))} />
            </div>
            {sidebar}
          </div>
        </DrawerContent>
      </Drawer>
    </Layout>
  );
}
