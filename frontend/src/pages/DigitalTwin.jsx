import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../lib/api";
import Layout, { PageHeader } from "../components/Layout";
import BeamTwinViewer, { BedTwinViewer } from "../components/BeamViewer";
import { bedState, qcState } from "../lib/constants";
import { toast } from "sonner";
import { Layers3, Loader2, MapPin, Ruler, ScanLine, Box, Construction } from "lucide-react";

function SpecRows({ spec }) {
  return Object.entries(spec || {}).map(([key, value]) => (
    <div key={key} className="flex items-center justify-between gap-3 text-xs font-mono">
      <span className="text-muted-foreground uppercase tracking-wider">{key.replace(/_/g, " ")}</span>
      <span className="text-white text-right">{typeof value === "object" ? JSON.stringify(value) : String(value)}</span>
    </div>
  ));
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
  const featureCounts = [
    ["Lift loops", blueprint.lift_loops?.length || 0],
    ["Inserts", blueprint.inserts?.length || 0],
    ["Tubes", blueprint.tubes?.length || 0],
    ["Tie-rods", blueprint.tie_rod_openings?.length || 0],
    ["Drain holes", blueprint.drain_holes?.length || 0],
    ["Hold-downs", blueprint.hold_downs?.length || 0],
  ];

  return (
    <Layout>
      <PageHeader
        title="Digital Twin Viewer"
        subtitle="Production-grade beam and bed twins driven by product blueprint data"
        right={
          <div className="flex items-center gap-3">
            <button onClick={() => setShowCallouts((value) => !value)} className={`min-h-11 px-4 rounded-sm border text-xs font-mono uppercase tracking-wider ${showCallouts ? "border-primary text-primary" : "border-border text-muted-foreground"}`}>
              {showCallouts ? "Hide" : "Show"} Callouts
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
              {bedStatus && <span className="font-mono text-xs font-bold tracking-widest px-3 py-1 rounded-sm" style={{ color: bedStatus.color, border: `1px solid ${bedStatus.color}55` }}>{bedStatus.label}</span>}
              {beamState && <span className="font-mono text-xs font-bold tracking-widest px-3 py-1 rounded-sm" style={{ color: beamState.color, border: `1px solid ${beamState.color}55` }}>{beamState.label}</span>}
            </div>
          </div>

          <div className="flex-1">
            {mode === "beam" && beam ? (
              <BeamTwinViewer
                beam={beam}
                anomalies={beam.anomalies || []}
                showCallouts={showCallouts}
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
                </div>
                <div className="border border-border rounded-sm p-3">
                  <div className="text-xs uppercase tracking-widest text-muted-foreground mb-3 flex items-center gap-2"><ScanLine className="w-4 h-4" /> Embedded details</div>
                  <div className="grid grid-cols-2 gap-2">
                    {featureCounts.map(([label, count]) => (
                      <div key={label} className="flex items-center justify-between text-xs"><span className="text-muted-foreground">{label}</span><span className="text-white">{count}</span></div>
                    ))}
                  </div>
                </div>
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
              <div className="text-sm text-muted-foreground font-mono">Tap any loop, insert, tube, tie-rod, strand, groove, or hold-down to inspect its spec.</div>
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
