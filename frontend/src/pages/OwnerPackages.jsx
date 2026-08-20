import React, { useEffect, useState } from "react";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, Field, inputClass, cardClass } from "../components/Layout";
import { toast } from "sonner";
import { Download, FileSpreadsheet, Loader2, Package } from "lucide-react";
import { useOpenJob } from "../context/OpenJobContext";
import { jobListParams } from "../lib/jobAccess";

export default function OwnerPackages() {
  const { openJob } = useOpenJob();
  const [pours, setPours] = useState([]);
  const [pourId, setPourId] = useState("");
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState("");

  const load = async (id) => {
    try {
      const { data } = await api.get("/packages", { params: id ? { pour_id: id } : {} });
      setRows(data || []);
    } catch (err) {
      console.error("[packages] list failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to list packages");
    }
  };

  useEffect(() => {
    api.get("/pours", { params: jobListParams(openJob) }).then((r) => {
      setPours(r.data || []);
      setPourId((cur) => cur || r.data?.[0]?.id || "");
    }).catch((err) => {
      console.error("[packages] pours failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load pours");
    });
  }, [openJob?.id]);

  useEffect(() => {
    load(pourId);
  }, [pourId]);

  const generate = async () => {
    if (!pourId) return;
    setBusy("gen");
    try {
      const { data } = await api.post("/packages", { pour_id: pourId, include_excel: true });
      toast.success(`Package saved for pour ${data.pour_number || ""}`);
      await load(pourId);
    } catch (err) {
      console.error("[packages] generate failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to generate package");
    } finally {
      setBusy("");
    }
  };

  const download = async (pkg, kind) => {
    setBusy(`${pkg.id}-${kind}`);
    try {
      const res = await api.get(`/packages/${pkg.id}/${kind}`, { responseType: "blob" });
      const name = kind === "pdf" ? pkg.pdf_filename : pkg.xlsx_filename;
      const blob = new Blob([res.data], { type: kind === "pdf" ? "application/pdf" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = name || `package.${kind}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      console.error("[packages] download failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Download failed");
    } finally {
      setBusy("");
    }
  };

  return (
    <Layout>
      <PageHeader
        title="DOT / Owner packages"
        subtitle="One-click pour packet: QIR, tension, strength & camber, finish, pre-delivery, heats, drawings. Branded PDF + Excel, stored on the pour forever."
      />
      <div className="p-4 sm:p-6 lg:p-8 max-w-5xl space-y-4">
        <div className={`${cardClass} p-5 space-y-4`}>
          <Field label="Pour">
            <select className={inputClass} value={pourId} onChange={(e) => setPourId(e.target.value)} data-testid="package-pour">
              {pours.map((p) => (
                <option key={p.id} value={p.id}>{p.pour_number} · {p.pour_date || ""}</option>
              ))}
            </select>
          </Field>
          <button
            type="button"
            data-testid="package-generate"
            disabled={!pourId || busy === "gen"}
            onClick={generate}
            className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest disabled:opacity-60"
          >
            {busy === "gen" ? <Loader2 className="w-4 h-4 animate-spin inline" /> : <><Package className="w-4 h-4 inline mr-2" /> Generate package</>}
          </button>
        </div>
        <div className={`${cardClass} p-5`} data-testid="package-history">
          <div className="font-display font-bold uppercase tracking-wider mb-3">Stored packets</div>
          {(rows || []).map((pkg) => (
            <div key={pkg.id} className="border-b border-[#1C2230] py-3 flex flex-col sm:flex-row sm:items-center gap-2">
              <div className="min-w-0">
                <div className="font-mono text-sm">Pour {pkg.pour_number} · Job {pkg.job_number || "—"}</div>
                <div className="text-[10px] font-mono text-muted-foreground">{(pkg.beam_marks || []).join(", ")} · {String(pkg.created_at || "").slice(0, 16)} · {pkg.created_by}</div>
              </div>
              <div className="flex gap-2 sm:ml-auto">
                <button type="button" onClick={() => download(pkg, "pdf")} className="min-h-10 px-3 border border-[#1C2230] text-[10px] font-mono uppercase hover:border-primary hover:text-primary">
                  <Download className="w-3 h-3 inline mr-1" /> PDF
                </button>
                {pkg.xlsx_filename && (
                  <button type="button" onClick={() => download(pkg, "xlsx")} className="min-h-10 px-3 border border-[#1C2230] text-[10px] font-mono uppercase hover:border-primary hover:text-primary">
                    <FileSpreadsheet className="w-3 h-3 inline mr-1" /> Excel
                  </button>
                )}
              </div>
            </div>
          ))}
          {!(rows || []).length && <div className="text-xs font-mono text-muted-foreground">No packages yet. Generate one for this pour.</div>}
        </div>
      </div>
    </Layout>
  );
}
