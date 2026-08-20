import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AlertTriangle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { Field, PageHeader, cardClass, inputClass } from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import { useOpenJob } from "../context/OpenJobContext";
import { jobListParams } from "../lib/jobAccess";
import {
  NCR_CATEGORIES, NCR_SEVERITIES, NCR_STATUSES, canCloseNcr, canCreateNcr, canManageNcr, ncrPhotoPath,
} from "../lib/ncr";

const EMPTY = {
  category: "visual",
  sub_type: "",
  severity: "minor",
  description: "",
  containment: "",
  root_cause: "",
  corrective_action: "",
  preventive_action: "",
  verification_how: "",
  verification_by: "",
  signoff: "",
  assigned_to: "",
  assigned_role: "",
  beam_ids: [],
  job_id: "",
  pour_id: "",
  bed_id: "",
  batch_id: "",
};

function sevColor(s) {
  return (NCR_SEVERITIES.find((x) => x.id === s) || {}).color || "#8B93A7";
}

function PhotoThumb({ ncrId, filename }) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    if (!ncrId || !filename) return undefined;
    let alive = true;
    let objectUrl = "";
    api.get(ncrPhotoPath(ncrId, filename), { responseType: "blob" })
      .then((r) => {
        objectUrl = URL.createObjectURL(r.data);
        if (alive) setSrc(objectUrl);
      })
      .catch((err) => console.error("[ncr] photo load failed", err));
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [ncrId, filename]);
  if (!src) {
    return <div className="h-24 bg-[#0A0C10] border border-[#1C2230]" />;
  }
  return <img src={src} alt="" className="h-24 w-full object-cover border border-[#1C2230]" />;
}

