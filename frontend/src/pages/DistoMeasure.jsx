import React, { useEffect, useMemo, useRef, useState } from "react";
import { Bluetooth, Keyboard, Loader2, Ruler } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, Field, inputClass, cardClass } from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import { useOpenJob } from "../context/OpenJobContext";
import {
  connectDisto,
  isIosDevice,
  isWebBluetoothAvailable,
  parseDistanceToInches,
  startKeyboardWedge,
} from "../lib/distoBluetooth";
import { canSeeJobsCabinet, jobListParams } from "../lib/jobAccess";
import { pickBeamId, useBeamQuery } from "../lib/useBeamQuery";

const PURPOSES = [
  { id: "length", label: "Length" },
  { id: "width", label: "Width" },
  { id: "depth", label: "Depth" },
  { id: "layout", label: "Layout station" },
  { id: "other", label: "Other" },
];

function statusColor(status) {
  if (status === "override") return "#C9A227";
  if (status === "fail") return "#FF3366";
  if (status === "pass") return "#00E676";
  return "#8B93A7";
}

function inchesLabel(value) {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${n.toFixed(3)} in`;
}

function targetFromBeam(beam, purpose) {
  if (!beam) return "";
  if (purpose === "length") {
    const ft = Number(beam.length_ft || beam.beam_spec?.geometry?.length_ft);
    return Number.isFinite(ft) ? String(Math.round(ft * 12 * 1000) / 1000) : "";
  }
  if (purpose === "depth") {
    const depth = Number(beam.product_type?.depth_in || beam.beam_spec?.geometry?.depth_in);
    return Number.isFinite(depth) ? String(depth) : "";
  }
  if (purpose === "width") {
    const width = Number(beam.product_type?.width_in || beam.beam_spec?.geometry?.width_in);
    return Number.isFinite(width) ? String(width) : "";
  }
  return "";
}

export default function DistoMeasure() {
  const { user } = useAuth();
  const { openJob } = useOpenJob();
  const queryBeam = useBeamQuery();
  const canOverride = canSeeJobsCabinet(user?.role) || user?.role === "qc_supervisor";
  const bluetoothOk = isWebBluetoothAvailable();
  const ios = isIosDevice();
  const [beams, setBeams] = useState([]);
  const [beamId, setBeamId] = useState(queryBeam);
  const [purpose, setPurpose] = useState("length");
  const [station, setStation] = useState("");
  const [measured, setMeasured] = useState("");
  const [target, setTarget] = useState("");
  const [tolerance, setTolerance] = useState("0.125");
  const [preview, setPreview] = useState(null);
  const [history, setHistory] = useState([]);
  const [saving, setSaving] = useState(false);
  const [btStatus, setBtStatus] = useState(bluetoothOk ? "idle" : "unavailable");
  const [deviceName, setDeviceName] = useState("");
  const [wedgeBuffer, setWedgeBuffer] = useState("");
  const [overrideId, setOverrideId] = useState("");
  const [overrideNote, setOverrideNote] = useState("");
  const disconnectRef = useRef(null);
  const sourceRef = useRef("manual");

  const beam = useMemo(() => beams.find((row) => row.id === beamId) || null, [beams, beamId]);

  useEffect(() => {
    let cancelled = false;
    api.get("/beams", { params: jobListParams(openJob) })
      .then((res) => {
        if (cancelled) return;
        setBeams(res.data || []);
        setBeamId((current) => pickBeamId(current, queryBeam, res.data || []));
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[disto] beams load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load beams");
      });
    return () => {
      cancelled = true;
    };
  }, [queryBeam, openJob?.id]);

  useEffect(() => {
    setTarget(targetFromBeam(beam, purpose));
  }, [beam, purpose]);

  useEffect(() => {
    let cancelled = false;
    const params = { ...(jobListParams(openJob) || {}) };
    if (beamId) params.beam_id = beamId;
    api.get("/instrument-readings", { params })
      .then((res) => {
        if (!cancelled) setHistory(res.data || []);
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[disto] history load failed", err);
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load DISTO readings");
      });
    return () => {
      cancelled = true;
    };
  }, [beamId, openJob?.id]);

  useEffect(() => {
    const stop = startKeyboardWedge({
      onReading: (shot) => {
        sourceRef.current = shot.source;
        setDeviceName(shot.device_name || "DISTO keyboard");
        setMeasured(String(Math.round(shot.measured_in * 1000) / 1000));
        toast.success(`Keyboard capture ${inchesLabel(shot.measured_in)}`);
      },
      onBuffer: setWedgeBuffer,
    });
    return stop;
  }, []);

  useEffect(() => () => {
    if (disconnectRef.current) disconnectRef.current();
  }, []);

  useEffect(() => {
    const measuredN = Number(measured);
    if (!Number.isFinite(measuredN)) {
      setPreview(null);
      return undefined;
    }
    let cancelled = false;
    api.post("/instrument-readings/evaluate", {
      measured_in: measuredN,
      target_in: target === "" ? null : Number(target),
      tolerance_in: Number(tolerance) || 0.125,
    })
      .then((res) => {
        if (!cancelled) setPreview(res.data);
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[disto] evaluate failed", err);
      });
    return () => {
      cancelled = true;
    };
  }, [measured, target, tolerance]);

  const connect = async () => {
    try {
      setBtStatus("connecting");
      const session = await connectDisto({
        onReading: (shot) => {
          sourceRef.current = "bluetooth";
          setDeviceName(shot.device_name || "DISTO");
          setMeasured(String(Math.round(shot.measured_in * 1000) / 1000));
          toast.success(`DISTO ${inchesLabel(shot.measured_in)}`);
        },
        onStatus: (kind, detail) => {
          setBtStatus(kind);
          if (detail) setDeviceName(detail);
        },
      });
      disconnectRef.current = session.disconnect;
    } catch (err) {
      console.error("[disto] bluetooth connect failed", err);
      setBtStatus("idle");
      toast.error(err.message || "Could not connect to DISTO");
    }
  };

  const save = async () => {
    const measuredN = Number(measured);
    if (!Number.isFinite(measuredN)) {
      toast.error("Capture or type a DISTO reading first");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post("/instrument-readings", {
        job_id: openJob?.id || null,
        beam_id: beamId || null,
        station,
        purpose,
        source: sourceRef.current || "manual",
        device_name: deviceName,
        measured_in: measuredN,
        target_in: target === "" ? null : Number(target),
        tolerance_in: Number(tolerance) || 0.125,
      });
      setHistory((rows) => [data, ...rows]);
      toast.success(data.status === "pass" ? "Reading saved — within tolerance" : "Reading saved — outside tolerance");
    } catch (err) {
      console.error("[disto] save failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to save reading");
    } finally {
      setSaving(false);
    }
  };

  const applyOverride = async () => {
    if (!overrideId) return;
    if ((overrideNote || "").trim().length < 8) {
      toast.error("Override note must explain the gate (8+ characters)");
      return;
    }
    try {
      const { data } = await api.post(`/instrument-readings/${overrideId}/override`, { note: overrideNote.trim() });
      setHistory((rows) => rows.map((row) => (row.id === data.id ? data : row)));
      setOverrideId("");
      setOverrideNote("");
      toast.success("Supervisor override recorded");
    } catch (err) {
      console.error("[disto] override failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Override failed");
    }
  };

  const applyTyped = (value) => {
    const inches = parseDistanceToInches(value);
    if (inches == null) {
      setMeasured(value);
      return;
    }
    sourceRef.current = "manual";
    setMeasured(String(Math.round(inches * 1000) / 1000));
  };

  return (
    <Layout>
      <PageHeader
        title="DISTO / LDM"
        subtitle="Leica laser or iPhone keyboard wedge — evaluate against the open-job spec, never invent a length."
        right={(
          <div className="flex items-center gap-2">
            <div className="hidden sm:block text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
              {ios ? "iOS keyboard mode" : bluetoothOk ? "Web Bluetooth ready" : "Manual / keyboard"}
            </div>
          </div>
        )}
      />
      <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-6xl">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <section className={`${cardClass} p-5 lg:col-span-2 relative overflow-hidden`}>
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(0,229,255,0.12),transparent_42%)]" />
            <div className="relative space-y-4">
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  data-testid="disto-bluetooth"
                  disabled={!bluetoothOk}
                  onClick={connect}
                  className="min-h-12 px-4 border border-primary/50 bg-primary/10 text-primary font-semibold uppercase tracking-wider flex items-center gap-2 disabled:opacity-40"
                >
                  <Bluetooth className="w-4 h-4" />
                  {btStatus === "connected" ? `Live · ${deviceName}` : "Connect DISTO"}
                </button>
                <div className="min-h-12 px-4 border border-[#C9A227]/40 text-[#C9A227] font-semibold uppercase tracking-wider flex items-center gap-2">
                  <Keyboard className="w-4 h-4" />
                  Keyboard wedge {wedgeBuffer ? `· ${wedgeBuffer}` : "listening"}
                </div>
              </div>
              <p className="text-sm text-muted-foreground">
                Chrome/Edge can pair a Leica DISTO over Bluetooth. iPhone Safari has no Web Bluetooth — put the DISTO in keyboard mode and fire the laser; BedForge captures the typed distance.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Field label="Beam">
                  <select className={inputClass} value={beamId} onChange={(e) => setBeamId(e.target.value)} data-testid="disto-beam">
                    <option value="">Select mark</option>
                    {beams.map((row) => (
                      <option key={row.id} value={row.id}>{row.mark}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Purpose">
                  <select className={inputClass} value={purpose} onChange={(e) => setPurpose(e.target.value)}>
                    {PURPOSES.map((row) => (
                      <option key={row.id} value={row.id}>{row.label}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Station / note">
                  <input className={inputClass} value={station} onChange={(e) => setStation(e.target.value)} placeholder="ME, midspan, UE…" />
                </Field>
                <Field label="Tolerance (in)">
                  <input className={inputClass} value={tolerance} onChange={(e) => setTolerance(e.target.value)} />
                </Field>
                <Field label="Measured (in)">
                  <input
                    className={inputClass}
                    data-testid="disto-measured"
                    data-disto-wedge="true"
                    value={measured}
                    onChange={(e) => applyTyped(e.target.value)}
                    placeholder="12.345 m or 47 ft 3 in"
                  />
                </Field>
                <Field label="Spec target (in)">
                  <input className={inputClass} value={target} onChange={(e) => setTarget(e.target.value)} placeholder="From Spec DNA when known" />
                </Field>
              </div>
              <div
                className="min-h-24 border border-[#1C2230] bg-black/50 px-4 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
                data-testid="disto-preview"
              >
                <div>
                  <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-muted-foreground">Gate</div>
                  <div className="font-display font-extrabold text-2xl uppercase" style={{ color: statusColor(preview?.status) }}>
                    {preview?.status || "waiting"}
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-4 text-sm font-mono">
                  <div>
                    <div className="text-muted-foreground uppercase text-[10px]">Delta</div>
                    <div>{inchesLabel(preview?.delta_in)}</div>
                  </div>
                  <div>
                    <div className="text-muted-foreground uppercase text-[10px]">Low</div>
                    <div>{inchesLabel(preview?.lower_bound_in)}</div>
                  </div>
                  <div>
                    <div className="text-muted-foreground uppercase text-[10px]">High</div>
                    <div>{inchesLabel(preview?.upper_bound_in)}</div>
                  </div>
                </div>
              </div>
              <button
                type="button"
                data-testid="disto-save"
                disabled={saving}
                onClick={save}
                className="min-h-12 px-6 bg-primary text-black font-display font-bold uppercase tracking-widest flex items-center gap-2"
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Ruler className="w-4 h-4" />}
                Save reading
              </button>
            </div>
          </section>
          <section className={`${cardClass} p-5`}>
            <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-[#C9A227] mb-3">Open job</div>
            <div className="font-display font-bold uppercase tracking-wider text-lg">{openJob?.job_number || "No open job"}</div>
            <div className="text-sm text-muted-foreground mt-1">{beam?.mark ? `Mark ${beam.mark}` : "Select a mark"}</div>
            <div className="mt-4 text-xs text-muted-foreground leading-relaxed">
              Spec target fills from JOB Specs when the print gave a length/depth/width. Empty target = capture only, not a invented dimension.
            </div>
          </section>
        </div>

        <section className={`${cardClass} overflow-x-auto`}>
          <div className="px-4 py-3 border-b border-[#1C2230] text-[10px] font-mono uppercase tracking-[0.25em] text-muted-foreground">Saved shots</div>
          <table className="w-full text-sm" data-testid="disto-history">
            <thead>
              <tr className="text-left text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                <th className="px-4 py-3">Mark / station</th>
                <th className="px-4 py-3">Measured</th>
                <th className="px-4 py-3">Target</th>
                <th className="px-4 py-3">Gate</th>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {history.map((row) => (
                <tr key={row.id} className="border-t border-[#1C2230]">
                  <td className="px-4 py-3">{row.station || row.beam_id || "—"}</td>
                  <td className="px-4 py-3 font-mono">{inchesLabel(row.measured_in)}</td>
                  <td className="px-4 py-3 font-mono">{inchesLabel(row.target_in)}</td>
                  <td className="px-4 py-3 font-display uppercase" style={{ color: statusColor(row.status) }}>{row.status}</td>
                  <td className="px-4 py-3 text-muted-foreground">{row.source} {row.device_name ? `· ${row.device_name}` : ""}</td>
                  <td className="px-4 py-3">
                    {canOverride && row.status === "fail" && (
                      <button type="button" className="text-[#C9A227] uppercase tracking-wider text-xs" onClick={() => setOverrideId(row.id)}>
                        Override
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {!history.length && (
                <tr>
                  <td className="px-4 py-6 text-muted-foreground" colSpan={6}>No DISTO shots on this mark yet.</td>
                </tr>
              )}
            </tbody>
          </table>
          {overrideId && (
            <div className="p-4 border-t border-[#1C2230] space-y-3">
              <Field label="Supervisor override note">
                <input className={inputClass} value={overrideNote} onChange={(e) => setOverrideNote(e.target.value)} placeholder="Why this laser shot is accepted" />
              </Field>
              <button type="button" onClick={applyOverride} className="min-h-12 px-4 border border-[#C9A227] text-[#C9A227] uppercase tracking-wider">
                Record override
              </button>
            </div>
          )}
        </section>
      </div>
    </Layout>
  );
}
