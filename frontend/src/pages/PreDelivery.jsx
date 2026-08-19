import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, Field, inputClass, cardClass } from "../components/Layout";
import { toast } from "sonner";
import { Loader2, Truck } from "lucide-react";
import { pickBeamId, useBeamQuery } from "../lib/useBeamQuery";
import { useAuth } from "../context/AuthContext";
import { toastNcrFromError, toastNcrFromResponse } from "../lib/ncr";

const CHECKS = [
  { key: "dimensional_check", label: "Dimensional check complete" },
  { key: "camber_verified", label: "Camber verified" },
  { key: "finish_complete", label: "Finish sheet complete" },
  { key: "hardware_installed", label: "Hardware installed" },
  { key: "marked_end_id_verified", label: "Marked End ID verified" },
  { key: "cracks_documented", label: "Cracks / anomalies documented" },
];

const EMPTY = {
  dimensional_check: false,
  camber_verified: false,
  finish_complete: false,
  hardware_installed: false,
  marked_end_id_verified: false,
  cracks_documented: false,
  truck_number: "",
  destination: "",
  load_position: "",
  qc_signoff: "",
  production_signoff: "",
  carrier_signoff: "",
  notes: "",
};

export default function PreDelivery() {
  const { user } = useAuth();
  const queryBeam = useBeamQuery();
  const [beams, setBeams] = useState([]);
  const [beamId, setBeamId] = useState(queryBeam);
  const [form, setForm] = useState({ ...EMPTY, qc_signoff: user?.name || "" });
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
        console.error("[pre-delivery] beams load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load beams");
      });
    return () => {
      cancelled = true;
    };
  }, [queryBeam]);

  useEffect(() => {
    if (!beamId) return undefined;
    let cancelled = false;
    api.get("/pre-delivery", { params: { beam_id: beamId } })
      .then((r) => {
        if (!cancelled) setHistory(r.data || []);
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[pre-delivery] history load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load pre-delivery records");
      });
    return () => {
      cancelled = true;
    };
  }, [beamId]);

  const toggle = (key) => setForm({ ...form, [key]: !form[key] });
  const allChecks = CHECKS.every((c) => form[c.key]);
  const allSigns = form.qc_signoff.trim() && form.production_signoff.trim() && form.carrier_signoff.trim();

  const save = async (released) => {
    if (!beamId) {
      toast.error("Select a beam");
      return;
    }
    if (released && (!allChecks || !allSigns || !form.truck_number.trim() || !form.destination.trim())) {
      toast.error("Complete checks, truck/destination, and all three sign-offs before release");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post("/pre-delivery", {
        ...form,
        beam_id: beamId,
        released,
      });
      toast.success(released ? "Beam released for delivery" : "Pre-delivery record saved");
      toastNcrFromResponse(data);
      const r = await api.get("/pre-delivery", { params: { beam_id: beamId } });
      setHistory(r.data || []);
    } catch (err) {
      console.error("[pre-delivery] save failed", err);
      toastNcrFromError(err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to save pre-delivery");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Layout>
      <PageHeader title="Pre-Delivery / Release" subtitle="Final checks · truck & destination · multi-party sign-off · cylinder crush" right={<Link to="/tags" className="min-h-12 px-4 border border-[#1C2230] font-semibold uppercase tracking-wider text-sm hover:border-primary hover:text-primary">Cylinder tags</Link>} />
      <div className="p-4 sm:p-6 lg:p-8 grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6 max-w-6xl">
        <div className={`${cardClass} p-5 sm:p-8 space-y-4`}>
          <h3 className="font-display font-bold uppercase tracking-wider text-lg flex items-center gap-2">
            <Truck className="w-5 h-5 text-primary" /> Final Checks
          </h3>
          <Field label="Beam">
            <select data-testid="pd-beam" value={beamId} onChange={(e) => setBeamId(e.target.value)} className={inputClass}>
              {beams.map((b) => (
                <option key={b.id} value={b.id}>{b.mark} · {b.qc_state}</option>
              ))}
            </select>
          </Field>
          <div className="space-y-2">
            {CHECKS.map((c) => (
              <button
                type="button"
                key={c.key}
                data-testid={`pd-${c.key}`}
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
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Field label="Truck #">
              <input data-testid="pd-truck" value={form.truck_number} onChange={(e) => setForm({ ...form, truck_number: e.target.value })} className={inputClass} />
            </Field>
            <Field label="Destination">
              <input data-testid="pd-destination" value={form.destination} onChange={(e) => setForm({ ...form, destination: e.target.value })} className={inputClass} />
            </Field>
            <Field label="Load Position">
              <input data-testid="pd-load" value={form.load_position} onChange={(e) => setForm({ ...form, load_position: e.target.value })} className={inputClass} />
            </Field>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Field label="QC Sign-off">
              <input data-testid="pd-qc" value={form.qc_signoff} onChange={(e) => setForm({ ...form, qc_signoff: e.target.value })} className={inputClass} />
            </Field>
            <Field label="Production Sign-off">
              <input data-testid="pd-prod" value={form.production_signoff} onChange={(e) => setForm({ ...form, production_signoff: e.target.value })} className={inputClass} />
            </Field>
            <Field label="Carrier Sign-off">
              <input data-testid="pd-carrier" value={form.carrier_signoff} onChange={(e) => setForm({ ...form, carrier_signoff: e.target.value })} className={inputClass} />
            </Field>
          </div>
          <Field label="Notes">
            <textarea data-testid="pd-notes" rows={3} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className={`${inputClass} py-2`} />
          </Field>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <button
              data-testid="pd-save"
              onClick={() => save(false)}
              disabled={saving}
              className="min-h-12 border border-[#1C2230] rounded-none font-semibold uppercase tracking-wider hover:border-primary hover:text-primary disabled:opacity-60"
            >
              Save Draft
            </button>
            <button
              data-testid="pd-release"
              onClick={() => save(true)}
              disabled={saving}
              className="min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest rounded-none hover:bg-white hover:text-black transition-colors duration-100 disabled:opacity-60 flex items-center justify-center gap-2"
            >
              {saving && <Loader2 className="w-4 h-4 animate-spin" />} Release Beam
            </button>
          </div>
        </div>

        <div className={`${cardClass} p-5 sm:p-8`}>
          <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-4">Release History</h3>
          <div className="space-y-3" data-testid="pd-history">
            {history.length === 0 && <div className="text-sm text-muted-foreground font-mono">No pre-delivery records for this beam.</div>}
            {history.map((r) => (
              <div key={r.id} className="border border-[#1C2230] rounded-none p-4">
                <div className="flex justify-between items-center">
                  <span className="font-mono text-sm">{r.truck_number || "NO TRUCK"} → {r.destination || "—"}</span>
                  <span className="font-mono text-xs uppercase" style={{ color: r.released ? "#00E676" : "#FFD600" }}>
                    {r.released ? "RELEASED" : "DRAFT"}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground font-mono mt-1">
                  QC {r.qc_signoff || "—"} · PROD {r.production_signoff || "—"} · CARRIER {r.carrier_signoff || "—"}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Layout>
  );
}
