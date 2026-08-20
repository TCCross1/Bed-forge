import React, { useEffect, useState } from "react";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, Field, inputClass, cardClass, ARMeasureLink } from "../components/Layout";
import { toast } from "sonner";
import { CheckCircle2, XCircle, PauseCircle, ChevronRight, ChevronLeft, Loader2 } from "lucide-react";
import { pickBeamId, useBeamQuery } from "../lib/useBeamQuery";
import { toastNcrFromResponse } from "../lib/ncr";
import { useOpenJob } from "../context/OpenJobContext";
import { jobListParams } from "../lib/jobAccess";

const SECTIONS = [
  {
    key: "layout",
    label: "Layout",
    desc: "Bed setup, forms, bulkheads, length & alignment",
    checks: [
      { key: "bed_clean", label: "Bed cleaned & inspected" },
      { key: "forms_aligned", label: "Side forms aligned & locked" },
      { key: "bulkheads_square", label: "Bulkheads square to bed" },
      { key: "length_verified", label: "Product length verified" },
      { key: "release_agent", label: "Release agent applied" },
      { key: "inserts_located", label: "Inserts / embeds located per drawing" },
    ],
  },
  {
    key: "reinforcement",
    label: "Reinforcement",
    desc: "Strand pattern, rebar, stirrups, chairs & cover",
    checks: [
      { key: "strand_pattern", label: "Strand pattern matches shop drawing" },
      { key: "strand_condition", label: "Strand condition / rust acceptable" },
      { key: "rebar_grade", label: "Rebar grade & size confirmed" },
      { key: "stirrup_spacing", label: "Stirrup spacing within tolerance" },
      { key: "cover_ok", label: "Concrete cover maintained" },
      { key: "chairs_tied", label: "Chairs / ties secure" },
    ],
  },
  {
    key: "casting",
    label: "Casting",
    desc: "Placement, vibration, temperature & weather",
    checks: [
      { key: "mix_id", label: "Approved mix ID on ticket" },
      { key: "placement_continuous", label: "Placement continuous / no cold joints" },
      { key: "vibration_ok", label: "Vibration adequate — no honeycomb risk" },
      { key: "weather_ok", label: "Weather / ambient within spec" },
      { key: "screed_finish", label: "Screed / strike-off complete" },
    ],
    fields: [
      { key: "mix_id_value", label: "Mix ID", type: "text" },
      { key: "placement_start", label: "Placement Start", type: "time" },
      { key: "placement_end", label: "Placement End", type: "time" },
      { key: "ambient_f", label: "Ambient °F", type: "number" },
    ],
  },
  {
    key: "concrete_testing",
    label: "Concrete Testing",
    desc: "Slump, air, temperature, cylinders & unit weight",
    checks: [
      { key: "slump_in_spec", label: "Slump within specification" },
      { key: "air_in_spec", label: "Air content within specification" },
      { key: "cylinders_cast", label: "Cylinders cast & labeled" },
    ],
    fields: [
      { key: "slump_in", label: "Slump (in)", type: "number" },
      { key: "air_pct", label: "Air (%)", type: "number" },
      { key: "concrete_temp_f", label: "Concrete Temp °F", type: "number" },
      { key: "unit_weight", label: "Unit Weight (pcf)", type: "number" },
      { key: "cylinder_set", label: "Cylinder Set ID", type: "text" },
    ],
  },
  {
    key: "post_production",
    label: "Post-Production",
    desc: "Strip, release strength, strand cut & camber",
    checks: [
      { key: "release_strength_met", label: "Release strength met before detension" },
      { key: "strand_cut_ok", label: "Strand cut / recessed per spec" },
      { key: "camber_recorded", label: "Camber recorded at strip" },
      { key: "no_damage", label: "No handling damage at strip" },
    ],
    fields: [
      { key: "strip_time", label: "Strip Time", type: "time" },
      { key: "release_psi", label: "Release Strength (psi)", type: "number" },
      { key: "required_psi", label: "Required Strength (psi)", type: "number" },
    ],
  },
  {
    key: "detailing",
    label: "Detailing",
    desc: "Marked End ID, hardware, finish & lifting devices",
    checks: [
      { key: "marked_end_id", label: "Marked End ID applied & legible" },
      { key: "hardware_complete", label: "Hardware / inserts complete" },
      { key: "surface_finish", label: "Surface finish accepted" },
      { key: "lifting_ok", label: "Lifting devices inspected" },
      { key: "dimensions_ok", label: "Final dimensions within tolerance" },
    ],
    fields: [
      { key: "marked_end_value", label: "Marked End ID", type: "text" },
    ],
  },
];

