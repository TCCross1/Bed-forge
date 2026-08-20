import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Download, Loader2, Plus, Printer, Tags, Upload } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, Field, inputClass, cardClass } from "../components/Layout";
import CylinderPrint from "../components/CylinderPrint";
import { useAuth } from "../context/AuthContext";
import { useCompany } from "../context/CompanyContext";
import { useOpenJob } from "../context/OpenJobContext";
import { jobListParams } from "../lib/jobAccess";
import { toastNcrFromResponse } from "../lib/ncr";
import {
  MAX_BEAMS, MAX_SLOTS, cleanBeams, emptyRun, padBeams,
  statusColor, summarizeRun, todayISO,
} from "../lib/cylinderTags";

const STEPS = [
  { id: "setup", label: "Morning" },
  { id: "beams", label: "Beams" },
  { id: "summary", label: "Summary" },
  { id: "print", label: "Print" },
];

function cloneRun(run, tech) {
  const next = emptyRun(tech, run?.run_date || todayISO());
  if (!run) return next;
  next.id = run.id;
  next.run_date = run.run_date || next.run_date;
  next.job_count = run.job_count || 1;
  next.notes = run.notes || "";
  next.print_rows = run.print_rows || [];
  next.summaries = run.summaries || [];
  next.cylinders = run.cylinders || [];
  next.printed_at = run.printed_at;
  next.status = run.status;
  (run.slots || []).forEach((slot, i) => {
    if (i >= MAX_SLOTS) return;
    next.slots[i] = {
      ...next.slots[i],
      ...slot,
      beam_marks: padBeams(slot.beam_marks),
      job_id: slot.job_id || "",
      pour_id: slot.pour_id || "",
    };
  });
  return next;
}