export default function NCRDesk() {
  const { user } = useAuth();
  const { openJob } = useOpenJob();
  const [params] = useSearchParams();
  const manage = canManageNcr(user?.role);
  const canFile = canCreateNcr(user?.role);
  const [jobs, setJobs] = useState([]);
  const [pours, setPours] = useState([]);
  const [beams, setBeams] = useState([]);
  const [beds, setBeds] = useState([]);
  const [rows, setRows] = useState([]);
  const [insights, setInsights] = useState([]);
  const [selectedId, setSelectedId] = useState(params.get("id") || "");
  const [form, setForm] = useState({ ...EMPTY });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [filter, setFilter] = useState({
    status: params.get("status") || "",
    severity: params.get("severity") && !params.get("source") ? (params.get("severity") || "") : "",
    overdue: params.get("overdue") === "1",
  });
  const [note, setNote] = useState("");

  const query = useMemo(() => ({
    beam: params.get("beam") || "",
    bed: params.get("bed") || "",
    pour: params.get("pour") || "",
    job: params.get("job") || "",
    batch: params.get("batch") || "",
    source: params.get("source") || "",
    source_id: params.get("source_id") || "",
    category: params.get("category") || "",
    severity: params.get("severity") || "",
    desc: params.get("desc") || "",
    title: params.get("title") || "",
  }), [params]);

  const selected = rows.find((r) => r.id === selectedId) || null;
  const locked = Boolean(selected?.immutable);
  const photos = selected?.photos || [];
  const canCloseThis = canCloseNcr(user?.role, form.severity || selected?.severity);
  const majorNeedsRoot = ["major", "critical"].includes(form.severity) && !String(form.root_cause || "").trim();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [j, p, b, d, n, ins] = await Promise.all([
        api.get("/jobs"),
        api.get("/pours", { params: jobListParams(openJob) }),
        api.get("/beams", { params: jobListParams(openJob) }),
        api.get("/beds"),
        api.get("/ncrs", { params: { beam_id: query.beam || undefined } }),
        api.get("/ncrs/insights"),
      ]);
      setJobs(j.data || []);
      setPours(p.data || []);
      setBeams(b.data || []);
      setBeds(d.data || []);
      setRows(n.data || []);
      setInsights(ins.data?.recommendations || []);
    } catch (err) {
      console.error("[ncr] load failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load NCRs");
    } finally {
      setLoading(false);
    }
  }, [query.beam, openJob?.id]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (selected) {
      setForm({
        category: selected.category || "visual",
        sub_type: selected.sub_type || "",
        severity: selected.severity || "minor",
        description: selected.description || "",
        containment: selected.containment || "",
        root_cause: selected.root_cause || "",
        corrective_action: selected.corrective_action || "",
        preventive_action: selected.preventive_action || "",
        verification_how: selected.verification_how || "",
        verification_by: selected.verification_by || "",
        signoff: selected.signoff || "",
        assigned_to: selected.assigned_to || "",
        assigned_role: selected.assigned_role || "",
        beam_ids: selected.beam_ids || [],
        job_id: selected.job_id || "",
        pour_id: selected.pour_id || "",
        bed_id: selected.bed_id || "",
        batch_id: selected.batch_id || "",
      });
      return;
    }
    setForm({
      ...EMPTY,
      category: query.category || "visual",
      severity: query.severity || "minor",
      description: query.desc || "",
      beam_ids: query.beam ? [query.beam] : [],
      job_id: query.job,
      pour_id: query.pour,
      bed_id: query.bed,
      batch_id: query.batch,
    });
  }, [selectedId, selected, query]);

  const set = (key, value) => setForm((cur) => ({ ...cur, [key]: value }));

  const saveNew = async () => {
    if (!canFile) {
      toast.error("Not allowed to file an NCR");
      return;
    }
    if (!form.description.trim()) {
      toast.error("Describe the non-conformance");
      return;
    }
    if (!form.containment.trim()) {
      toast.error("Record the immediate containment action");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post("/ncrs", {
        ...form,
        source_type: query.source || "manual",
        source_id: query.source_id || "",
      });
      toast.success("NCR filed");
      setSelectedId(data.id);
      await load();
    } catch (err) {
      console.error("[ncr] create failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail, err) || "Failed to file NCR");
    } finally {
      setSaving(false);
    }
  };

  const saveEdit = async () => {
    if (!selectedId) return;
    setSaving(true);
    try {
      await api.patch(`/ncrs/${selectedId}`, form);
      toast.success("NCR updated");
      await load();
    } catch (err) {
      console.error("[ncr] update failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to update NCR");
    } finally {
      setSaving(false);
    }
  };

  const move = async (status) => {
    if (!selectedId) return;
    if (status === "closed" && majorNeedsRoot) {
      toast.error("Root cause is required before closing a Major or Critical NCR");
      return;
    }
    if (status === "closed" && !canCloseThis) {
      toast.error("QC supervisor or plant manager must close Major and Critical NCRs");
      return;
    }
    if (status === "investigating" && selected?.immutable && !note.trim()) {
      toast.error("Written reason required to reopen a closed NCR");
      return;
    }
    setSaving(true);
    try {
      await api.post(`/ncrs/${selectedId}/transition`, {
        status,
        note,
        root_cause: form.root_cause,
        corrective_action: form.corrective_action,
        verification_by: form.verification_by || user?.name,
        verification_how: form.verification_how,
        signoff: form.signoff || user?.name,
      });
      toast.success(`Moved to ${status.replace(/_/g, " ")}`);
      setNote("");
      await load();
    } catch (err) {
      console.error("[ncr] transition failed", err);
      const statusCode = err?.response?.status;
      const detail = formatApiErrorDetail(err.response?.data?.detail) || "Could not move NCR";
      toast.error(statusCode === 409 ? detail : detail);
    } finally {
      setSaving(false);
    }
  };

  const uploadPhoto = async (file) => {
    if (!selectedId || !file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      await api.post(`/ncrs/${selectedId}/photos`, fd);
      toast.success("Photo attached");
      await load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Photo failed");
    }
  };

  const download = async (kind) => {
    if (!selectedId) return;
    try {
      const { data } = await api.get(`/ncrs/${selectedId}/export.${kind}`, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ncr-${selectedId.slice(0, 8)}.${kind}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Export failed");
    }
  };

  const visible = rows.filter((r) => {
    if (filter.status && r.status !== filter.status) return false;
    if (filter.severity && r.severity !== filter.severity) return false;
    if (filter.overdue && !r.overdue && !r.escalated) return false;
    return true;
  });
  const statusMeta = NCR_STATUSES.find((s) => s.id === (selected?.status || "open"));
  const sourceLabel = query.source && !selectedId ? (query.title || `Fail from ${query.source}`) : "";

  return (
    <Layout>
      <PageHeader
        title="Non-conformance"
        subtitle="Twin pins, failed checks, and mix deviations become one closable record. Does not bypass tension or release gates."
        right={<Link to="/guide?section=ncr" className="min-h-12 px-4 border border-[#1C2230] flex items-center text-sm font-semibold uppercase tracking-wider hover:border-[#C9A227] hover:text-[#C9A227]">Tutorial</Link>}
      />
      <div className="p-4 sm:p-6 lg:p-8 grid grid-cols-1 xl:grid-cols-[320px_1fr] gap-4">
        <div className="space-y-3">
          <div className={`${cardClass} p-3 space-y-2`}>
            <select className={inputClass} value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })}>
              <option value="">All statuses</option>
              {NCR_STATUSES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
            <select className={inputClass} value={filter.severity} onChange={(e) => setFilter({ ...filter, severity: e.target.value })}>
              <option value="">All severities</option>
              {NCR_SEVERITIES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
            <button type="button" onClick={() => setFilter({ ...filter, overdue: !filter.overdue })} className={`w-full min-h-12 border text-xs font-semibold uppercase ${filter.overdue ? "border-[#FF3366] text-[#FF3366]" : "border-[#1C2230]"}`}>
              {filter.overdue ? "Showing overdue / critical" : "Overdue only"}
            </button>
            <button type="button" data-testid="ncr-new" onClick={() => setSelectedId("")} className="w-full min-h-12 bg-primary text-white font-display font-bold uppercase tracking-widest">
              File NCR
            </button>
          </div>
          <div className={`${cardClass} overflow-hidden`} data-testid="ncr-list">
            {loading && <div className="p-4 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin inline mr-2" />Loading…</div>}
            {!loading && visible.length === 0 && <div className="p-4 text-xs font-mono text-muted-foreground">No NCRs match. File one from a fail toast or here.</div>}
            {visible.map((row) => (
              <button
                type="button"
                key={row.id}
                onClick={() => setSelectedId(row.id)}
                className={`w-full text-left min-h-12 px-3 py-2 border-b border-[#1C2230] ${selectedId === row.id ? "bg-primary/20" : ""}`}
              >
                <div className="flex justify-between gap-2">
                  <span className="font-mono text-xs uppercase" style={{ color: sevColor(row.severity) }}>{row.severity}</span>
                  {(row.escalated || row.overdue) && <AlertTriangle className="w-4 h-4 text-[#FF3366]" />}
                </div>
                <div className="text-sm truncate">{row.description || row.sub_type || row.category}</div>
                <div className="text-[10px] font-mono text-muted-foreground">{row.status} · {(row.created_at || "").slice(0, 16)}</div>
              </button>
            ))}
          </div>
        </div>

        <div className={`${cardClass} p-4 sm:p-6 space-y-4`}>
          {sourceLabel && (
            <div className="border border-[#FF9100]/50 bg-[#FF9100]/10 px-3 py-3" data-testid="ncr-source-banner">
              <div className="text-[10px] font-mono uppercase tracking-widest text-[#FF9100]">Opened from a fail</div>
              <p className="text-sm mt-1">{sourceLabel}. Containment is required. Filing again on the same source returns the open record.</p>
            </div>
          )}

          <div className="grid grid-cols-2 sm:grid-cols-5 gap-1" data-testid="ncr-workflow">
            {NCR_STATUSES.filter((s) => s.id !== "rejected").map((s) => {
              const active = (selected?.status || "open") === s.id;
              return (
                <div
                  key={s.id}
                  className={`min-h-12 px-2 py-2 border text-[10px] font-mono uppercase tracking-wider flex items-center justify-center text-center ${active ? "border-primary text-primary" : "border-[#1C2230] text-muted-foreground"}`}
                >
                  {s.label}
                </div>
              );
            })}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Category">
              <select className={inputClass} disabled={locked} value={form.category} onChange={(e) => set("category", e.target.value)}>
                {NCR_CATEGORIES.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
              </select>
            </Field>
            <Field label="Severity">
              <select data-testid="ncr-severity" className={inputClass} disabled={locked} value={form.severity} onChange={(e) => set("severity", e.target.value)}>
                {NCR_SEVERITIES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
              </select>
            </Field>
            <Field label="Sub-type">
              <input className={inputClass} disabled={locked} value={form.sub_type} onChange={(e) => set("sub_type", e.target.value)} placeholder="crack, insert, elongation…" />
            </Field>
            <Field label="Beam">
              <select className={inputClass} disabled={locked} value={form.beam_ids[0] || ""} onChange={(e) => set("beam_ids", e.target.value ? [e.target.value] : [])}>
                <option value="">—</option>
                {beams.map((b) => <option key={b.id} value={b.id}>{b.mark}</option>)}
              </select>
            </Field>
            <Field label="Job">
              <select className={inputClass} disabled={locked} value={form.job_id} onChange={(e) => set("job_id", e.target.value)}>
                <option value="">—</option>
                {jobs.map((j) => <option key={j.id} value={j.id}>{j.job_number}</option>)}
              </select>
            </Field>
            <Field label="Pour">
              <select className={inputClass} disabled={locked} value={form.pour_id} onChange={(e) => set("pour_id", e.target.value)}>
                <option value="">—</option>
                {pours.map((p) => <option key={p.id} value={p.id}>{p.pour_number}</option>)}
              </select>
            </Field>
            <Field label="Bed">
              <select className={inputClass} disabled={locked} value={form.bed_id} onChange={(e) => set("bed_id", e.target.value)}>
                <option value="">—</option>
                {beds.map((b) => <option key={b.id} value={b.id}>Bed {b.bed_number}</option>)}
              </select>
            </Field>
            <Field label="Assign to">
              <input className={inputClass} disabled={locked} value={form.assigned_to} onChange={(e) => set("assigned_to", e.target.value)} placeholder="Name or role" />
            </Field>
          </div>
          <Field label="Description">
            <textarea data-testid="ncr-description" className={`${inputClass} py-2`} rows={3} disabled={locked} value={form.description} onChange={(e) => set("description", e.target.value)} />
          </Field>
          <Field label="Immediate containment">
            <textarea data-testid="ncr-containment" className={`${inputClass} py-2`} rows={2} disabled={locked} value={form.containment} onChange={(e) => set("containment", e.target.value)} />
          </Field>
          {form.category !== "documentation" && !photos.length && (
            <p className="text-xs text-[#FF9100]">Photos are required for this category before close — snap after filing.</p>
          )}
          <Field label="Root cause (required to close Major/Critical)">
            <textarea
              data-testid="ncr-root-cause"
              className={`${inputClass} py-2 ${majorNeedsRoot ? "border-[#FF3366]" : ""}`}
              rows={2}
              disabled={locked}
              value={form.root_cause}
              onChange={(e) => set("root_cause", e.target.value)}
            />
          </Field>
          <Field label="Corrective action">
            <textarea className={`${inputClass} py-2`} rows={2} disabled={locked} value={form.corrective_action} onChange={(e) => set("corrective_action", e.target.value)} />
          </Field>
          <Field label="Preventive action">
            <textarea className={`${inputClass} py-2`} rows={2} disabled={locked} value={form.preventive_action} onChange={(e) => set("preventive_action", e.target.value)} />
          </Field>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Verified by">
              <input className={inputClass} disabled={locked} value={form.verification_by} onChange={(e) => set("verification_by", e.target.value)} />
            </Field>
            <Field label="Sign-off">
              <input className={inputClass} disabled={locked} value={form.signoff} onChange={(e) => set("signoff", e.target.value)} />
            </Field>
          </div>
          <Field label="How verified">
            <input className={inputClass} disabled={locked} value={form.verification_how} onChange={(e) => set("verification_how", e.target.value)} />
          </Field>

          {selected && (
            <div className="flex flex-wrap gap-2">
              <label className="min-h-12 px-4 border border-[#1C2230] flex items-center text-xs font-semibold uppercase cursor-pointer">
                Add photo
                <input type="file" accept="image/*" className="hidden" disabled={locked} onChange={(e) => uploadPhoto(e.target.files?.[0])} />
              </label>
              <button type="button" onClick={() => download("pdf")} className="min-h-12 px-4 border border-[#1C2230] text-xs font-semibold uppercase">PDF</button>
              <button type="button" onClick={() => download("csv")} className="min-h-12 px-4 border border-[#1C2230] text-xs font-semibold uppercase">CSV</button>
              {form.beam_ids[0] && <Link to={`/job-specs?beam=${form.beam_ids[0]}`} className="min-h-12 px-4 border border-[#1C2230] flex items-center text-xs font-semibold uppercase">Twin</Link>}
              {form.beam_ids[0] && <Link to={`/b/${beams.find((b) => b.id === form.beam_ids[0])?.qr_token || ""}`} className="min-h-12 px-4 border border-[#1C2230] flex items-center text-xs font-semibold uppercase">Dossier</Link>}
              {form.batch_id && <Link to={`/batch`} className="min-h-12 px-4 border border-[#1C2230] flex items-center text-xs font-semibold uppercase">Batch</Link>}
            </div>
          )}
          {photos.length > 0 && (
            <div className="grid grid-cols-3 sm:grid-cols-6 gap-2" data-testid="ncr-photos">
              {photos.map((name) => (
                <PhotoThumb key={name} ncrId={selectedId} filename={name} />
              ))}
            </div>
          )}

          {!selectedId && (
            <button type="button" data-testid="ncr-save" disabled={saving || !canFile} onClick={saveNew} className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest">
              {saving ? <Loader2 className="w-4 h-4 animate-spin inline" /> : "File NCR"}
            </button>
          )}
          {selectedId && !locked && (
            <button type="button" disabled={saving} onClick={saveEdit} className="w-full min-h-12 border border-[#1C2230] font-semibold uppercase tracking-wider">Save fields</button>
          )}
          {selected && !locked && statusMeta?.next && (
            <div className="space-y-2">
              <input className={inputClass} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Transition note (audited)" />
              {statusMeta.next === "closed" && !canCloseThis ? (
                <p className="text-xs text-[#FF3366]">A supervisor must close Major and Critical after root cause, CA, and sign-off. The server will 409 a silent close.</p>
              ) : (
                <button
                  type="button"
                  data-testid="ncr-advance"
                  disabled={saving}
                  onClick={() => move(statusMeta.next)}
                  className="w-full min-h-14 bg-[#00E676] text-black font-display font-bold uppercase tracking-widest"
                >
                  {statusMeta.next === "closed" ? "Close NCR" : `Advance to ${statusMeta.next.replace(/_/g, " ")}`}
                </button>
              )}
              {selected.status === "open" && manage && (
                <button type="button" disabled={saving} onClick={() => move("rejected")} className="w-full min-h-12 border border-[#FF3366] text-[#FF3366] text-xs font-semibold uppercase">Reject</button>
              )}
            </div>
          )}
          {selected?.immutable && manage && (
            <div className="space-y-2">
              <input className={inputClass} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Written reason to reopen (audited)" />
              <button type="button" disabled={saving} onClick={() => move("investigating")} className="w-full min-h-12 border border-[#FFD600] text-[#FFD600] text-xs font-semibold uppercase">
                Reopen (audited)
              </button>
            </div>
          )}
          {selected?.immutable && !manage && <p className="text-xs text-muted-foreground">Closed. A supervisor reopens with a written reason.</p>}

          {selected?.history?.length > 0 && (
            <div className="border border-[#1C2230] p-3 space-y-1">
              <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">History</div>
              {selected.history.slice(-8).map((h, i) => (
                <div key={`${h.at}-${i}`} className="text-[11px] font-mono text-muted-foreground">
                  {(h.at || "").slice(0, 16)} · {h.by || "—"} · {h.action} {h.status ? `→ ${h.status}` : ""} {h.note ? `· ${h.note}` : ""}
                </div>
              ))}
            </div>
          )}

          {insights.length > 0 && (
            <div className="border border-[#1C2230] p-3 space-y-2" data-testid="ncr-insights">
              <div className="text-[10px] font-mono uppercase tracking-widest text-[#C9A227]">Learning loop — recommendations only</div>
              {insights.map((r) => (
                <div key={r.id}>
                  <div className="font-semibold text-sm">{r.title}</div>
                  <p className="text-xs text-muted-foreground">{r.body}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
