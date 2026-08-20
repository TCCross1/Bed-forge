import React, { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Briefcase, Lock, ShieldCheck } from "lucide-react";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, Field, inputClass, cardClass } from "../components/Layout";
import { useOpenJob } from "../context/OpenJobContext";
import { useAuth } from "../context/AuthContext";

export default function OpenJobPage() {
  const { user } = useAuth();
  const { jobs, openJob, pours, marks, privileges, openJobById, refresh } = useOpenJob();
  const [note, setNote] = useState("");
  const [managerEmail, setManagerEmail] = useState("admin@bedforge.com");
  const [managerPassword, setManagerPassword] = useState("");
  const [busy, setBusy] = useState("");
  const [draft, setDraft] = useState({ job_number: "", name: "", customer: "", state_spec: "KYTC" });
  const [jobNotes, setJobNotes] = useState("");
  const [jobStatus, setJobStatus] = useState("open");
  const canEdit = Boolean(privileges.can_edit_job);
  const selected = useMemo(() => jobs.find((item) => item.id === openJob?.id) || openJob, [jobs, openJob]);

  React.useEffect(() => {
    setJobNotes(selected?.notes || "");
    setJobStatus(selected?.status || "open");
  }, [selected?.id, selected?.notes, selected?.status]);

  const open = async (jobId) => {
    setBusy("open");
    try {
      await openJobById(jobId);
      toast.success("Open Job set");
    } catch (err) {
      const status = err?.response?.status;
      const detail = formatApiErrorDetail(err.response?.data?.detail, err);
      console.error("[open-job] set failed", status, err.response?.data, err);
      toast.error(status ? `${status}: ${detail}` : detail || "Failed to open job");
    } finally {
      setBusy("");
    }
  };

  const saveNotes = async () => {
    if (!selected?.id) return;
    setBusy("save");
    try {
      await api.patch(`/jobs/${selected.id}`, { notes: jobNotes, status: jobStatus, name: selected.name, customer: selected.customer });
      await refresh();
      toast.success("Job saved");
    } catch (err) {
      console.error("[open-job] save failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Job save requires Plant Manager authorization");
    } finally {
      setBusy("");
    }
  };

  const createJob = async () => {
    setBusy("create");
    try {
      const { data } = await api.post("/jobs", draft);
      await openJobById(data.id);
      toast.success(`Created ${data.job_number}`);
    } catch (err) {
      console.error("[open-job] create failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Could not create job");
    } finally {
      setBusy("");
    }
  };

  const requestOverride = async () => {
    setBusy("override");
    try {
      await api.post("/job-overrides", { note, manager_email: managerEmail, manager_password: managerPassword });
      setManagerPassword("");
      await refresh();
      toast.success("Override active — Spec DNA edits are logged");
    } catch (err) {
      console.error("[open-job] override failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Override was not accepted");
    } finally {
      setBusy("");
    }
  };

  return (
    <Layout>
      <PageHeader
        title="Open Job"
        subtitle="The open job is the plant cabinet — Specs, twins, tension, tags, and forms follow this job only"
      />
      <div className="p-4 sm:p-6 lg:p-8 grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2 space-y-4">
          <div className={`${cardClass} p-5`}>
            <div className="flex items-center gap-2 text-primary font-mono text-[11px] uppercase tracking-[0.2em]">
              <Briefcase className="w-4 h-4" /> Current cabinet
            </div>
            <div className="mt-3 font-display font-extrabold text-3xl uppercase tracking-tight">{selected?.job_number || "No job"}</div>
            <div className="mt-1 text-muted-foreground">{selected?.name || "Select a job to open"} — {selected?.customer || "—"}</div>
            <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                ["Status", (selected?.status || "open").toUpperCase()],
                ["Marks", String((marks || []).length)],
                ["Pours", String((pours || []).length)],
                ["Specs", String(selected?.spec_count ?? marks.length)],
              ].map(([label, value]) => (
                <div key={label} className="border border-border px-3 py-2">
                  <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">{label}</div>
                  <div className="font-mono text-white mt-1">{value}</div>
                </div>
              ))}
            </div>
            {(marks || []).length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {marks.map((mark) => (
                  <span key={mark} className="px-2 py-1 border border-primary/40 text-primary font-mono text-xs">MK {mark}</span>
                ))}
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {jobs.map((job) => (
              <button
                key={job.id}
                type="button"
                onClick={() => open(job.id)}
                data-testid={`open-job-${job.job_number}`}
                className={`text-left border rounded-sm p-4 min-h-24 ${job.id === selected?.id ? "border-primary bg-primary/10" : "border-border hover:border-primary/50"}`}
              >
                <div className="font-display font-bold uppercase tracking-wider">{job.job_number}</div>
                <div className="text-xs text-muted-foreground mt-1">{job.name} — {job.spec_count || 0} specs</div>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-4">
          {privileges.can_request_override && (
            <div className={`${cardClass} p-5 space-y-3`} data-testid="job-override-gate">
              <div className="flex items-center gap-2 text-[#E8C872] font-mono text-[11px] uppercase tracking-[0.18em]">
                <Lock className="w-4 h-4" /> Supervisor override
              </div>
              <p className="text-sm text-muted-foreground">QC Supervisor Spec edits require a proof note and Plant Manager password. This is logged. Do not use it for convenience.</p>
              <Field label="Proof note">
                <textarea className={`${inputClass} min-h-[88px] py-3`} value={note} onChange={(e) => setNote(e.target.value)} minLength={8} />
              </Field>
              <Field label="Plant Manager email">
                <input className={inputClass} value={managerEmail} onChange={(e) => setManagerEmail(e.target.value)} />
              </Field>
              <Field label="Plant Manager password">
                <input type="password" className={inputClass} value={managerPassword} onChange={(e) => setManagerPassword(e.target.value)} autoComplete="off" />
              </Field>
              <button type="button" onClick={requestOverride} disabled={busy === "override"} className="w-full min-h-12 bg-primary text-white font-display font-bold uppercase tracking-widest">
                {privileges.override_active ? "Refresh override" : "Request override"}
              </button>
              {privileges.override_active && <div className="text-xs font-mono text-[#00E676]">Override active until {String(privileges.override_expires_at || "").slice(11, 16)} UTC</div>}
            </div>
          )}

          <div className={`${cardClass} p-5 space-y-3`}>
            <div className="flex items-center gap-2 text-primary font-mono text-[11px] uppercase tracking-[0.18em]">
              <ShieldCheck className="w-4 h-4" /> Job record
            </div>
            <p className="text-xs text-muted-foreground">{canEdit ? `${user?.name} can save job edits.` : "Read-only. Plant Manager (or a logged supervisor override) can save."}</p>
            <Field label="Status">
              <select className={inputClass} disabled={!canEdit} value={jobStatus} onChange={(e) => setJobStatus(e.target.value)}>
                {["open", "hold", "complete"].map((status) => <option key={status} value={status}>{status}</option>)}
              </select>
            </Field>
            <Field label="Notes">
              <textarea
                className={`${inputClass} min-h-[88px] py-3`}
                disabled={!canEdit}
                value={jobNotes}
                onChange={(e) => setJobNotes(e.target.value)}
              />
            </Field>
            <button type="button" disabled={!canEdit || busy === "save"} onClick={saveNotes} className="w-full min-h-12 border border-border font-display font-bold uppercase tracking-widest disabled:opacity-50">
              Save job
            </button>
          </div>

          {canEdit && (
            <div className={`${cardClass} p-5 space-y-3`}>
              <div className="font-display font-bold uppercase tracking-wider">Create job</div>
              {["job_number", "name", "customer"].map((key) => (
                <Field key={key} label={key.replace("_", " ")}>
                  <input className={inputClass} value={draft[key]} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} />
                </Field>
              ))}
              <button type="button" onClick={createJob} disabled={busy === "create"} className="w-full min-h-12 bg-primary text-white font-display font-bold uppercase tracking-widest">Create & open</button>
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
