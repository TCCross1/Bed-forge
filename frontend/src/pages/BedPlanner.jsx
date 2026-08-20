import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, cardClass, inputClass, ARMeasureLink } from "../components/Layout";
import BedViewer from "../components/BedViewer";
import { useAuth } from "../context/AuthContext";
import { useDevice } from "../context/DeviceContext";
import { PRODUCTION_STATUS_STYLES, canPlan, productionStatus } from "../lib/constants";
import { addDays, dragPayload, isoToday, readDragPayload, weekStartMonday } from "../lib/bedLayout";
import { toast } from "sonner";
import { ArrowLeftRight, CalendarDays, GripVertical, Loader2, RefreshCw, Trash2 } from "lucide-react";

function setParam(params, key, value) {
  const next = new URLSearchParams(params);
  if (value) next.set(key, value);
  else next.delete(key);
  return next;
}

export default function BedPlanner() {
  const { user } = useAuth();
  const device = useDevice();
  const plan = canPlan(user?.role);
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const date = params.get("date") || isoToday();
  const bedId = params.get("bed") || "";
  const highlightBeam = params.get("beam") || "";

  const [calendar, setCalendar] = useState(null);
  const [layout, setLayout] = useState(null);
  const [pool, setPool] = useState({ jobs: [], beams: [] });
  const [jobId, setJobId] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [dragOverId, setDragOverId] = useState("");
  const [suggest, setSuggest] = useState(null);

  const weekStart = useMemo(() => weekStartMonday(date), [date]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [calRes, poolRes, sugRes] = await Promise.all([
        api.get("/beds/calendar", { params: { start: weekStart, days: 7 } }),
        api.get("/planner/pool", { params: { date } }),
        api.get("/beds/suggest", { params: { date } }).catch(() => ({ data: null })),
      ]);
      setCalendar(calRes.data);
      setPool(poolRes.data);
      setSuggest(sugRes.data);
      const beds = calRes.data.beds || [];
      const selected = bedId || beds[0]?.id || "";
      if (selected) {
        const lay = await api.get(`/beds/${selected}/layout`, { params: { date } });
        setLayout(lay.data);
      }
    } catch (err) {
      console.error("[planner] load failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load bed planner");
    } finally {
      setLoading(false);
    }
  }, [bedId, date, weekStart]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!bedId && calendar?.beds?.[0]?.id) {
      setParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("bed", calendar.beds[0].id);
        return next;
      }, { replace: true });
    }
  }, [bedId, calendar, setParams]);

  useEffect(() => {
    if (!jobId && pool.jobs?.[0]?.id) setJobId(pool.jobs[0].id);
  }, [jobId, pool.jobs]);

  const beds = calendar?.beds || [];
  const selectedBed = beds.find((b) => b.id === bedId) || beds[0];
  const jobBeams = (pool.beams || []).filter((b) => !jobId || b.job_id === jobId);
  const available = jobBeams.filter((b) => !b.assigned);
  const assigned = jobBeams.filter((b) => b.assigned);

  const assignBeam = async (payload, targetBedId, targetDate, positionOnBed) => {
    if (!plan) {
      toast.error("Supervisors and production can assign beds");
      return;
    }
    setBusy(true);
    try {
      await api.post("/bed-assignments", {
        bed_id: targetBedId,
        beam_id: payload.beam_id,
        job_id: payload.job_id,
        pour_id: payload.pour_id,
        scheduled_date: targetDate,
        position_on_bed: positionOnBed || undefined,
        marked_end_toward: "header",
      });
      toast.success(`${payload.mark || "Beam"} assigned to bed`);
      await load();
    } catch (err) {
      console.error("[planner] assign failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Assignment conflict");
    } finally {
      setBusy(false);
    }
  };

  const onDropAssign = (event, targetBedId, targetDate, positionOnBed) => {
    event.preventDefault();
    setDragOverId("");
    const payload = readDragPayload(event);
    if (!payload?.beam_id) return;
    assignBeam(payload, targetBedId, targetDate, positionOnBed);
  };

  const reorder = async (fromIndex, toIndex) => {
    if (!plan || !layout?.assignments) return;
    const ids = layout.assignments.map((row) => row.id);
    const [moved] = ids.splice(fromIndex, 1);
    ids.splice(toIndex, 0, moved);
    setBusy(true);
    try {
      const { data } = await api.post(`/beds/${layout.bed.id}/reorder`, { date, assignment_ids: ids });
      setLayout(data);
    } catch (err) {
      console.error("[planner] reorder failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Could not reorder bed");
    } finally {
      setBusy(false);
    }
  };

  const removeAssignment = async (assignmentId) => {
    setBusy(true);
    try {
      await api.delete(`/bed-assignments/${assignmentId}`);
      toast.success("Beam removed from bed");
      await load();
    } catch (err) {
      console.error("[planner] remove failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to remove assignment");
    } finally {
      setBusy(false);
    }
  };

  const flipMarkedEnd = async (row) => {
    setBusy(true);
    try {
      await api.patch(`/bed-assignments/${row.id}`, {
        marked_end_toward: row.marked_end_toward === "bulkhead" ? "header" : "bulkhead",
      });
      await load();
    } catch (err) {
      console.error("[planner] flip ME failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to flip marked end");
    } finally {
      setBusy(false);
    }
  };

  const setStatus = async (row, production_status) => {
    setBusy(true);
    try {
      await api.patch(`/bed-assignments/${row.id}`, { production_status });
      await load();
    } catch (err) {
      console.error("[planner] status failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to update status");
    } finally {
      setBusy(false);
    }
  };

  const setActive = async (row) => {
    if (!plan || !layout?.bed?.id) return;
    try {
      await api.post(`/beds/${layout.bed.id}/active-beam`, null, { params: { beam_id: row.beam_id } });
      await load();
    } catch (err) {
      console.error("[planner] active beam failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to highlight working beam");
    }
  };

  const cellMap = useMemo(() => {
    const map = {};
    (calendar?.cells || []).forEach((cell) => {
      map[`${cell.bed_id}:${cell.date}`] = cell;
    });
    return map;
  }, [calendar]);

  return (
    <Layout>
      <PageHeader
        title="Bed Twin Planner"
        subtitle="Assign job beams to a casting bed and day. Capacity, live occupancy, and packing with least changeover."
        right={
          <div className="flex flex-wrap gap-2 justify-end">
            <ARMeasureLink beamId={highlightBeam} purpose="layout" />
            <button
              data-testid="refresh-planner"
              onClick={load}
              className="min-h-12 px-4 border border-[#1C2230] rounded-none flex items-center gap-2 text-sm font-semibold uppercase tracking-wider hover:border-primary hover:text-primary"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
          </div>
        }
      />

      <div className="p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6">
        <div className={`${cardClass} p-4 grid grid-cols-1 md:grid-cols-4 gap-3`}>
          <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
            Bed
            <select
              data-testid="planner-bed-select"
              className={`${inputClass} mt-1`}
              value={selectedBed?.id || ""}
              onChange={(e) => setParams(setParam(params, "bed", e.target.value))}
            >
              {beds.map((bed) => (
                <option key={bed.id} value={bed.id}>Bed {bed.bed_number} · {bed.length_ft} ft</option>
              ))}
            </select>
          </label>
          <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
            Date
            <input
              data-testid="planner-date"
              type="date"
              className={`${inputClass} mt-1`}
              value={date}
              onChange={(e) => setParams(setParam(params, "date", e.target.value))}
            />
          </label>
          <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
            Job
            <select
              data-testid="planner-job-select"
              className={`${inputClass} mt-1`}
              value={jobId}
              onChange={(e) => setJobId(e.target.value)}
            >
              {(pool.jobs || []).map((job) => (
                <option key={job.id} value={job.id}>{job.job_number} · {job.name}</option>
              ))}
            </select>
          </label>
          <div className="flex items-end">
            <div className="text-xs font-mono text-muted-foreground">
              <div>REMAINING <span className="text-white">{layout?.remaining_ft ?? "—"} ft</span></div>
              <div>BEAMS <span className="text-white">{layout?.assignments?.length || 0}</span>{layout?.over_typical ? " · OVER TYPICAL 4" : ""}</div>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {Object.entries(PRODUCTION_STATUS_STYLES).map(([key, st]) => (
            <span key={key} className="text-[10px] font-mono px-2 py-1 border border-[#1C2230]" style={{ color: st.color }}>
              {st.label}
            </span>
          ))}
        </div>

        {(suggest?.suggestions || []).length > 0 && (
          <div className={`${cardClass} p-4 space-y-2`} data-testid="planner-suggest">
            <div className="font-display font-bold uppercase tracking-wider">Packing suggestions</div>
            {(suggest.suggestions || []).slice(0, 4).map((s) => (
              <div key={s.bed_id} className="border border-[#1C2230] p-3 flex flex-col sm:flex-row sm:items-center gap-2">
                <div className="min-w-0">
                  <div className="font-mono text-sm">{s.headline}</div>
                  <div className="text-[10px] font-mono text-muted-foreground">{s.marks?.join(", ")} · {s.remaining_ft} ft left · {s.utilization_pct}% full</div>
                </div>
                {plan && (
                  <button
                    type="button"
                    disabled={busy}
                    className="min-h-10 px-3 border border-[#1C2230] text-[10px] font-mono uppercase hover:border-primary sm:ml-auto"
                    onClick={async () => {
                      for (const id of s.beam_ids || []) {
                        const beam = (pool.beams || []).find((b) => b.id === id) || { id, beam_id: id };
                        await assignBeam({ beam_id: id, mark: beam.mark, job_id: beam.job_id, pour_id: beam.pour_id }, s.bed_id, date);
                      }
                    }}
                  >
                    Apply
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {loading && !layout ? (
          <div className="flex items-center justify-center h-64 text-muted-foreground">
            <Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading bed twins…
          </div>
        ) : (
          <div className="grid grid-cols-1 xl:grid-cols-[280px_1fr] gap-4">
            <div className={`${cardClass} p-4 space-y-3`} data-testid="planner-pool">
              <div className="font-display font-bold uppercase tracking-wider">Job beams</div>
              <div className="text-[10px] font-mono text-muted-foreground">Drag onto the calendar or bed sequence</div>
              {available.map((beam) => (
                <div
                  key={beam.id}
                  draggable={plan}
                  onDragStart={(e) => {
                    e.dataTransfer.setData("application/json", dragPayload(beam));
                    e.dataTransfer.effectAllowed = "copy";
                  }}
                  className={`border border-[#1C2230] p-3 ${highlightBeam === beam.id ? "border-primary" : ""} ${plan ? "cursor-grab" : ""}`}
                  data-testid={`pool-beam-${beam.mark}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-sm font-bold">{beam.mark}</span>
                    <span className="text-[10px] font-mono" style={{ color: productionStatus(beam.production_status).color }}>
                      {productionStatus(beam.production_status).label}
                    </span>
                  </div>
                  <div className="text-[10px] font-mono text-muted-foreground">{beam.length_ft} ft · {beam.pour_number || "no pour"}</div>
                  {plan && selectedBed && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => assignBeam(beam, selectedBed.id, date)}
                      className="mt-2 min-h-10 w-full border border-[#1C2230] text-[10px] font-mono uppercase tracking-widest hover:border-primary hover:text-primary"
                    >
                      Assign to Bed {selectedBed.bed_number}
                    </button>
                  )}
                </div>
              ))}
              {available.length === 0 && (
                <div className="text-xs font-mono text-muted-foreground">All job beams are assigned this day.</div>
              )}
              {assigned.length > 0 && (
                <div className="pt-2 border-t border-[#1C2230] space-y-1">
                  <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">On beds today</div>
                  {assigned.map((beam) => (
                    <div key={beam.id} className="text-[11px] font-mono text-muted-foreground">
                      {beam.mark} → Bed {beam.bed_number} pos {beam.position_on_bed}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-4">
              <div className={`${cardClass} overflow-hidden`}>
                <div className="px-4 py-3 border-b border-[#1C2230] font-display font-bold uppercase tracking-wider">
                  Bed {selectedBed?.bed_number} twin · {date}
                  {layout?.remaining_ft != null && (
                    <span className="ml-2 text-[10px] font-mono text-muted-foreground">
                      {layout.remaining_ft} ft open · {layout.utilization_pct ?? "—"}%
                    </span>
                  )}
                </div>
                {layout && (
                  <BedViewer
                    layout={layout}
                    height={device.field ? 280 : 420}
                    onSelectBeam={(row) => {
                      if (row?.beam_id) navigate(`/job-specs?beam=${row.beam_id}`);
                    }}
                  />
                )}
              </div>

              <div
                className={`${cardClass} p-4 ${dragOverId === "sequence" ? "border-primary" : ""}`}
                onDragOver={(e) => { e.preventDefault(); setDragOverId("sequence"); }}
                onDragLeave={() => setDragOverId("")}
                onDrop={(e) => onDropAssign(e, selectedBed?.id, date, (layout?.assignments?.length || 0) + 1)}
                data-testid="planner-sequence"
              >
                <div className="font-display font-bold uppercase tracking-wider mb-3">Cast sequence</div>
                {(layout?.assignments || []).map((row, index) => {
                  const st = productionStatus(row.production_status);
                  const active = layout.active_beam_id === row.beam_id;
                  return (
                    <div
                      key={row.id}
                      draggable={plan}
                      onDragStart={(e) => {
                        e.dataTransfer.setData("text/plain", String(index));
                        e.dataTransfer.effectAllowed = "move";
                      }}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => {
                        e.preventDefault();
                        const from = Number(e.dataTransfer.getData("text/plain"));
                        if (Number.isInteger(from)) reorder(from, index);
                      }}
                      className={`flex flex-col sm:flex-row sm:items-center gap-2 border border-[#1C2230] p-3 mb-2 ${active ? "border-[#FFD600]" : ""}`}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        {plan && <GripVertical className="w-4 h-4 text-muted-foreground shrink-0" />}
                        <span className="font-mono text-xs text-muted-foreground">POS {row.position_on_bed}</span>
                        <button type="button" className="font-mono font-bold text-sm truncate hover:text-primary" onClick={() => navigate(`/job-specs?beam=${row.beam_id}`)}>
                          {row.beam?.mark || "BEAM"}
                        </button>
                        <span className="text-[10px] font-mono" style={{ color: st.color }}>{st.label}</span>
                      </div>
                      <div className="text-[10px] font-mono text-muted-foreground">
                        {row.station_ft}'–{row.end_station_ft}' · ME {row.marked_end_toward === "bulkhead" ? "BULKHEAD" : "HEADER"}
                      </div>
                      <div className="flex flex-wrap gap-2 sm:ml-auto">
                        {plan && (
                          <select
                            value={row.production_status || "planned"}
                            onChange={(e) => setStatus(row, e.target.value)}
                            className={`${inputClass} min-h-10 py-0 text-xs`}
                          >
                            {Object.keys(PRODUCTION_STATUS_STYLES).map((key) => (
                              <option key={key} value={key}>{PRODUCTION_STATUS_STYLES[key].label}</option>
                            ))}
                          </select>
                        )}
                        {plan && (
                          <button type="button" onClick={() => flipMarkedEnd(row)} className="min-h-10 px-3 border border-[#1C2230] text-[10px] font-mono uppercase hover:border-primary">
                            <ArrowLeftRight className="w-3 h-3 inline mr-1" /> ME
                          </button>
                        )}
                        {plan && (
                          <button type="button" onClick={() => setActive(row)} className="min-h-10 px-3 border border-[#1C2230] text-[10px] font-mono uppercase hover:border-[#FFD600] hover:text-[#FFD600]">
                            Working
                          </button>
                        )}
                        {plan && (
                          <button type="button" onClick={() => removeAssignment(row.id)} className="min-h-10 px-3 border border-[#1C2230] hover:border-destructive hover:text-destructive">
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
                {(layout?.assignments || []).length === 0 && (
                  <div className="text-xs font-mono text-muted-foreground">Drop a beam here to start the day’s layout.</div>
                )}
              </div>
            </div>
          </div>
        )}

        <div className={`${cardClass} overflow-x-auto`} data-testid="bed-calendar">
          <div className="px-4 py-3 border-b border-[#1C2230] flex items-center justify-between gap-3">
            <div className="font-display font-bold uppercase tracking-wider flex items-center gap-2">
              <CalendarDays className="w-4 h-4 text-primary" /> Week occupancy
            </div>
            <div className="flex gap-2">
              <button type="button" className="min-h-10 px-3 border border-[#1C2230] text-xs font-mono" onClick={() => setParams(setParam(params, "date", addDays(weekStart, -7)))}>Prev</button>
              <button type="button" className="min-h-10 px-3 border border-[#1C2230] text-xs font-mono" onClick={() => setParams(setParam(params, "date", addDays(weekStart, 7)))}>Next</button>
            </div>
          </div>
          <table className="w-full min-w-[720px] text-left">
            <thead>
              <tr className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                <th className="p-3">Bed</th>
                {(calendar?.dates || []).map((day) => (
                  <th key={day} className={`p-3 ${day === date ? "text-primary" : ""}`}>{day.slice(5)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {beds.map((bed) => (
                <tr key={bed.id} className="border-t border-[#1C2230]">
                  <td className="p-3 font-mono text-xs font-bold whitespace-nowrap">BED {bed.bed_number}</td>
                  {(calendar?.dates || []).map((day) => {
                    const cell = cellMap[`${bed.id}:${day}`];
                    const hot = dragOverId === `${bed.id}:${day}`;
                    return (
                      <td
                        key={day}
                        onDragOver={(e) => { e.preventDefault(); setDragOverId(`${bed.id}:${day}`); }}
                        onDragLeave={() => setDragOverId("")}
                        onDrop={(e) => onDropAssign(e, bed.id, day)}
                        onClick={() => {
                          const next = setParam(params, "bed", bed.id);
                          next.set("date", day);
                          setParams(next);
                        }}
                        className={`p-2 align-top min-h-16 cursor-pointer ${hot || (bed.id === selectedBed?.id && day === date) ? "bg-primary/10" : ""}`}
                        data-testid={`cal-${bed.bed_number}-${day}`}
                      >
                        <div className="flex flex-wrap gap-1">
                          {(cell?.marks || []).map((mark, i) => (
                            <span
                              key={`${mark}-${i}`}
                              className="text-[10px] font-mono px-1 border border-[#1C2230]"
                              style={{ color: productionStatus(cell.statuses?.[i]).color }}
                            >
                              {mark}
                            </span>
                          ))}
                          {(!cell || cell.count === 0) && <span className="text-[10px] font-mono text-muted-foreground">OPEN</span>}
                        </div>
                        {cell && (
                          <div className="text-[9px] font-mono text-muted-foreground mt-1">
                            {cell.utilization_pct || 0}% · {cell.remaining_ft ?? "—"} ft
                          </div>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Layout>
  );
}
