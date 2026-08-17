import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { Field, PageHeader, cardClass, inputClass } from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import { pickIdentity, readLastIdentity } from "../lib/freshConcrete";
import {
  canConfirmBatch,
  canDraftBatch,
  emptyBatchForm,
  formFromRecord,
  payloadFromForm,
  readLastBatchIdentity,
  saveLastBatchIdentity,
  waterCementitiousRatio,
} from "../lib/batchPlant";

export default function BatchPlant() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const role = user?.role || "";
  const canDraft = canDraftBatch(role);
  const canConfirm = canConfirmBatch(role);

  const [jobs, setJobs] = useState([]);
  const [pours, setPours] = useState([]);
  const [beams, setBeams] = useState([]);
  const [beds, setBeds] = useState([]);
  const [designs, setDesigns] = useState([]);
  const [jobId, setJobId] = useState("");
  const [pourId, setPourId] = useState("");
  const [beamIds, setBeamIds] = useState([]);
  const [bedId, setBedId] = useState("");
  const [form, setForm] = useState(emptyBatchForm());
  const [rows, setRows] = useState([]);
  const [fresh, setFresh] = useState([]);
  const [cylinders, setCylinders] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [selected, setSelected] = useState(null);
  const [recs, setRecs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [envBusy, setEnvBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [amendReason, setAmendReason] = useState("");

  const query = useMemo(() => ({
    job: params.get("job") || "",
    pour: params.get("pour") || "",
    beam: params.get("beam") || "",
  }), [params]);

  const wcm = waterCementitiousRatio(form.ingredients);
  const locked = Boolean(selected?.immutable || selected?.status === "confirmed");
  const fieldsLocked = locked || !canDraft;

  const loadLists = useCallback(async () => {
    setLoading(true);
    try {
      const [j, p, b, d, plant, mixes] = await Promise.all([
        api.get("/jobs"),
        api.get("/pours"),
        api.get("/beams"),
        api.get("/beds"),
        api.get("/beds/plant-layout"),
        api.get("/mix-designs"),
      ]);
      setJobs(j.data || []);
      setPours(p.data || []);
      setBeams(b.data || []);
      setBeds(d.data || []);
      setDesigns(mixes.data || []);
      const picked = pickIdentity({
        jobs: j.data || [],
        pours: p.data || [],
        beams: b.data || [],
        beds: d.data || [],
        plant: plant.data,
        query,
        last: { ...readLastIdentity(), ...readLastBatchIdentity() },
      });
      setJobId(picked.jobId);
      setPourId(picked.pourId);
      setBeamIds(picked.beamIds);
      setBedId(picked.bedId);
      const lastMix = readLastBatchIdentity().mixCode;
      if (lastMix) setForm((cur) => ({ ...cur, mix_code: cur.mix_code || lastMix, mixer_operator: cur.mixer_operator || user?.name || "" }));
      else setForm((cur) => ({ ...cur, mixer_operator: cur.mixer_operator || user?.name || "" }));
    } catch (err) {
      console.error("[batch] identity load failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load plant identity");
    } finally {
      setLoading(false);
    }
  }, [query, user?.name]);

  useEffect(() => { loadLists(); }, [loadLists]);

  const loadRows = useCallback(() => {
    if (!pourId && !jobId) {
      setRows([]);
      return;
    }
    api.get("/batches", { params: { pour_id: pourId || undefined, job_id: jobId || undefined } })
      .then((r) => setRows(r.data || []))
      .catch((err) => {
        console.error("[batch] list failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to list batches");
      });
  }, [jobId, pourId]);

  useEffect(() => { loadRows(); }, [loadRows]);

  useEffect(() => {
    if (!pourId) {
      setFresh([]);
      setCylinders([]);
      return undefined;
    }
    const pourRow = pours.find((p) => p.id === pourId);
    const jobRow = jobs.find((j) => j.id === jobId);
    api.get("/fresh-tests", { params: { pour_id: pourId } })
      .then((r) => setFresh(r.data || []))
      .catch((err) => console.error("[batch] fresh link load failed", err));
    api.get("/cylinders", { params: { job_id: jobId || undefined, job_number: jobRow?.job_number, pour_number: pourRow?.pour_number } })
      .then((r) => setCylinders(r.data || []))
      .catch((err) => console.error("[batch] cylinders load failed", err));
    return undefined;
  }, [pourId, jobId, jobs, pours]);

  useEffect(() => {
    saveLastBatchIdentity({ jobId, pourId, mixCode: form.mix_code });
  }, [jobId, pourId, form.mix_code]);

  const jobPours = pours.filter((p) => p.job_id === jobId);
  const pourBeams = beams.filter((b) => b.pour_id === pourId);

  const setIng = (idx, key, value) => {
    setForm((cur) => {
      const ingredients = cur.ingredients.map((row, i) => (i === idx ? { ...row, [key]: value } : row));
      return { ...cur, ingredients };
    });
  };

  const setEnv = (key, value) => {
    setForm((cur) => ({
      ...cur,
      environment: { ...cur.environment, [key]: value, manual_override: true, env_flag: cur.environment.env_flag || "estimated/manual" },
    }));
  };

  const captureEnv = async () => {
    setEnvBusy(true);
    const apply = (env) => {
      setForm((cur) => ({
        ...cur,
        environment: {
          ...cur.environment,
          ...env,
          mix_temp_f: cur.environment.mix_temp_f,
          manual_override: false,
        },
      }));
    };
    const fallback = () => {
      apply({
        source: "manual",
        env_flag: "estimated/manual",
        captured_at: new Date().toISOString(),
        weather: form.environment.weather || "overcast",
      });
      toast.error("Weather unavailable — enter conditions by hand. Batching is not blocked.");
    };
    try {
      const pos = await new Promise((resolve, reject) => {
        if (!navigator.geolocation) {
          reject(new Error("no geo"));
          return;
        }
        navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 8000 });
      });
      const { data } = await api.get("/batch-plant/weather", {
        params: { lat: pos.coords.latitude, lon: pos.coords.longitude },
      });
      apply(data);
      if (data.env_flag) toast("Outdoor conditions estimated — override any field");
      else toast.success("Outdoor conditions captured — override if the sensor is wrong");
    } catch (err) {
      console.error("[batch] weather failed", err);
      fallback();
    } finally {
      setEnvBusy(false);
    }
  };

  const applyDesign = (id) => {
    const mix = designs.find((d) => d.id === id);
    setForm((cur) => ({
      ...cur,
      mix_design_id: id,
      mix_code: mix?.mix_code || cur.mix_code,
      target_strength_psi: mix?.target_strength_psi ?? cur.target_strength_psi,
      target_air_pct: mix?.target_air_pct ?? cur.target_air_pct,
      target_slump_in: mix?.target_slump_in ?? cur.target_slump_in,
      target_spread_in: mix?.target_spread_in ?? cur.target_spread_in,
      target_temp_f: mix?.target_temp_f ?? cur.target_temp_f,
      ingredients: (mix?.ingredients || []).length
        ? mix.ingredients.map((row) => ({ ...row }))
        : cur.ingredients,
    }));
  };

  const copyPrevious = async () => {
    if (!form.mix_code) {
      toast.error("Enter a mix code first");
      return;
    }
    try {
      const { data } = await api.get("/batches/previous", { params: { mix_code: form.mix_code } });
      if (!data?.id) {
        toast.error("No previous batch with that mix code");
        return;
      }
      setForm(formFromRecord({ ...data, mixer_operator: user?.name || data.mixer_operator }));
      toast.success("Copied last mix — check weights before you confirm");
    } catch (err) {
      console.error("[batch] copy previous failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Could not copy previous mix");
    }
  };

  const saveDraft = async () => {
    if (!canDraft) {
      toast.error("Mixer / production drafts only — QC views confirmed tickets");
      return;
    }
    if (!jobId || !pourId) {
      toast.error("Pick job and pour");
      return;
    }
    setSaving(true);
    try {
      const body = payloadFromForm(form, { jobId, pourId, beamIds, bedId });
      let rec;
      if (selectedId && !locked) {
        rec = (await api.patch(`/batches/${selectedId}`, body)).data;
      } else {
        rec = (await api.post("/batches", body)).data;
      }
      setSelectedId(rec.id);
      setSelected(rec);
      saveLastBatchIdentity({ jobId, pourId, mixCode: form.mix_code });
      toast.success(rec.queuedOffline ? "Queued on this device" : "Draft saved");
      loadRows();
    } catch (err) {
      console.error("[batch] save failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail, err) || "Failed to save draft");
    } finally {
      setSaving(false);
    }
  };

  const confirm = async () => {
    if (!canConfirm || !selectedId) return;
    if (!String(form.mix_code || "").trim()) {
      toast.error("Mix code is required before confirm");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post(`/batches/${selectedId}/confirm`);
      setSelected(data);
      toast.success("Batch confirmed — this ticket is now permanent");
      loadRows();
    } catch (err) {
      console.error("[batch] confirm failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Could not confirm");
    } finally {
      setSaving(false);
    }
  };

  const amend = async () => {
    if (!canConfirm || !selectedId || !amendReason.trim()) {
      toast.error("Plant manager amendment needs a written reason");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post(`/batches/${selectedId}/amend`, {
        reason: amendReason.trim(),
        patch: payloadFromForm(form, { jobId, pourId, beamIds, bedId }),
      });
      setSelectedId(data.id);
      setSelected(data);
      setForm(formFromRecord(data));
      setAmendReason("");
      toast.success("Amendment drafted as a new revision — confirm it when it is right");
      loadRows();
    } catch (err) {
      console.error("[batch] amend failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Amendment failed");
    } finally {
      setSaving(false);
    }
  };

  const openRow = async (id) => {
    try {
      const { data } = await api.get(`/batches/${id}`);
      setSelectedId(id);
      setSelected(data);
      setForm(formFromRecord(data));
      setJobId(data.job_id);
      setPourId(data.pour_id);
      setBeamIds(data.beam_ids || []);
      setBedId((data.bed_ids || [])[0] || "");
      const rec = await api.get(`/batches/${id}/recommendations`);
      setRecs(rec.data?.recommendations || []);
    } catch (err) {
      console.error("[batch] open failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to open batch");
    }
  };

  const linkQc = async (freshIds, cylIds) => {
    if (!selectedId) {
      toast.error("Save the draft first");
      return;
    }
    try {
      const { data } = await api.post(`/batches/${selectedId}/link-qc`, {
        fresh_test_ids: freshIds,
        cylinder_ids: cylIds,
      });
      setSelected(data);
      toast.success("QC linked to this batch");
    } catch (err) {
      console.error("[batch] link qc failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to link QC");
    }
  };

  const downloadExport = async (kind) => {
    if (!selectedId) return;
    try {
      const res = await api.get(`/batches/${selectedId}/export.${kind}`, { responseType: "blob" });
      const url = window.URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `batch-${selectedId.slice(0, 8)}.${kind}`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("[batch] export failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Export failed");
    }
  };

  const filtered = rows.filter((row) => {
    const blob = `${row.mix_code} ${row.status} ${row.truck_id} ${row.mixer_operator}`.toLowerCase();
    return blob.includes(search.toLowerCase());
  });

  return (
    <Layout>
      <PageHeader
        title="Batch Plant"
        subtitle="Mixer record for every load. Analyst recommends. Plant manager confirms. Never silent edits."
        right={
          <Link to="/guide?section=batch" className="min-h-12 px-4 border border-[#1C2230] flex items-center text-sm font-semibold uppercase tracking-wider hover:border-[#C9A227] hover:text-[#C9A227]">
            Why this exists
          </Link>
        }
      />
      <div className="p-4 sm:p-6 lg:p-8 grid grid-cols-1 xl:grid-cols-[320px_1fr] gap-4 max-w-7xl">
        <div className="space-y-3">
          <div className={`${cardClass} p-4 space-y-3`}>
            <Field label="Search this pour">
              <input data-testid="batch-search" value={search} onChange={(e) => setSearch(e.target.value)} className={inputClass} placeholder="mix code, truck, operator" />
            </Field>
            {canDraft && (
              <button
                type="button"
                data-testid="batch-new"
                onClick={() => {
                  setSelectedId("");
                  setSelected(null);
                  setRecs([]);
                  setForm((cur) => ({ ...emptyBatchForm(), mix_code: cur.mix_code, mixer_operator: user?.name || "" }));
                }}
                className="w-full min-h-12 bg-primary text-white font-display font-bold uppercase tracking-widest"
              >
                New draft
              </button>
            )}
          </div>
          <div className={`${cardClass} p-2 max-h-[70vh] overflow-y-auto`} data-testid="batch-list">
            {loading && <div className="p-4 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin inline mr-2" /> Loading…</div>}
            {!loading && filtered.length === 0 && <div className="p-4 text-sm text-muted-foreground">No batches on this pour yet.</div>}
            {filtered.map((row) => (
              <button
                key={row.id}
                type="button"
                onClick={() => openRow(row.id)}
                className={`w-full text-left min-h-12 px-3 py-2 border-b border-[#1C2230] ${selectedId === row.id ? "bg-primary/20" : ""}`}
              >
                <div className="font-mono text-sm">{row.mix_code || "no mix code"} · {row.status}</div>
                <div className="text-[10px] text-muted-foreground font-mono">{String(row.batched_at || "").slice(0, 16)} · w/cm {row.w_cm ?? "—"}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-4">
          {!canDraft && (
            <div className="min-h-12 px-4 border border-[#1C2230] flex items-center text-sm text-muted-foreground" data-testid="batch-readonly">
              QC / supervisors are read-only here. Production drafts. Plant manager confirms. Analyst never changes the mix.
            </div>
          )}
          <div className={`${cardClass} p-4 sm:p-6 space-y-4`} data-testid="batch-identity">
            <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-[#C9A227]">Pour identity</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Job">
                <select data-testid="batch-job" value={jobId} disabled={locked} onChange={(e) => setJobId(e.target.value)} className={inputClass}>
                  <option value="">Select job</option>
                  {jobs.map((j) => <option key={j.id} value={j.id}>{j.job_number} · {j.name}</option>)}
                </select>
              </Field>
              <Field label="Pour">
                <select data-testid="batch-pour" value={pourId} disabled={locked} onChange={(e) => setPourId(e.target.value)} className={inputClass}>
                  <option value="">Select pour</option>
                  {jobPours.map((p) => <option key={p.id} value={p.id}>{p.pour_number} · {p.pour_date}</option>)}
                </select>
              </Field>
            </div>
            <Field label="Beams">
              <div className="flex flex-wrap gap-2">
                {pourBeams.map((b) => (
                  <button
                    key={b.id}
                    type="button"
                    disabled={locked}
                    onClick={() => setBeamIds((cur) => (cur.includes(b.id) ? cur.filter((x) => x !== b.id) : [...cur, b.id]))}
                    className={`min-h-12 px-3 border text-xs font-semibold uppercase ${beamIds.includes(b.id) ? "bg-primary text-white border-primary" : "border-[#1C2230]"}`}
                  >
                    {b.mark}
                  </button>
                ))}
                {pourBeams.length === 0 && <span className="text-sm text-muted-foreground">No beams on this pour.</span>}
              </div>
            </Field>
            <Field label="Bed">
              <select data-testid="batch-bed" value={bedId} disabled={locked} onChange={(e) => setBedId(e.target.value)} className={inputClass}>
                <option value="">Not set</option>
                {beds.map((b) => <option key={b.id} value={b.id}>{b.name || `Bed ${b.bed_number}`}</option>)}
              </select>
            </Field>
          </div>

          <div className={`${cardClass} p-4 sm:p-6 space-y-4`}>
            <div className="flex flex-wrap gap-2 justify-between">
              <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-[#C9A227]">Mix + process</div>
              <button type="button" data-testid="batch-copy-prev" disabled={fieldsLocked} onClick={copyPrevious} className="min-h-12 px-4 border border-[#1C2230] text-xs font-semibold uppercase tracking-wider">Copy previous mix</button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Field label="Mix library">
                <select data-testid="batch-mix-library" value={form.mix_design_id} disabled={fieldsLocked} onChange={(e) => applyDesign(e.target.value)} className={inputClass}>
                  <option value="">Custom</option>
                  {designs.map((d) => <option key={d.id} value={d.id}>{d.mix_code}</option>)}
                </select>
              </Field>
              <Field label="Mix code">
                <input data-testid="batch-mix-code" disabled={fieldsLocked} value={form.mix_code} onChange={(e) => setForm({ ...form, mix_code: e.target.value })} className={inputClass} />
              </Field>
              <Field label="Mixer operator">
                <input disabled={fieldsLocked} value={form.mixer_operator} onChange={(e) => setForm({ ...form, mixer_operator: e.target.value })} className={inputClass} />
              </Field>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              <Field label="Target psi"><input disabled={fieldsLocked} inputMode="decimal" value={form.target_strength_psi} onChange={(e) => setForm({ ...form, target_strength_psi: e.target.value })} className={inputClass} /></Field>
              <Field label="Target air %"><input disabled={fieldsLocked} inputMode="decimal" value={form.target_air_pct} onChange={(e) => setForm({ ...form, target_air_pct: e.target.value })} className={inputClass} /></Field>
              <Field label="Target spread in"><input disabled={fieldsLocked} inputMode="decimal" value={form.target_spread_in} onChange={(e) => setForm({ ...form, target_spread_in: e.target.value })} className={inputClass} /></Field>
              <Field label="Target slump in"><input disabled={fieldsLocked} inputMode="decimal" value={form.target_slump_in} onChange={(e) => setForm({ ...form, target_slump_in: e.target.value })} className={inputClass} /></Field>
              <Field label="Target temp °F"><input disabled={fieldsLocked} inputMode="decimal" value={form.target_temp_f} onChange={(e) => setForm({ ...form, target_temp_f: e.target.value })} className={inputClass} /></Field>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Field label="Batch size"><input disabled={fieldsLocked} inputMode="decimal" value={form.batch_size} onChange={(e) => setForm({ ...form, batch_size: e.target.value })} className={inputClass} /></Field>
              <Field label="Unit">
                <select disabled={fieldsLocked} value={form.batch_unit} onChange={(e) => setForm({ ...form, batch_unit: e.target.value })} className={inputClass}>
                  <option value="yd3">yd³</option>
                  <option value="m3">m³</option>
                </select>
              </Field>
              <Field label="Mix time (sec)"><input disabled={fieldsLocked} inputMode="decimal" value={form.mixing_time_sec} onChange={(e) => setForm({ ...form, mixing_time_sec: e.target.value })} className={inputClass} /></Field>
              <Field label="Truck / mixer ID"><input disabled={fieldsLocked} value={form.truck_id} onChange={(e) => setForm({ ...form, truck_id: e.target.value })} className={inputClass} /></Field>
            </div>
            <Field label="Sequence notes">
              <textarea disabled={fieldsLocked} data-testid="batch-notes" rows={2} value={form.sequence_notes} onChange={(e) => setForm({ ...form, sequence_notes: e.target.value })} className={`${inputClass} py-2`} placeholder="Charge sequence" />
            </Field>
            <Field label="Deviations">
              <textarea disabled={fieldsLocked} rows={2} value={form.deviations} onChange={(e) => setForm({ ...form, deviations: e.target.value })} className={`${inputClass} py-2`} />
            </Field>
            <div className="min-h-12 px-4 border border-[#1C2230] flex items-center font-mono" data-testid="batch-wcm">
              w/cm {wcm != null ? wcm : "—"} (water+ice / cement+SCM)
            </div>
          </div>

          <div className={`${cardClass} p-4 sm:p-6 space-y-3`} data-testid="batch-env">
            <div className="flex items-center justify-between gap-2">
              <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-[#C9A227]">Environment</div>
              <button type="button" data-testid="batch-env-capture" disabled={fieldsLocked || envBusy} onClick={captureEnv} className="min-h-12 px-4 border border-[#C9A227] text-[#C9A227] text-xs font-semibold uppercase tracking-wider">
                {envBusy ? "Capturing…" : "Capture outdoor now"}
              </button>
            </div>
            {form.environment.env_flag && <div className="text-xs text-[#FFD600]">Flag: {form.environment.env_flag} — override any field. Weather down never blocks a batch.</div>}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Field label="Ambient °F"><input disabled={fieldsLocked} inputMode="decimal" value={form.environment.ambient_f || ""} onChange={(e) => setEnv("ambient_f", e.target.value)} className={inputClass} /></Field>
              <Field label="Mix temp °F"><input disabled={fieldsLocked} inputMode="decimal" value={form.environment.mix_temp_f || ""} onChange={(e) => setEnv("mix_temp_f", e.target.value)} className={inputClass} /></Field>
              <Field label="RH %"><input disabled={fieldsLocked} inputMode="decimal" value={form.environment.rh_pct || ""} onChange={(e) => setEnv("rh_pct", e.target.value)} className={inputClass} /></Field>
              <Field label="Pressure inHg"><input disabled={fieldsLocked} inputMode="decimal" value={form.environment.pressure_inhg || ""} onChange={(e) => setEnv("pressure_inhg", e.target.value)} className={inputClass} /></Field>
              <Field label="Wind mph"><input disabled={fieldsLocked} inputMode="decimal" value={form.environment.wind_mph || ""} onChange={(e) => setEnv("wind_mph", e.target.value)} className={inputClass} /></Field>
              <Field label="Weather">
                <select disabled={fieldsLocked} value={form.environment.weather || ""} onChange={(e) => setEnv("weather", e.target.value)} className={inputClass}>
                  <option value="">Tag</option>
                  {["sunny", "mainly sunny", "partly cloudy", "overcast", "rain", "fog", "snow", "thunderstorm"].map((w) => <option key={w} value={w}>{w}</option>)}
                </select>
              </Field>
              <Field label="Solar load"><input disabled={fieldsLocked} value={form.environment.solar_proxy || ""} onChange={(e) => setEnv("solar_proxy", e.target.value)} className={inputClass} /></Field>
            </div>
          </div>

          <div className={`${cardClass} p-4 sm:p-6 space-y-3`} data-testid="batch-ingredients">
            <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-[#C9A227]">Ingredients — big numbers</div>
            <div className="space-y-2">
              {form.ingredients.map((row, idx) => (
                <div key={`${row.kind}-${row.name}-${idx}`} className="grid grid-cols-2 sm:grid-cols-6 gap-2">
                  <input disabled={fieldsLocked} className={inputClass} value={row.name} onChange={(e) => setIng(idx, "name", e.target.value)} />
                  <input disabled={fieldsLocked} className={inputClass} placeholder="source" value={row.source || ""} onChange={(e) => setIng(idx, "source", e.target.value)} />
                  <input disabled={fieldsLocked} className={inputClass} inputMode="decimal" placeholder={row.kind === "admixture" ? "dose" : "lb"} value={row.kind === "admixture" ? (row.dosage ?? "") : (row.weight_lb ?? "")} onChange={(e) => setIng(idx, row.kind === "admixture" ? "dosage" : "weight_lb", e.target.value)} />
                  <input disabled={fieldsLocked} className={inputClass} placeholder="unit" value={row.dosage_unit || ""} onChange={(e) => setIng(idx, "dosage_unit", e.target.value)} />
                  <input disabled={fieldsLocked} className={inputClass} inputMode="decimal" placeholder="moist %" value={row.moisture_pct ?? ""} onChange={(e) => setIng(idx, "moisture_pct", e.target.value)} />
                  <div className="text-[10px] font-mono uppercase text-muted-foreground flex items-center">{row.kind}</div>
                </div>
              ))}
            </div>
          </div>

          <div className={`${cardClass} p-4 sm:p-6 space-y-3`} data-testid="batch-qc">
            <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-[#C9A227]">QC results — link Fresh Test + cylinders</div>
            <p className="text-xs text-muted-foreground">Prefer linking the chute ticket instead of retyping. Cylinders can be linked after confirm when breaks come in.</p>
            <div className="flex flex-wrap gap-2">
              {fresh.map((t) => {
                const on = (selected?.fresh_test_ids || []).includes(t.id);
                return (
                  <button key={t.id} type="button" onClick={() => {
                    const ids = new Set(selected?.fresh_test_ids || []);
                    if (on) ids.delete(t.id); else ids.add(t.id);
                    linkQc([...ids], selected?.cylinder_ids || []);
                  }} className={`min-h-12 px-3 border text-xs ${on ? "border-[#00E676] text-[#00E676]" : "border-[#1C2230]"}`}>
                    {(t.test_types || []).join("+") || "spread"} {t.spread_avg_in != null ? `${t.spread_avg_in}"` : ""} {t.air_content_pct != null ? `${t.air_content_pct}%` : ""}
                  </button>
                );
              })}
              {fresh.length === 0 && <Link to={`/fresh?job=${jobId}&pour=${pourId}`} className="min-h-12 px-4 border border-[#C9A227] text-[#C9A227] text-xs font-semibold uppercase flex items-center">Open Fresh Test</Link>}
            </div>
            <div className="flex flex-wrap gap-2">
              {cylinders.slice(0, 24).map((c) => {
                const on = (selected?.cylinder_ids || []).includes(c.id);
                return (
                  <button key={c.id} type="button" onClick={() => {
                    const ids = new Set(selected?.cylinder_ids || []);
                    if (on) ids.delete(c.id); else ids.add(c.id);
                    linkQc(selected?.fresh_test_ids || [], [...ids]);
                  }} className={`min-h-12 px-3 border text-xs font-mono ${on ? "border-[#00E676] text-[#00E676]" : "border-[#1C2230]"}`}>
                    {c.job_number} d{c.crush_age_days ?? "?"} {c.crush_psi ? `${c.crush_psi} psi` : "open"}
                  </button>
                );
              })}
            </div>
          </div>

          {recs.length > 0 && (
            <div className={`${cardClass} p-4 sm:p-6 space-y-3`} data-testid="batch-analyst">
              <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.25em] text-[#C9A227]">
                <Sparkles className="w-4 h-4" /> Analyst — recommendations only, never writes the mix
              </div>
              {recs.map((r) => (
                <div key={r.id} className="border border-[#1C2230] p-3">
                  <div className="font-semibold">{r.title}</div>
                  <p className="text-sm text-muted-foreground mt-1">{r.body}</p>
                  {(r.cite_batch_ids || []).length > 0 && <div className="text-[10px] font-mono mt-2 text-muted-foreground">Cited: {(r.cite_batch_ids || []).join(", ")}</div>}
                </div>
              ))}
            </div>
          )}

          <div className="flex flex-col sm:flex-row gap-2">
            {canDraft && !locked && (
              <button type="button" data-testid="batch-save" onClick={saveDraft} disabled={saving} className="flex-1 min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest">
                {saving ? "Saving…" : selectedId ? "Save draft" : "Save draft"}
              </button>
            )}
            {canConfirm && selectedId && !locked && (
              <button type="button" data-testid="batch-confirm" onClick={confirm} disabled={saving} className="flex-1 min-h-14 border border-[#00E676] text-[#00E676] font-display font-bold uppercase tracking-widest">
                Confirm (permanent)
              </button>
            )}
            {selectedId && (
              <>
                <Link
                  to={`/ncr?source=batch&batch=${selectedId}&category=batch&severity=major&job=${jobId}&pour=${pourId}&bed=${bedId}`}
                  className="min-h-14 px-4 border border-[#FF9100] text-[#FF9100] text-xs font-semibold uppercase flex items-center justify-center"
                >
                  File NCR
                </Link>
                <button type="button" onClick={() => downloadExport("pdf")} className="min-h-14 px-4 border border-[#1C2230] text-xs font-semibold uppercase">PDF</button>
                <button type="button" onClick={() => downloadExport("csv")} className="min-h-14 px-4 border border-[#1C2230] text-xs font-semibold uppercase">CSV</button>
              </>
            )}
          </div>
          {locked && canConfirm && (
            <div className={`${cardClass} p-4 space-y-2`}>
              <div className="text-xs text-[#FFD600]">Confirmed. Corrections are a new revision with a written reason — the original ticket stays.</div>
              <textarea rows={2} value={amendReason} onChange={(e) => setAmendReason(e.target.value)} placeholder="Why this amendment exists" className={`${inputClass} py-2`} />
              <button type="button" onClick={amend} className="min-h-12 px-4 border border-[#FFD600] text-[#FFD600] text-xs font-semibold uppercase">Draft amendment revision</button>
            </div>
          )}
          {locked && !canConfirm && (
            <div className="text-sm text-muted-foreground">This ticket is confirmed. QC and production are read-only. A plant manager amends with a written reason.</div>
          )}
        </div>
      </div>
    </Layout>
  );
}