export default function CylinderTags() {
  const { user } = useAuth();
  const company = useCompany();
  const { openJob } = useOpenJob();
  const tech = user?.name || "";
  const canBrand = user?.role === "admin" || user?.role === "executive" || user?.role === "qc_supervisor";

  const [step, setStep] = useState("list");
  const [run, setRun] = useState(() => emptyRun(tech));
  const [runs, setRuns] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [pours, setPours] = useState([]);
  const [beams, setBeams] = useState([]);
  const [activeSlot, setActiveSlot] = useState(1);
  const [busy, setBusy] = useState("");
  const [loading, setLoading] = useState(true);
  const [brandName, setBrandName] = useState("");
  const [appName, setAppName] = useState("");
  const [tagHeader, setTagHeader] = useState("");
  const [crush, setCrush] = useState({});

  const live = useMemo(() => summarizeRun(run), [run]);
  const visibleSlots = run.slots.slice(0, Math.max(1, Math.min(MAX_SLOTS, Number(run.job_count) || 1)));
  const current = run.slots[activeSlot - 1] || run.slots[0];

  const loadCatalog = useCallback(async () => {
    try {
      const [jobRes, pourRes, beamRes, runRes] = await Promise.all([
        api.get("/jobs"),
        api.get("/pours", { params: jobListParams(openJob) }),
        api.get("/beams", { params: jobListParams(openJob) }),
        api.get("/cylinder-runs"),
      ]);
      const allJobs = jobRes.data || [];
      setJobs(openJob?.id ? allJobs.filter((job) => job.id === openJob.id) : allJobs);
      setPours(pourRes.data || []);
      setBeams(beamRes.data || []);
      setRuns(runRes.data || []);
    } catch (err) {
      console.error("[tags] catalog failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load jobs");
    } finally {
      setLoading(false);
    }
  }, [openJob?.id]);

  useEffect(() => {
    loadCatalog();
  }, [loadCatalog]);

  useEffect(() => {
    setBrandName(company.company_name || "");
    setAppName(company.app_name || "");
    setTagHeader(company.tag_header || "");
  }, [company.company_name, company.app_name, company.tag_header]);

  const patchSlot = (index, patch) => {
    setRun((cur) => {
      const slots = cur.slots.map((slot, i) => (i === index ? { ...slot, ...patch } : slot));
      return { ...cur, slots };
    });
  };

  const startNew = () => {
    const draft = emptyRun(tech);
    draft.slots[0].use_today = true;
    draft.slots[0].qc_tech = tech;
    if (openJob?.id) {
      draft.slots[0].job_id = openJob.id;
      draft.slots[0].job_number = openJob.job_number || "";
    }
    setRun(draft);
    setActiveSlot(1);
    setStep("setup");
  };

  const openRun = async (id) => {
    setBusy("open");
    try {
      const { data } = await api.get(`/cylinder-runs/${id}`);
      setRun(cloneRun(data, tech));
      setActiveSlot(1);
      setStep("summary");
    } catch (err) {
      console.error("[tags] open failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to open tag run");
    } finally {
      setBusy("");
    }
  };

  const pullJob = (slotIndex, jobId) => {
    const job = jobs.find((j) => j.id === jobId);
    if (!job) {
      patchSlot(slotIndex, { job_id: "", job_number: "" });
      return;
    }
    const jobPours = pours.filter((p) => p.job_id === job.id);
    const pour = jobPours[0];
    const marks = beams.filter((b) => b.job_id === job.id && (!pour || !b.pour_id || b.pour_id === pour.id)).map((b) => b.mark);
    patchSlot(slotIndex, {
      use_today: true,
      job_id: job.id,
      job_number: job.job_number,
      pour_id: pour?.id || "",
      pour_number: pour?.pour_number || "",
      pour_date: pour?.pour_date || run.run_date,
      expected_beam_count: marks.length,
      beam_marks: padBeams(marks),
      qc_tech: run.slots[slotIndex].qc_tech || tech,
    });
    toast.success(`Pulled ${job.job_number}${marks.length ? ` · ${marks.length} beams` : ""}`);
  };

  const pullPour = (slotIndex, pourId) => {
    const pour = pours.find((p) => p.id === pourId);
    if (!pour) {
      patchSlot(slotIndex, { pour_id: "", pour_number: "" });
      return;
    }
    const job = jobs.find((j) => j.id === pour.job_id);
    const marks = beams.filter((b) => b.pour_id === pour.id || (b.job_id === pour.job_id && !b.pour_id)).map((b) => b.mark);
    patchSlot(slotIndex, {
      pour_id: pour.id,
      pour_number: pour.pour_number,
      pour_date: pour.pour_date || run.run_date,
      job_id: job?.id || run.slots[slotIndex].job_id,
      job_number: job?.job_number || run.slots[slotIndex].job_number,
      expected_beam_count: marks.length || run.slots[slotIndex].expected_beam_count,
      beam_marks: marks.length ? padBeams(marks) : run.slots[slotIndex].beam_marks,
    });
  };

  const saveRun = async (nextStep) => {
    setBusy("save");
    try {
      const payload = {
        run_date: run.run_date || todayISO(),
        job_count: Number(run.job_count) || 1,
        notes: run.notes || "",
        slots: run.slots.map((slot) => ({
          ...slot,
          job_id: slot.job_id || null,
          pour_id: slot.pour_id || null,
          expected_beam_count: Number(slot.expected_beam_count) || 0,
          cylinder_tags_needed: Number(slot.cylinder_tags_needed) || 0,
          beam_marks: padBeams(slot.beam_marks),
        })),
      };
      const req = run.id ? api.patch(`/cylinder-runs/${run.id}`, payload) : api.post("/cylinder-runs", payload);
      const { data } = await req;
      setRun(cloneRun(data, tech));
      await loadCatalog();
      toast.success(data.print_ready ? "Run saved — ready to print" : "Run saved");
      if (nextStep) setStep(nextStep);
      return data;
    } catch (err) {
      console.error("[tags] save failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to save tag run");
    } finally {
      setBusy("");
    }
  };

  const downloadPdf = async () => {
    setBusy("pdf");
    try {
      let id = run.id;
      if (!id) {
        const saved = await saveRun("print");
        id = saved?.id;
      }
      if (!id) throw new Error("Save the run before downloading PDF");
      const res = await api.get(`/cylinder-runs/${id}/pdf`, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `cylinder-tags-${run.run_date || "run"}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      await api.post(`/cylinder-runs/${id}/print`);
      toast.success("PDF downloaded — print at Actual Size / 100%");
    } catch (err) {
      console.error("[tags] pdf failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to build PDF");
    } finally {
      setBusy("");
    }
  };

  const printTags = async () => {
    try {
      let id = run.id;
      if (!id) {
        const saved = await saveRun("print");
        id = saved?.id;
      }
      if (id) await api.post(`/cylinder-runs/${id}/print`);
    } catch (err) {
      console.error("[tags] print mark failed", err);
    }
    window.print();
  };

  const saveBrand = async () => {
    setBusy("brand");
    try {
      await api.patch("/company", { company_name: brandName, app_name: appName, tag_header: tagHeader });
      await company.reload();
      toast.success("Company branding saved");
    } catch (err) {
      console.error("[tags] brand failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to save branding");
    } finally {
      setBusy("");
    }
  };

  const uploadLogo = async (file) => {
    if (!file) return;
    setBusy("logo");
    try {
      const body = new FormData();
      body.append("file", file);
      await api.post("/company/logo", body);
      await company.reload();
      toast.success("Company logo updated — tags will use it");
    } catch (err) {
      console.error("[tags] logo failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to upload logo");
    } finally {
      setBusy("");
    }
  };

  const saveCrush = async (cylinder) => {
    const form = crush[cylinder.id] || {};
    setBusy(`crush-${cylinder.id}`);
    try {
      const { data } = await api.patch(`/cylinders/${cylinder.id}/crush`, {
        crush_psi: form.crush_psi === "" || form.crush_psi == null ? null : parseFloat(form.crush_psi),
        crush_date: form.crush_date || todayISO(),
        crush_age_days: form.crush_age_days === "" || form.crush_age_days == null ? null : parseInt(form.crush_age_days, 10),
        required_psi: form.required_psi === "" || form.required_psi == null ? null : parseFloat(form.required_psi),
        notes: form.notes || "",
      });
      setRun((cur) => ({
        ...cur,
        cylinders: (cur.cylinders || []).map((c) => (c.id === data.id ? data : c)),
      }));
      toast.success(data.release_ok ? "Crush recorded — release OK" : "Crush recorded");
      toastNcrFromResponse(data);
    } catch (err) {
      console.error("[tags] crush failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to record crush");
    } finally {
      setBusy("");
    }
  };

  const printRows = run.print_rows || [];

  return (
    <Layout>
      <PageHeader
        title="Cylinder Tags"
        subtitle="Morning setup · beam entry · auto labels · white-label print"
        right={
          <div className="flex flex-wrap gap-2 justify-end">
            {canBrand && (
              <button type="button" onClick={() => setStep("brand")} className="min-h-12 px-4 border border-[#1C2230] font-semibold uppercase tracking-wider text-sm hover:border-primary hover:text-primary">
                Branding
              </button>
            )}
            <button type="button" data-testid="tags-new" onClick={startNew} className="min-h-12 px-4 bg-primary text-white font-display font-bold uppercase tracking-widest flex items-center gap-2">
              <Plus className="w-4 h-4" /> New run
            </button>
          </div>
        }
      />

      <div className="p-4 sm:p-6 lg:p-8 space-y-4 max-w-6xl cylinder-tags-app">
        {step !== "list" && step !== "brand" && (
          <div className={`${cardClass} p-2 grid grid-cols-4 gap-1`} data-testid="tags-steps">
            {STEPS.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setStep(item.id)}
                className={`min-h-12 font-display font-bold uppercase tracking-widest text-xs sm:text-sm ${step === item.id ? "bg-primary text-white" : "text-muted-foreground hover:text-white"}`}
              >
                {item.label}
              </button>
            ))}
          </div>
        )}

        {step === "list" && (
          <div className="space-y-3" data-testid="tags-run-list">
            {loading ? (
              <div className="flex items-center justify-center h-40 text-muted-foreground"><Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading runs…</div>
            ) : runs.length === 0 ? (
              <div className={`${cardClass} p-8 text-center`}>
                <Tags className="w-8 h-8 mx-auto mb-3 text-primary" />
                <div className="font-display font-bold uppercase">No cylinder tag runs</div>
                <p className="text-sm text-muted-foreground mt-2">Replace the Excel generator. Set up this morning’s jobs, enter beams, print.</p>
                <button type="button" onClick={startNew} className="mt-4 min-h-14 px-6 bg-primary text-white font-display font-bold uppercase tracking-widest">Start morning setup</button>
              </div>
            ) : runs.map((row) => (
              <button
                key={row.id}
                type="button"
                onClick={() => openRun(row.id)}
                className={`${cardClass} p-4 w-full text-left hover:border-primary`}
                data-testid={`tags-run-${row.id}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-display font-bold uppercase tracking-wider">{row.run_date} · {row.ready_jobs || 0} jobs ready</div>
                    <div className="text-xs font-mono text-muted-foreground mt-1">
                      {row.total_physical_labels || 0} physical labels · {row.created_by || "—"}
                    </div>
                  </div>
                  <span className="text-[10px] font-mono uppercase tracking-widest" style={{ color: row.print_ready ? "#00E676" : "#FFD600" }}>
                    {row.status || "draft"}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}

        {step === "setup" && (
          <div className="space-y-4" data-testid="tags-morning-setup">
            <div className={`${cardClass} p-4 sm:p-6 grid grid-cols-1 sm:grid-cols-3 gap-3`}>
              <Field label="Run date">
                <input type="date" data-testid="tags-run-date" value={run.run_date} onChange={(e) => setRun({ ...run, run_date: e.target.value })} className={inputClass} />
              </Field>
              <Field label="Jobs today (max 10)">
                <input type="number" min={1} max={MAX_SLOTS} data-testid="tags-job-count" value={run.job_count} onChange={(e) => setRun({ ...run, job_count: Math.max(1, Math.min(MAX_SLOTS, parseInt(e.target.value, 10) || 1)) })} className={inputClass} />
              </Field>
              <Field label="Live labels">
                <div className={`${inputClass} flex items-center`} data-testid="tags-live-count">{live.total_physical_labels} physical</div>
              </Field>
            </div>
            {visibleSlots.map((slot, index) => {
              const summary = live.summaries[index];
              const jobPours = pours.filter((p) => !slot.job_id || p.job_id === slot.job_id);
              return (
                <div key={slot.slot} className={`${cardClass} p-4 sm:p-6 space-y-3`} data-testid={`tags-slot-${slot.slot}`}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-display font-bold uppercase tracking-wider">Job slot {slot.slot}</div>
                    <button
                      type="button"
                      data-testid={`tags-use-today-${slot.slot}`}
                      onClick={() => patchSlot(index, { use_today: !slot.use_today, qc_tech: slot.qc_tech || tech })}
                      className={`min-h-12 px-4 font-mono text-xs uppercase ${slot.use_today ? "bg-primary text-white" : "border border-[#1C2230] text-muted-foreground"}`}
                    >
                      Use today? {slot.use_today ? "Yes" : "No"}
                    </button>
                  </div>
                  {slot.use_today && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                      <Field label="QC tech name">
                        <input data-testid={`tags-tech-${slot.slot}`} value={slot.qc_tech} onChange={(e) => patchSlot(index, { qc_tech: e.target.value })} className={inputClass} />
                      </Field>
                      <Field label="Pull BedForge job">
                        <select data-testid={`tags-pull-job-${slot.slot}`} value={slot.job_id || ""} onChange={(e) => pullJob(index, e.target.value)} className={inputClass}>
                          <option value="">Manual entry</option>
                          {jobs.map((job) => (
                            <option key={job.id} value={job.id}>{job.job_number} · {job.name}</option>
                          ))}
                        </select>
                      </Field>
                      <Field label="Job #">
                        <input data-testid={`tags-jobno-${slot.slot}`} value={slot.job_number} onChange={(e) => patchSlot(index, { job_number: e.target.value })} className={inputClass} />
                      </Field>
                      <Field label="Expected beam count">
                        <input type="number" min={0} max={MAX_BEAMS} value={slot.expected_beam_count} onChange={(e) => patchSlot(index, { expected_beam_count: parseInt(e.target.value, 10) || 0 })} className={inputClass} />
                      </Field>
                      <Field label="Pour">
                        <select value={slot.pour_id || ""} onChange={(e) => pullPour(index, e.target.value)} className={inputClass}>
                          <option value="">Manual pour</option>
                          {jobPours.map((pour) => (
                            <option key={pour.id} value={pour.id}>{pour.pour_number} · {pour.pour_date}</option>
                          ))}
                        </select>
                      </Field>
                      <Field label="Pour #">
                        <input value={slot.pour_number} onChange={(e) => patchSlot(index, { pour_number: e.target.value })} className={inputClass} />
                      </Field>
                      <Field label="Date">
                        <input type="date" value={slot.pour_date} onChange={(e) => patchSlot(index, { pour_date: e.target.value })} className={inputClass} />
                      </Field>
                      <Field label="Cylinder tags needed">
                        <input type="number" min={0} max={24} data-testid={`tags-cyl-needed-${slot.slot}`} value={slot.cylinder_tags_needed} onChange={(e) => patchSlot(index, { cylinder_tags_needed: parseInt(e.target.value, 10) || 0 })} className={inputClass} />
                      </Field>
                      <div className="flex items-end">
                        <div className="text-[10px] font-mono uppercase tracking-widest" style={{ color: statusColor(summary?.status) }}>{summary?.status}</div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
            <button type="button" onClick={() => setStep("beams")} className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest">Enter beam numbers</button>
          </div>
        )}

        {step === "beams" && (
          <div className="space-y-4" data-testid="tags-beam-entry">
            <div className="flex gap-2 overflow-x-auto pb-1">
              {visibleSlots.filter((s) => s.use_today).map((slot) => (
                <button
                  key={slot.slot}
                  type="button"
                  onClick={() => setActiveSlot(slot.slot)}
                  className={`min-h-12 px-4 shrink-0 font-mono text-xs uppercase ${activeSlot === slot.slot ? "bg-primary text-white" : "border border-[#1C2230]"}`}
                >
                  Slot {slot.slot} · {slot.job_number || "JOB"}
                </button>
              ))}
            </div>
            <div className={`${cardClass} p-4 sm:p-6 space-y-3`}>
              <div className="font-display font-bold uppercase tracking-wider">
                Beams for {current.job_number || `slot ${current.slot}`} · QC {current.qc_tech || "—"}
              </div>
              <p className="text-xs text-muted-foreground">One beam number per cell. Unused cells stay blank and never print. Max {MAX_BEAMS}.</p>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
                {current.beam_marks.map((mark, i) => (
                  <input
                    key={`${current.slot}-${i}`}
                    data-testid={`tags-beam-${current.slot}-${i}`}
                    value={mark}
                    placeholder={`${i + 1}`}
                    onChange={(e) => {
                      const marks = [...current.beam_marks];
                      marks[i] = e.target.value;
                      patchSlot(current.slot - 1, { beam_marks: marks });
                    }}
                    className={inputClass}
                  />
                ))}
              </div>
              <div className="text-[10px] font-mono text-muted-foreground">
                Entered {cleanBeams(current.beam_marks).length}
                {current.expected_beam_count ? ` / expected ${current.expected_beam_count}` : ""}
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button type="button" onClick={() => setStep("setup")} className="min-h-14 border border-[#1C2230] font-mono text-xs uppercase">Back to setup</button>
              <button type="button" onClick={() => saveRun("summary")} disabled={busy === "save"} className="min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest disabled:opacity-60">
                {busy === "save" ? "Saving…" : "Save & summary"}
              </button>
            </div>
          </div>
        )}

        {step === "summary" && (
          <div className="space-y-4" data-testid="tags-summary">
            <div className={`${cardClass} p-4 sm:p-6 grid grid-cols-2 sm:grid-cols-4 gap-3`}>
              <div>
                <div className="text-[10px] font-mono uppercase text-muted-foreground">Ready jobs</div>
                <div className="font-mono text-xl text-[#00E676]">{live.ready_jobs}</div>
              </div>
              <div>
                <div className="text-[10px] font-mono uppercase text-muted-foreground">Incomplete</div>
                <div className="font-mono text-xl text-[#FFD600]">{live.incomplete_jobs}</div>
              </div>
              <div>
                <div className="text-[10px] font-mono uppercase text-muted-foreground">Physical labels</div>
                <div className="font-mono text-xl">{live.total_physical_labels}</div>
              </div>
              <div>
                <div className="text-[10px] font-mono uppercase text-muted-foreground">Status</div>
                <div className="font-display font-bold uppercase" style={{ color: live.print_ready ? "#00E676" : "#FFD600" }}>
                  {live.print_ready ? "READY TO PRINT" : live.incomplete_jobs ? "INCOMPLETE" : "NOT USED"}
                </div>
              </div>
            </div>
            {live.summaries.filter((_, i) => i < (Number(run.job_count) || 1)).map((summary) => (
              <div key={summary.slot} className={`${cardClass} p-4 sm:p-6`} data-testid={`tags-summary-${summary.slot}`}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-display font-bold uppercase tracking-wider">Slot {summary.slot} · {summary.job_number || "No job"}</div>
                    <div className="text-xs font-mono text-muted-foreground mt-1">
                      QC {summary.qc_tech || "—"} · Pour {summary.pour_number || "—"} · {summary.pour_date || "—"}
                    </div>
                  </div>
                  <span className="text-[10px] font-mono uppercase tracking-widest" style={{ color: statusColor(summary.status) }}>{summary.status}</span>
                </div>
                {summary.status !== "NOT USED" && (
                  <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] font-mono">
                    <div>Expected {summary.expected_beam_count}</div>
                    <div>Entered {summary.entered_beam_count}</div>
                    <div>Cyl tags {summary.cylinder_tags_needed}</div>
                    <div>Labels/cyl {summary.labels_per_cylinder}</div>
                    <div>Physical {summary.physical_labels}</div>
                    <div>Cumulative {summary.cumulative_labels}</div>
                  </div>
                )}
                {summary.beam_list?.length > 0 && (
                  <div className="mt-3 text-sm font-mono text-primary">{summary.beam_list.join("  ·  ")}</div>
                )}
              </div>
            ))}
            {(run.cylinders || []).length > 0 && (
              <div className={`${cardClass} p-4 sm:p-6 space-y-3`} data-testid="tags-cylinders">
                <div className="font-display font-bold uppercase tracking-wider">Cylinder sets · crush / release</div>
                {(run.cylinders || []).map((cyl) => {
                  const form = crush[cyl.id] || {
                    crush_psi: cyl.crush_psi ?? "",
                    crush_date: cyl.crush_date || todayISO(),
                    crush_age_days: cyl.crush_age_days ?? "",
                    required_psi: cyl.required_psi ?? "",
                    notes: cyl.notes || "",
                  };
                  return (
                    <div key={cyl.id} className="border border-[#1C2230] p-3 space-y-2">
                      <div className="flex justify-between gap-2">
                        <div className="font-mono text-sm">{cyl.set_id}</div>
                        <span className="text-[10px] font-mono uppercase" style={{ color: cyl.release_ok ? "#00E676" : cyl.crush_psi ? "#FFD600" : "#8B93A7" }}>{cyl.status}</span>
                      </div>
                      <div className="text-[10px] font-mono text-muted-foreground">{(cyl.beam_marks || []).join(" · ")}</div>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                        <input placeholder="Crush psi" type="number" value={form.crush_psi} onChange={(e) => setCrush((c) => ({ ...c, [cyl.id]: { ...form, crush_psi: e.target.value } }))} className={inputClass} />
                        <input placeholder="Required psi" type="number" value={form.required_psi} onChange={(e) => setCrush((c) => ({ ...c, [cyl.id]: { ...form, required_psi: e.target.value } }))} className={inputClass} />
                        <input placeholder="Age days" type="number" value={form.crush_age_days} onChange={(e) => setCrush((c) => ({ ...c, [cyl.id]: { ...form, crush_age_days: e.target.value } }))} className={inputClass} />
                        <input type="date" value={form.crush_date} onChange={(e) => setCrush((c) => ({ ...c, [cyl.id]: { ...form, crush_date: e.target.value } }))} className={inputClass} />
                      </div>
                      <button type="button" onClick={() => saveCrush(cyl)} disabled={Boolean(busy)} className="min-h-12 px-4 border border-[#1C2230] font-mono text-xs uppercase hover:border-primary">
                        Record crush
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <button type="button" onClick={() => setStep("beams")} className="min-h-14 border border-[#1C2230] font-mono text-xs uppercase">Edit beams</button>
              <button type="button" onClick={() => saveRun("summary")} disabled={busy === "save"} className="min-h-14 border border-[#1C2230] font-display font-bold uppercase tracking-widest disabled:opacity-60">
                {busy === "save" ? "Saving…" : "Save run"}
              </button>
              <button type="button" onClick={() => saveRun("print")} disabled={busy === "save" || live.ready_jobs < 1} className="min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest disabled:opacity-60">
                Print tags
              </button>
            </div>
          </div>
        )}

        {step === "print" && (
          <div className="space-y-4" data-testid="tags-print">
            <div className={`${cardClass} p-4 sm:p-6 flex flex-col sm:flex-row gap-2 justify-between items-start print:hidden`}>
              <div>
                <div className="font-display font-bold uppercase tracking-wider">{printRows.length} physical labels</div>
                <p className="text-xs text-muted-foreground mt-1">Print at Actual Size / 100%. Empty fields are omitted. Continuation pages show PAGE n OF m.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button type="button" data-testid="tags-print-btn" onClick={printTags} className="min-h-12 px-4 bg-primary text-white font-display font-bold uppercase tracking-widest flex items-center gap-2">
                  <Printer className="w-4 h-4" /> Print
                </button>
                <button type="button" data-testid="tags-pdf-btn" onClick={downloadPdf} disabled={busy === "pdf"} className="min-h-12 px-4 border border-[#1C2230] font-semibold uppercase tracking-wider flex items-center gap-2 disabled:opacity-60">
                  {busy === "pdf" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />} PDF
                </button>
              </div>
            </div>
            <div className={`${cardClass} p-3 overflow-auto max-h-[480px] print:max-h-none print:overflow-visible print:border-0 print:bg-white`}>
              <CylinderPrint rows={printRows} runDate={run.run_date} />
            </div>
            {printRows.length > 0 && (
              <div className={`${cardClass} p-4 overflow-x-auto print:hidden`}>
                <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2">Auto-generated print data</div>
                <table className="w-full text-[11px] font-mono">
                  <thead>
                    <tr className="text-left text-muted-foreground">
                      <th className="pr-3 py-1">#</th>
                      <th className="pr-3">Slot</th>
                      <th className="pr-3">Job</th>
                      <th className="pr-3">Cyl</th>
                      <th className="pr-3">Part</th>
                      <th>Beams</th>
                    </tr>
                  </thead>
                  <tbody>
                    {printRows.map((row) => (
                      <tr key={row.label_number} className="border-t border-[#1C2230]">
                        <td className="pr-3 py-1">{row.label_number}</td>
                        <td className="pr-3">{row.job_slot}</td>
                        <td className="pr-3">{row.job_number}</td>
                        <td className="pr-3">{row.cylinder_copy}/{row.copies_total}</td>
                        <td className="pr-3">{row.part_caption || `${row.part}/${row.parts_total}`}</td>
                        <td>{[row.beam_1, row.beam_2, row.beam_3, row.beam_4, row.beam_5, row.beam_6].filter(Boolean).join(" · ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {step === "brand" && canBrand && (
          <div className={`${cardClass} p-4 sm:p-6 space-y-4`} data-testid="tags-branding">
            <div className="font-display font-bold uppercase tracking-wider">Multi-company branding</div>
            <p className="text-sm text-muted-foreground">Logo and company name are interchangeable. Tags, PDFs, and form headers use this tenant — not a hard-coded lockup.</p>
            {company.logoSrc ? <img src={company.logoSrc} alt="Company logo" className="h-16 object-contain bg-white p-2" /> : <div className="text-xs font-mono text-muted-foreground">No logo uploaded — tags print the company name.</div>}
            <Field label="Company name">
              <input data-testid="tags-company-name" value={brandName} onChange={(e) => setBrandName(e.target.value)} className={inputClass} />
            </Field>
            <Field label="App name">
              <input value={appName} onChange={(e) => setAppName(e.target.value)} className={inputClass} />
            </Field>
            <Field label="Tag header (optional override)">
              <input value={tagHeader} onChange={(e) => setTagHeader(e.target.value)} className={inputClass} placeholder="Leave blank to use company name" />
            </Field>
            <label className="min-h-12 px-4 border border-[#1C2230] flex items-center justify-center gap-2 cursor-pointer font-semibold uppercase tracking-wider hover:border-primary">
              <Upload className="w-4 h-4" /> Upload logo
              <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => uploadLogo(e.target.files?.[0])} />
            </label>
            <button type="button" onClick={saveBrand} disabled={busy === "brand"} className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest disabled:opacity-60">
              {busy === "brand" ? "Saving…" : "Save branding"}
            </button>
            <button type="button" onClick={() => setStep("list")} className="w-full min-h-12 border border-[#1C2230] font-mono text-xs uppercase">Back</button>
          </div>
        )}
      </div>
    </Layout>
  );
}
