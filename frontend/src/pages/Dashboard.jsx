import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, cardClass, ARMeasureLink } from "../components/Layout";
import PlantFloor from "../components/PlantFloor";
import { bedState, productionStatus, qcState } from "../lib/constants";
import { isoToday } from "../lib/bedLayout";
import { Activity, Layers, CheckCircle2, AlertTriangle, XCircle, Loader2, RefreshCw, Box, LayoutGrid, ScanLine } from "lucide-react";
import { toast } from "sonner";
import { useDevice } from "../context/DeviceContext";
import { useSync } from "../context/SyncContext";

function Stat({ label, value, color, icon: Icon, testid }) {
  return (
    <div className={`${cardClass} p-4 sm:p-6`} data-testid={testid}>
      <div className="flex items-center justify-between">
        <span className="text-[10px] sm:text-xs font-mono uppercase tracking-widest text-muted-foreground">{label}</span>
        <Icon className="w-4 h-4 sm:w-5 sm:h-5" style={{ color }} />
      </div>
      <div className="font-mono text-3xl sm:text-4xl font-bold mt-2 sm:mt-3" style={{ color }}>{value ?? "—"}</div>
    </div>
  );
}

function BedCard({ bed, onOpen, onOpenBeam }) {
  const st = bedState(bed.status);
  return (
    <button
      type="button"
      data-testid={`bed-card-${bed.bed_number}`}
      className={`${cardClass} p-4 sm:p-5 flex flex-col text-left transition-colors duration-100 hover:border-primary w-full min-h-[180px]`}
      style={{ borderColor: bed.status === "idle" ? "#1C2230" : `${st.color}55` }}
      onClick={() => onOpen(bed)}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="font-display font-extrabold text-xl sm:text-2xl">BED {bed.bed_number}</div>
        <span className="w-3 h-3 rounded-none animate-pulse" style={{ background: st.dot }} />
      </div>
      <div className="flex items-center gap-2 mb-4">
        <span
          className="text-xs font-mono font-bold tracking-widest px-2 py-1 rounded-none"
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
        {(bed.beams || []).slice(0, 8).map((b) => {
          const q = qcState(b.qc_state);
          const p = productionStatus(b.production_status);
          return (
            <span
              key={b.id}
              title={`${b.mark} · ${p.label} · ${q.label}`}
              className="text-[10px] font-mono px-1.5 py-0.5 rounded-none border"
              style={{ color: p.color, borderColor: `${p.color}55` }}
              onClick={(e) => {
                e.stopPropagation();
                onOpenBeam(b);
              }}
            >
              {b.mark}
            </span>
          );
        })}
      </div>
    </button>
  );
}

export default function Dashboard() {
  const device = useDevice();
  const { events, measurements } = useSync();
  const [data, setData] = useState(null);
  const [plant, setPlant] = useState(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState(() => sessionStorage.getItem("bf_board_view") || "twins");
  const navigate = useNavigate();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [dash, floor] = await Promise.all([
        api.get("/dashboard"),
        api.get("/beds/plant-layout", { params: { date: isoToday() } }),
      ]);
      setData(dash.data);
      setPlant(floor.data);
    } catch (err) {
      console.error("[dashboard] load failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load plant board");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  const setBoardView = (next) => {
    setView(next);
    sessionStorage.setItem("bf_board_view", next);
  };

  const openBed = (bed) => {
    navigate(`/planner?bed=${bed.id}&date=${isoToday()}`);
  };

  const openBeam = (beam) => {
    if (beam?.beam_id) navigate(`/twin?beam=${beam.beam_id}`);
    else if (beam?.id) navigate(`/twin?beam=${beam.id}`);
  };

  const s = data?.stats || {};

  return (
    <Layout>
      <PageHeader
        title="Multi-Bed Live Board"
        subtitle="Real-time production sequence across all 8 casting beds"
        right={
          <div className="flex items-center gap-2">
            <div className={`${cardClass} p-1 grid grid-cols-2`}>
              <button
                type="button"
                data-testid="board-view-twins"
                onClick={() => setBoardView("twins")}
                className={`min-h-10 px-3 font-condensed uppercase tracking-wider text-xs ${view === "twins" ? "bg-primary text-white" : "text-muted-foreground"}`}
              >
                <Box className="w-4 h-4 inline mr-1" /> 3D
              </button>
              <button
                type="button"
                data-testid="board-view-cards"
                onClick={() => setBoardView("cards")}
                className={`min-h-10 px-3 font-condensed uppercase tracking-wider text-xs ${view === "cards" ? "bg-primary text-white" : "text-muted-foreground"}`}
              >
                <LayoutGrid className="w-4 h-4 inline mr-1" /> Cards
              </button>
            </div>
            <button
              data-testid="refresh-dashboard"
              onClick={load}
              className="min-h-12 px-4 border border-[#1C2230] rounded-none flex items-center gap-2 text-sm font-semibold uppercase tracking-wider hover:border-primary hover:text-primary transition-colors duration-100"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
          </div>
        }
      />

      <div className="p-4 sm:p-6 lg:p-8">
        {loading && !data ? (
          <div className="flex items-center justify-center h-64 text-muted-foreground">
            <Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading plant status…
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4 mb-6 sm:mb-8">
              <Stat label="Active Beds" value={s.active_beds} color="#2979FF" icon={Activity} testid="stat-active-beds" />
              <Stat label="Total Beams" value={s.total_beams} color="#FFFFFF" icon={Layers} testid="stat-total-beams" />
              <Stat label="Passed" value={s.passed} color="#00E676" icon={CheckCircle2} testid="stat-passed" />
              <Stat label="In Progress" value={s.in_progress} color="#2979FF" icon={Loader2} testid="stat-inprogress" />
              <Stat label="On Hold" value={s.hold} color="#FFD600" icon={AlertTriangle} testid="stat-hold" />
              <Stat label="Failed" value={s.failed} color="#FF3366" icon={XCircle} testid="stat-failed" />
            </div>

            {(measurements[0] || events[0]) && (
              <div className={`${cardClass} p-4 mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3`} data-testid="live-sync-strip">
                <div>
                  <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground flex items-center gap-2">
                    <ScanLine className="w-3 h-3" /> Live field sync
                  </div>
                  <div className="font-mono text-sm mt-1">
                    {measurements[0]
                      ? `${measurements[0].level ? "LEVEL" : "OFF LEVEL"} · ${measurements[0].distance_ft} ft · Δ${measurements[0].delta_height_in}" · ${measurements[0].engine}`
                      : events[0]?.title}
                  </div>
                </div>
                <ARMeasureLink compact={device.field} />
              </div>
            )}

            {view === "twins" ? (
              <div className={`${cardClass} overflow-hidden mb-4`}>
                <div className="px-4 py-3 border-b border-[#1C2230] flex items-center justify-between">
                  <div className="font-display font-bold uppercase tracking-wider">Plant floor · 8 bed twins</div>
                  <span className="text-[10px] font-mono text-muted-foreground">CLICK BED TO PLAN · CLICK BEAM FOR QC TWIN</span>
                </div>
                <PlantFloor
                  plant={plant}
                  height={device.field ? 340 : 520}
                  onSelectBed={openBed}
                  onSelectBeam={openBeam}
                />
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4" data-testid="bed-grid">
                {(data?.beds || []).map((bed) => (
                  <BedCard key={bed.id} bed={bed} onOpen={openBed} onOpenBeam={openBeam} />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </Layout>
  );
}
