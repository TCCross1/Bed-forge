import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, Field, inputClass, cardClass } from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import { KIND_LABELS } from "../lib/beamSpec";
import { toast } from "sonner";
import { Loader2, Upload, Lock, FileSearch, CheckCircle2, CalendarDays } from "lucide-react";

export default function Drawings() {
  const { user } = useAuth();
  const canLock = user?.role === "admin" || user?.role === "executive" || user?.role === "qc_supervisor";
  const [beams, setBeams] = useState([]);
  const [beamId, setBeamId] = useState("");
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState("");
  const [spec, setSpec] = useState(null);
  const [reviewNotes, setReviewNotes] = useState("");
  const [history, setHistory] = useState([]);
  const [corpus, setCorpus] = useState([]);
  const [catalogId, setCatalogId] = useState("");

  useEffect(() => {
    let cancelled = false;
    api.get("/beams")
      .then((r) => {
        if (cancelled) return;
        setBeams(r.data);
        setBeamId((cur) => cur || r.data[0]?.id || "");
      })
      .catch((err) => {
        console.error("[drawings] beams failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load beams");
      });
    api.get("/beam-specs/corpus")
      .then((r) => {
        if (cancelled) return;
        const items = r.data?.items || [];
        setCorpus(items);
        setCatalogId((cur) => cur || items[0]?.catalog_id || "");
      })
      .catch((err) => {
        console.error("[drawings] corpus failed", err);
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!beamId) return undefined;
    let cancelled = false;
    api.get("/beam-specs", { params: { beam_id: beamId } })
      .then((r) => {
        if (cancelled) return;
        setHistory(r.data || []);
        if (r.data?.[0]) {
          setSpec(r.data[0]);
          setReviewNotes(r.data[0].review_notes || "");
        } else {
          setSpec(null);
        }
      })
      .catch((err) => {
        console.error("[drawings] specs failed", err);
      });
    return () => { cancelled = true; };
  }, [beamId]);

  const upload = async () => {
    if (!files.length) {
      toast.error("Choose a PDF or image set of shop drawings");
      return;
    }
    setBusy("upload");
    try {
      const body = new FormData();
      files.forEach((f) => body.append("files", f));
      if (beamId) body.append("beam_id", beamId);
      const beam = beams.find((b) => b.id === beamId);
      if (beam?.mark) body.append("beam_mark", beam.mark);
      if (beam?.job_id) body.append("job_id", beam.job_id);
      body.append("extract", "true");
      const { data } = await api.post("/blueprints/upload", body, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`Extracted via ${data.extractor || "pipeline"}`);
      setSpec(data.spec);
      setReviewNotes(data.spec?.review_notes || "");
      const list = await api.get("/beam-specs", { params: { beam_id: beamId } });
      setHistory(list.data || []);
    } catch (err) {
      console.error("[drawings] upload failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Upload / extract failed");
    } finally {
      setBusy("");
    }
  };

  const loadCorpus = async () => {
    if (!beamId || !catalogId) {
      toast.error("Select a beam and a standard drawing");
      return;
    }
    setBusy("corpus");
    try {
      const { data } = await api.post("/beam-specs/from-corpus", null, { params: { catalog_id: catalogId, beam_id: beamId } });
      setSpec(data);
      setReviewNotes(data.review_notes || "");
      toast.info(`${data.product_name} attached — review then lock`);
      const list = await api.get("/beam-specs", { params: { beam_id: beamId } });
      setHistory(list.data || []);
    } catch (err) {
      console.error("[drawings] corpus attach failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to attach corpus spec");
    } finally {
      setBusy("");
    }
  };

  const loadReference = async () => {
    if (!beamId) {
      toast.error("Select a beam first");
      return;
    }
    setBusy("ref");
    try {
      const { data } = await api.post("/beam-specs/from-l25390", null, { params: { beam_id: beamId } });
      setSpec(data);
      setReviewNotes(data.review_notes || "");
      toast.info("Larue County / L25390 Type 2 spec attached — review then lock");
      const list = await api.get("/beam-specs", { params: { beam_id: beamId } });
      setHistory(list.data || []);
    } catch (err) {
      console.error("[drawings] reference failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to attach reference spec");
    } finally {
      setBusy("");
    }
  };

  const saveReview = async () => {
    if (!spec?.id) {
      toast.error("Extract a drawing first");
      return;
    }
    setBusy("review");
    try {
      const { data } = await api.patch(`/beam-specs/${spec.id}`, { review_notes: reviewNotes, status: "reviewed" });
      setSpec(data);
      toast.success("Spec marked reviewed");
    } catch (err) {
      console.error("[drawings] review failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to save review");
    } finally {
      setBusy("");
    }
  };

  const lock = async () => {
    if (!spec?.id) return;
    setBusy("lock");
    try {
      const { data } = await api.post(`/beam-specs/${spec.id}/lock`);
      setSpec(data);
      toast.success("Twin locked as design-of-record");
    } catch (err) {
      console.error("[drawings] lock failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Lock requires QC Supervisor or Admin");
    } finally {
      setBusy("");
    }
  };

  const geo = spec?.geometry || {};
  const counts = {};
  (spec?.hardware || []).forEach((h) => {
    counts[h.kind] = (counts[h.kind] || 0) + 1;
  });

  return (
    <Layout>
      <PageHeader
        title="Shop Drawings"
        subtitle="Upload → AI extract BeamSpec → Supervisor review → Lock twin → Plan the bed"
        right={
          <Link
            to="/planner"
            className="min-h-12 px-4 border border-[#1C2230] rounded-none flex items-center gap-2 text-sm font-semibold uppercase tracking-wider hover:border-primary hover:text-primary"
          >
            <CalendarDays className="w-4 h-4" /> Planner
          </Link>
        }
      />
      <div className="p-4 sm:p-6 lg:p-8 grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6 max-w-6xl">
        <div className={`${cardClass} p-5 sm:p-8 space-y-4`}>
          <h3 className="font-display font-bold uppercase tracking-wider text-lg flex items-center gap-2">
            <Upload className="w-5 h-5 text-primary" /> 1. Upload drawing
          </h3>
          <Field label="Beam">
            <select data-testid="dwg-beam" value={beamId} onChange={(e) => setBeamId(e.target.value)} className={inputClass}>
              {beams.map((b) => (
                <option key={b.id} value={b.id}>{b.mark} · {b.twin_type === "box_beam" ? "Box" : "I-Beam"}</option>
              ))}
            </select>
          </Field>
          <Field label="PDF or images">
            <input
              data-testid="dwg-files"
              type="file"
              multiple
              accept=".pdf,image/*"
              onChange={(e) => setFiles(Array.from(e.target.files || []))}
              className={`${inputClass} py-2 file:mr-3 file:border-0 file:bg-primary file:text-white file:px-3 file:min-h-10`}
            />
          </Field>
          <div className="text-xs font-mono text-muted-foreground">
            {files.length ? files.map((f) => f.name).join(", ") : "Upload a shop drawing or load a NY/SC/NC/OR gold standard from the corpus."}
          </div>
          <button
            data-testid="dwg-upload"
            onClick={upload}
            disabled={busy === "upload"}
            className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest rounded-none hover:bg-white hover:text-black transition-colors duration-100 disabled:opacity-60 flex items-center justify-center gap-2"
          >
            {busy === "upload" && <Loader2 className="w-4 h-4 animate-spin" />} Extract BeamSpec
          </button>
          <Field label="Training corpus standard">
            <select data-testid="dwg-corpus" value={catalogId} onChange={(e) => setCatalogId(e.target.value)} className={inputClass}>
              {corpus.map((item) => (
                <option key={item.catalog_id} value={item.catalog_id}>
                  {item.agency} · {item.product_name}
                </option>
              ))}
            </select>
          </Field>
          <button
            data-testid="dwg-corpus-load"
            onClick={loadCorpus}
            disabled={busy === "corpus"}
            className="w-full min-h-12 border border-[#1C2230] rounded-none font-semibold uppercase tracking-wider hover:border-primary hover:text-primary"
          >
            Load selected standard
          </button>
          <button
            data-testid="dwg-reference"
            onClick={loadReference}
            disabled={busy === "ref"}
            className="w-full min-h-12 border border-[#1C2230] rounded-none font-semibold uppercase tracking-wider hover:border-primary hover:text-primary"
          >
            Load L25390 reference spec
          </button>
        </div>

        <div className={`${cardClass} p-5 sm:p-8 space-y-4`}>
          <h3 className="font-display font-bold uppercase tracking-wider text-lg flex items-center gap-2">
            <FileSearch className="w-5 h-5 text-primary" /> 2. Review spec
          </h3>
          {!spec ? (
            <div className="text-sm text-muted-foreground font-mono">No spec yet. Upload a drawing or load the Larue County reference.</div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-2 font-mono text-xs">
                <div>JOB {spec.job_number}</div>
                <div>MARK {spec.beam_mark}</div>
                <div>{geo.product_name || spec.product_name}</div>
                <div>{geo.length_ft}' × {geo.depth_in}" {geo.twin_type === "box_beam" ? "BOX" : "I-BEAM"}</div>
                <div>STRANDS {spec.strands?.length || 0}</div>
                <div>HARDWARE {spec.hardware?.length || 0}</div>
                <div>EXTRACTOR {spec.extractor}</div>
                <div>STATUS {spec.status}</div>
              </div>
              <div className="flex flex-wrap gap-1">
                {Object.entries(counts).map(([kind, n]) => (
                  <span key={kind} className="text-[10px] font-mono px-2 py-1 border border-[#1C2230]">
                    {KIND_LABELS[kind] || kind} {n}
                  </span>
                ))}
              </div>
              <div className="max-h-40 overflow-y-auto space-y-1" data-testid="dwg-hardware-list">
                {(spec.hardware || []).slice(0, 40).map((h) => (
                  <div key={h.id} className="text-xs font-mono border-b border-[#1C2230] py-1 flex justify-between gap-2">
                    <span>{h.name}</span>
                    <span className="text-muted-foreground">{h.position?.station_ft}' ME</span>
                  </div>
                ))}
              </div>
              {(spec.notes || []).length > 0 && (
                <div className="max-h-28 overflow-y-auto space-y-1" data-testid="dwg-notes-list">
                  {spec.notes.map((note) => (
                    <div key={note} className="text-[11px] text-muted-foreground leading-snug">{note}</div>
                  ))}
                </div>
              )}
              {(spec.special_finishes || []).length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {spec.special_finishes.map((finish) => (
                    <span key={finish} className="text-[10px] font-mono px-2 py-1 border border-[#C9A22755] text-[#C9A227]">{finish}</span>
                  ))}
                </div>
              )}
              <Field label="Supervisor review notes">
                <textarea data-testid="dwg-notes" rows={3} value={reviewNotes} onChange={(e) => setReviewNotes(e.target.value)} className={`${inputClass} py-2`} />
              </Field>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <button data-testid="dwg-review" onClick={saveReview} disabled={busy === "review" || spec.status === "locked"} className="min-h-12 border border-[#1C2230] rounded-none font-semibold uppercase tracking-wider hover:border-primary hover:text-primary disabled:opacity-40">
                  Save review
                </button>
                <button
                  data-testid="dwg-lock"
                  onClick={lock}
                  disabled={!canLock || busy === "lock" || spec.status === "locked" || !spec.id}
                  className="min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest rounded-none hover:bg-white hover:text-black disabled:opacity-40 flex items-center justify-center gap-2"
                >
                  {busy === "lock" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Lock className="w-4 h-4" />}
                  {spec.status === "locked" ? "Locked" : "Lock twin"}
                </button>
              </div>
              {!canLock && <div className="text-xs text-muted-foreground font-mono">Lock requires QC Supervisor or Admin.</div>}
              {spec.id && (
                <Link to={`/twin?beam=${beamId}`} className="min-h-12 border border-[#1C2230] rounded-none flex items-center justify-center gap-2 font-semibold uppercase tracking-wider hover:border-primary hover:text-primary">
                  <CheckCircle2 className="w-4 h-4" /> Open twin
                </Link>
              )}
            </>
          )}
        </div>

        <div className={`${cardClass} p-5 sm:p-8 lg:col-span-2`}>
          <h3 className="font-display font-bold uppercase tracking-wider text-lg mb-3">Spec history</h3>
          <div className="space-y-2" data-testid="dwg-history">
            {history.length === 0 && <div className="text-sm text-muted-foreground font-mono">No specs for this beam.</div>}
            {history.map((s) => (
              <button
                type="button"
                key={s.id}
                onClick={() => { setSpec(s); setReviewNotes(s.review_notes || ""); }}
                className="w-full text-left border border-[#1C2230] p-3 hover:border-primary"
              >
                <div className="flex justify-between font-mono text-xs">
                  <span>{s.job_number} · {s.beam_mark} · {s.extractor}</span>
                  <span style={{ color: s.status === "locked" ? "#00E676" : "#FFD600" }}>{s.status}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </Layout>
  );
}
