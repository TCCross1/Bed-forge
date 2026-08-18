import React, { useEffect, useMemo, useState } from "react";
import api from "../lib/api";
import Layout, { PageHeader } from "../components/Layout";
import { Download, FileSpreadsheet, FileText, Loader2 } from "lucide-react";
import { toast } from "sonner";

const LEGACY_FORMS = [
  { type: "qir", title: "QIR 2026.6.1", desc: "Quality Inspection Report — full section summary per beam", needsBeam: true },
  { type: "tension", title: "Tension Report", desc: "Strand tension & elongation across all active beds", needsBeam: false },
  { type: "camber", title: "Camber / Strength Sheet", desc: "Release strength & camber readings", needsBeam: false },
  { type: "crackmap", title: "Crack Map / Anomaly Log", desc: "All logged surface anomalies", needsBeam: false },
];

const PACKAGE_TYPES = [
  { type: "pour_complete", title: "Pour Complete Package", desc: "Cover, beams, batch/environment, QIR, tension, strength/camber, finish, sign-off, strand traceability, NCRs" },
  { type: "single_beam", title: "Single Beam Package", desc: "Full beam package with signatures, anomalies, and linked NCRs" },
  { type: "full_job", title: "Full Job Package", desc: "All pours, beds, and beams compiled into one job PDF" },
];

