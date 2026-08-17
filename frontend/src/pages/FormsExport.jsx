import React, { useEffect, useState } from "react";
import api, { API } from "../lib/api";
import Layout, { PageHeader } from "../components/Layout";
import { FileSpreadsheet, Download, Loader2 } from "lucide-react";
import { toast } from "sonner";

const FORMS = [
  { type: "qir", title: "QIR 2026.6.1", desc: "Quality Inspection Report — full section summary per beam", needsBeam: true },
  { type: "tension", title: "Tension Report", desc: "Strand tension & elongation across all active beds", needsBeam: false },
  { type: "camber", title: "Camber / Strength Sheet", desc: "Release strength & camber readings", needsBeam: false },
  { type: "crackmap", title: "Crack Map / Anomaly Log", desc: "All logged surface anomalies", needsBeam: false },
];

export default function FormsExport() {
  const [beams, setBeams] = useState([]);
  const [beamId, setBeamId] = useState("");
  const [busy, setBusy] = useState("");

  useEffect(() => {
    api.get("/beams").then((r) => { setBeams(r.data); if (r.data.length) setBeamId(r.data[0].id); });
  }, []);

  const download = async (form) => {
    setBusy(form.type);
    try {
      const url = `/forms/export/${form.type}${form.needsBeam ? `?beam_id=${beamId}` : ""}`;
      const res = await api.get(url, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `${form.title.replace(/[^a-z0-9]/gi, "_")}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success(`${form.title} exported`);
    } catch {
      toast.error("Export failed");
    } finally {
      setBusy("");
    }
  };

  return (
    <Layout>
      <PageHeader title="Forms Export" subtitle="Digital versions of plant Excel/PDF forms" />
      <div className="p-8 max-w-4xl">
        <div className="bg-card border border-border rounded-sm p-6 mb-6">
          <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Beam (for QIR)</label>
          <select data-testid="forms-beam-select" value={beamId} onChange={(e) => setBeamId(e.target.value)} className="mt-2 w-full md:max-w-sm bg-background border border-border rounded-sm px-4 min-h-12 font-mono text-sm">
            {beams.map((b) => <option key={b.id} value={b.id}>{b.mark}</option>)}
          </select>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {FORMS.map((form) => (
            <div key={form.type} className="bg-card border border-border rounded-sm p-6 flex flex-col" data-testid={`form-card-${form.type}`}>
              <div className="flex items-start gap-3 mb-4">
                <div className="w-11 h-11 bg-primary/15 border border-primary/40 rounded-sm flex items-center justify-center">
                  <FileSpreadsheet className="w-6 h-6 text-primary" />
                </div>
                <div>
                  <h3 className="font-display font-bold text-lg uppercase tracking-wide leading-tight">{form.title}</h3>
                </div>
              </div>
              <p className="text-sm text-muted-foreground mb-6 flex-1">{form.desc}</p>
              <button
                data-testid={`export-${form.type}`}
                onClick={() => download(form)}
                disabled={busy === form.type}
                className="min-h-12 w-full border border-border rounded-sm flex items-center justify-center gap-2 font-semibold uppercase tracking-wider hover:bg-primary hover:border-primary hover:text-white transition-colors duration-100 disabled:opacity-60"
              >
                {busy === form.type ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                Export .xlsx
              </button>
            </div>
          ))}
        </div>
      </div>
    </Layout>
  );
}
