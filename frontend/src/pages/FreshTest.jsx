import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, Droplets, FlaskConical, Loader2, PauseCircle, XCircle } from "lucide-react";
import { toast } from "sonner";
import { toastNcrFromResponse } from "../lib/ncr";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { Field, PageHeader, cardClass, inputClass } from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import {
  applyComputedFields,
  blockingAssessment,
  diameterAverage,
  formatStamp,
  gateColor,
  pickIdentity,
  readLastIdentity,
  saveLastIdentity,
  stampNowIso,
} from "../lib/freshConcrete";

const EMPTY_MEASURE = {
  spread_d1_in: "",
  spread_d2_in: "",
  t50_sec: "",
  visual_stability: "",
  spread_spec_min_in: "",
  spread_spec_max_in: "",
  slump_in: "",
  slump_spec_min_in: "",
  slump_spec_max_in: "",
  unconstrained_avg_in: "",
  jring_d1_in: "",
  jring_d2_in: "",
  jring_note: "standard J-ring",
  mix_ticket: "",
  load_number: "",
  concrete_temp_f: "",
  air_content_pct: "",
  notes: "",
};

function num(value) {
  if (value === "" || value == null) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function Chip({ active, onClick, children, testid, color }) {
  return (
    <button
      type="button"
      data-testid={testid}
      onClick={onClick}
      className={`min-h-12 px-4 font-semibold uppercase tracking-wider text-xs border rounded-none ${
        active ? "text-black" : "text-muted-foreground"
      }`}
      style={active ? { background: color || "#2979FF", borderColor: color || "#2979FF" } : { borderColor: "#1C2230" }}
    >
      {children}
    </button>
  );
}

export default function FreshTest() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const [jobs, setJobs] = useState([]);
  const [pours, setPours] = useState([]);
  const [beams, setBeams] = useState([]);
  const [beds, setBeds] = useState([]);
  const [jobId, setJobId] = useState("");
  const [pourId, setPourId] = useState("");
  const [beamIds, setBeamIds] = useState([]);
  const [bedId, setBedId] = useState("");
  const [types, setTypes] = useState(["spread"]);
  const [form, setForm] = useState({ ...EMPTY_MEASURE, time_sampled: stampNowIso(), gate: "hold" });
  const [recent, setRecent] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  const query = useMemo(() => ({
    job: params.get("job") || "",
    pour: params.get("pour") || "",
    beam: params.get("beam") || "",
    bed: params.get("bed") || "",
  }), [params]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      api.get("/jobs"),
      api.get("/pours"),
      api.get("/beams"),
      api.get("/beds"),
      api.get("/beds/plant-layout"),
    ])
      .then(([j, p, b, d, plant]) => {
        if (cancelled) return;
        const jobsList = j.data || [];
        const poursList = p.data || [];
        const beamsList = b.data || [];
        const bedsList = d.data || [];
        setJobs(jobsList);
        setPours(poursList);
        setBeams(beamsList);
        setBeds(bedsList);
        const picked = pickIdentity({
          jobs: jobsList,
          pours: poursList,
          beams: beamsList,
          beds: bedsList,
          plant: plant.data,
          query,
          last: readLastIdentity(),
        });
        setJobId(picked.jobId);
        setPourId(picked.pourId);
        setBeamIds(picked.beamIds);
        setBedId(picked.bedId);
        setHydrated(true);
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[fresh] identity load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load jobs and pours");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  const loadRecent = useCallback((id) => {
    if (!id) {
      setRecent([]);
      return;
    }
    api.get("/fresh-tests", { params: { pour_id: id } })
      .then((r) => setRecent(r.data || []))
      .catch((err) => {
        console.error("[fresh] recent load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load recent tests");
      });
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    loadRecent(pourId);
  }, [hydrated, pourId, loadRecent]);

  useEffect(() => {
    if (!hydrated) return;
    saveLastIdentity({ jobId, pourId });
  }, [hydrated, jobId, pourId]);

  const jobPours = pours.filter((p) => p.job_id === jobId);
  const pourBeams = beams.filter((b) => b.pour_id === pourId);
  const live = applyComputedFields({
    spread_d1_in: num(form.spread_d1_in),
    spread_d2_in: num(form.spread_d2_in),
    unconstrained_avg_in: num(form.unconstrained_avg_in),
    jring_d1_in: num(form.jring_d1_in),
    jring_d2_in: num(form.jring_d2_in),
  });
  const spreadAvg = live.spread_avg_in;
  const jringAvg = live.jring_avg_in;
  const blocking = blockingAssessment(live.blocking_delta_in);
  const showSpread = types.includes("spread") || types.includes("jring");
  const showSlump = types.includes("slump");
  const showJring = types.includes("jring");

  const set = (key, value) => setForm((cur) => ({ ...cur, [key]: value }));

  const onJob = (id) => {
    setJobId(id);
    const nextPours = pours.filter((p) => p.job_id === id);
    const nextPour = nextPours.find((p) => p.id === pourId) || nextPours.find((p) => p.status === "active") || nextPours[0];
    const nextPourId = nextPour?.id || "";
    setPourId(nextPourId);
    const nextBeams = beams.filter((b) => b.pour_id === nextPourId);
    const nextIds = nextBeams.length === 1 ? [nextBeams[0].id] : [];
    setBeamIds(nextIds);
    inferBed(nextIds);
    setSaved(false);
  };

  const onPour = (id) => {
    setPourId(id);
    const nextBeams = beams.filter((b) => b.pour_id === id);
    const nextIds = nextBeams.length === 1 ? [nextBeams[0].id] : [];
    setBeamIds(nextIds);
    inferBed(nextIds);
    setSaved(false);
  };

  const inferBed = (ids) => {
    const selected = beams.filter((b) => ids.includes(b.id));
    const unique = [...new Set(selected.map((b) => b.bed_id).filter(Boolean))];
    setBedId(unique.length === 1 ? unique[0] : "");
  };

  const toggleBeam = (id) => {
    const next = beamIds.includes(id) ? beamIds.filter((x) => x !== id) : [...beamIds, id];
    setBeamIds(next);
    inferBed(next);
  };

  const toggleType = (key) => {
    setTypes((cur) => {
      const has = cur.includes(key);
      if (has) {
        if (key === "spread" && cur.includes("jring")) return cur;
        const next = cur.filter((k) => k !== key);
        return next.length ? next : ["spread"];
      }
      const next = [...cur, key];
      if (key === "jring" && !next.includes("spread")) next.unshift("spread");
      return next;
    });
    setSaved(false);
  };

  const save = async () => {
    if (!jobId || !pourId) {
      toast.error("Pick the job and pour — the truck will not wait on typing");
      return;
    }
    setSaving(true);
    setSaved(false);
    try {
      const { data } = await api.post("/fresh-tests", {
        job_id: jobId,
        pour_id: pourId,
        beam_ids: beamIds,
        bed_id: bedId || null,
        test_types: types,
        mix_ticket: form.mix_ticket || "",
        load_number: form.load_number || "",
        concrete_temp_f: num(form.concrete_temp_f),
        air_content_pct: num(form.air_content_pct),
        time_sampled: form.time_sampled || stampNowIso(),
        spread_d1_in: num(form.spread_d1_in),
        spread_d2_in: num(form.spread_d2_in),
        t50_sec: num(form.t50_sec),
        visual_stability: form.visual_stability || null,
        spread_spec_min_in: num(form.spread_spec_min_in),
        spread_spec_max_in: num(form.spread_spec_max_in),
        slump_in: num(form.slump_in),
        slump_spec_min_in: num(form.slump_spec_min_in),
        slump_spec_max_in: num(form.slump_spec_max_in),
        unconstrained_avg_in: num(form.unconstrained_avg_in) ?? spreadAvg,
        jring_d1_in: num(form.jring_d1_in),
        jring_d2_in: num(form.jring_d2_in),
        jring_note: form.jring_note || "standard J-ring",
        gate: form.gate || "hold",
        notes: form.notes || "",
      });
      setSaved(true);
      toast.success("Fresh test saved — keep the same pour for the next truck");
      toastNcrFromResponse(data);
      setForm((cur) => ({
        ...EMPTY_MEASURE,
        time_sampled: stampNowIso(),
        gate: "hold",
        jring_note: cur.jring_note || "standard J-ring",
      }));
      saveLastIdentity({ jobId, pourId });
      loadRecent(pourId);
    } catch (err) {
      console.error("[fresh] save failed", err);
      if (err?.queuedOffline) {
        setSaved(true);
        toast.success("Saved on this device — will sync when Wi-Fi returns.");
        setForm((cur) => ({
          ...EMPTY_MEASURE,
          time_sampled: stampNowIso(),
          gate: "hold",
          jring_note: cur.jring_note || "standard J-ring",
        }));
      } else {
        toast.error(formatApiErrorDetail(err.response?.data?.detail, err) || "Failed to save fresh test");
      }
    } finally {
      setSaving(false);
    }
  };

  const bedLabel = (id) => {
    const bed = beds.find((b) => b.id === id);
    if (!bed) return "—";
    return bed.name || `Bed ${bed.bed_number}`;
  };

  return (
    <Layout>
      <PageHeader
        title="Fresh Test"
        subtitle="Plastic concrete at delivery — spread, slump, J-ring. Stamp it before the bed is poured."
        right={
          <Link
            to="/guide?section=fresh"
            className="min-h-12 px-4 border border-[#1C2230] flex items-center gap-2 text-sm font-semibold uppercase tracking-wider hover:border-[#C9A227] hover:text-[#C9A227]"
          >
            Why this matters
          </Link>
        }
      />
      <div className="p-4 sm:p-6 lg:p-8 max-w-5xl space-y-4">
        {saved && (
          <div
            className="min-h-12 px-4 border flex items-center gap-2 font-semibold uppercase tracking-wider text-sm"
            style={{ borderColor: "#00E676", color: "#00E676", background: "#00E67614" }}
            data-testid="fresh-saved"
          >
            <CheckCircle2 className="w-5 h-5" /> Saved — same pour is ready for the next load
          </div>
        )}

        <div className={`${cardClass} p-4 sm:p-6 space-y-4`} data-testid="fresh-identity">
          <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-[#C9A227]">Ticket identity — dropdowns only</div>
          {loading ? (
            <div className="min-h-12 flex items-center text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading jobs…
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Job">
                <select data-testid="fresh-job" value={jobId} onChange={(e) => onJob(e.target.value)} className={inputClass}>
                  <option value="">Select job</option>
                  {jobs.map((j) => (
                    <option key={j.id} value={j.id}>{j.job_number} · {j.name}</option>
                  ))}
                </select>
              </Field>
              <Field label="Pour">
                <select data-testid="fresh-pour" value={pourId} onChange={(e) => onPour(e.target.value)} className={inputClass}>
                  <option value="">Select pour</option>
                  {jobPours.map((p) => (
                    <option key={p.id} value={p.id}>{p.pour_number} · {p.pour_date}{p.concrete_mix ? ` · ${p.concrete_mix}` : ""}</option>
                  ))}
                </select>
              </Field>
            </div>
          )}
          <Field label="Beam(s) on this pour">
            <div className="flex flex-wrap gap-2" data-testid="fresh-beams">
              {pourBeams.length === 0 && (
                <span className="text-sm text-muted-foreground">No beams on this pour yet — you can still log the load.</span>
              )}
              {pourBeams.map((b) => (
                <Chip
                  key={b.id}
                  testid={`fresh-beam-${b.mark}`}
                  active={beamIds.includes(b.id)}
                  onClick={() => toggleBeam(b.id)}
                >
                  {b.mark}
                </Chip>
              ))}
              {pourBeams.length > 1 && (
                <button
                  type="button"
                  data-testid="fresh-beams-all"
                  onClick={() => {
                    const ids = pourBeams.map((b) => b.id);
                    setBeamIds(ids);
                    inferBed(ids);
                  }}
                  className="min-h-12 px-4 border border-[#1C2230] text-xs font-semibold uppercase tracking-wider"
                >
                  All on pour
                </button>
              )}
            </div>
          </Field>
          <Field label="Bed (optional — inferred from beams)">
            <select data-testid="fresh-bed" value={bedId} onChange={(e) => setBedId(e.target.value)} className={inputClass}>
              <option value="">Not set</option>
              {beds.map((b) => (
                <option key={b.id} value={b.id}>{b.name || `Bed ${b.bed_number}`} · {b.status}</option>
              ))}
            </select>
          </Field>
        </div>

        <div className={`${cardClass} p-4 sm:p-6 space-y-4`} data-testid="fresh-types">
          <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-[#C9A227]">Test type — this plant defaults to spread</div>
          <div className="flex flex-wrap gap-2">
            <Chip testid="fresh-type-spread" active={types.includes("spread")} onClick={() => toggleType("spread")} color="#2979FF">Spread (C1611)</Chip>
            <Chip testid="fresh-type-slump" active={types.includes("slump")} onClick={() => toggleType("slump")} color="#C9A227">Slump (C143)</Chip>
            <Chip testid="fresh-type-jring" active={types.includes("jring")} onClick={() => toggleType("jring")} color="#2979FF">J-Ring (C1621)</Chip>
          </div>
          <p className="text-xs text-muted-foreground">
            SCC / spread is the default. Tap more than one for the same load — spread + J-ring is common. J-ring still shows unconstrained spread because blocking is the difference. Slump stays available for states that still call it.
          </p>
        </div>

        {showSpread && (
          <div className={`${cardClass} p-4 sm:p-6 space-y-4`} data-testid="fresh-spread">
            <h3 className="font-display font-bold uppercase tracking-wider flex items-center gap-2">
              <Droplets className="w-5 h-5 text-primary" /> Spread / slump-flow (ASTM C1611)
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Field label="Diameter 1 (in)">
                <input data-testid="fresh-spread-d1" inputMode="decimal" type="number" step="0.25" value={form.spread_d1_in} onChange={(e) => set("spread_d1_in", e.target.value)} className={inputClass} />
              </Field>
              <Field label="Diameter 2 (in)">
                <input data-testid="fresh-spread-d2" inputMode="decimal" type="number" step="0.25" value={form.spread_d2_in} onChange={(e) => set("spread_d2_in", e.target.value)} className={inputClass} />
              </Field>
              <Field label="Average (in)">
                <div data-testid="fresh-spread-avg" className={`${inputClass} flex items-center text-primary`}>{spreadAvg != null ? spreadAvg : "—"}</div>
              </Field>
              <Field label="T50 / T20 (sec, optional)">
                <input data-testid="fresh-t50" inputMode="decimal" type="number" step="0.1" value={form.t50_sec} onChange={(e) => set("t50_sec", e.target.value)} className={inputClass} />
              </Field>
            </div>
            <Field label="Visual stability (optional)">
              <div className="flex flex-wrap gap-2">
                {[
                  ["stable", "Stable"],
                  ["minor_halo", "Minor halo"],
                  ["segregation", "Segregation"],
                ].map(([key, label]) => (
                  <Chip key={key} testid={`fresh-stability-${key}`} active={form.visual_stability === key} onClick={() => set("visual_stability", form.visual_stability === key ? "" : key)} color={key === "segregation" ? "#FF3366" : key === "minor_halo" ? "#FFD600" : "#00E676"}>
                    {label}
                  </Chip>
                ))}
              </div>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Spec min (in, optional)">
                <input data-testid="fresh-spread-min" inputMode="decimal" type="number" step="0.25" value={form.spread_spec_min_in} onChange={(e) => set("spread_spec_min_in", e.target.value)} className={inputClass} />
              </Field>
              <Field label="Spec max (in, optional)">
                <input data-testid="fresh-spread-max" inputMode="decimal" type="number" step="0.25" value={form.spread_spec_max_in} onChange={(e) => set("spread_spec_max_in", e.target.value)} className={inputClass} />
              </Field>
            </div>
            <p className="text-xs text-muted-foreground">Leave spec blank if the mix ticket has no spread window. Average updates as you type.</p>
          </div>
        )}

        {showSlump && (
          <div className={`${cardClass} p-4 sm:p-6 space-y-4`} data-testid="fresh-slump">
            <h3 className="font-display font-bold uppercase tracking-wider">Conventional slump (ASTM C143)</h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Field label="Slump (in)">
                <input data-testid="fresh-slump-in" inputMode="decimal" type="number" step="0.25" value={form.slump_in} onChange={(e) => set("slump_in", e.target.value)} className={inputClass} />
              </Field>
              <Field label="Spec min (optional)">
                <input data-testid="fresh-slump-min" inputMode="decimal" type="number" step="0.25" value={form.slump_spec_min_in} onChange={(e) => set("slump_spec_min_in", e.target.value)} className={inputClass} />
              </Field>
              <Field label="Spec max (optional)">
                <input data-testid="fresh-slump-max" inputMode="decimal" type="number" step="0.25" value={form.slump_spec_max_in} onChange={(e) => set("slump_spec_max_in", e.target.value)} className={inputClass} />
              </Field>
            </div>
          </div>
        )}

        {showJring && (
          <div className={`${cardClass} p-4 sm:p-6 space-y-4`} data-testid="fresh-jring">
            <h3 className="font-display font-bold uppercase tracking-wider flex items-center gap-2">
              <FlaskConical className="w-5 h-5 text-primary" /> J-ring passing ability (ASTM C1621)
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Field label="Unconstrained slump-flow avg (in)">
                <input
                  data-testid="fresh-unconstrained"
                  inputMode="decimal"
                  type="number"
                  step="0.25"
                  placeholder={spreadAvg != null ? String(spreadAvg) : ""}
                  value={form.unconstrained_avg_in}
                  onChange={(e) => set("unconstrained_avg_in", e.target.value)}
                  className={inputClass}
                />
              </Field>
              <Field label="J-ring diameter 1 (in)">
                <input data-testid="fresh-jring-d1" inputMode="decimal" type="number" step="0.25" value={form.jring_d1_in} onChange={(e) => set("jring_d1_in", e.target.value)} className={inputClass} />
              </Field>
              <Field label="J-ring diameter 2 (in)">
                <input data-testid="fresh-jring-d2" inputMode="decimal" type="number" step="0.25" value={form.jring_d2_in} onChange={(e) => set("jring_d2_in", e.target.value)} className={inputClass} />
              </Field>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Field label="J-ring average (in)">
                <div data-testid="fresh-jring-avg" className={`${inputClass} flex items-center`}>{jringAvg != null ? jringAvg : "—"}</div>
              </Field>
              <Field label="Blocking Δ (in)">
                <div data-testid="fresh-blocking-delta" className={`${inputClass} flex items-center`}>{live.blocking_delta_in != null ? live.blocking_delta_in : "—"}</div>
              </Field>
              <Field label="Blocking assessment">
                <div
                  data-testid="fresh-blocking"
                  className={`${inputClass} flex items-center font-bold`}
                  style={{ color: blocking?.color || undefined, borderColor: blocking?.color || "#1C2230" }}
                >
                  {blocking ? `${blocking.label} — ${blocking.detail}` : "Need both flows"}
                </div>
              </Field>
            </div>
            <Field label="J-ring type / bars (optional)">
              <input data-testid="fresh-jring-note" value={form.jring_note} onChange={(e) => set("jring_note", e.target.value)} className={inputClass} />
            </Field>
            <p className="text-xs text-muted-foreground">
              Δ = unconstrained spread − J-ring. Leave unconstrained blank to reuse the spread average on this ticket. Default apparatus is a standard J-ring.
            </p>
          </div>
        )}

        <div className={`${cardClass} p-4 sm:p-6 space-y-4`} data-testid="fresh-ticket">
          <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-[#C9A227]">Always on the ticket</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Mix / ticket number (optional)">
              <input data-testid="fresh-mix" value={form.mix_ticket} onChange={(e) => set("mix_ticket", e.target.value)} className={inputClass} />
            </Field>
            <Field label="Load / truck number (optional)">
              <input data-testid="fresh-load" value={form.load_number} onChange={(e) => set("load_number", e.target.value)} className={inputClass} />
            </Field>
            <Field label="Concrete temperature (°F)">
              <input data-testid="fresh-temp" inputMode="decimal" type="number" step="0.5" value={form.concrete_temp_f} onChange={(e) => set("concrete_temp_f", e.target.value)} className={inputClass} />
            </Field>
            <Field label="Air content (%, optional)">
              <input data-testid="fresh-air" inputMode="decimal" type="number" step="0.1" value={form.air_content_pct} onChange={(e) => set("air_content_pct", e.target.value)} className={inputClass} />
            </Field>
          </div>
          <Field label="Time sampled">
            <div className="flex gap-2">
              <div className={`${inputClass} flex items-center`} data-testid="fresh-time">{formatStamp(form.time_sampled)}</div>
              <button
                type="button"
                data-testid="fresh-stamp"
                onClick={() => set("time_sampled", stampNowIso())}
                className="min-h-12 px-4 shrink-0 bg-primary text-white font-semibold uppercase tracking-wider text-xs"
              >
                Stamp now
              </button>
            </div>
          </Field>
          <Field label="Pass / Fail / Hold">
            <div className="grid grid-cols-3 gap-2" data-testid="fresh-gate">
              {[
                ["pass", "Pass", CheckCircle2, "#00E676"],
                ["fail", "Fail", XCircle, "#FF3366"],
                ["hold", "Hold", PauseCircle, "#FFD600"],
              ].map(([key, label, Icon, color]) => (
                <button
                  key={key}
                  type="button"
                  data-testid={`fresh-gate-${key}`}
                  onClick={() => set("gate", key)}
                  className="min-h-12 border rounded-none flex items-center justify-center gap-2 font-display font-bold uppercase tracking-widest text-sm"
                  style={{
                    borderColor: form.gate === key ? color : "#1C2230",
                    color: form.gate === key ? color : "#8B949E",
                    background: form.gate === key ? `${color}18` : "transparent",
                  }}
                >
                  <Icon className="w-4 h-4" /> {label}
                </button>
              ))}
            </div>
          </Field>
          <Field label="Notes">
            <textarea data-testid="fresh-notes" rows={2} value={form.notes} onChange={(e) => set("notes", e.target.value)} className={`${inputClass} py-2`} />
          </Field>
          <Field label="Inspector">
            <div data-testid="fresh-inspector" className={`${inputClass} flex items-center`}>{user?.name || "—"}</div>
          </Field>
          <button
            type="button"
            data-testid="fresh-save"
            onClick={save}
            disabled={saving}
            className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest rounded-none hover:bg-white hover:text-black transition-colors duration-100 disabled:opacity-60 flex items-center justify-center gap-2"
          >
            {saving && <Loader2 className="w-4 h-4 animate-spin" />} Save fresh test
          </button>
        </div>

        <div className={`${cardClass} p-4 sm:p-6`} data-testid="fresh-recent">
          <div className="font-display font-bold uppercase tracking-wider mb-3">Recent tests this pour</div>
          {recent.length === 0 ? (
            <p className="text-sm text-muted-foreground">None yet — the first save lands here.</p>
          ) : (
            <div className="space-y-2">
              {recent.map((row) => {
                const color = gateColor(row.gate);
                const avg = row.spread_avg_in ?? diameterAverage(row.spread_d1_in, row.spread_d2_in);
                return (
                  <div key={row.id} className="border border-[#1C2230] p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div>
                      <div className="font-mono text-sm">
                        {(row.test_types || []).join(" + ") || "spread"}
                        {avg != null ? ` · spread ${avg}"` : ""}
                        {row.jring_avg_in != null ? ` · J-ring ${row.jring_avg_in}"` : ""}
                        {row.slump_in != null ? ` · slump ${row.slump_in}"` : ""}
                      </div>
                      <div className="text-xs text-muted-foreground font-mono mt-1">
                        {formatStamp(row.time_sampled || row.created_at)} · {row.inspector || "—"}
                        {row.load_number ? ` · truck ${row.load_number}` : ""}
                        {row.blocking_label ? ` · ${row.blocking_label}` : ""}
                      </div>
                    </div>
                    <span className="text-xs font-bold uppercase tracking-widest" style={{ color }}>{row.gate || "hold"}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
