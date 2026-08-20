import React, { useEffect, useMemo, useState } from "react";
import { Download, FlaskConical, Loader2, ShieldCheck, Sparkles } from "lucide-react";
import { toast } from "sonner";
import api, { API, formatApiErrorDetail } from "../lib/api";
import Layout, { Field, PageHeader, cardClass, inputClass } from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import { useOpenJob } from "../context/OpenJobContext";
import { isPlantManager } from "../lib/jobAccess";
import { emptyIntelligenceQuery, envelopeToTicketText } from "../lib/batchPlant";

const TEAL = "#2EE6D6";
const ORANGE = "#FF6B1A";
const GOLD = "#C9A227";

function num(value) {
  if (value === "" || value == null) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function DriverChip({ driver }) {
  if (!driver) return null;
  const on = Boolean(driver.used);
  return (
    <div
      data-testid={`mix-intel-driver-${driver.id}`}
      className="min-h-12 px-3 border flex flex-col justify-center"
      style={{
        borderColor: on ? TEAL : "#1C2230",
        background: on ? "rgba(46,230,214,0.08)" : "rgba(10,12,16,0.6)",
        boxShadow: on ? "0 0 18px rgba(46,230,214,0.12)" : "none",
      }}
    >
      <div className="text-[10px] font-mono uppercase tracking-[0.2em]" style={{ color: on ? TEAL : "#8B93A7" }}>
        {on ? "Used" : "Not in score"}
      </div>
      <div className="font-display font-bold uppercase tracking-wider text-sm">{driver.label}</div>
      <div className="text-[11px] text-muted-foreground leading-snug">{driver.detail}</div>
    </div>
  );
}

export default function BatchPlant() {
  const { user } = useAuth();
  const { openJob } = useOpenJob();
  const manager = isPlantManager(user?.role);
  const [records, setRecords] = useState([]);
  const [pours, setPours] = useState([]);
  const [beams, setBeams] = useState([]);
  const [busy, setBusy] = useState("");
  const [intel, setIntel] = useState(null);
  const [form, setForm] = useState({
    pour_id: "",
    ticket_number: "",
    mix_design: "8500psi HPC",
    ambient_temp_f: 75,
    concrete_temp_f: 72,
    humidity_pct: 55,
    wind_mph: 5,
    weather: "Clear",
    notes: "",
    ingredientsText: "Type III Cement|940|938\nCoarse Aggregate|1780|1788",
    admixturesText: "Mid-range Water Reducer|112",
    cylindersText: "CYL-NEW-A|18|6100",
  });
  const [query, setQuery] = useState(() => emptyIntelligenceQuery({ mix_design: "8500psi HPC", ambient_temp_f: 75, humidity_pct: 55 }));

  const parseLines = (text, keys) =>
    text
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const parts = line.split("|").map((item) => item.trim());
        return Object.fromEntries(keys.map((key, index) => [key, parts[index] || ""]));
      });

  const load = () =>
    Promise.all([api.get("/batch-records"), api.get("/pours"), api.get("/beams")]).then(([recordsRes, poursRes, beamsRes]) => {
      setRecords(recordsRes.data || []);
      setPours(poursRes.data || []);
      setBeams(beamsRes.data || []);
      setForm((current) => ({ ...current, pour_id: current.pour_id || poursRes.data[0]?.id || "" }));
    });

  useEffect(() => {
    load().catch((err) => {
      console.error("[batch] load failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load batch plant");
    });
  }, []);

  const drivers = useMemo(() => Object.values(intel?.drivers || {}), [intel]);
  const insufficient = intel?.status === "insufficient_lab_history";
  const canAccept = manager && intel?.recommend_id && intel?.status === "ok" && (intel?.mix_envelope?.materials || []).length > 0;

  const create = async () => {
    setBusy("save");
    try {
      const { data } = await api.post("/batch-records", {
        ...form,
        job_id: openJob?.id || null,
        beam_ids: beams.filter((beam) => beam.pour_id === form.pour_id).map((beam) => beam.id),
        ingredients: parseLines(form.ingredientsText, ["name", "target_lb", "actual_lb"]),
        admixtures: parseLines(form.admixturesText, ["name", "dosage_oz"]),
        cylinders: parseLines(form.cylindersText, ["id", "age_hr", "strength_psi"]),
      });
      try {
        await api.post("/batch-intelligence/lab", { source_type: "batch_record", source_id: data.id, document: data, pour_id: form.pour_id, batch_id: data.id });
      } catch (err) {
        console.error("[batch] vault ingest failed", err);
      }
      await load();
      toast.success("Batch record created");
    } catch (err) {
      console.error("[batch] save failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to create batch record");
    } finally {
      setBusy("");
    }
  };

  const runRecommend = async () => {
    setBusy("recommend");
    try {
      const { data } = await api.post("/batch-intelligence/recommend", {
        mix_code: query.mix_code || form.mix_design,
        mix_design: form.mix_design,
        pour_id: form.pour_id || null,
        job_id: openJob?.id || null,
        required_release_psi: num(query.required_release_psi),
        required_7d_psi: num(query.required_7d_psi),
        required_28d_psi: num(query.required_28d_psi),
        target_air_pct: num(query.target_air_pct),
        target_slump_in: num(query.target_slump_in),
        ambient_f: num(query.ambient_f || form.ambient_temp_f),
        rh_pct: num(query.rh_pct || form.humidity_pct),
        air_tolerance_pct: 1.0,
        slump_tolerance_in: 1.5,
        env_temp_window_f: 5,
        env_rh_window_pct: 10,
      });
      setIntel(data);
      if (data.status === "insufficient_lab_history") {
        toast.error("Insufficient lab history — no admixture doses invented");
      } else {
        toast.success(`Mix Intelligence scored ${data.winner_count} winning batches`);
      }
    } catch (err) {
      console.error("[batch] recommend failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to score mix intelligence");
    } finally {
      setBusy("");
    }
  };

  const acceptMix = async () => {
    if (!canAccept) {
      toast.error("Plant manager accept is required before applying mix to a ticket");
      return;
    }
    setBusy("accept");
    try {
      const { data } = await api.post("/batch-intelligence/accept", {
        recommend_id: intel.recommend_id,
        pour_id: form.pour_id,
        ticket_number: form.ticket_number || `MI-${Date.now().toString().slice(-6)}`,
        mix_design: query.mix_code || form.mix_design,
        job_id: openJob?.id || null,
        apply_to_ticket: true,
      });
      const text = envelopeToTicketText(intel.mix_envelope);
      if (text.ingredientsText || text.admixturesText) {
        setForm((current) => ({
          ...current,
          ticket_number: data.ticket?.ticket_number || current.ticket_number,
          ingredientsText: text.ingredientsText || current.ingredientsText,
          admixturesText: text.admixturesText || current.admixturesText,
        }));
      }
      await load();
      toast.success("Manager accepted — recorded mix envelope applied to a new batch ticket");
    } catch (err) {
      console.error("[batch] accept failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Accept failed");
    } finally {
      setBusy("");
    }
  };

  const exportVault = async () => {
    setBusy("export");
    try {
      const token = sessionStorage.getItem("bf_token") || localStorage.getItem("bf_token") || "";
      const res = await fetch(`${API}/batch-intelligence/export?format=csv`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "batch-intelligence-vault.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast.success("Append-only vault exported");
    } catch (err) {
      console.error("[batch] export failed", err);
      toast.error("Failed to export batch vault");
    } finally {
      setBusy("");
    }
  };

  return (
    <Layout>
      <PageHeader
        title="Batch Plant"
        subtitle="Mix records, full QC lab suite, and Mix Intelligence — manager accept required before a new ticket"
        right={
          <button
            type="button"
            data-testid="mix-intel-export"
            onClick={exportVault}
            disabled={Boolean(busy)}
            className="min-h-12 px-4 border font-mono text-xs uppercase tracking-widest flex items-center gap-2"
            style={{ borderColor: GOLD, color: GOLD }}
          >
            <Download className="w-4 h-4" /> Export vault
          </button>
        }
      />
      <div className="p-4 sm:p-8 grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className={`${cardClass} p-6 space-y-4`}>
          <h3 className="font-display font-bold uppercase tracking-wider text-lg">Record Batch Ticket</h3>
          <select value={form.pour_id} onChange={(e) => setForm({ ...form, pour_id: e.target.value })} className={inputClass} data-testid="batch-pour">
            {pours.map((pour) => (
              <option key={pour.id} value={pour.id}>{pour.pour_number}</option>
            ))}
          </select>
          <input value={form.ticket_number} onChange={(e) => setForm({ ...form, ticket_number: e.target.value })} placeholder="Ticket number" className={inputClass} data-testid="batch-ticket" />
          <input value={form.mix_design} onChange={(e) => { setForm({ ...form, mix_design: e.target.value }); setQuery((q) => ({ ...q, mix_code: e.target.value })); }} placeholder="Mix design" className={inputClass} data-testid="batch-mix" />
          <div className="grid grid-cols-2 gap-3">
            {[
              ["ambient_temp_f", "Ambient °F"],
              ["concrete_temp_f", "Concrete °F"],
              ["humidity_pct", "Humidity %"],
              ["wind_mph", "Wind MPH"],
            ].map(([key, label]) => (
              <input key={key} type="number" value={form[key]} onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })} placeholder={label} className={inputClass} />
            ))}
          </div>
          <input value={form.weather} onChange={(e) => setForm({ ...form, weather: e.target.value })} placeholder="Weather" className={inputClass} />
          <textarea value={form.ingredientsText} onChange={(e) => setForm({ ...form, ingredientsText: e.target.value })} placeholder="Ingredient|Target|Actual" rows={3} className={`${inputClass} py-2 text-xs`} />
          <textarea value={form.admixturesText} onChange={(e) => setForm({ ...form, admixturesText: e.target.value })} placeholder="Admixture|Dosage" rows={2} className={`${inputClass} py-2 text-xs`} />
          <textarea value={form.cylindersText} onChange={(e) => setForm({ ...form, cylindersText: e.target.value })} placeholder="Cylinder|Age Hr|Strength PSI" rows={2} className={`${inputClass} py-2 text-xs`} />
          <textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Notes" rows={3} className={`${inputClass} py-2`} />
          <button type="button" onClick={create} disabled={Boolean(busy)} className="w-full min-h-12 bg-primary text-white font-display font-bold uppercase tracking-widest" data-testid="batch-save">
            {busy === "save" ? "Saving…" : "Save Batch Record"}
          </button>
        </div>

        <div className="xl:col-span-2 space-y-6">
          <div
            className="p-6 space-y-5 border relative overflow-hidden"
            data-testid="mix-intelligence"
            style={{
              background: "linear-gradient(135deg, rgba(15,18,24,0.96), rgba(10,12,16,0.88))",
              borderColor: "rgba(46,230,214,0.35)",
              boxShadow: "0 0 40px rgba(46,230,214,0.08), inset 0 1px 0 rgba(201,162,39,0.2)",
              backdropFilter: "blur(16px)",
            }}
          >
            <div className="absolute inset-0 pointer-events-none" style={{ background: "radial-gradient(ellipse at top right, rgba(255,107,26,0.08), transparent 40%)" }} />
            <div className="relative flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-[0.28em]" style={{ color: GOLD }}>Mix Intelligence</div>
                <h3 className="font-display font-bold uppercase tracking-wider text-xl flex items-center gap-2">
                  <Sparkles className="w-5 h-5" style={{ color: TEAL }} /> Full QC lab suite
                </h3>
                <p className="text-sm text-muted-foreground max-w-2xl">
                  Scores historical batches on release and later-age PSI, air and slump bands, open concrete NCRs, and a ±5°F / ±10% RH window. Complete lab records outrank cylinder PSI alone. Thin history never invents admixture doses.
                </p>
              </div>
              <div className="text-right font-mono text-xs uppercase tracking-widest" style={{ color: intel?.confidence?.level === "high" ? TEAL : intel?.confidence?.level === "none" ? ORANGE : GOLD }}>
                Confidence {intel?.confidence?.level || "—"}
                <div className="text-muted-foreground normal-case tracking-normal">
                  {intel ? `${intel.winner_count || 0} winners / ${intel.scanned_count || 0} scanned` : "Run a recommendation"}
                </div>
              </div>
            </div>

            <div className="relative grid grid-cols-2 md:grid-cols-4 gap-3">
              <Field label="Mix code">
                <input data-testid="mix-intel-mix" className={inputClass} value={query.mix_code} onChange={(e) => setQuery({ ...query, mix_code: e.target.value })} />
              </Field>
              <Field label="Release PSI">
                <input data-testid="mix-intel-release" type="number" className={inputClass} value={query.required_release_psi} onChange={(e) => setQuery({ ...query, required_release_psi: e.target.value })} />
              </Field>
              <Field label="Target air %">
                <input data-testid="mix-intel-air" type="number" className={inputClass} value={query.target_air_pct} onChange={(e) => setQuery({ ...query, target_air_pct: e.target.value })} />
              </Field>
              <Field label="Target slump in">
                <input data-testid="mix-intel-slump" type="number" className={inputClass} value={query.target_slump_in} onChange={(e) => setQuery({ ...query, target_slump_in: e.target.value })} />
              </Field>
              <Field label="7-day PSI (optional)">
                <input type="number" className={inputClass} value={query.required_7d_psi} onChange={(e) => setQuery({ ...query, required_7d_psi: e.target.value })} />
              </Field>
              <Field label="28-day PSI (optional)">
                <input type="number" className={inputClass} value={query.required_28d_psi} onChange={(e) => setQuery({ ...query, required_28d_psi: e.target.value })} />
              </Field>
              <Field label="Ambient °F window">
                <input type="number" className={inputClass} value={query.ambient_f} onChange={(e) => setQuery({ ...query, ambient_f: e.target.value })} />
              </Field>
              <Field label="RH % window">
                <input type="number" className={inputClass} value={query.rh_pct} onChange={(e) => setQuery({ ...query, rh_pct: e.target.value })} />
              </Field>
            </div>

            <div className="relative flex flex-wrap gap-2">
              <button
                type="button"
                data-testid="mix-intel-run"
                onClick={runRecommend}
                disabled={Boolean(busy)}
                className="min-h-12 px-5 font-display font-bold uppercase tracking-widest text-black flex items-center gap-2"
                style={{ background: TEAL, boxShadow: "0 0 24px rgba(46,230,214,0.35)" }}
              >
                {busy === "recommend" ? <Loader2 className="w-4 h-4 animate-spin" /> : <FlaskConical className="w-4 h-4" />}
                Recommend from lab history
              </button>
              <button
                type="button"
                data-testid="mix-intel-accept"
                onClick={acceptMix}
                disabled={!canAccept || Boolean(busy)}
                className="min-h-12 px-5 font-display font-bold uppercase tracking-widest flex items-center gap-2 disabled:opacity-40"
                style={{ background: canAccept ? ORANGE : "transparent", color: canAccept ? "#0A0C10" : ORANGE, border: `1px solid ${ORANGE}` }}
              >
                <ShieldCheck className="w-4 h-4" /> Manager Accept
              </button>
            </div>
            <p className="relative text-xs text-muted-foreground">
              {manager
                ? "Accept copies recorded min/median/max chemistry onto a new batch ticket. The analyst cannot silently write mix."
                : "Plant manager (admin / executive) must accept before a recommendation can apply to a new ticket."}
            </p>

            {insufficient && (
              <div data-testid="mix-intel-insufficient" className="relative border p-4" style={{ borderColor: ORANGE, color: ORANGE, background: "rgba(255,107,26,0.08)" }}>
                <div className="font-display font-bold uppercase tracking-widest">Insufficient lab history</div>
                <p className="text-sm mt-1 text-white/80">Not enough complete winning batches to recommend a mix. Admixture doses will not be invented. Log crush, air, slump, and placement temperature against the pour / batch ticket.</p>
              </div>
            )}

            {drivers.length > 0 && !insufficient && (
              <div className="relative grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="mix-intel-drivers">
                {drivers.map((driver) => <DriverChip key={driver.id} driver={driver} />)}
              </div>
            )}

            {intel?.mix_envelope?.materials?.length > 0 && (
              <div className="relative overflow-x-auto" data-testid="mix-intel-envelope">
                <div className="text-[10px] font-mono uppercase tracking-[0.25em] mb-2" style={{ color: GOLD }}>Mix envelope from winners — min / median / max</div>
                <table className="w-full text-sm font-mono">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-widest text-muted-foreground">
                      <th className="py-2">Material</th>
                      <th>Kind</th>
                      <th>Min</th>
                      <th>Median</th>
                      <th>Max</th>
                      <th>n</th>
                    </tr>
                  </thead>
                  <tbody>
                    {intel.mix_envelope.materials.map((row) => (
                      <tr key={`${row.kind}-${row.name}`} className="border-t border-[#1C2230]">
                        <td className="py-2">{row.name}</td>
                        <td>{row.kind}</td>
                        <td>{row.min} {row.unit}</td>
                        <td style={{ color: TEAL }}>{row.median} {row.unit}</td>
                        <td>{row.max} {row.unit}</td>
                        <td>{row.sample_size}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {(intel?.comparables || []).length > 0 && (
              <div className="relative space-y-3" data-testid="mix-intel-comparables">
                <div className="text-[10px] font-mono uppercase tracking-[0.25em]" style={{ color: GOLD }}>Top comparables — full lab snapshot</div>
                {intel.comparables.map((row) => {
                  const lab = row.lab_snapshot || {};
                  return (
                    <div key={row.batch_id} className="border border-[#1C2230] p-3 grid grid-cols-2 md:grid-cols-4 gap-2 font-mono text-xs">
                      <div><div className="text-muted-foreground uppercase">Ticket / mix</div>{row.ticket_number || "—"} · {row.mix_code || "—"}</div>
                      <div><div className="text-muted-foreground uppercase">Score</div>{row.score} · complete {row.completeness}</div>
                      <div><div className="text-muted-foreground uppercase">Air / slump / temp</div>{lab.air_content_pct ?? "—"}% · {lab.slump_in ?? "—"} in · {lab.concrete_temp_f ?? "—"}°F</div>
                      <div>
                        <div className="text-muted-foreground uppercase">Strength curve</div>
                        {(lab.compressive || []).map((c) => `${c.test_type} ${c.psi ?? "—"}`).join(" · ") || "—"}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className={`${cardClass} p-6`}>
            <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-4">Permanent Batch History</h3>
            <div className="space-y-3">
              {records.map((record) => (
                <div key={record.id} className="border border-border p-4 grid grid-cols-1 md:grid-cols-6 gap-3 font-mono text-sm">
                  <div><div className="text-xs text-muted-foreground uppercase">Ticket</div><div>{record.ticket_number}</div></div>
                  <div><div className="text-xs text-muted-foreground uppercase">Mix</div><div>{record.mix_design}</div></div>
                  <div><div className="text-xs text-muted-foreground uppercase">Ambient</div><div>{record.ambient_temp_f}°F</div></div>
                  <div><div className="text-xs text-muted-foreground uppercase">Concrete</div><div>{record.concrete_temp_f}°F</div></div>
                  <div><div className="text-xs text-muted-foreground uppercase">Humidity</div><div>{record.humidity_pct}%</div></div>
                  <div><div className="text-xs text-muted-foreground uppercase">Wind</div><div>{record.wind_mph} mph</div></div>
                </div>
              ))}
              {records.length === 0 && <div className="text-sm text-muted-foreground font-mono">No batch records yet.</div>}
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
}
