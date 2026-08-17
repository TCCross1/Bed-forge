import React, { useEffect, useMemo, useState } from "react";
import { MonitorPlay, Clock3, Factory, Layers3, ShieldAlert, Gauge, Activity } from "lucide-react";
import api from "../lib/api";

const STATE_STYLES = {
  layout_strand: { border: "#FFD600", glow: "rgba(255, 214, 0, 0.12)", text: "#FFD600" },
  pour_cure: { border: "#2979FF", glow: "rgba(41, 121, 255, 0.14)", text: "#7EB0FF" },
  ready_release: { border: "#00E676", glow: "rgba(0, 230, 118, 0.12)", text: "#6BFFB0" },
  hold_ncr: { border: "#FF3366", glow: "rgba(255, 51, 102, 0.12)", text: "#FF7A9D" },
};

const qcTone = {
  pending: "#8B949E",
  in_progress: "#2979FF",
  passed: "#00E676",
  hold: "#FFD600",
  failed: "#FF3366",
  shipped: "#00E676",
};

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

function formatBoardTime(value) {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
    timeZone: "UTC",
  }).format(value);
}

function formatEventTime(value) {
  if (!value) return "--:--";
  return new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(new Date(value));
}

function formatMetric(value, suffix = "") {
  return value == null ? "—" : `${value}${suffix}`;
}

function SummaryTile({ icon: Icon, label, value }) {
  return (
    <div className="min-w-[140px] rounded-sm border border-border bg-card/80 px-4 py-3">
      <div className="flex items-center justify-between gap-3 text-[11px] uppercase tracking-[0.25em] text-muted-foreground font-mono">
        <span>{label}</span>
        <Icon className="h-4 w-4 text-primary" />
      </div>
      <div className="mt-2 font-mono text-3xl font-bold text-white">{value}</div>
    </div>
  );
}

function BeamMiniTwin({ beam }) {
  const tone = qcTone[beam.qc_state] || "#8B949E";
  return (
    <div className="rounded-sm border border-white/5 bg-black/20 p-2">
      <div className="flex items-center justify-between gap-3 text-[10px] uppercase tracking-[0.24em] text-muted-foreground font-mono">
        <span>P{beam.position_on_bed}</span>
        <span style={{ color: tone }}>{(beam.qc_state || "pending").replace(/_/g, " ")}</span>
      </div>
      <div className="mt-2 h-3 rounded-full bg-[#11151d] p-[2px]">
        <div className="h-full rounded-full" style={{ width: `${Math.max(18, Math.min(100, (beam.length_ft / 150) * 100))}%`, background: tone }} />
      </div>
      <div className="mt-2 flex items-center justify-between gap-3 text-xs font-mono">
        <span className="font-semibold text-white">{beam.mark}</span>
        <span className="text-muted-foreground">{beam.release_tag || `${beam.length_ft} ft`}</span>
      </div>
    </div>
  );
}

function LaneCard({ lane }) {
  const style = STATE_STYLES[lane.lane_state?.key] || STATE_STYLES.layout_strand;
  return (
    <section
      className="flex min-h-0 flex-col rounded-sm border p-4"
      style={{ borderColor: `${style.border}55`, background: `linear-gradient(180deg, ${style.glow}, rgba(10,12,16,0.82))` }}
    >
      <div className="flex items-start justify-between gap-4 border-b border-white/5 pb-3">
        <div>
          <div className="text-[11px] font-mono uppercase tracking-[0.3em] text-muted-foreground">Bed {lane.bed_number}</div>
          <div className="mt-1 font-display text-3xl font-extrabold uppercase leading-none text-white">{lane.lane_state?.label}</div>
          <div className="mt-2 text-sm text-muted-foreground">{lane.pour_number ? `Pour ${lane.pour_number}` : "No active pour"}</div>
        </div>
        <div className="rounded-sm border px-3 py-2 text-right" style={{ borderColor: `${style.border}55`, color: style.text }}>
          <div className="text-[11px] font-mono uppercase tracking-[0.24em]">{(lane.status || "idle").replace(/_/g, " ")}</div>
          <div className="mt-1 font-mono text-xl font-bold">{lane.beams.length}</div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
        <div>
          <div className="text-[11px] font-mono uppercase tracking-[0.24em] text-muted-foreground">Beam Order</div>
          <div className="mt-1 font-mono text-sm text-white">{lane.beam_order}</div>
        </div>
        <div>
          <div className="text-[11px] font-mono uppercase tracking-[0.24em] text-muted-foreground">QC Owner</div>
          <div className="mt-1 text-white">{lane.qc_owner}</div>
        </div>
        <div>
          <div className="text-[11px] font-mono uppercase tracking-[0.24em] text-muted-foreground">Est. Release</div>
          <div className="mt-1 font-mono text-white">{lane.estimated_release}</div>
        </div>
      </div>

      <div className="mt-4 grid flex-1 grid-cols-1 gap-3 xl:grid-cols-2">
        {lane.beams.map((beam) => (
          <BeamMiniTwin key={beam.id} beam={beam} />
        ))}
        {lane.beams.length === 0 && (
          <div className="col-span-full flex items-center justify-center rounded-sm border border-dashed border-border bg-black/10 p-6 text-sm font-mono text-muted-foreground">
            No beams staged on this bed
          </div>
        )}
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-white/5 pt-3 text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">
        <span>{lane.name}</span>
        <span style={{ color: lane.ncr_count ? "#FF7A9D" : "#8B949E" }}>{lane.ncr_count} open NCR</span>
      </div>
    </section>
  );
}