export default function FormsExport() {
  const [jobs, setJobs] = useState([]);
  const [pours, setPours] = useState([]);
  const [beds, setBeds] = useState([]);
  const [beams, setBeams] = useState([]);
  const [license, setLicense] = useState(null);
  const [jobId, setJobId] = useState("");
  const [pourId, setPourId] = useState("");
  const [beamId, setBeamId] = useState("");
  const [busy, setBusy] = useState("");

  useEffect(() => {
    Promise.all([
      api.get("/jobs"),
      api.get("/pours"),
      api.get("/beds"),
      api.get("/beams"),
      api.get("/license"),
    ]).then(([jobsRes, poursRes, bedsRes, beamsRes, licenseRes]) => {
      setJobs(jobsRes.data);
      setPours(poursRes.data);
      setBeds(bedsRes.data);
      setBeams(beamsRes.data);
      setLicense(licenseRes.data);
      setJobId(jobsRes.data[0]?.id || "");
      setPourId(poursRes.data[0]?.id || "");
      setBeamId(beamsRes.data[0]?.id || "");
    });
  }, []);

  const selectedBeam = useMemo(() => beams.find((item) => item.id === beamId), [beams, beamId]);

  const downloadBlob = (blob, filename) => {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  const exportLegacy = async (form) => {
    setBusy(form.type);
    try {
      const url = `/forms/export/${form.type}${form.needsBeam ? `?beam_id=${beamId}` : ""}`;
      const res = await api.get(url, { responseType: "blob" });
      downloadBlob(new Blob([res.data], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }), `${form.title.replace(/[^a-z0-9]/gi, "_")}.xlsx`);
      toast.success(`${form.title} exported`);
    } catch {
      toast.error("Export failed");
    } finally {
      setBusy("");
    }
  };

  const exportPackage = async (pkg) => {
    const enabled = license?.status !== "expired"
      && license?.feature_flags?.package_export
      && (pkg.type !== "full_job" || license?.feature_flags?.advanced_exports);
    if (!enabled) {
      toast.error("This export is not enabled by the current license");
      return;
    }
    setBusy(pkg.type);
    try {
      const params = new URLSearchParams({ package_type: pkg.type });
      if (pkg.type === "pour_complete") params.set("pour_id", pourId);
      if (pkg.type === "single_beam") params.set("beam_id", beamId);
      if (pkg.type === "full_job") params.set("job_id", jobId);
      const res = await api.get(`/packages/export/pdf?${params.toString()}`, { responseType: "blob" });
      downloadBlob(new Blob([res.data], { type: "application/pdf" }), `${pkg.type}.pdf`);
      toast.success(`${pkg.title} exported`);
    } catch {
      toast.error("Package export failed");
    } finally {
      setBusy("");
    }
  };

  return (
    <Layout>
      <PageHeader title="Package & Forms Export" subtitle="State / DOT packages plus legacy BedForge form exports" />
      <div className="p-8 space-y-6">
        <div className="bg-card border border-border rounded-sm p-6 grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Job</label>
            <select value={jobId} onChange={(e) => setJobId(e.target.value)} className="mt-2 w-full bg-background border border-border rounded-sm px-4 min-h-12 font-mono text-sm">
              {jobs.map((item) => <option key={item.id} value={item.id}>{item.job_number} · {item.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Pour</label>
            <select value={pourId} onChange={(e) => setPourId(e.target.value)} className="mt-2 w-full bg-background border border-border rounded-sm px-4 min-h-12 font-mono text-sm">
              {pours.map((item) => <option key={item.id} value={item.id}>{item.pour_number}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Beam</label>
            <select value={beamId} onChange={(e) => setBeamId(e.target.value)} className="mt-2 w-full bg-background border border-border rounded-sm px-4 min-h-12 font-mono text-sm" data-testid="forms-beam-select">
              {beams.map((item) => <option key={item.id} value={item.id}>{item.mark} · Bed {beds.find((bed) => bed.id === item.bed_id)?.bed_number || "—"}</option>)}
            </select>
          </div>
          <div className="border border-border rounded-sm px-4 py-3 text-sm font-mono">
            <div className="text-xs uppercase tracking-widest text-muted-foreground">Selected Beam</div>
            <div className="mt-2 text-white">{selectedBeam?.product_type?.name || "—"}</div>
            <div className="text-muted-foreground mt-1">{selectedBeam?.length_ft || "—"} ft</div>
            <div className="text-muted-foreground mt-1">Blueprint {selectedBeam?.blueprint_source?.status === "locked" ? `locked · ${selectedBeam?.blueprint_source?.revision_id?.slice(0, 8)}` : selectedBeam?.blueprint_source?.status || "legacy_seed"}</div>
          </div>
        </div>

        <div>
          <h2 className="font-display font-extrabold text-xl uppercase tracking-wide mb-4">Print-ready PDF Packages</h2>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {PACKAGE_TYPES.map((pkg) => (
              <div key={pkg.type} className="bg-card border border-border rounded-sm p-6 flex flex-col">
                <div className="flex items-start gap-3 mb-4">
                  <div className="w-11 h-11 bg-primary/15 border border-primary/40 rounded-sm flex items-center justify-center"><FileText className="w-6 h-6 text-primary" /></div>
                  <div><h3 className="font-display font-bold text-lg uppercase tracking-wide leading-tight">{pkg.title}</h3></div>
                </div>
                <p className="text-sm text-muted-foreground mb-6 flex-1">{pkg.desc}</p>
                <button onClick={() => exportPackage(pkg)} disabled={busy === pkg.type || license?.status === "expired" || !license?.feature_flags?.package_export || (pkg.type === "full_job" && !license?.feature_flags?.advanced_exports)} className="min-h-12 w-full bg-primary text-white rounded-sm flex items-center justify-center gap-2 font-semibold uppercase tracking-wider hover:bg-white hover:text-black transition-colors duration-100 disabled:opacity-60">
                  {busy === pkg.type ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />} {pkg.type === "full_job" && !license?.feature_flags?.advanced_exports ? "Enterprise Required" : "Export PDF"}
                </button>
              </div>
            ))}
          </div>
        </div>

        <div>
          <h2 className="font-display font-extrabold text-xl uppercase tracking-wide mb-4">Legacy XLSX Sheets</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {LEGACY_FORMS.map((form) => (
              <div key={form.type} className="bg-card border border-border rounded-sm p-6 flex flex-col" data-testid={`form-card-${form.type}`}>
                <div className="flex items-start gap-3 mb-4">
                  <div className="w-11 h-11 bg-primary/15 border border-primary/40 rounded-sm flex items-center justify-center"><FileSpreadsheet className="w-6 h-6 text-primary" /></div>
                  <div><h3 className="font-display font-bold text-lg uppercase tracking-wide leading-tight">{form.title}</h3></div>
                </div>
                <p className="text-sm text-muted-foreground mb-6 flex-1">{form.desc}</p>
                <button data-testid={`export-${form.type}`} onClick={() => exportLegacy(form)} disabled={busy === form.type || license?.status === "expired" || !license?.feature_flags?.package_export} className="min-h-12 w-full border border-border rounded-sm flex items-center justify-center gap-2 font-semibold uppercase tracking-wider hover:bg-primary hover:border-primary hover:text-white transition-colors duration-100 disabled:opacity-60">
                  {busy === form.type ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />} Export XLSX
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Layout>
  );
}
