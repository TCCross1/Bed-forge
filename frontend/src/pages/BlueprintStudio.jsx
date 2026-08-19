import React, { useEffect, useMemo, useState } from "react";
import api from "../lib/api";
import Layout, { PageHeader } from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";
import { Loader2, Lock, ScanSearch, Upload, AlertTriangle, CheckCircle2, Download } from "lucide-react";

const ROLE_CAN_LOCK = ["qc_supervisor", "admin"];

function prettyValue(value) {
  if (value == null) return "";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function Badge({ tone = "slate", children }) {
  const tones = {
    green: "border-[#00E67655] text-[#00E676]",
    amber: "border-[#FFD60055] text-[#FFD600]",
    red: "border-[#FF336655] text-[#FF3366]",
    blue: "border-[#2979FF55] text-[#2979FF]",
    slate: "border-border text-muted-foreground",
  };
  return <span className={`px-2 py-1 rounded-sm border text-[11px] font-mono uppercase tracking-wider ${tones[tone] || tones.slate}`}>{children}</span>;
}

function toneForStatus(status) {
  if (status === "locked" || status === "confirmed" || status === "manually_confirmed") return "green";
  if (status === "needs_review" || status === "unconfirmed") return "amber";
  if (status === "failed" || status === "insufficient_quality") return "red";
  return "blue";
}

export default function BlueprintStudio() {
  const { user } = useAuth();
  const [jobs, setJobs] = useState([]);
  const [beams, setBeams] = useState([]);
  const [productTypes, setProductTypes] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState(null);
  const [fieldDrafts, setFieldDrafts] = useState({});
  const [uploading, setUploading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [locking, setLocking] = useState(false);
  const [file, setFile] = useState(null);
  const [uploadForm, setUploadForm] = useState({
    job_id: "",
    beam_id: "",
    product_type_id: "",
    product_family_hint: "",
    beam_mark_hint: "",
    project_name_hint: "",
  });

  const canLock = ROLE_CAN_LOCK.includes(user?.role);

  const loadAll = async (keepSelectedId) => {
    const [jobsRes, beamsRes, productTypeRes, docsRes] = await Promise.all([
      api.get("/jobs"),
      api.get("/beams"),
      api.get("/product-types"),
      api.get("/blueprints"),
    ]);
    setJobs(jobsRes.data);
    setBeams(beamsRes.data);
    setProductTypes(productTypeRes.data);
    setDocuments(docsRes.data);
    const nextId = keepSelectedId || selectedId || docsRes.data[0]?.id || "";
    setSelectedId(nextId);
    if (nextId) {
      const blueprintRes = await api.get(`/blueprints/${nextId}`);
      setDetail(blueprintRes.data);
    } else {
      setDetail(null);
    }
  };

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!detail?.latest_extraction?.fields) {
      setFieldDrafts({});
      return;
    }
    const mapped = {};
    Object.entries(detail.latest_extraction.fields).forEach(([key, field]) => {
      mapped[key] = {
        value: prettyValue(field.value),
        confidence: field.confidence || "low",
        status: field.status || "unconfirmed",
        source_page: field.source_page ?? "",
        extraction_notes: field.extraction_notes || "",
      };
    });
    setFieldDrafts(mapped);
  }, [detail]);

  const selectedBeam = useMemo(() => beams.find((beam) => beam.id === uploadForm.beam_id), [beams, uploadForm.beam_id]);

  const uploadBlueprint = async () => {
    if (!file) {
      toast.error("Select a multi-page shop drawing PDF first");
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    Object.entries(uploadForm).forEach(([key, value]) => {
      if (value) formData.append(key, value);
    });
    setUploading(true);
    try {
      const { data } = await api.post("/blueprints/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("Blueprint uploaded");
      setFile(null);
      setUploadForm({
        job_id: "",
        beam_id: "",
        product_type_id: "",
        product_family_hint: "",
        beam_mark_hint: "",
        project_name_hint: "",
      });
      await loadAll(data.id);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const runExtraction = async () => {
    if (!selectedId) return;
    setExtracting(true);
    try {
      const { data } = await api.post(`/blueprints/${selectedId}/extract`);
      setDetail(data);
      await loadAll(selectedId);
      toast.success("Controlled extraction complete");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Extraction failed");
    } finally {
      setExtracting(false);
    }
  };

  
  const downloadAssessmentPdf = async () => {
    if (!selectedId) {
      toast.error("Select a blueprint first");
      return;
    }
    try {
      const res = await api.get(`/blueprints/${selectedId}/extraction-report.pdf`, {
        responseType: "blob",
      });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const base = detail?.filename || detail?.original_filename || selectedId;
      a.download = `blueprint-assessment-${base}`.replace(/\.pdf$/i, "") + ".pdf";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Blueprint Assessment PDF downloaded");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to download Blueprint Assessment PDF");
    }
  };

const saveReview = async () => {
    if (!selectedId) return;
    setSaving(true);
    try {
      const payload = {
        fields: Object.fromEntries(
          Object.entries(fieldDrafts).map(([key, draft]) => [
            key,
            {
              value: draft.value,
              confidence: draft.confidence,
              status: draft.status,
              source_page: draft.source_page === "" ? null : Number(draft.source_page),
              extraction_notes: draft.extraction_notes,
            },
          ]),
        ),
      };
      const { data } = await api.patch(`/blueprints/${selectedId}/extraction`, payload);
      setDetail(data);
      await loadAll(selectedId);
      toast.success("Review changes saved");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to save review edits");
    } finally {
      setSaving(false);
    }
  };

  const lockBlueprint = async () => {
    if (!selectedId) return;
    setLocking(true);
    try {
      const { data } = await api.post(`/blueprints/${selectedId}/lock`, {
        beam_ids: detail?.beam_id ? [detail.beam_id] : [],
        product_type_id: detail?.product_type_id || null,
        notes: "Verified and locked in Blueprint Studio",
      });
      setDetail(data);
      await loadAll(selectedId);
      toast.success("Blueprint revision locked");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Unable to lock blueprint");
    } finally {
      setLocking(false);
    }
  };

  return (
    <Layout>
      <PageHeader
        title="Blueprint Intelligence"
        subtitle="Controlled intake, extraction, review, and immutable lock workflow for prestress shop drawings"
        right={
          <div className="flex items-center gap-2">
            <Badge tone={canLock ? "green" : "amber"}>{canLock ? "lock authority" : "review only"}</Badge>
            <Badge tone="blue">{user?.role || "user"}</Badge>
          </div>
        }
      />

      <div className="p-8 grid grid-cols-1 xl:grid-cols-12 gap-6">
        <div className="xl:col-span-4 space-y-6">
          <div className="bg-card border border-border rounded-sm p-6 space-y-4">
            <div>
              <h3 className="font-display font-bold uppercase tracking-wider text-lg">Blueprint Intake</h3>
              <p className="text-sm text-muted-foreground mt-1">Upload the original PDF, link it to a beam or product, and extract into strict review fields.</p>
            </div>
            <input
              type="file"
              accept="application/pdf,.pdf"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="w-full bg-background border border-border rounded-sm px-4 py-3 font-mono text-sm"
            />
            <select value={uploadForm.job_id} onChange={(e) => setUploadForm({ ...uploadForm, job_id: e.target.value })} className="w-full bg-background border border-border rounded-sm px-4 min-h-12 font-mono text-sm">
              <option value="">Link job (optional)</option>
              {jobs.map((job) => <option key={job.id} value={job.id}>{job.job_number} · {job.name}</option>)}
            </select>
            <select
              value={uploadForm.beam_id}
              onChange={(e) => {
                const beam = beams.find((item) => item.id === e.target.value);
                setUploadForm({
                  ...uploadForm,
                  beam_id: e.target.value,
                  beam_mark_hint: beam?.mark || uploadForm.beam_mark_hint,
                  product_family_hint: beam?.twin_type || uploadForm.product_family_hint,
                  product_type_id: beam?.product_type_id || uploadForm.product_type_id,
                });
              }}
              className="w-full bg-background border border-border rounded-sm px-4 min-h-12 font-mono text-sm"
            >
              <option value="">Bind beam (optional)</option>
              {beams.map((beam) => <option key={beam.id} value={beam.id}>{beam.mark} · Bed {beam.position_on_bed} · {beam.twin_type}</option>)}
            </select>
            <select value={uploadForm.product_type_id} onChange={(e) => setUploadForm({ ...uploadForm, product_type_id: e.target.value })} className="w-full bg-background border border-border rounded-sm px-4 min-h-12 font-mono text-sm">
              <option value="">Default product type (optional)</option>
              {productTypes.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}
            </select>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <input value={uploadForm.product_family_hint} onChange={(e) => setUploadForm({ ...uploadForm, product_family_hint: e.target.value })} placeholder="Family hint: i_beam / box_beam" className="bg-background border border-border rounded-sm px-4 min-h-12 font-mono text-sm" />
              <input value={uploadForm.beam_mark_hint} onChange={(e) => setUploadForm({ ...uploadForm, beam_mark_hint: e.target.value })} placeholder="Beam mark hint" className="bg-background border border-border rounded-sm px-4 min-h-12 font-mono text-sm" />
            </div>
            <input value={uploadForm.project_name_hint} onChange={(e) => setUploadForm({ ...uploadForm, project_name_hint: e.target.value })} placeholder="Project name hint" className="w-full bg-background border border-border rounded-sm px-4 min-h-12 font-mono text-sm" />
            {selectedBeam && (
              <div className="border border-border rounded-sm px-4 py-3 text-xs font-mono text-muted-foreground">
                Bound beam preview: <span className="text-white">{selectedBeam.mark}</span> · current source <span className="text-white">{selectedBeam.blueprint_source?.status || "legacy_seed"}</span>
              </div>
            )}
            <button onClick={uploadBlueprint} disabled={uploading} className="w-full min-h-12 bg-primary text-white rounded-sm font-display font-bold uppercase tracking-widest flex items-center justify-center gap-2 disabled:opacity-60">
              {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />} Upload PDF
            </button>
          </div>

          <div className="bg-card border border-border rounded-sm p-6">
            <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-4">Blueprint Library</h3>
            <div className="space-y-3 max-h-[720px] overflow-auto pr-1">
              {documents.map((doc) => (
                <button
                  key={doc.id}
                  onClick={async () => {
                    setSelectedId(doc.id);
                    const { data } = await api.get(`/blueprints/${doc.id}`);
                    setDetail(data);
                  }}
                  className={`w-full text-left border rounded-sm p-4 transition-colors duration-100 ${selectedId === doc.id ? "border-primary bg-primary/10" : "border-border hover:border-primary/50"}`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-semibold">{doc.filename}</div>
                    <Badge tone={toneForStatus(doc.status)}>{doc.status}</Badge>
                  </div>
                  <div className="mt-2 text-xs font-mono text-muted-foreground space-y-1">
                    <div>{doc.beam_mark_hint || doc.latest_extraction?.fields?.beam_mark?.value || "No mark hint"} · {doc.product_family_hint || doc.latest_extraction?.fields?.product_family?.value || "family unknown"}</div>
                    <div>{doc.page_count} pages · {doc.created_by || "system"}</div>
                    <div>{doc.latest_summary || "Ready for extraction"}</div>
                  </div>
                </button>
              ))}
              {documents.length === 0 && <div className="text-sm text-muted-foreground font-mono">No blueprint documents uploaded yet.</div>}
            </div>
          </div>
        </div>

        <div className="xl:col-span-8 space-y-6">
          {!detail ? (
            <div className="bg-card border border-border rounded-sm p-10 text-sm text-muted-foreground font-mono">Select a blueprint document to review extraction confidence, page references, and lock status.</div>
          ) : (
            <>
              <div className="bg-card border border-border rounded-sm p-6">
                <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="font-display font-bold uppercase tracking-wider text-xl">{detail.filename}</h3>
                      <Badge tone={toneForStatus(detail.status)}>{detail.status}</Badge>
                      {detail.locked_revision && <Badge tone="green">locked revision {detail.locked_revision.revision_number}</Badge>}
                    </div>
                    <div className="mt-3 text-sm text-muted-foreground space-y-1">
                      <div>{detail.page_count} pages · linked beam {detail.beam_id || "none"} · product type {detail.product_type_id || "none"}</div>
                      <div>{detail.latest_summary || "Upload complete. Run controlled extraction to populate review fields."}</div>
                    </div>
                    {detail.latest_extraction?.fail_reasons?.length > 0 && (
                      <div className="mt-4 border border-[#FFD60055] bg-[#FFD60011] rounded-sm p-3 text-sm">
                        <div className="flex items-center gap-2 text-[#FFD600] font-semibold"><AlertTriangle className="w-4 h-4" /> Controlled fail states</div>
                        <ul className="mt-2 list-disc pl-5 text-muted-foreground">
                          {detail.latest_extraction.fail_reasons.map((reason) => <li key={reason}>{reason}</li>)}
                        </ul>
                      </div>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-3">
                    <button
                      type="button"
                      onClick={downloadAssessmentPdf}
                      disabled={!selectedId}
                      className="min-h-12 px-4 bg-[#0F172A] text-white rounded-sm text-sm font-bold uppercase tracking-wider flex items-center gap-2 hover:bg-[#1E293B] disabled:opacity-60"
                    >
                      <Download className="w-4 h-4" /> Download Assessment PDF
                    </button>
                    <button onClick={runExtraction} disabled={extracting} className="min-h-12 px-4 border border-border rounded-sm text-sm font-semibold uppercase tracking-wider flex items-center gap-2 hover:border-primary hover:text-primary disabled:opacity-60">
                      {extracting ? <Loader2 className="w-4 h-4 animate-spin" /> : <ScanSearch className="w-4 h-4" />} Extract
                    </button>
                    <button onClick={saveReview} disabled={saving || !detail.latest_extraction} className="min-h-12 px-4 border border-border rounded-sm text-sm font-semibold uppercase tracking-wider hover:border-primary hover:text-primary disabled:opacity-60">
                      {saving ? "Saving…" : "Save Review"}
                    </button>
                    <button onClick={lockBlueprint} disabled={!canLock || locking || !detail.latest_extraction} className="min-h-12 px-4 bg-primary text-white rounded-sm text-sm font-bold uppercase tracking-wider flex items-center gap-2 disabled:opacity-60">
                      {locking ? <Loader2 className="w-4 h-4 animate-spin" /> : <Lock className="w-4 h-4" />} Verify & Lock
                    </button>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 2xl:grid-cols-3 gap-6">
                <div className="2xl:col-span-2 bg-card border border-border rounded-sm p-6 space-y-6">
                  {detail.latest_extraction ? Object.entries(detail.field_groups || {}).map(([group, keys]) => (
                    <div key={group}>
                      <div className="flex items-center gap-2 mb-4">
                        <h4 className="font-display font-bold uppercase tracking-wider text-lg">{group.replace(/_/g, " ")}</h4>
                        <Badge tone="blue">{keys.length} fields</Badge>
                      </div>
                      <div className="space-y-4">
                        {keys.map((key) => {
                          const field = detail.latest_extraction.fields?.[key];
                          const draft = fieldDrafts[key] || {};
                          const value = draft.value ?? prettyValue(field?.value);
                          return (
                            <div key={key} className="border border-border rounded-sm p-4 space-y-3">
                              <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
                                <div>
                                  <div className="font-semibold uppercase tracking-wide text-sm">{key.replace(/_/g, " ")}</div>
                                  <div className="text-xs text-muted-foreground font-mono">Source page {field?.source_page ?? "—"} · confidence {field?.confidence || "low"}</div>
                                </div>
                                <div className="flex items-center gap-2 flex-wrap">
                                  <Badge tone={toneForStatus(draft.status || field?.status)}>{draft.status || field?.status || "unconfirmed"}</Badge>
                                  <Badge tone={toneForStatus(draft.confidence || field?.confidence)}>{draft.confidence || field?.confidence || "low"}</Badge>
                                </div>
                              </div>
                              <textarea
                                rows={typeof value === "string" && value.length > 80 ? 4 : 2}
                                value={value}
                                onChange={(e) => setFieldDrafts({ ...fieldDrafts, [key]: { ...draft, value: e.target.value } })}
                                className="w-full bg-background border border-border rounded-sm px-3 py-2 font-mono text-sm"
                              />
                              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                                <select value={draft.status || field?.status || "unconfirmed"} onChange={(e) => setFieldDrafts({ ...fieldDrafts, [key]: { ...draft, status: e.target.value } })} className="bg-background border border-border rounded-sm px-3 min-h-11 font-mono text-xs">
                                  {["confirmed", "manually_confirmed", "unconfirmed", "not_applicable"].map((option) => <option key={option} value={option}>{option}</option>)}
                                </select>
                                <select value={draft.confidence || field?.confidence || "low"} onChange={(e) => setFieldDrafts({ ...fieldDrafts, [key]: { ...draft, confidence: e.target.value } })} className="bg-background border border-border rounded-sm px-3 min-h-11 font-mono text-xs">
                                  {["high", "medium", "low"].map((option) => <option key={option} value={option}>{option}</option>)}
                                </select>
                                <input value={draft.source_page ?? field?.source_page ?? ""} onChange={(e) => setFieldDrafts({ ...fieldDrafts, [key]: { ...draft, source_page: e.target.value } })} placeholder="Source page" className="bg-background border border-border rounded-sm px-3 min-h-11 font-mono text-xs" />
                                <input value={draft.extraction_notes ?? field?.extraction_notes ?? ""} onChange={(e) => setFieldDrafts({ ...fieldDrafts, [key]: { ...draft, extraction_notes: e.target.value } })} placeholder="Extraction notes" className="bg-background border border-border rounded-sm px-3 min-h-11 font-mono text-xs" />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )) : (
                    <div className="text-sm text-muted-foreground font-mono">Run extraction to create strict field review records with page references and confidence markers.</div>
                  )}
                </div>

                <div className="space-y-6">
                  <div className="bg-card border border-border rounded-sm p-6">
                    <h4 className="font-display font-bold uppercase tracking-wider text-lg mb-4">Page Review</h4>
                    <div className="space-y-3 max-h-[420px] overflow-auto pr-1">
                      {(detail.latest_extraction?.page_text || []).map((pageText, index) => (
                        <div key={index} className="border border-border rounded-sm p-3">
                          <div className="text-xs font-mono uppercase tracking-widest text-primary mb-2">Page {index + 1}</div>
                          <div className="text-xs text-muted-foreground whitespace-pre-wrap break-words">{pageText || "No machine-readable text found on this page."}</div>
                        </div>
                      ))}
                      {!detail.latest_extraction && <div className="text-sm text-muted-foreground font-mono">No extraction pages yet.</div>}
                    </div>
                  </div>

                  <div className="bg-card border border-border rounded-sm p-6">
                    <h4 className="font-display font-bold uppercase tracking-wider text-lg mb-4">Audit Trail</h4>
                    <div className="space-y-3 max-h-[340px] overflow-auto pr-1">
                      {(detail.audit_events || []).map((event) => (
                        <div key={event.id} className="border border-border rounded-sm p-3">
                          <div className="flex items-center justify-between gap-2">
                            <div className="font-semibold uppercase text-sm">{event.event_type}</div>
                            <Badge tone={event.event_type === "lock" ? "green" : event.event_type === "extract" ? "blue" : "amber"}>{event.actor_role || "system"}</Badge>
                          </div>
                          <div className="text-xs font-mono text-muted-foreground mt-2">{event.actor_name || "system"} · {event.created_at}</div>
                          <div className="text-xs text-muted-foreground mt-2 break-words">{JSON.stringify(event.details || {})}</div>
                        </div>
                      ))}
                      {detail.audit_events?.length === 0 && <div className="text-sm text-muted-foreground font-mono">No audit events yet.</div>}
                    </div>
                  </div>

                  <div className="bg-card border border-border rounded-sm p-6">
                    <h4 className="font-display font-bold uppercase tracking-wider text-lg mb-4">Lock Control Rules</h4>
                    <div className="space-y-3 text-sm text-muted-foreground">
                      <div className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-primary mt-0.5" /> Critical geometry stays unconfirmed until a reviewer explicitly verifies it.</div>
                      <div className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-primary mt-0.5" /> Verify & Lock creates the immutable revision used by downstream twins.</div>
                      <div className="flex items-start gap-2"><AlertTriangle className="w-4 h-4 text-[#FFD600] mt-0.5" /> Draft extractions never count as legal production geometry.</div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </Layout>
  );
}
