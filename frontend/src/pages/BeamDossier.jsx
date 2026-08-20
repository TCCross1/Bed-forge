import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Box, FileText, Loader2, LogIn, QrCode, ScanLine } from "lucide-react";
import api, { API, formatApiErrorDetail } from "../lib/api";
import { drawingHref, normalizeToken } from "../lib/beamQr";
import { productionStatus, qcState } from "../lib/constants";
import { useAuth } from "../context/AuthContext";
import { useCompany } from "../context/CompanyContext";
import BeamViewer from "../components/BeamViewer";
import { BrandMark } from "../components/Layout";

const BACKEND = process.env.REACT_APP_BACKEND_URL || "";

function Chip({ label, color }) {
  return (
    <span
      className="font-mono text-[10px] font-bold tracking-widest px-2 py-1 rounded-none"
      style={{ color, border: `1px solid ${color}55` }}
    >
      {label}
    </span>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-3 py-2 border-b border-[#1C2230] last:border-0">
      <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">{label}</span>
      <span className="font-mono text-sm text-right">{value || "—"}</span>
    </div>
  );
}

export default function BeamDossier() {
  const { token: rawToken } = useParams();
  const token = normalizeToken(rawToken);
  const { user, ready } = useAuth();
  const company = useCompany();
  const [dossier, setDossier] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ready) return undefined;
    if (!token) {
      setError("This QR code is not a valid beam identity.");
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    api.get(`/public/beams/${token}`)
      .then((r) => {
        if (cancelled) return;
        setDossier(r.data);
        setError("");
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[dossier] load failed", err);
        setDossier(null);
        setError(formatApiErrorDetail(err.response?.data?.detail) || "Beam record not found");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [token, ready, user?.id]);

  const full = dossier?.access === "full";
  const q = qcState(dossier?.qc_state);
  const p = productionStatus(dossier?.production_status);
  const summary = dossier?.spec_summary || {};
  const logoSrc = dossier?.company?.has_logo
    ? `${API}${dossier.company.logo_url || "/company/logo"}`
    : company.logoSrc;
  const plantName = dossier?.company?.company_name || company.company_name || "BedForge QC";

  return (
    <div className="min-h-screen bg-[#0A0C10] grain" data-testid="beam-dossier">
      <header className="sticky top-0 z-20 border-b border-[#1C2230] bg-[#0A0C10]/95 backdrop-blur">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 min-h-16 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            {logoSrc ? (
              <img src={logoSrc} alt={plantName} className="h-10 w-auto object-contain bg-white p-1" />
            ) : (
              <BrandMark className="h-10 w-auto" testid="dossier-brand" />
            )}
            <div className="min-w-0">
              <div className="font-display font-extrabold uppercase tracking-tight truncate">{plantName}</div>
              <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground">Beam identity</div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {user ? (
              <Link to="/" className="min-h-12 px-4 border border-[#1C2230] rounded-none flex items-center font-semibold uppercase tracking-wider text-xs hover:border-primary hover:text-primary">
                Plant
              </Link>
            ) : (
              <Link
                to={`/login?next=/b/${token}`}
                className="min-h-12 px-4 bg-primary text-white rounded-none flex items-center gap-2 font-display font-bold uppercase tracking-widest text-xs"
              >
                <LogIn className="w-4 h-4" /> Sign in
              </Link>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto p-4 sm:p-6 lg:p-8">
        {loading && (
          <div className="min-h-[40vh] flex items-center justify-center">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
          </div>
        )}

        {!loading && error && (
          <div className="bg-[#0F1218] border border-[#1C2230] p-8 text-center" data-testid="dossier-missing">
            <QrCode className="w-10 h-10 mx-auto mb-3 text-muted-foreground" />
            <h1 className="font-display font-extrabold text-2xl uppercase">Beam not found</h1>
            <p className="text-sm text-muted-foreground mt-2">{error}</p>
          </div>
        )}

        {!loading && dossier && (
          <div className="space-y-4 sm:space-y-6">
            <section className="bg-[#0F1218] border border-[#1C2230] p-5 sm:p-6" data-testid="dossier-identity">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                <div>
                  <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-[#C9A227]">Permanent record</div>
                  <h1 className="font-display font-extrabold text-3xl sm:text-4xl uppercase tracking-tight mt-1">{dossier.mark}</h1>
                  <p className="text-sm text-muted-foreground mt-1">
                    {dossier.job?.job_number || "Job"} · {dossier.pour?.pour_number || "Pour"} · Bed {dossier.bed?.bed_number || "—"}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Chip label={p.label} color={p.color} />
                  <Chip label={q.label} color={q.color} />
                  <Chip label={full ? "FULL ACCESS" : "FIELD VIEW"} color={full ? "#00E676" : "#2979FF"} />
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-8 mt-4">
                <Row label="Job" value={dossier.job?.job_number} />
                <Row label="Customer" value={dossier.job?.customer} />
                <Row label="Pour" value={dossier.pour?.pour_number} />
                <Row label="Pour date" value={dossier.pour?.pour_date} />
                <Row label="Bed" value={dossier.bed?.name || (dossier.bed?.bed_number ? `Bed ${dossier.bed.bed_number}` : "")} />
                <Row label="Marked end" value={dossier.marked_end?.label || dossier.marked_end?.toward} />
                <Row label="Product" value={dossier.product_type?.name || summary.product_name} />
                <Row label="Length" value={dossier.length_ft ? `${dossier.length_ft} ft` : (summary.length_ft ? `${summary.length_ft} ft` : "")} />
                <Row label="Mix" value={dossier.pour?.concrete_mix} />
              </div>
            </section>

            <section className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
              <div className="lg:col-span-2 bg-[#0F1218] border border-[#1C2230] overflow-hidden" style={{ minHeight: 360 }}>
                <div className="px-4 py-3 border-b border-[#1C2230] flex items-center justify-between">
                  <div className="font-display font-bold uppercase tracking-wider">3D Digital Twin</div>
                  {full && dossier.id && (
                    <Link to={`/job-specs?beam=${dossier.id}`} className="text-xs font-semibold uppercase tracking-wider text-primary flex items-center gap-1">
                      <Box className="w-4 h-4" /> Open interactive
                    </Link>
                  )}
                </div>
                <div className="h-[360px]">
                  <BeamViewer
                    spec={dossier.spec}
                    twinType={dossier.twin_type}
                    length={dossier.length_ft}
                    anomalies={full ? (dossier.anomalies || []) : []}
                    compact
                  />
                </div>
              </div>
              <div className="bg-[#0F1218] border border-[#1C2230] p-5">
                <div className="font-display font-bold uppercase tracking-wider mb-3">BeamSpec</div>
                <Row label="Depth" value={summary.depth_in ? `${summary.depth_in}"` : ""} />
                <Row label="Width" value={summary.width_in ? `${summary.width_in}"` : ""} />
                <Row label="Strands" value={summary.strand_count} />
                <Row label="Hold-downs" value={summary.hold_down_count} />
                <Row label="Hardware" value={summary.hardware_count} />
                <Row label="Spec" value={summary.status} />
                {!full && (
                  <p className="text-xs text-muted-foreground mt-4">
                    Sign in as QC or Supervisor to open QIR, tension, camber, finish, and strand heat history.
                  </p>
                )}
              </div>
            </section>

            <section className="bg-[#0F1218] border border-[#1C2230] p-5 sm:p-6" data-testid="dossier-drawings">
              <div className="font-display font-bold uppercase tracking-wider mb-3">Shop drawings</div>
              {(dossier.blueprints || []).length === 0 ? (
                <p className="text-sm text-muted-foreground">No drawings linked to this beam yet.</p>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {dossier.blueprints.map((bp) => (
                    <a
                      key={bp.id}
                      href={drawingHref(bp.url, BACKEND)}
                      target="_blank"
                      rel="noreferrer"
                      className="min-h-12 px-4 border border-[#1C2230] rounded-none flex items-center gap-2 hover:border-primary hover:text-primary"
                    >
                      <FileText className="w-4 h-4" />
                      <span className="truncate text-sm">{bp.original_name || "Drawing"}</span>
                    </a>
                  ))}
                </div>
              )}
            </section>

            {full && (
              <section className="bg-[#0F1218] border border-[#1C2230] p-5 sm:p-6 space-y-4" data-testid="dossier-qc">
                <div className="font-display font-bold uppercase tracking-wider">QC history</div>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-8 gap-2">
                  {[
                    ["QIR", (dossier.inspections || []).length, `/inspection?beam=${dossier.id}`],
                    ["Fresh", (dossier.fresh_tests || []).length, `/fresh?beam=${dossier.id}&job=${dossier.job?.id || ""}&pour=${dossier.pour?.id || ""}`],
                    ["Batch", (dossier.batch_records || []).length, `/batch?beam=${dossier.id}&job=${dossier.job?.id || ""}&pour=${dossier.pour?.id || ""}`],
                    ["Tension", (dossier.tension_reports || []).length, `/tension?beam=${dossier.id}`],
                    ["Camber", (dossier.camber_readings || []).length, `/camber?beam=${dossier.id}`],
                    ["Finish", (dossier.finish_sheets || []).length, `/finish?beam=${dossier.id}`],
                    ["NCR", (dossier.ncrs || []).length, `/ncr?beam=${dossier.id}`],
                    ["Release", (dossier.pre_delivery || []).length, `/release?beam=${dossier.id}`],
                  ].map(([label, count, href]) => (
                    <Link key={label} to={href} className="border border-[#1C2230] p-3 hover:border-primary">
                      <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">{label}</div>
                      <div className="font-mono text-2xl font-bold">{count}</div>
                    </Link>
                  ))}
                </div>
                <div>
                  <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2">Strand heats</div>
                  {(dossier.traceability?.heat_numbers || []).length ? (
                    <div className="flex flex-wrap gap-2">
                      {dossier.traceability.heat_numbers.map((heat) => (
                        <span key={heat} className="font-mono text-xs px-2 py-1 border border-[#1C2230]">{heat}</span>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">No strand roll assigned yet.</p>
                  )}
                </div>
                {(dossier.ncrs || []).length > 0 && (
                  <div data-testid="dossier-ncrs">
                    <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2">NCR history</div>
                    <ul className="space-y-1">
                      {dossier.ncrs.slice(0, 12).map((item) => (
                        <li key={item.id}>
                          <Link to={`/ncr?id=${item.id}`} className="text-sm font-mono hover:text-primary">
                            {(item.severity || "—").toUpperCase()} · {item.status} · {item.description || item.sub_type || item.category}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {(dossier.anomalies || []).length > 0 && (
                  <div>
                    <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2">Anomalies</div>
                    <ul className="space-y-1">
                      {dossier.anomalies.slice(0, 8).map((item) => (
                        <li key={item.id} className="text-sm font-mono">
                          {(item.type || "note").toUpperCase()} · {item.severity || "—"} · {item.note || ""}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="flex flex-wrap gap-2 pt-2">
                  <Link to={`/job-specs?beam=${dossier.id}`} className="min-h-12 px-4 bg-primary text-white font-display font-bold uppercase tracking-widest flex items-center">
                    Digital Twin
                  </Link>
                  <Link to={`/qr?beam=${dossier.id}`} className="min-h-12 px-4 border border-[#1C2230] font-semibold uppercase tracking-wider flex items-center gap-2 hover:border-primary hover:text-primary">
                    <QrCode className="w-4 h-4" /> Reprint QR
                  </Link>
                  <Link to="/scan" className="min-h-12 px-4 border border-[#1C2230] font-semibold uppercase tracking-wider flex items-center gap-2 hover:border-primary hover:text-primary">
                    <ScanLine className="w-4 h-4" /> Scan another
                  </Link>
                </div>
              </section>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
