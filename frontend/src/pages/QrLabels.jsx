import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Download, Loader2, Printer, QrCode } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, Field, inputClass, cardClass } from "../components/Layout";
import QrLabelPrint from "../components/QrLabelPrint";

function downloadBlob(data, filename, type) {
  const blob = new Blob([data], { type });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

export default function QrLabels() {
  const [params] = useSearchParams();
  const [jobs, setJobs] = useState([]);
  const [pours, setPours] = useState([]);
  const [beams, setBeams] = useState([]);
  const [jobId, setJobId] = useState("");
  const [pourId, setPourId] = useState(params.get("pour") || "");
  const [selected, setSelected] = useState(() => new Set(params.get("beam") ? [params.get("beam")] : []));
  const [pack, setPack] = useState([]);
  const [busy, setBusy] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.get("/jobs"), api.get("/pours"), api.get("/beams")])
      .then(([jobRes, pourRes, beamRes]) => {
        if (cancelled) return;
        setJobs(jobRes.data || []);
        setPours(pourRes.data || []);
        setBeams(beamRes.data || []);
        const seedBeam = params.get("beam");
        const found = (beamRes.data || []).find((b) => b.id === seedBeam);
        if (found) {
          setJobId(found.job_id || "");
          setPourId(found.pour_id || "");
        } else if ((pourRes.data || []).length && !params.get("pour")) {
          const first = pourRes.data[0];
          setPourId(first.id);
          setJobId(first.job_id || "");
        }
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[qr] catalog failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load jobs");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [params]);

  const jobPours = useMemo(() => pours.filter((p) => !jobId || p.job_id === jobId), [pours, jobId]);

  const loadPack = useCallback(async (nextPour, nextJob) => {
    if (!nextPour && !nextJob) {
      setPack([]);
      return;
    }
    try {
      const qs = nextPour ? `pour_id=${encodeURIComponent(nextPour)}` : `job_id=${encodeURIComponent(nextJob)}`;
      const { data } = await api.get(`/qr-labels/pack?${qs}`);
      const rows = data.beams || [];
      setPack(rows);
      setSelected((cur) => {
        if (cur.size) {
          const keep = new Set(rows.filter((r) => cur.has(r.id)).map((r) => r.id));
          if (keep.size) return keep;
        }
        return new Set(rows.map((r) => r.id));
      });
    } catch (err) {
      console.error("[qr] pack failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load QR pack");
    }
  }, []);

  useEffect(() => {
    if (loading) return undefined;
    loadPack(pourId, pourId ? "" : jobId);
    return undefined;
  }, [loading, pourId, jobId, loadPack]);

  const visible = pack.filter((row) => selected.has(row.id));
  const seedBeam = params.get("beam");
  const seedRow = pack.find((row) => row.id === seedBeam) || beams.find((b) => b.id === seedBeam);

  const toggle = (id) => {
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const downloadPdf = async (beamIds) => {
    if (!beamIds.length) {
      toast.error("Select at least one beam");
      return;
    }
    setBusy("pdf");
    try {
      const res = await api.post("/qr-labels", { beam_ids: beamIds }, { responseType: "blob" });
      downloadBlob(res.data, "beam-qr-labels.pdf", "application/pdf");
      toast.success("PDF downloaded — print at Actual Size / 100%");
    } catch (err) {
      console.error("[qr] pdf failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to generate QR labels");
    } finally {
      setBusy("");
    }
  };

  const reprintOne = async (beamId, mark) => {
    setBusy(beamId);
    try {
      const res = await api.get(`/beams/${beamId}/qr-label.pdf`, { responseType: "blob" });
      downloadBlob(res.data, `qr-${mark || beamId.slice(0, 8)}.pdf`, "application/pdf");
      toast.success(`Reprinted ${mark || "beam"} QR`);
    } catch (err) {
      console.error("[qr] reprint failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to reprint QR");
    } finally {
      setBusy("");
    }
  };

  return (
    <Layout>
      <PageHeader
        title="Beam QR Labels"
        subtitle="Laminate tags — Job # + Beam # + QR. Scan opens the living beam record."
        right={
          <div className="flex flex-wrap gap-2 justify-end print:hidden">
            <button
              type="button"
              data-testid="qr-print-btn"
              onClick={() => window.print()}
              disabled={!visible.length}
              className="min-h-12 px-4 border border-[#1C2230] rounded-none flex items-center gap-2 text-sm font-semibold uppercase tracking-wider hover:border-primary hover:text-primary disabled:opacity-50"
            >
              <Printer className="w-4 h-4" /> Print
            </button>
            <button
              type="button"
              data-testid="qr-pdf-btn"
              onClick={() => downloadPdf(visible.map((r) => r.id))}
              disabled={busy === "pdf" || !visible.length}
              className="min-h-12 px-4 bg-primary text-white rounded-none flex items-center gap-2 font-display font-bold uppercase tracking-widest disabled:opacity-60"
            >
              {busy === "pdf" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
              PDF
            </button>
          </div>
        }
      />
      <div className="p-4 sm:p-6 lg:p-8 max-w-6xl">
        <div className={`${cardClass} p-4 sm:p-6 mb-4 grid grid-cols-1 sm:grid-cols-2 gap-4 print:hidden`} data-testid="qr-filters">
          <Field label="Job">
            <select
              value={jobId}
              onChange={(e) => {
                const next = e.target.value;
                setJobId(next);
                const nextPours = pours.filter((p) => !next || p.job_id === next);
                setPourId(nextPours[0]?.id || "");
              }}
              className={inputClass}
              data-testid="qr-job-select"
            >
              <option value="">All jobs</option>
              {jobs.map((job) => (
                <option key={job.id} value={job.id}>{job.job_number} · {job.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Pour">
            <select
              value={pourId}
              onChange={(e) => setPourId(e.target.value)}
              className={inputClass}
              data-testid="qr-pour-select"
            >
              <option value="">Entire job</option>
              {jobPours.map((pour) => (
                <option key={pour.id} value={pour.id}>{pour.pour_number} · {pour.pour_date}</option>
              ))}
            </select>
          </Field>
        </div>

        {seedRow && (
          <div className={`${cardClass} p-4 mb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 print:hidden`} data-testid="qr-reprint-one">
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-[#C9A227]">Reprint single beam</div>
              <div className="font-display font-bold text-xl uppercase">{seedRow.mark}</div>
            </div>
            <button
              type="button"
              onClick={() => reprintOne(seedRow.id, seedRow.mark)}
              disabled={Boolean(busy)}
              className="min-h-12 px-4 bg-primary text-white font-display font-bold uppercase tracking-widest disabled:opacity-60"
            >
              {busy === seedRow.id ? <Loader2 className="w-4 h-4 animate-spin inline" /> : <QrCode className="w-4 h-4 inline mr-2" />}
              Reprint this QR
            </button>
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-16"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>
        ) : (
          <>
            <div className={`${cardClass} p-4 sm:p-6 mb-4 print:hidden`}>
              <div className="flex items-center justify-between mb-3">
                <div className="font-display font-bold uppercase tracking-wider">{pack.length} beams</div>
                <button
                  type="button"
                  className="text-xs font-semibold uppercase tracking-wider text-primary"
                  onClick={() => setSelected(new Set(pack.map((r) => r.id)))}
                >
                  Select all
                </button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {pack.map((row) => (
                  <label key={row.id} className="min-h-12 px-3 border border-[#1C2230] flex items-center gap-3 cursor-pointer hover:border-primary">
                    <input type="checkbox" checked={selected.has(row.id)} onChange={() => toggle(row.id)} />
                    <span className="font-mono text-sm">{row.job_number}</span>
                    <span className="font-display font-bold uppercase">{row.mark}</span>
                    <button
                      type="button"
                      className="ml-auto text-[10px] font-mono uppercase tracking-widest text-muted-foreground hover:text-primary"
                      onClick={(e) => {
                        e.preventDefault();
                        reprintOne(row.id, row.mark);
                      }}
                    >
                      Reprint
                    </button>
                  </label>
                ))}
              </div>
            </div>
            <div className={`${cardClass} p-3 overflow-auto print:border-0 print:bg-white print:p-0`}>
              <QrLabelPrint rows={visible} />
            </div>
          </>
        )}
      </div>
    </Layout>
  );
}
