import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../lib/api";
import Layout, { PageHeader } from "../components/Layout";
import BeamViewer from "../components/BeamViewer";
import { qcState } from "../lib/constants";
import { toast } from "sonner";
import { Loader2, MapPin } from "lucide-react";

export default function DigitalTwin() {
  const [params] = useSearchParams();
  const [beams, setBeams] = useState([]);
  const [selectedId, setSelectedId] = useState(params.get("beam") || "");
  const [beam, setBeam] = useState(null);
  const [pickPos, setPickPos] = useState(null);
  const [form, setForm] = useState({ type: "crack", severity: "minor", note: "", length_in: 0 });

  useEffect(() => {
    api.get("/beams").then((r) => {
      setBeams(r.data);
      if (!selectedId && r.data.length) setSelectedId(r.data[0].id);
    });
  }, []);

  const loadBeam = (id) => {
    if (!id) return;
    api.get(`/beams/${id}`).then((r) => setBeam(r.data));
  };

  useEffect(() => { loadBeam(selectedId); }, [selectedId]);

  const saveAnomaly = async () => {
    if (!pickPos) { toast.error("Tap the 3D beam to place the anomaly first"); return; }
    try {
      await api.post("/anomalies", {
        beam_id: selectedId,
        type: form.type,
        severity: form.severity,
        note: form.note,
        length_in: parseFloat(form.length_in) || 0,
        position: { x: +(pickPos.z * 10).toFixed(1), y: +pickPos.y.toFixed(2), z: +pickPos.x.toFixed(2) },
      });
      toast.success("Anomaly captured on twin");
      setPickPos(null);
      setForm({ type: "crack", severity: "minor", note: "", length_in: 0 });
      loadBeam(selectedId);
    } catch {
      toast.error("Failed to save anomaly");
    }
  };

  const q = beam ? qcState(beam.qc_state) : null;

  return (
    <Layout>
      <PageHeader title="Digital Twin Viewer" subtitle="Interactive 3D beam · tap surface to capture anomalies" />
      <div className="p-8 grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 3D viewer */}
        <div className="lg:col-span-2 bg-card border border-border rounded-sm overflow-hidden flex flex-col" style={{ minHeight: 520 }}>
          <div className="flex items-center justify-between px-5 py-3 border-b border-border">
            <select
              data-testid="twin-beam-select"
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              className="bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            >
              {beams.map((b) => <option key={b.id} value={b.id}>{b.mark} · {b.twin_type === "box_beam" ? "Box" : "I-Beam"}</option>)}
            </select>
            {q && <span className="font-mono text-xs font-bold tracking-widest px-3 py-1 rounded-sm" style={{ color: q.color, border: `1px solid ${q.color}55` }}>{q.label}</span>}
          </div>
          <div className="flex-1">
            {beam ? (
              <BeamViewer twinType={beam.twin_type} length={beam.length_ft} anomalies={beam.anomalies || []} onPick={(p) => { setPickPos(p); toast.info("Point marked — fill details & save"); }} />
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground"><Loader2 className="w-6 h-6 animate-spin" /></div>
            )}
          </div>
        </div>

        {/* Anomaly capture */}
        <div className="space-y-6">
          <div className="bg-card border border-border rounded-sm p-6">
            <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-4 flex items-center gap-2"><MapPin className="w-5 h-5 text-primary" /> Capture Anomaly</h3>
            <div className="space-y-4">
              <div className={`text-xs font-mono px-3 py-2 rounded-sm border ${pickPos ? "border-primary text-primary" : "border-border text-muted-foreground"}`} data-testid="pick-status">
                {pickPos ? `POINT SET · x${(pickPos.z*10).toFixed(1)} y${pickPos.y.toFixed(2)}` : "TAP THE BEAM TO SET LOCATION"}
              </div>
              <div>
                <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Type</label>
                <select data-testid="anomaly-type" value={form.type} onChange={(e)=>setForm({...form,type:e.target.value})} className="mt-1 w-full bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm">
                  {["crack","spall","honeycomb","chip","stain","other"].map(t=><option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Severity</label>
                <select data-testid="anomaly-severity" value={form.severity} onChange={(e)=>setForm({...form,severity:e.target.value})} className="mt-1 w-full bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm">
                  {["minor","moderate","major"].map(t=><option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Length (in)</label>
                <input data-testid="anomaly-length" type="number" value={form.length_in} onChange={(e)=>setForm({...form,length_in:e.target.value})} className="mt-1 w-full bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm" />
              </div>
              <div>
                <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Note</label>
                <textarea data-testid="anomaly-note" value={form.note} onChange={(e)=>setForm({...form,note:e.target.value})} rows={2} className="mt-1 w-full bg-background border border-border rounded-sm px-3 py-2 font-mono text-sm" />
              </div>
              <button data-testid="save-anomaly" onClick={saveAnomaly} className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest rounded-sm hover:bg-white hover:text-black transition-colors duration-100">Save To Twin</button>
            </div>
          </div>

          <div className="bg-card border border-border rounded-sm p-6">
            <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-4">Logged Anomalies</h3>
            <div className="space-y-2" data-testid="anomaly-list">
              {(beam?.anomalies || []).length === 0 && <div className="text-sm text-muted-foreground font-mono">No anomalies recorded.</div>}
              {(beam?.anomalies || []).map((a)=>{
                const color = a.severity==="major"?"#FF3366":a.severity==="moderate"?"#FFD600":"#2979FF";
                return (
                  <div key={a.id} className="border-b border-border pb-2 last:border-0">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-sm font-bold" style={{color}}>{a.type.toUpperCase()} · {a.severity}</span>
                      <span className="font-mono text-xs text-muted-foreground">{a.length_in}"</span>
                    </div>
                    {a.note && <div className="text-xs text-muted-foreground mt-1">{a.note}</div>}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
}
