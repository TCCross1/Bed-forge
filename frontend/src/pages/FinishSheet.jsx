import React, { useEffect, useState } from "react";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, Field, inputClass, cardClass } from "../components/Layout";
import { toast } from "sonner";
import { toastNcrFromResponse } from "../lib/ncr";
import { Loader2, Sparkles } from "lucide-react";
import { pickBeamId, useBeamQuery } from "../lib/useBeamQuery";

const CHECKS = [
  { key: "strand_cut_flush", label: "Strands cut flush" },
  { key: "strand_recessed", label: "Strands recessed" },
  { key: "strand_grouted", label: "Strand pockets grouted" },
  { key: "hardware_complete", label: "Hardware complete" },
  { key: "surface_pass", label: "Surface finish accepted" },
  { key: "marked_end_verified", label: "Marked End ID verified" },
  { key: "lifting_devices_ok", label: "Lifting devices OK" },
  { key: "voids_grouted", label: "Voids grouted" },
];

const EMPTY = {
  strand_cut_flush: false,
  strand_recessed: false,
  strand_grouted: false,
  strand_treatment_notes: "",
  hardware_complete: false,
  hardware_notes: "",
  surface_finish: "trowel",
  surface_pass: false,
  surface_notes: "",
  marked_end_id: "",
  marked_end_verified: false,
  lifting_devices_ok: false,
  voids_grouted: false,
  status: "pass",
  notes: "",
};

export default function FinishSheet() {
  const queryBeam = useBeamQuery();
  const [beams, setBeams] = useState([]);
  const [beamId, setBeamId] = useState(queryBeam);
  const [form, setForm] = useState(EMPTY);
  const [history, setHistory] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get("/beams")
      .then((r) => {
        if (cancelled) return;
        setBeams(r.data);
        setBeamId((current) => pickBeamId(current, queryBeam, r.data));
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[finish] beams load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load beams");
      });
    return () => {
      cancelled = true;
    };
  }, [queryBeam]);

  useEffect(() => {
    if (!beamId) return undefined;
    let cancelled = false;
    api.get("/finish-sheets", { params: { beam_id: beamId } })
      .then((r) => {
        if (!cancelled) setHistory(r.data || []);
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[finish] history load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load finish sheets");
      });
    api.get(`/beams/${beamId}`)
      .then((r) => {
        if (cancelled) return;
        const me = r.data?.spec?.marked_end_id || "";
        if (me) setForm((cur) => ({ ...cur, marked_end_id: cur.marked_end_id || me }));
      })
      .catch((err) => console.error("[finish] spec prefill failed", err));
    return () => {
      cancelled = true;
    };
  }, [beamId]);

  const toggle = (key) => setForm({ ...form, [key]: !form[key] });

  const save = async () => {
    if (!beamId) {
      toast.error("Select a beam");
      return;
    }
    if (!form.marked_end_id.trim()) {
      toast.error("Marked End ID is required");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post("/finish-sheets", { ...form, beam_id: beamId });
      toast.success("Finish sheet saved");
      toastNcrFromResponse(data);
      setForm({ ...EMPTY, marked_end_id: form.marked_end_id });
      const r = await api.get("/finish-sheets", { params: { beam_id: beamId } });
      setHistory(r.data || []);
    } catch (err) {
      console.error("[finish] save failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to save finish sheet");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Layout>
      <PageHeader title="Finish Sheet" subtitle="Post-pour checklist · strand treatment, hardware, surface, Marked End ID" />
      <div className="p-4 sm:p-6 lg:p-8 grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6 max-w-6xl">
        <div className={`${cardClass} p-5 sm:p-8 space-y-4`}>
          <h3 className="font-display font-bold uppercase tracking-wider text-lg flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-primary" /> Post-Pour Checklist
          </h3>
          <Field label="Beam">
            <select data-testid="finish-beam" value={beamId} onChange={(e) => setBeamId(e.target.value)} className={inputClass}>
              {beams.map((b) => (
                <option key={b.id} value={b.id}>{b.mark}</option>
              ))}
            </select>
          </Field>
          <div className="space-y-2">
            {CHECKS.map((c) => (
              <button
                type="button"
                key={c.key}
                data-testid={`finish-${c.key}`}
                onClick={() => toggle(c.key)}
                className={`w-full min-h-12 px-4 border rounded-none flex items-center justify-between ${
                  form[c.key] ? "border-[#00E676] text-[#00E676]" : "border-[#1C2230] text-muted-foreground"
                }`}
              >
                <span className="text-sm">{c.label}</span>
                <span className="font-mono text-xs">{form[c.key] ? "YES" : "NO"}</span>
              </button>
            ))}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Surface Finish">
              <select data-testid="finish-surface" value={form.surface_finish} onChange={(e) => setForm({ ...form, surface_finish: e.target.value })} className={inputClass}>
                <option value="trowel">Trowel</option>
                <option value="broom">Broom</option>
                <option value="other">Other</option>
              </select>
            </Field>
            <Field label="Result Gate">
              <select data-testid="finish-status" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} className={inputClass}>
                <option value="pass">PASS</option>
                <option value="fail">FAIL</option>
                <option value="hold">HOLD</option>
              </select>
            </Field>
          </div>
          <Field label="Marked End ID">
            <input data-testid="finish-marked-end" value={form.marked_end_id} onChange={(e) => setForm({ ...form, marked_end_id: e.target.value })} className={inputClass} />
          </Field>
          <Field label="Strand Treatment Notes">
            <textarea data-testid="finish-strand-notes" rows={2} value={form.strand_treatment_notes} onChange={(e) => setForm({ ...form, strand_treatment_notes: e.target.value })} className={`${inputClass} py-2`} />
          </Field>
          <Field label="Hardware Notes">
            <textarea data-testid="finish-hardware-notes" rows={2} value={form.hardware_notes} onChange={(e) => setForm({ ...form, hardware_notes: e.target.value })} className={`${inputClass} py-2`} />
          </Field>
          <Field label="Surface Notes">
            <textarea data-testid="finish-surface-notes" rows={2} value={form.surface_notes} onChange={(e) => setForm({ ...form, surface_notes: e.target.value })} className={`${inputClass} py-2`} />
          </Field>
          <Field label="General Notes">
            <textarea data-testid="finish-notes" rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className={`${inputClass} py-2`} />
          </Field>
          <button
            data-testid="finish-save"
            onClick={save}
            disabled={saving}
            className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest rounded-none hover:bg-white hover:text-black transition-colors duration-100 disabled:opacity-60 flex items-center justify-center gap-2"
          >
            {saving && <Loader2 className="w-4 h-4 animate-spin" />} Save Finish Sheet
          </button>
        </div>

        <div className={`${cardClass} p-5 sm:p-8`}>
          <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-4">Saved Sheets</h3>
          <div className="space-y-3" data-testid="finish-history">
            {history.length === 0 && <div className="text-sm text-muted-foreground font-mono">No finish sheets for this beam.</div>}
            {history.map((s) => (
              <div key={s.id} className="border border-[#1C2230] rounded-none p-4">
                <div className="flex justify-between items-center">
                  <span className="font-mono text-sm font-bold">{s.marked_end_id || "NO ID"}</span>
                  <span className="font-mono text-xs uppercase" style={{ color: s.status === "pass" ? "#00E676" : s.status === "fail" ? "#FF3366" : "#FFD600" }}>
                    {s.status}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground font-mono mt-1">{(s.created_at || "").slice(0, 16)} · {s.inspector}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Layout>
  );
}
