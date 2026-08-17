import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, Field, inputClass, cardClass, ARMeasureLink } from "../components/Layout";
import { toast } from "sonner";
import { Loader2, Ruler, CheckCircle2, XCircle } from "lucide-react";

const EMPTY = {
  required_strength_psi: 4000,
  release_strength_psi: "",
  design_camber_in: "",
  marked_end_in: "",
  midspan_in: "",
  unmarked_end_in: "",
  notes: "",
};

export default function CamberSheet() {
  const [beams, setBeams] = useState([]);
  const [beamId, setBeamId] = useState("");
  const [form, setForm] = useState(EMPTY);
  const [history, setHistory] = useState([]);
  const [cylinders, setCylinders] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get("/beams")
      .then((r) => {
        if (cancelled) return;
        setBeams(r.data);
        setBeamId((current) => current || r.data[0]?.id || "");
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[camber] beams load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load camber data");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!beamId) return undefined;
    let cancelled = false;
    api.get("/camber-readings", { params: { beam_id: beamId } })
      .then((r) => {
        if (!cancelled) setHistory(r.data || []);
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[camber] load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load camber data");
      });
    const mark = (beams.find((b) => b.id === beamId) || {}).mark;
    if (mark) {
      api.get("/cylinders", { params: { beam_mark: mark } })
        .then((r) => {
          if (!cancelled) setCylinders(r.data || []);
        })
        .catch((err) => {
          console.error("[camber] cylinders failed", err);
        });
    } else {
      setCylinders([]);
    }
    return () => {
      cancelled = true;
    };
  }, [beamId, beams]);

  const set = (key, value) => setForm({ ...form, [key]: value });

  const measured = parseFloat(form.midspan_in);
  const required = parseFloat(form.required_strength_psi) || 0;
  const release = parseFloat(form.release_strength_psi);
  const strengthOk = Number.isFinite(release) && release >= required && required > 0;

  const save = async () => {
    if (!beamId) {
      toast.error("Select a beam");
      return;
    }
    setSaving(true);
    try {
      await api.post("/camber-readings", {
        beam_id: beamId,
        design_camber_in: parseFloat(form.design_camber_in) || 0,
        measured_camber_in: Number.isFinite(measured) ? measured : 0,
        marked_end_in: parseFloat(form.marked_end_in) || 0,
        midspan_in: Number.isFinite(measured) ? measured : 0,
        unmarked_end_in: parseFloat(form.unmarked_end_in) || 0,
        release_strength_psi: Number.isFinite(release) ? release : 0,
        required_strength_psi: required,
        notes: form.notes,
      });
      toast.success("Camber / strength sheet saved");
      setForm(EMPTY);
      const r = await api.get("/camber-readings", { params: { beam_id: beamId } });
      setHistory(r.data || []);
    } catch (err) {
      console.error("[camber] save failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to save camber reading");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Layout>
      <PageHeader
        title="Camber / Strength Sheet"
        subtitle="Release strength + 3-point camber (Marked / Mid / Unmarked)"
        right={<ARMeasureLink beamId={beamId} purpose="camber" />}
      />
      <div className="p-4 sm:p-6 lg:p-8 grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6 max-w-6xl">
        <div className={`${cardClass} p-5 sm:p-8 space-y-4`}>
          <h3 className="font-display font-bold uppercase tracking-wider text-lg flex items-center gap-2">
            <Ruler className="w-5 h-5 text-primary" /> Record Reading
          </h3>
          <Field label="Beam">
            <select data-testid="camber-beam" value={beamId} onChange={(e) => setBeamId(e.target.value)} className={inputClass}>
              {beams.map((b) => (
                <option key={b.id} value={b.id}>{b.mark} · {b.length_ft} ft</option>
              ))}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Required Strength (psi)">
              <input data-testid="camber-required" type="number" value={form.required_strength_psi} onChange={(e) => set("required_strength_psi", e.target.value)} className={inputClass} />
            </Field>
            <Field label="Release Strength (psi)">
              <input data-testid="camber-release" type="number" value={form.release_strength_psi} onChange={(e) => set("release_strength_psi", e.target.value)} className={inputClass} />
            </Field>
          </div>
          {Number.isFinite(release) && (
            <div
              className="min-h-12 px-4 border rounded-none flex items-center gap-2 font-mono text-sm"
              style={{ borderColor: strengthOk ? "#00E676" : "#FF3366", color: strengthOk ? "#00E676" : "#FF3366" }}
              data-testid="camber-strength-gate"
            >
              {strengthOk ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
              {strengthOk ? "RELEASE STRENGTH MET" : "BELOW REQUIRED STRENGTH"}
            </div>
          )}
          <Field label="Design Camber (in)">
            <input data-testid="camber-design" type="number" step="0.01" value={form.design_camber_in} onChange={(e) => set("design_camber_in", e.target.value)} className={inputClass} />
          </Field>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Field label="Marked End (in)">
              <input data-testid="camber-marked" type="number" step="0.01" value={form.marked_end_in} onChange={(e) => set("marked_end_in", e.target.value)} className={inputClass} />
            </Field>
            <Field label="Midspan (in)">
              <input data-testid="camber-mid" type="number" step="0.01" value={form.midspan_in} onChange={(e) => set("midspan_in", e.target.value)} className={inputClass} />
            </Field>
            <Field label="Unmarked End (in)">
              <input data-testid="camber-unmarked" type="number" step="0.01" value={form.unmarked_end_in} onChange={(e) => set("unmarked_end_in", e.target.value)} className={inputClass} />
            </Field>
          </div>
          <Field label="Notes">
            <textarea data-testid="camber-notes" rows={3} value={form.notes} onChange={(e) => set("notes", e.target.value)} className={`${inputClass} py-2`} />
          </Field>
          <button
            data-testid="camber-save"
            onClick={save}
            disabled={saving}
            className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest rounded-none hover:bg-white hover:text-black transition-colors duration-100 disabled:opacity-60 flex items-center justify-center gap-2"
          >
            {saving && <Loader2 className="w-4 h-4 animate-spin" />} Save Camber Sheet
          </button>
        </div>

        <div className={`${cardClass} p-5 sm:p-8`}>
          <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-4">History</h3>
          <div className="space-y-3" data-testid="camber-history">
            {history.length === 0 && <div className="text-sm text-muted-foreground font-mono">No camber readings for this beam.</div>}
            {history.map((r) => (
              <div key={r.id} className="border border-[#1C2230] rounded-none p-4">
                <div className="flex justify-between font-mono text-xs text-muted-foreground mb-2">
                  <span>{(r.reading_date || r.created_at || "").slice(0, 10)}</span>
                  <span>{r.release_strength_psi} psi</span>
                </div>
                <div className="grid grid-cols-3 gap-2 font-mono text-sm">
                  <div>M {r.marked_end_in ?? "—"}"</div>
                  <div>MID {r.midspan_in ?? r.measured_camber_in}"</div>
                  <div>U {r.unmarked_end_in ?? "—"}"</div>
                </div>
              </div>
            ))}
          </div>
          {cylinders.length > 0 && (
            <div className="mt-6" data-testid="camber-cylinders">
              <h4 className="font-display font-bold uppercase tracking-wider text-sm mb-2">Linked cylinders</h4>
              {cylinders.map((cyl) => (
                <div key={cyl.id} className="border border-[#1C2230] p-3 mb-2 font-mono text-xs">
                  <div className="flex justify-between">
                    <span>{cyl.set_id}</span>
                    <span style={{ color: cyl.release_ok ? "#00E676" : cyl.crush_psi ? "#FFD600" : "#8B93A7" }}>{cyl.status}</span>
                  </div>
                  <div className="text-muted-foreground mt-1">{cyl.crush_psi ? `${cyl.crush_psi} psi` : "No crush yet"}{cyl.required_psi ? ` / req ${cyl.required_psi}` : ""}</div>
                </div>
              ))}
              <Link to="/tags" className="inline-block mt-2 text-[10px] font-mono uppercase tracking-widest text-primary">Open cylinder tags</Link>
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
