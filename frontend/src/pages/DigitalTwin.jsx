import React, { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, Field, inputClass, cardClass, ARMeasureLink } from "../components/Layout";
import BeamViewer from "../components/BeamViewer";
import { useAuth } from "../context/AuthContext";
import { useSync } from "../context/SyncContext";
import { canPlan, qcState } from "../lib/constants";
import { isoToday } from "../lib/bedLayout";
import { ELEMENT_COLORS, KIND_LABELS, hardwareColor, latestMeasurements } from "../lib/beamSpec";
import { toast } from "sonner";
import { Loader2, MapPin, Ruler, Upload, CalendarDays, ScanLine, QrCode } from "lucide-react";

export default function DigitalTwin() {
  const { user } = useAuth();
  const { measurements: liveAr } = useSync();
  const plan = canPlan(user?.role);
  const [params] = useSearchParams();
  const [beams, setBeams] = useState([]);
  const [beds, setBeds] = useState([]);
  const [selectedId, setSelectedId] = useState(params.get("beam") || "");
  const [beam, setBeam] = useState(null);
  const [pickPos, setPickPos] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ type: "crack", severity: "minor", note: "", length_in: 0 });
  const [tab, setTab] = useState("hardware");
  const [selectedHw, setSelectedHw] = useState(null);
  const [measuredFt, setMeasuredFt] = useState("");
  const [assignBed, setAssignBed] = useState("");
  const [assignDate, setAssignDate] = useState(isoToday());

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
    api.get("/beds")
      .then((r) => {
        if (cancelled) return;
        setBeds(r.data || []);
        setAssignBed((cur) => cur || r.data?.[0]?.id || "");
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[twin] beds load failed", err);
      });
    return () => { cancelled = true; };
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

  const latestArId = (liveAr || []).find((m) => m.beam_id === selectedId)?.id;

  useEffect(() => {
    if (!selectedId) return undefined;
    let cancelled = false;
    api.get(`/beams/${selectedId}`)
      .then((r) => { if (!cancelled) setBeam(r.data); })
      .catch((err) => {
        if (cancelled) return;
        console.error("[twin] beam load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load beam twin");
      });
    return () => { cancelled = true; };
  }, [selectedId, latestArId]);

  const spec = beam?.spec || null;
  const measurementMap = useMemo(() => latestMeasurements(beam?.measurements), [beam]);

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
          x: +(pickPos.z || 0).toFixed(2),
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

  const saveMeasure = async () => {
    if (!spec?.id || !selectedHw) {
      toast.error("Select a hardware item on the twin first");
      return;
    }
    const val = parseFloat(measuredFt);
    if (Number.isNaN(val)) {
      toast.error("Enter measured station from Marked End (ft)");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post(`/beam-specs/${spec.id}/measurements`, {
        element_id: selectedHw.id,
        measured_station_ft: val,
      });
      toast.success(data.within_tolerance ? "WITHIN TOLERANCE" : "OUT OF TOLERANCE");
      setMeasuredFt("");
      await loadBeam(selectedId);
    } catch (err) {
      console.error("[twin] measure failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to save measurement");
    } finally {
      setSaving(false);
    }
  };

  const assignToBed = async () => {
    if (!plan) {
      toast.error("Supervisors and production can assign beds");
      return;
    }
    if (!selectedId || !assignBed) {
      toast.error("Select a beam and a bed");
      return;
    }
    setSaving(true);
    try {
      await api.post("/bed-assignments", {
        bed_id: assignBed,
        beam_id: selectedId,
        job_id: beam?.job_id,
        pour_id: beam?.pour_id,
        scheduled_date: assignDate,
        marked_end_toward: "header",
      });
      toast.success("Beam assigned to bed");
    } catch (err) {
      console.error("[twin] assign failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Assignment conflict");
    } finally {
      setSaving(false);
    }
  };

  const q = beam ? qcState(beam.qc_state) : null;

  return (
    <Layout>
      <PageHeader
        title="Digital Twin"
        subtitle={spec ? `${spec.product_name} · ${spec.geometry?.length_ft}' · ${spec.status}` : "Upload a shop drawing to generate a blueprint-accurate twin"}
        right={
          <div className="flex flex-wrap gap-2 justify-end">
            <ARMeasureLink beamId={selectedId} purpose="tape" />
            {beam?.qr_token && (
              <Link
                to={`/b/${beam.qr_token}`}
                className="min-h-12 px-4 border border-[#1C2230] rounded-none flex items-center gap-2 text-sm font-semibold uppercase tracking-wider hover:border-primary hover:text-primary"
                data-testid="twin-dossier-link"
              >
                <QrCode className="w-4 h-4" /> Dossier
              </Link>
            )}
            {selectedId && (
              <Link
                to={`/qr?beam=${selectedId}`}
                className="min-h-12 px-4 border border-[#1C2230] rounded-none flex items-center gap-2 text-sm font-semibold uppercase tracking-wider hover:border-primary hover:text-primary"
                data-testid="twin-qr-reprint"
              >
                <QrCode className="w-4 h-4" /> QR
              </Link>
            )}
            <Link
              to={selectedId ? `/planner?beam=${selectedId}` : "/planner"}
              className="min-h-12 px-4 border border-[#1C2230] rounded-none flex items-center gap-2 text-sm font-semibold uppercase tracking-wider hover:border-primary hover:text-primary"
            >
              <CalendarDays className="w-4 h-4" /> Planner
            </Link>
            <Link
              to="/drawings"
              className="min-h-12 px-4 border border-[#1C2230] rounded-none flex items-center gap-2 text-sm font-semibold uppercase tracking-wider hover:border-primary hover:text-primary"
            >
              <Upload className="w-4 h-4" /> Drawings
            </Link>
          </div>
        }
      />
      <div className="p-4 sm:p-6 lg:p-8 grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
        <div className={`${cardClass} overflow-hidden flex flex-col lg:col-span-2`} style={{ minHeight: 480 }}>
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
            <div className="flex items-center gap-2">
              {spec && (
                <span className="font-mono text-xs font-bold tracking-widest px-3 py-1 rounded-none" style={{ color: spec.status === "locked" ? "#00E676" : "#FFD600", border: `1px solid ${spec.status === "locked" ? "#00E67655" : "#FFD60055"}` }}>
                  SPEC {spec.status.toUpperCase()}
                </span>
              )}
              {q && (
                <span className="font-mono text-xs font-bold tracking-widest px-3 py-1 rounded-none" style={{ color: q.color, border: `1px solid ${q.color}55` }}>
                  {q.label}
                </span>
              )}
            </div>
          </div>
          <div className="flex-1 min-h-[360px]">
            {beam ? (
              <BeamViewer
                spec={spec}
                twinType={beam.twin_type}
                length={beam.length_ft}
                anomalies={beam.anomalies || []}
                measurements={beam.measurements || []}
                selectedId={selectedHw?.id}
                onSelectHardware={(item) => {
                  setSelectedHw(item);
                  setTab("measure");
                  setMeasuredFt(String(item.position?.station_ft ?? ""));
                  toast.info(`${item.name} · design ${item.position?.station_ft}' from ME`);
                }}
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
          <div className="px-4 py-2 border-t border-[#1C2230] flex flex-wrap gap-2">
            {Object.entries(ELEMENT_COLORS).slice(0, 8).map(([kind, color]) => (
              <span key={kind} className="text-[10px] font-mono flex items-center gap-1">
                <span className="w-2 h-2 inline-block" style={{ background: color }} />
                {KIND_LABELS[kind] || kind}
              </span>
            ))}
          </div>
        </div>

        <div className="space-y-4 sm:space-y-6">
          {(beam?.traceability?.heat_numbers || []).length > 0 && (
            <div className={`${cardClass} p-5 sm:p-6`} data-testid="strand-traceability">
              <h3 className="font-display font-bold uppercase tracking-wider text-lg">Strand heat chain</h3>
              <p className="text-[10px] font-mono text-muted-foreground mt-1">{beam.traceability.chain}</p>
              <div className="mt-3 font-mono text-sm text-[#00E676]">
                {(beam.traceability.heat_numbers || []).map((h) => `HEAT ${h}`).join("  ·  ")}
              </div>
              <div className="text-[10px] font-mono text-muted-foreground mt-1">
                {(beam.traceability.reel_numbers || []).map((r) => `REEL ${r}`).join("  ·  ")}
              </div>
              <Link to="/rolls" className="inline-block mt-3 text-[10px] font-mono uppercase tracking-widest text-primary">Open strand rolls</Link>
            </div>
          )}
          <div className={`${cardClass} p-5 sm:p-6 space-y-3`} data-testid="assign-to-bed">
            <h3 className="font-display font-bold uppercase tracking-wider text-lg">Assign to Bed</h3>
            <Field label="Casting bed">
              <select data-testid="twin-assign-bed" value={assignBed} onChange={(e) => setAssignBed(e.target.value)} className={inputClass}>
                {beds.map((b) => (
                  <option key={b.id} value={b.id}>Bed {b.bed_number} · {b.length_ft} ft</option>
                ))}
              </select>
            </Field>
            <Field label="Scheduled date">
              <input data-testid="twin-assign-date" type="date" value={assignDate} onChange={(e) => setAssignDate(e.target.value)} className={inputClass} />
            </Field>
            <button
              data-testid="twin-assign-btn"
              type="button"
              onClick={assignToBed}
              disabled={saving || !plan}
              className="w-full min-h-12 bg-primary text-white font-display font-bold uppercase tracking-widest rounded-none hover:bg-white hover:text-black disabled:opacity-60"
            >
              {saving ? "Assigning…" : "Assign to Bed"}
            </button>
            <Link to={`/planner?beam=${selectedId}&bed=${assignBed}&date=${assignDate}`} className="block text-center text-[10px] font-mono uppercase tracking-widest text-muted-foreground hover:text-primary">
              Open in bed twin planner
            </Link>
          </div>

          <div className={`${cardClass} p-2 grid grid-cols-3`}>
            {["hardware", "measure", "anomaly"].map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`min-h-12 font-condensed uppercase tracking-wider text-sm ${tab === t ? "bg-primary text-white" : "text-muted-foreground"}`}
              >
                {t === "measure" ? "tape" : t}
              </button>
            ))}
          </div>

          {tab === "hardware" && (
            <div className={`${cardClass} p-5 sm:p-6`}>
              <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-3">Hardware from spec</h3>
              {!spec && <div className="text-sm text-muted-foreground font-mono">No BeamSpec. Upload a drawing to generate the twin.</div>}
              <div className="max-h-[420px] overflow-y-auto space-y-1" data-testid="twin-hardware-list">
                {(spec?.hardware || []).map((h) => {
                  const m = measurementMap[h.id];
                  const color = hardwareColor(h.kind, m);
                  return (
                    <button
                      type="button"
                      key={h.id}
                      onClick={() => { setSelectedHw(h); setTab("measure"); setMeasuredFt(String(h.position?.station_ft ?? "")); }}
                      className="w-full text-left border-b border-[#1C2230] py-2 hover:border-primary"
                    >
                      <div className="flex justify-between gap-2">
                        <span className="font-mono text-xs font-bold" style={{ color }}>{h.name}</span>
                        <span className="font-mono text-xs text-muted-foreground">{h.position?.station_ft}'</span>
                      </div>
                      <div className="text-[10px] text-muted-foreground font-mono">{h.type_code || h.kind} · {h.size}</div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {tab === "measure" && (
            <div className={`${cardClass} p-5 sm:p-6 space-y-4`}>
              <h3 className="font-display font-bold uppercase tracking-wider text-lg flex items-center gap-2">
                <Ruler className="w-5 h-5 text-primary" /> Measured vs design
              </h3>
              <div className="text-xs font-mono px-3 py-2 border border-[#1C2230] space-y-1" data-testid="measure-target">
                {selectedHw ? (
                  <>
                    <div>{selectedHw.name} · DESIGN {selectedHw.position?.station_ft}' ME · TOL ±{selectedHw.tolerance_in}"</div>
                    <div className="text-muted-foreground">{selectedHw.type_code || selectedHw.kind} · {selectedHw.size} · soffit {selectedHw.position?.height_from_soffit_in}"</div>
                    {selectedHw.notes ? <div className="text-muted-foreground">{selectedHw.notes}</div> : null}
                  </>
                ) : (
                  "TAP HARDWARE ON THE TWIN"
                )}
              </div>
              <Field label="Measured station from Marked End (ft)">
                <input data-testid="measure-station" type="number" step="0.01" value={measuredFt} onChange={(e) => setMeasuredFt(e.target.value)} className={inputClass} />
              </Field>
              <button
                data-testid="measure-save"
                onClick={saveMeasure}
                disabled={saving || !spec?.id}
                className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest rounded-none hover:bg-white hover:text-black disabled:opacity-60"
              >
                {saving ? "Saving…" : "Check tolerance"}
              </button>
              {selectedHw && measurementMap[selectedHw.id] && (
                <div className="font-mono text-sm" style={{ color: measurementMap[selectedHw.id].within_tolerance ? "#00E676" : "#FF3366" }}>
                  Δ {measurementMap[selectedHw.id].delta_in}" · {measurementMap[selectedHw.id].within_tolerance ? "PASS" : "FAIL"}
                </div>
              )}
              <div className="border-t border-[#1C2230] pt-3 space-y-3" data-testid="twin-ar-history">
                <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2 flex items-center gap-2">
                  <ScanLine className="w-3 h-3" /> Digital tape vs twin
                </div>
                {(beam?.tape_runs || []).slice(0, 3).map((run) => (
                  <div key={run.id} className="border border-[#1C2230] p-3 space-y-1">
                    <div className="font-mono text-[11px]" style={{ color: (run.compare?.rescan_count || 0) ? "#FF3366" : "#00E676" }}>
                      {run.shot_count} pts · {run.compare?.pass_count || 0} pass · {run.compare?.rescan_count || 0} rescan · {run.engine}
                    </div>
                    {run.compare?.ai?.summary && (
                      <p className="text-xs text-[#D5D9E2] leading-relaxed">{run.compare.ai.summary}</p>
                    )}
                    {(run.compare?.needs_rescan || []).slice(0, 6).map((row) => (
                      <div key={`${run.id}-${row.station_index}`} className="font-mono text-[10px]" style={{ color: "#FF3366" }}>
                        Rescan #{row.station_index} · {row.element_name || "station"} · {row.measured_station_ft}' vs {row.design_station_ft}' · {row.flag}
                      </div>
                    ))}
                  </div>
                ))}
                {!(beam?.tape_runs || []).length && (
                  <div className="text-xs font-mono text-muted-foreground">No multi-point tape runs on this beam yet. Shoot from Digital Tape — origin on the header, snap on green.</div>
                )}
                {(beam?.ar_measurements || []).slice(0, 6).map((m) => (
                  <div key={m.id} className="border-b border-[#1C2230] py-2 font-mono text-[11px]">
                    <span style={{ color: m.level ? "#00E676" : "#FF3366" }}>{m.level ? "LEVEL" : "OFF"}</span>
                    {" · "}{m.distance_ft} ft · Δ{m.delta_height_in}" · {m.engine}
                    {m.forced ? " · FORCED" : ""}
                    {m.station_index ? ` · #${m.station_index}` : ""}
                  </div>
                ))}
                {!(beam?.ar_measurements || []).length && (
                  <div className="text-xs font-mono text-muted-foreground">No AR shots on this beam yet.</div>
                )}
              </div>
            </div>
          )}

          {tab === "anomaly" && (
            <div className={`${cardClass} p-5 sm:p-6`}>
              <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-4 flex items-center gap-2">
                <MapPin className="w-5 h-5 text-primary" /> Capture Anomaly
              </h3>
              <div className="space-y-4">
                <div
                  className={`text-xs font-mono px-3 py-2 rounded-none border ${pickPos ? "border-primary text-primary" : "border-[#1C2230] text-muted-foreground"}`}
                  data-testid="pick-status"
                >
                  {pickPos ? `POINT SET · z${(pickPos.z || 0).toFixed(1)}` : "TAP THE BEAM TO SET LOCATION"}
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
                <button data-testid="save-anomaly" onClick={saveAnomaly} disabled={saving} className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest rounded-none hover:bg-white hover:text-black disabled:opacity-60">
                  {saving ? "Saving…" : "Save To Twin"}
                </button>
              </div>
              <div className="mt-4 space-y-2" data-testid="anomaly-list">
                {(beam?.anomalies || []).map((a) => {
                  const color = a.severity === "major" ? "#FF3366" : a.severity === "moderate" ? "#FFD600" : "#2979FF";
                  return (
                    <div key={a.id} className="border-b border-[#1C2230] pb-2">
                      <span className="font-mono text-sm font-bold" style={{ color }}>{a.type.toUpperCase()} · {a.severity}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
