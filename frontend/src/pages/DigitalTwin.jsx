import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, Field, inputClass, cardClass } from "../components/Layout";
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
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ type: "crack", severity: "minor", note: "", length_in: 0 });

  useEffect(() => {
    let cancelled = false;
    api.get("/beams")
      .then((r) => {
        if (cancelled) return;
        setBeams(r.data);
        setSelectedId((current) => current || r.data[0]?.id || "");
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[twin] beams load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load beams");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const loadBeam = async (id) => {
    if (!id) return;
    try {
      const r = await api.get(`/beams/${id}`);
      setBeam(r.data);
    } catch (err) {
      console.error("[twin] beam load failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load beam twin");
    }
  };

  useEffect(() => {
    if (!selectedId) return undefined;
    let cancelled = false;
    api.get(`/beams/${selectedId}`)
      .then((r) => {
        if (!cancelled) setBeam(r.data);
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[twin] beam load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load beam twin");
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const saveAnomaly = async () => {
    if (!pickPos) {
      toast.error("Tap the 3D beam to place the anomaly first");
      return;
    }
    setSaving(true);
    try {
      await api.post("/anomalies", {
        beam_id: selectedId,
        type: form.type,
        severity: form.severity,
        note: form.note,
        length_in: parseFloat(form.length_in) || 0,
        position: {
          x: +(pickPos.z * 10).toFixed(1),
          y: +pickPos.y.toFixed(2),
          z: +pickPos.x.toFixed(2),
        },
      });
      toast.success("Anomaly captured on twin");
      setPickPos(null);
      setForm({ type: "crack", severity: "minor", note: "", length_in: 0 });
      await loadBeam(selectedId);
    } catch (err) {
      console.error("[twin] save anomaly failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to save anomaly");
    } finally {
      setSaving(false);
    }
  };

  const q = beam ? qcState(beam.qc_state) : null;

  return (
    <Layout>
      <PageHeader title="Digital Twin Viewer" subtitle="Interactive 3D beam · tap surface to capture anomalies" />
      <div className="p-4 sm:p-6 lg:p-8 grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
        <div className={`${cardClass} overflow-hidden flex flex-col lg:col-span-2`} style={{ minHeight: 420 }}>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-4 sm:px-5 py-3 border-b border-[#1C2230]">
            <select
              data-testid="twin-beam-select"
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              className={`${inputClass} sm:max-w-xs`}
            >
              {beams.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.mark} · {b.twin_type === "box_beam" ? "Box" : "I-Beam"}
                </option>
              ))}
            </select>
            {q && (
              <span className="font-mono text-xs font-bold tracking-widest px-3 py-1 rounded-none self-start sm:self-auto" style={{ color: q.color, border: `1px solid ${q.color}55` }}>
                {q.label}
              </span>
            )}
          </div>
          <div className="flex-1 min-h-[320px]">
            {beam ? (
              <BeamViewer
                twinType={beam.twin_type}
                length={beam.length_ft}
                anomalies={beam.anomalies || []}
                pickPos={pickPos}
                onPick={(p) => {
                  setPickPos(p);
                  toast.info("Point marked — fill details & save");
                }}
              />
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                <Loader2 className="w-6 h-6 animate-spin" />
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4 sm:space-y-6">
          <div className={`${cardClass} p-5 sm:p-6`}>
            <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-4 flex items-center gap-2">
              <MapPin className="w-5 h-5 text-primary" /> Capture Anomaly
            </h3>
            <div className="space-y-4">
              <div
                className={`text-xs font-mono px-3 py-2 rounded-none border ${pickPos ? "border-primary text-primary" : "border-[#1C2230] text-muted-foreground"}`}
                data-testid="pick-status"
              >
                {pickPos ? `POINT SET · x${(pickPos.z * 10).toFixed(1)} y${pickPos.y.toFixed(2)}` : "TAP THE BEAM TO SET LOCATION"}
              </div>
              <Field label="Type">
                <select data-testid="anomaly-type" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className={inputClass}>
                  {["crack", "spall", "honeycomb", "chip", "stain", "other"].map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </Field>
              <Field label="Severity">
                <select data-testid="anomaly-severity" value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })} className={inputClass}>
                  {["minor", "moderate", "major"].map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </Field>
              <Field label="Length (in)">
                <input data-testid="anomaly-length" type="number" value={form.length_in} onChange={(e) => setForm({ ...form, length_in: e.target.value })} className={inputClass} />
              </Field>
              <Field label="Note">
                <textarea data-testid="anomaly-note" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} rows={2} className={`${inputClass} py-2`} />
              </Field>
              <button
                data-testid="save-anomaly"
                onClick={saveAnomaly}
                disabled={saving}
                className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest rounded-none hover:bg-white hover:text-black transition-colors duration-100 disabled:opacity-60"
              >
                {saving ? "Saving…" : "Save To Twin"}
              </button>
            </div>
          </div>

          <div className={`${cardClass} p-5 sm:p-6`}>
            <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-4">Logged Anomalies</h3>
            <div className="space-y-2" data-testid="anomaly-list">
              {(beam?.anomalies || []).length === 0 && (
                <div className="text-sm text-muted-foreground font-mono">No anomalies recorded.</div>
              )}
              {(beam?.anomalies || []).map((a) => {
                const color = a.severity === "major" ? "#FF3366" : a.severity === "moderate" ? "#FFD600" : "#2979FF";
                return (
                  <div key={a.id} className="border-b border-[#1C2230] pb-2 last:border-0">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-sm font-bold" style={{ color }}>{a.type.toUpperCase()} · {a.severity}</span>
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
