import React, { useEffect, useState } from "react";
import api from "../lib/api";
import Layout, { PageHeader } from "../components/Layout";
import { Loader2, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { useOpenJob } from "../context/OpenJobContext";
import { jobListParams } from "../lib/jobAccess";

const STATES = ["open", "investigation", "corrective_action", "verification", "closed"];

export default function NCRBoard() {
  const { openJob } = useOpenJob();
  const [ncrs, setNcrs] = useState([]);
  const [beams, setBeams] = useState([]);
  const [form, setForm] = useState({ title: "", severity: "major", beam_id: "", owner: "" });
  const [saving, setSaving] = useState(false);

  const load = () => Promise.all([api.get("/ncrs"), api.get("/beams", { params: jobListParams(openJob) })]).then(([ncrRes, beamRes]) => {
    setNcrs(ncrRes.data);
    setBeams(beamRes.data);
    setForm((current) => ({ ...current, beam_id: current.beam_id || beamRes.data[0]?.id || "" }));
  });

  useEffect(() => { load(); }, [openJob?.id]);

  const create = async () => {
    if (!form.title || !form.beam_id) return toast.error("Title and beam are required");
    setSaving(true);
    try {
      await api.post("/ncrs", form);
      setForm({ title: "", severity: "major", beam_id: beams[0]?.id || "", owner: "" });
      await load();
      toast.success("NCR created");
    } catch {
      toast.error("Failed to create NCR");
    } finally {
      setSaving(false);
    }
  };

  const advance = async (item, nextStatus) => {
    await api.patch(`/ncrs/${item.id}`, { status: nextStatus });
    await load();
  };

  return (
    <Layout>
      <PageHeader title="NCR Board" subtitle="Open → Investigation → Corrective Action → Verification → Closed" />
      <div className="p-8 grid grid-cols-1 xl:grid-cols-4 gap-6">
        <div className="xl:col-span-1 bg-card border border-border rounded-sm p-6 space-y-4">
          <h3 className="font-display font-bold uppercase tracking-wider text-lg">Create NCR</h3>
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Title" className="w-full bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm" />
          <select value={form.beam_id} onChange={(e) => setForm({ ...form, beam_id: e.target.value })} className="w-full bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm">
            {beams.map((beam) => <option key={beam.id} value={beam.id}>{beam.mark}</option>)}
          </select>
          <select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })} className="w-full bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm">
            {['minor','moderate','major'].map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <input value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} placeholder="Owner" className="w-full bg-background border border-border rounded-sm px-3 min-h-12 font-mono text-sm" />
          <button onClick={create} disabled={saving} className="w-full min-h-12 bg-primary text-white rounded-sm font-display font-bold uppercase tracking-widest">{saving ? "Saving" : "Create NCR"}</button>
        </div>
        <div className="xl:col-span-3 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4">
          {STATES.map((state) => (
            <div key={state} className="bg-card border border-border rounded-sm p-4 space-y-3">
              <div className="font-display font-bold uppercase tracking-wide text-sm">{state.replace(/_/g, " ")}</div>
              {ncrs.filter((item) => item.status === state).map((item) => (
                <div key={item.id} className="border border-border rounded-sm p-3 space-y-2">
                  <div className="flex items-start gap-2"><ShieldAlert className="w-4 h-4 text-primary mt-0.5" /><div><div className="font-mono text-xs text-primary">{item.code}</div><div className="font-semibold text-sm">{item.title}</div></div></div>
                  <div className="text-xs text-muted-foreground font-mono">Owner: {item.owner || "—"}</div>
                  <div className="text-xs text-muted-foreground font-mono">Severity: {item.severity}</div>
                  {state !== "closed" && (
                    <button onClick={() => advance(item, STATES[Math.min(STATES.indexOf(state) + 1, STATES.length - 1)])} className="w-full min-h-10 border border-border rounded-sm text-xs font-mono uppercase tracking-wider hover:border-primary hover:text-primary">Advance</button>
                  )}
                </div>
              ))}
              {ncrs.filter((item) => item.status === state).length === 0 && <div className="text-xs text-muted-foreground font-mono">No NCRs</div>}
            </div>
          ))}
        </div>
      </div>
    </Layout>
  );
}
