import React, { useEffect, useState } from "react";
import api from "../lib/api";
import Layout, { PageHeader } from "../components/Layout";
import { toast } from "sonner";
import { CheckCircle2, XCircle, PauseCircle, ChevronRight, ChevronLeft, Loader2 } from "lucide-react";

const SECTIONS = [
  { key: "pre_pour", label: "Pre-Pour / Forms", desc: "Bed, forms, bulkheads & release agent" },
  { key: "strand", label: "Strand & Tension", desc: "Strand pattern, tensioning & elongation" },
  { key: "concrete", label: "Concrete Placement", desc: "Mix, slump, air, cylinders" },
  { key: "finish", label: "Finish", desc: "Surface finish, dimensions & tolerances" },
  { key: "camber", label: "Camber / Strength", desc: "Release strength & camber at strip" },
  { key: "pre_delivery", label: "Pre-Delivery", desc: "Final inspection before shipment" },
];

const STATUS = [
  { key: "pass", label: "PASS", color: "#00E676", icon: CheckCircle2 },
  { key: "fail", label: "FAIL", color: "#FF3366", icon: XCircle },
  { key: "hold", label: "HOLD", color: "#FFD600", icon: PauseCircle },
];

export default function NewInspection() {
  const [beams, setBeams] = useState([]);
  const [beamId, setBeamId] = useState("");
  const [step, setStep] = useState(0);
  const [results, setResults] = useState({});
  const [notes, setNotes] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/beams").then((r) => { setBeams(r.data); if (r.data.length) setBeamId(r.data[0].id); });
  }, []);

  const section = SECTIONS[step];

  const setStatus = (s) => setResults({ ...results, [section.key]: s });

  const submitSection = async () => {
    const status = results[section.key];
    if (!status) { toast.error("Select a result gate for this section"); return; }
    setSaving(true);
    try {
      await api.post("/inspections", {
        beam_id: beamId,
        section: section.key,
        status,
        notes: notes[section.key] || "",
      });
      // Update beam qc_state on fail/hold/last pass
      if (status === "fail") await api.patch(`/beams/${beamId}`, { qc_state: "failed" });
      else if (status === "hold") await api.patch(`/beams/${beamId}`, { qc_state: "hold" });
      else await api.patch(`/beams/${beamId}`, { qc_state: step === SECTIONS.length - 1 ? "passed" : "in_progress" });

      toast.success(`${section.label} recorded — ${status.toUpperCase()}`);
      if (step < SECTIONS.length - 1) setStep(step + 1);
      else toast.success("Inspection complete for this beam");
    } catch {
      toast.error("Failed to save section");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Layout>
      <PageHeader title="Guided Inspection (QIR)" subtitle="Multi-state tolerance gates · QIR 2026.6.1" />
      <div className="p-8 max-w-4xl">
        {/* Beam selector + stepper */}
        <div className="bg-card border border-border rounded-sm p-6 mb-6">
          <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Beam Under Inspection</label>
          <select data-testid="inspection-beam-select" value={beamId} onChange={(e)=>setBeamId(e.target.value)} className="mt-2 w-full bg-background border border-border rounded-sm px-4 min-h-12 font-mono text-sm md:max-w-sm">
            {beams.map((b)=><option key={b.id} value={b.id}>{b.mark} · {b.twin_type==="box_beam"?"Box":"I-Beam"} · {b.length_ft}ft</option>)}
          </select>

          <div className="flex items-center gap-1 mt-6 overflow-x-auto pb-2" data-testid="inspection-stepper">
            {SECTIONS.map((sec, i) => {
              const done = results[sec.key];
              const active = i === step;
              const color = done === "fail" ? "#FF3366" : done === "hold" ? "#FFD600" : done ? "#00E676" : active ? "#2979FF" : "#222631";
              return (
                <React.Fragment key={sec.key}>
                  <button onClick={()=>setStep(i)} className="flex flex-col items-center min-w-16 shrink-0">
                    <span className="w-9 h-9 rounded-sm flex items-center justify-center font-mono font-bold text-sm border-2" style={{ borderColor: color, color: active||done?color:"#8B949E" }}>{i+1}</span>
                  </button>
                  {i < SECTIONS.length-1 && <div className="h-0.5 flex-1 min-w-4" style={{ background: done?color:"#222631" }} />}
                </React.Fragment>
              );
            })}
          </div>
        </div>

        {/* Current section */}
        <div className="bg-card border border-border rounded-sm p-8" data-testid="inspection-section-card">
          <div className="text-xs font-mono text-primary tracking-widest">SECTION {step+1} / {SECTIONS.length}</div>
          <h2 className="font-display font-extrabold text-3xl uppercase tracking-tight mt-1">{section.label}</h2>
          <p className="text-muted-foreground mt-2">{section.desc}</p>

          <div className="grid grid-cols-3 gap-3 mt-8">
            {STATUS.map((st) => {
              const Icon = st.icon;
              const selected = results[section.key] === st.key;
              return (
                <button
                  key={st.key}
                  data-testid={`gate-${st.key}`}
                  onClick={()=>setStatus(st.key)}
                  className="min-h-24 rounded-sm border-2 flex flex-col items-center justify-center gap-2 font-display font-bold uppercase tracking-widest transition-colors duration-100"
                  style={{ borderColor: selected?st.color:"#222631", background: selected?st.color+"1A":"transparent", color: selected?st.color:"#8B949E" }}
                >
                  <Icon className="w-8 h-8" /> {st.label}
                </button>
              );
            })}
          </div>

          <textarea
            data-testid="inspection-notes"
            placeholder="Measurements, tolerance readings, observations…"
            value={notes[section.key]||""}
            onChange={(e)=>setNotes({...notes,[section.key]:e.target.value})}
            rows={4}
            className="mt-6 w-full bg-background border border-border rounded-sm px-4 py-3 font-mono text-sm"
          />

          <div className="flex items-center justify-between mt-6">
            <button disabled={step===0} onClick={()=>setStep(step-1)} className="min-h-12 px-5 border border-border rounded-sm flex items-center gap-2 font-semibold uppercase tracking-wider disabled:opacity-40 hover:border-primary transition-colors duration-100">
              <ChevronLeft className="w-4 h-4" /> Back
            </button>
            <button data-testid="save-section" disabled={saving} onClick={submitSection} className="min-h-12 px-6 bg-primary text-white rounded-sm flex items-center gap-2 font-display font-bold uppercase tracking-widest hover:bg-white hover:text-black transition-colors duration-100 disabled:opacity-60">
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              {step===SECTIONS.length-1?"Finish":"Save & Next"} <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </Layout>
  );
}