const STATUS = [
  { key: "pass", label: "PASS", color: "#00E676", icon: CheckCircle2 },
  { key: "fail", label: "FAIL", color: "#FF3366", icon: XCircle },
  { key: "hold", label: "HOLD", color: "#FFD600", icon: PauseCircle },
];

export default function NewInspection() {
  const queryBeam = useBeamQuery();
  const { openJob } = useOpenJob();
  const [beams, setBeams] = useState([]);
  const [beamId, setBeamId] = useState(queryBeam);
  const [step, setStep] = useState(0);
  const [results, setResults] = useState({});
  const [notes, setNotes] = useState({});
  const [checks, setChecks] = useState({});
  const [fields, setFields] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/beams", { params: jobListParams(openJob) })
      .then((r) => {
        setBeams(r.data);
        setBeamId((current) => pickBeamId(current, queryBeam, r.data));
      })
      .catch((err) => {
        console.error("[inspection] beams load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load beams");
      });
  }, [queryBeam, openJob?.id]);

  const section = SECTIONS[step];
  const sectionChecks = checks[section.key] || {};
  const sectionFields = fields[section.key] || {};

  const toggleCheck = (key) => {
    setChecks({
      ...checks,
      [section.key]: { ...sectionChecks, [key]: !sectionChecks[key] },
    });
  };

  const setField = (key, value) => {
    setFields({
      ...fields,
      [section.key]: { ...sectionFields, [key]: value },
    });
  };

  const setStatus = (s) => setResults({ ...results, [section.key]: s });

  const submitSection = async () => {
    const status = results[section.key];
    if (!status) {
      toast.error("Select a result gate for this section");
      return;
    }
    if (!beamId) {
      toast.error("Select a beam under inspection");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post("/inspections", {
        beam_id: beamId,
        section: section.key,
        status,
        notes: notes[section.key] || "",
        data: {
          checks: sectionChecks,
          fields: sectionFields,
        },
      });
      if (status === "fail") await api.patch(`/beams/${beamId}`, { qc_state: "failed" });
      else if (status === "hold") await api.patch(`/beams/${beamId}`, { qc_state: "hold" });
      else await api.patch(`/beams/${beamId}`, { qc_state: step === SECTIONS.length - 1 ? "passed" : "in_progress" });

      toast.success(`${section.label} recorded — ${status.toUpperCase()}`);
      toastNcrFromResponse(data);
      if (step < SECTIONS.length - 1) setStep(step + 1);
      else toast.success("Inspection complete for this beam");
    } catch (err) {
      console.error("[inspection] save section failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to save section");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Layout>
      <PageHeader
        title="Guided Inspection (QIR)"
        subtitle="Prestress form sections · QIR 2026.6.1"
        right={<ARMeasureLink beamId={beamId} purpose="layout" />}
      />
      <div className="p-4 sm:p-6 lg:p-8 max-w-4xl">
        <div className={`${cardClass} p-4 sm:p-6 mb-4 sm:mb-6`}>
          <Field label="Beam Under Inspection">
            <select
              data-testid="inspection-beam-select"
              value={beamId}
              onChange={(e) => setBeamId(e.target.value)}
              className={`${inputClass} md:max-w-sm`}
            >
              {beams.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.mark} · {b.twin_type === "box_beam" ? "Box" : "I-Beam"} · {b.length_ft}ft
                </option>
              ))}
            </select>
          </Field>

          <div className="flex items-center gap-1 mt-6 overflow-x-auto pb-2" data-testid="inspection-stepper">
            {SECTIONS.map((sec, i) => {
              const done = results[sec.key];
              const active = i === step;
              const color = done === "fail" ? "#FF3366" : done === "hold" ? "#FFD600" : done ? "#00E676" : active ? "#2979FF" : "#1C2230";
              return (
                <React.Fragment key={sec.key}>
                  <button type="button" onClick={() => setStep(i)} className="flex flex-col items-center min-w-14 shrink-0">
                    <span
                      className="w-9 h-9 rounded-none flex items-center justify-center font-mono font-bold text-sm border-2"
                      style={{ borderColor: color, color: active || done ? color : "#8B949E" }}
                    >
                      {i + 1}
                    </span>
                    <span className="text-[9px] font-condensed uppercase tracking-wider mt-1 text-muted-foreground hidden sm:block">{sec.label}</span>
                  </button>
                  {i < SECTIONS.length - 1 && <div className="h-0.5 flex-1 min-w-4" style={{ background: done ? color : "#1C2230" }} />}
                </React.Fragment>
              );
            })}
          </div>
        </div>

        <div className={`${cardClass} p-5 sm:p-8`} data-testid="inspection-section-card">
          <div className="text-xs font-mono text-primary tracking-widest">SECTION {step + 1} / {SECTIONS.length}</div>
          <h2 className="font-display font-extrabold text-2xl sm:text-3xl uppercase tracking-tight mt-1">{section.label}</h2>
          <p className="text-muted-foreground mt-2 text-sm sm:text-base">{section.desc}</p>

          <div className="mt-6 space-y-2">
            {section.checks.map((c) => (
              <button
                type="button"
                key={c.key}
                data-testid={`check-${c.key}`}
                onClick={() => toggleCheck(c.key)}
                className={`w-full min-h-12 px-4 border rounded-none flex items-center justify-between text-left transition-colors duration-100 ${
                  sectionChecks[c.key] ? "border-[#00E676] text-[#00E676]" : "border-[#1C2230] text-muted-foreground"
                }`}
              >
                <span className="text-sm font-medium">{c.label}</span>
                <span className="font-mono text-xs">{sectionChecks[c.key] ? "YES" : "NO"}</span>
              </button>
            ))}
          </div>

          {section.fields && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-6">
              {section.fields.map((f) => (
                <Field key={f.key} label={f.label}>
                  <input
                    data-testid={`field-${f.key}`}
                    type={f.type}
                    value={sectionFields[f.key] || ""}
                    onChange={(e) => setField(f.key, e.target.value)}
                    className={inputClass}
                  />
                </Field>
              ))}
            </div>
          )}

          <div className="grid grid-cols-3 gap-2 sm:gap-3 mt-8">
            {STATUS.map((st) => {
              const Icon = st.icon;
              const selected = results[section.key] === st.key;
              return (
                <button
                  key={st.key}
                  data-testid={`gate-${st.key}`}
                  onClick={() => setStatus(st.key)}
                  className="min-h-20 sm:min-h-24 rounded-none border-2 flex flex-col items-center justify-center gap-2 font-display font-bold uppercase tracking-widest transition-colors duration-100"
                  style={{
                    borderColor: selected ? st.color : "#1C2230",
                    background: selected ? `${st.color}1A` : "transparent",
                    color: selected ? st.color : "#8B949E",
                  }}
                >
                  <Icon className="w-6 h-6 sm:w-8 sm:h-8" /> {st.label}
                </button>
              );
            })}
          </div>

          <textarea
            data-testid="inspection-notes"
            placeholder="Measurements, tolerance readings, observations…"
            value={notes[section.key] || ""}
            onChange={(e) => setNotes({ ...notes, [section.key]: e.target.value })}
            rows={4}
            className={`${inputClass} mt-6 py-3`}
          />

          <div className="flex items-center justify-between mt-6 gap-3">
            <button
              disabled={step === 0}
              onClick={() => setStep(step - 1)}
              className="min-h-12 px-4 sm:px-5 border border-[#1C2230] rounded-none flex items-center gap-2 font-semibold uppercase tracking-wider disabled:opacity-40 hover:border-primary transition-colors duration-100"
            >
              <ChevronLeft className="w-4 h-4" /> Back
            </button>
            <button
              data-testid="save-section"
              disabled={saving}
              onClick={submitSection}
              className="min-h-12 px-4 sm:px-6 bg-primary text-white rounded-none flex items-center gap-2 font-display font-bold uppercase tracking-widest hover:bg-white hover:text-black transition-colors duration-100 disabled:opacity-60"
            >
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              {step === SECTIONS.length - 1 ? "Finish" : "Save & Next"} <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </Layout>
  );
}
