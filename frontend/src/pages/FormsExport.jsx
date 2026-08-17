import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, Field, inputClass, cardClass, ARMeasureLink } from "../components/Layout";
import { Download, Loader2, ClipboardCheck, Calculator, Ruler, Sparkles, Truck, Tags } from "lucide-react";
import { toast } from "sonner";

const FORMS = [
  { type: "qir", title: "QIR 2026.6.1", desc: "Quality Inspection Report — Layout through Detailing", needsBeam: true, href: "/inspection", icon: ClipboardCheck },
  { type: "tension", title: "Tension Report", desc: "Strand tension & elongation across all active beds", needsBeam: false, href: "/tension", icon: Calculator },
  { type: "camber", title: "Camber / Strength Sheet", desc: "Release strength & 3-point camber readings", needsBeam: false, href: "/camber", icon: Ruler },
  { type: "finish", title: "Finish Sheet", desc: "Post-pour strand treatment, hardware, surface, Marked End ID", needsBeam: true, href: "/finish", icon: Sparkles },
  { type: "pre_delivery", title: "Pre-Delivery / Release", desc: "Final checks, truck, destination, multi-party sign-off", needsBeam: true, href: "/release", icon: Truck },
];

export default function FormsExport() {
  const [beams, setBeams] = useState([]);
  const [beamId, setBeamId] = useState("");
  const [busy, setBusy] = useState("");

  useEffect(() => {
    api.get("/beams")
      .then((r) => {
        setBeams(r.data);
        if (r.data.length) setBeamId(r.data[0].id);
      })
      .catch((err) => {
        console.error("[forms] beams load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load beams");
      });
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
    } catch (err) {
      console.error("[forms] export failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Export failed");
    } finally {
      setBusy("");
    }
  };

  return (
    <Layout>
      <PageHeader
        title="Forms Export"
        subtitle="Hub for QIR / Tension / Camber / Finish / Pre-Delivery"
        right={<ARMeasureLink beamId={beamId} purpose="level" />}
      />
      <div className="p-4 sm:p-6 lg:p-8 max-w-5xl">
        <div className={`${cardClass} p-5 sm:p-6 mb-4 sm:mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3`} data-testid="form-card-cylinders">
          <div className="flex items-start gap-3">
            <div className="w-11 h-11 bg-primary/15 border border-primary/40 rounded-none flex items-center justify-center">
              <Tags className="w-6 h-6 text-primary" />
            </div>
            <div>
              <h3 className="font-display font-bold text-lg uppercase tracking-wide leading-tight">Cylinder Tag Generator</h3>
              <p className="text-sm text-muted-foreground mt-1">Morning setup, beam entry, auto labels, white-label print — replaces the Excel file.</p>
            </div>
          </div>
          <Link to="/tags" className="min-h-12 px-4 bg-primary text-white font-display font-bold uppercase tracking-widest flex items-center justify-center">Open</Link>
        </div>
        <div className={`${cardClass} p-5 sm:p-6 mb-4 sm:mb-6`}>
          <Field label="Beam (for QIR, Finish, Pre-Delivery)">
            <select data-testid="forms-beam-select" value={beamId} onChange={(e) => setBeamId(e.target.value)} className={`${inputClass} md:max-w-sm`}>
              {beams.map((b) => (
                <option key={b.id} value={b.id}>{b.mark}</option>
              ))}
            </select>
          </Field>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {FORMS.map((form) => {
            const Icon = form.icon;
            return (
              <div key={form.type} className={`${cardClass} p-5 sm:p-6 flex flex-col`} data-testid={`form-card-${form.type}`}>
                <div className="flex items-start gap-3 mb-4">
                  <div className="w-11 h-11 bg-primary/15 border border-primary/40 rounded-none flex items-center justify-center">
                    <Icon className="w-6 h-6 text-primary" />
                  </div>
                  <div>
                    <h3 className="font-display font-bold text-lg uppercase tracking-wide leading-tight">{form.title}</h3>
                  </div>
                </div>
                <p className="text-sm text-muted-foreground mb-6 flex-1">{form.desc}</p>
                <div className="grid grid-cols-2 gap-2">
                  <Link
                    to={form.href}
                    className="min-h-12 border border-[#1C2230] rounded-none flex items-center justify-center font-semibold uppercase tracking-wider hover:border-primary hover:text-primary text-sm"
                  >
                    Open
                  </Link>
                  <button
                    data-testid={`export-${form.type}`}
                    onClick={() => download(form)}
                    disabled={busy === form.type}
                    className="min-h-12 border border-[#1C2230] rounded-none flex items-center justify-center gap-2 font-semibold uppercase tracking-wider hover:bg-primary hover:border-primary hover:text-white transition-colors duration-100 disabled:opacity-60"
                  >
                    {busy === form.type ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                    .xlsx
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Layout>
  );
}
