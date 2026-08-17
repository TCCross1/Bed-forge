import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import Layout, { PageHeader } from "../components/Layout";
import { bedState, qcState } from "../lib/constants";
import { Activity, Layers, CheckCircle2, AlertTriangle, XCircle, Loader2, RefreshCw } from "lucide-react";

function Stat({ label, value, color, icon: Icon, testid }) {
  return (
    <div className="bg-card border border-border rounded-sm p-6" data-testid={testid}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-mono uppercase tracking-widest text-muted-foreground">{label}</span>
        <Icon className="w-5 h-5" style={{ color }} />
      </div>
      <div className="font-mono text-4xl font-bold mt-3" style={{ color }}>{value}</div>
    </div>
  );
}

function BedCard({ bed, onOpen }) {
  const st = bedState(bed.status);
  return (
    <div
      data-testid={`bed-card-${bed.bed_number}`}
      className="bg-card border rounded-sm p-5 flex flex-col transition-colors duration-100 hover:border-primary cursor-pointer"
      style={{ borderColor: bed.status === "idle" ? "#222631" : st.color + "55" }}
      onClick={() => onOpen(bed)}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="font-display font-extrabold text-2xl">BED {bed.bed_number}</div>
        <span className="w-3 h-3 rounded-full animate-pulse" style={{ background: st.dot }} />
      </div>
      <div className="flex items-center gap-2 mb-4">
        <span
          className="text-xs font-mono font-bold tracking-widest px-2 py-1 rounded-sm"
          style={{ color: st.color, border: `1px solid ${st.color}55` }}
          data-testid={`bed-${bed.bed_number}-status`}
        >
          {st.label}
        </span>
      </div>
      <div className="text-xs font-mono text-muted-foreground space-y-1 mb-4">
        <div className="flex justify-between"><span>LENGTH</span><span className="text-white">{bed.length_ft} ft</span></div>
        <div className="flex justify-between"><span>POUR</span><span className="text-white">{bed.pour_number || "—"}</span></div>
        <div className="flex justify-between"><span>BEAMS</span><span className="text-white">{bed.beam_count}</span></div>
      </div>
      <div className="mt-auto flex flex-wrap gap-1">
        {bed.beams.slice(0, 6).map((b) => {
          const q = qcState(b.qc_state);
          return (
            <span key={b.id} title={`${b.mark} · ${q.label}`}
              className="text-[10px] font-mono px-1.5 py-0.5 rounded-sm border"
              style={{ color: q.color, borderColor: q.color + "55" }}>
              {b.mark}
            </span>
          );
        })}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const load = () => {
    setLoading(true);
    api.get("/dashboard").then((r) => setData(r.data)).finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  const openBed = (bed) => {
    const first = bed.beams?.[0];
    if (first) navigate(`/twin?beam=${first.id}`);
  };

  const s = data?.stats || {};

  return (
    <Layout>
      <PageHeader
        title="Multi-Bed Live Board"
        subtitle="Real-time production & QC status across all 8 beds"
        right={
          <button data-testid="refresh-dashboard" onClick={load}
            className="min-h-12 px-4 border border-border rounded-sm flex items-center gap-2 text-sm font-semibold uppercase tracking-wider hover:border-primary hover:text-primary transition-colors duration-100">
            <RefreshCw className="w-4 h-4" /> Refresh
          </button>
        }
      />

      <div className="p-8">
        {loading && !data ? (
          <div className="flex items-center justify-center h-64 text-muted-foreground">
            <Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading plant status…
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
              <Stat label="Active Beds" value={s.active_beds} color="#2979FF" icon={Activity} testid="stat-active-beds" />
              <Stat label="Total Beams" value={s.total_beams} color="#FFFFFF" icon={Layers} testid="stat-total-beams" />
              <Stat label="Passed" value={s.passed} color="#00E676" icon={CheckCircle2} testid="stat-passed" />
              <Stat label="In Progress" value={s.in_progress} color="#2979FF" icon={Loader2} testid="stat-inprogress" />
              <Stat label="On Hold" value={s.hold} color="#FFD600" icon={AlertTriangle} testid="stat-hold" />
              <Stat label="Failed" value={s.failed} color="#FF3366" icon={XCircle} testid="stat-failed" />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" data-testid="bed-grid">
              {(data?.beds || []).map((bed) => (
                <BedCard key={bed.id} bed={bed} onOpen={openBed} />
              ))}
            </div>
          </>
        )}
      </div>
    </Layout>
  );
}