function AnalyticsCard({ title, value, subtitle, tone = "text-white", children }) {
  return (
    <div className="rounded-sm border border-border bg-card/80 p-4">
      <div className="text-[11px] font-mono uppercase tracking-[0.28em] text-muted-foreground">{title}</div>
      <div className={`mt-2 font-mono text-3xl font-bold ${tone}`}>{value}</div>
      {subtitle ? <div className="mt-1 text-xs text-muted-foreground">{subtitle}</div> : null}
      {children}
    </div>
  );
}

function SeverityBars({ value }) {
  const total = (value?.minor || 0) + (value?.moderate || 0) + (value?.major || 0) || 1;
  const rows = [
    ["Major", value?.major || 0, "#FF3366"],
    ["Moderate", value?.moderate || 0, "#FFD600"],
    ["Minor", value?.minor || 0, "#2979FF"],
  ];
  return (
    <div className="mt-4 space-y-3">
      {rows.map(([label, count, color]) => (
        <div key={label}>
          <div className="mb-1 flex items-center justify-between text-xs font-mono uppercase tracking-[0.22em] text-muted-foreground">
            <span>{label}</span>
            <span>{count}</span>
          </div>
          <div className="h-2 rounded-full bg-[#11151d]">
            <div className="h-full rounded-full" style={{ width: `${(count / total) * 100}%`, background: color }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function StrengthTrend({ points }) {
  return (
    <div className="mt-4 space-y-3">
      {points?.map((point) => {
        const max = Math.max(point.value || 0, point.required || 0, 1);
        return (
          <div key={point.label}>
            <div className="mb-1 flex items-center justify-between gap-3 text-xs font-mono">
              <span className="truncate text-muted-foreground">{point.label}</span>
              <span className="text-white">{point.value} / {point.required}</span>
            </div>
            <div className="relative h-3 rounded-full bg-[#11151d]">
              <div className="absolute inset-y-0 left-0 rounded-full bg-primary" style={{ width: `${(point.value / max) * 100}%` }} />
              <div className="absolute inset-y-[-2px] w-px bg-[#FFD600]" style={{ left: `${(point.required / max) * 100}%` }} />
            </div>
          </div>
        );
      })}
      {!points?.length && <div className="text-sm font-mono text-muted-foreground">No strength snapshots yet.</div>}
    </div>
  );
}

function EventTicker({ events }) {
  const content = useMemo(() => {
    const items = events?.length ? events : [{ timestamp: null, message: "Waiting for plant events" }];
    return [...items, ...items];
  }, [events]);

  return (
    <div className="command-board-ticker mt-4 flex h-16 items-center overflow-hidden rounded-sm border border-border bg-card/70 px-4">
      <div className="mr-4 flex shrink-0 items-center gap-2 text-sm font-display font-bold uppercase tracking-[0.24em] text-primary">
        <Activity className="h-4 w-4" /> Live Plant Events
      </div>
      <div className="command-board-ticker-track flex min-w-max items-center gap-8 whitespace-nowrap font-mono text-sm text-white">
        {content.map((item, index) => (
          <div key={`${item.timestamp || "pending"}-${index}`} className="flex items-center gap-3">
            <span className="text-primary">{formatEventTime(item.timestamp)}</span>
            <span>{item.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function CommandBoard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const now = useClock();

  useEffect(() => {
    let active = true;
    const load = () => {
      api.get("/command-board")
        .then((response) => {
          if (active) {
            setData(response.data);
            setLoading(false);
          }
        })
        .catch(() => {
          if (active) {
            setLoading(false);
          }
        });
    };

    load();
    const timer = setInterval(load, 15000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  if (loading && !data) {
    return (
      <div className="grain flex min-h-screen items-center justify-center bg-background text-white">
        <div className="text-center">
          <MonitorPlay className="mx-auto h-10 w-10 animate-pulse text-primary" />
          <div className="mt-4 font-display text-2xl font-bold uppercase tracking-[0.18em]">Loading command board</div>
        </div>
      </div>
    );
  }

  const summary = data?.summary || {};
  const analytics = data?.analytics || {};

  return (
    <div className="grain min-h-screen overflow-hidden bg-background px-6 py-5 text-white xl:px-8 xl:py-6">
      <div className="mx-auto flex h-[calc(100vh-3rem)] max-w-[1900px] flex-col">
        <header className="rounded-sm border border-border bg-card/80 px-5 py-4">
          <div className="flex items-center justify-between gap-6">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-sm bg-primary/20 text-primary">
                <Factory className="h-7 w-7" />
              </div>
              <div>
                <div className="text-[11px] font-mono uppercase tracking-[0.32em] text-muted-foreground">Read-only kiosk surface</div>
                <h1 className="mt-1 font-display text-4xl font-extrabold uppercase tracking-tight">{data?.plant || "BedForge Command Center"}</h1>
              </div>
            </div>
            <div className="flex items-center gap-4 text-right">
              <div>
                <div className="text-[11px] font-mono uppercase tracking-[0.32em] text-muted-foreground">Shift</div>
                <div className="mt-1 font-display text-2xl font-bold uppercase">{data?.shift || "—"}</div>
              </div>
              <div className="rounded-sm border border-border px-4 py-3">
                <div className="flex items-center justify-end gap-2 text-[11px] font-mono uppercase tracking-[0.24em] text-muted-foreground">
                  <Clock3 className="h-4 w-4" /> Plant Time
                </div>
                <div className="mt-1 font-mono text-3xl font-bold">{formatBoardTime(now)}</div>
              </div>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-3">
            <SummaryTile icon={Layers3} label="Beds Active" value={summary.beds_active ?? "—"} />
            <SummaryTile icon={Gauge} label="Beams In Process" value={summary.beams_in_process ?? "—"} />
            <SummaryTile icon={MonitorPlay} label="Releases Today" value={summary.releases_today ?? "—"} />
            <SummaryTile icon={ShieldAlert} label="Open NCRs" value={summary.open_ncrs ?? "—"} />
          </div>
        </header>

        <div className="mt-4 grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_360px] gap-4">
          <main className="grid min-h-0 grid-cols-2 gap-4">
            {(data?.lanes || []).map((lane) => (
              <LaneCard key={lane.id} lane={lane} />
            ))}
          </main>

          <aside className="flex min-h-0 flex-col gap-4 overflow-hidden rounded-sm border border-border bg-card/70 p-4">
            <div className="border-b border-white/5 pb-3">
              <div className="text-[11px] font-mono uppercase tracking-[0.32em] text-muted-foreground">Analytics rail</div>
              <div className="mt-1 font-display text-2xl font-bold uppercase">Production health</div>
            </div>
            <div className="grid gap-4 overflow-y-auto pr-1">
              <AnalyticsCard title="Releases Today" value={formatMetric(analytics.releases_today)} subtitle="Beams released this shift day" />
              <AnalyticsCard title="Layout to Release" value={formatMetric(analytics.layout_to_release_hours, "h")} subtitle="Average observed cycle time" />
              <AnalyticsCard title="Open NCRs by Severity" value={summary.open_ncrs ?? "—"} subtitle="Live nonconformance load">
                <SeverityBars value={analytics.open_ncrs_by_severity} />
              </AnalyticsCard>
              <AnalyticsCard title="Camber Pass Rate" value={formatMetric(analytics.camber_pass_rate, "%")} subtitle="Within ±0.25 in of design" tone="text-[#6BFFB0]" />
              <AnalyticsCard title="Tension Within Tolerance" value={formatMetric(analytics.tension_within_tolerance_rate, "%")} subtitle="Accepted elongation reports" tone="text-[#7EB0FF]" />
              <AnalyticsCard title="Strength Trend" value={`${analytics.strength_trend?.length || 0} pts`} subtitle="Release PSI vs required PSI">
                <StrengthTrend points={analytics.strength_trend} />
              </AnalyticsCard>
            </div>
          </aside>
        </div>

        <EventTicker events={data?.events} />
      </div>
    </div>
  );
}
