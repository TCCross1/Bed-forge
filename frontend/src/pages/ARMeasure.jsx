import React, { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, Field, inputClass, cardClass } from "../components/Layout";
import { useDevice } from "../context/DeviceContext";
import { useSync } from "../context/SyncContext";
import { nativeARPlugin } from "../lib/device";
import {
  LEVEL_TOLERANCE_IN, SAMPLE_TARGET, averagePoints, confidenceFromSamples,
  gravityPose, haptic, metrics, requestMotion, setTorch, startCamera, stopCamera,
} from "../lib/arEngine";
import { toast } from "sonner";
import { Flashlight, Loader2, ScanLine, Sparkles } from "lucide-react";

const PURPOSES = [
  { id: "tape", label: "Digital tape" },
  { id: "level", label: "Level" },
  { id: "camber", label: "Camber" },
  { id: "layout", label: "Layout" },
];

function LevelGauge({ deltaIn, level }) {
  const clamped = Math.max(-0.5, Math.min(0.5, Number(deltaIn) || 0));
  const x = ((clamped + 0.5) / 1) * 100;
  return (
    <div className="w-full max-w-[220px]">
      <div className="text-[9px] font-mono uppercase tracking-widest mb-1" style={{ color: level ? "#00E676" : "#FFD600" }}>
        Self-level {level ? "GREEN" : "WAIT"} · ±{LEVEL_TOLERANCE_IN}"
      </div>
      <div className="relative h-5 border border-[#1C2230] bg-black/70">
        <div className="absolute inset-y-0 left-1/2 w-px bg-white/40" />
        <div
          className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3 h-3 rounded-full"
          style={{
            left: `${x}%`,
            background: level ? "#00E676" : "#FFD600",
            boxShadow: level ? "0 0 10px #00E676" : "0 0 8px #FFD600",
          }}
        />
      </div>
    </div>
  );
}

function flagColor(row) {
  if (!row) return "#8B93A7";
  if (row.rescan) return "#FF3366";
  if (!row.matched) return "#FFD600";
  return "#00E676";
}

function scheduleTapePreview(timerRef, list, beamId, setCompare) {
  clearTimeout(timerRef.current);
  if (!list?.length) {
    setCompare(null);
    return;
  }
  timerRef.current = setTimeout(async () => {
    try {
      const { data } = await api.post("/ar-tape-runs/preview", {
        beam_id: beamId || null,
        shots: list.map((s, i) => ({
          station_index: s.station_index || i + 1,
          point_b: s.point_b,
          distance_ft: s.distance_ft,
          station_ft: s.distance_ft,
          delta_height_in: s.delta_height_in,
          level: s.level,
          forced: s.forced,
        })),
      });
      setCompare(data);
    } catch (err) {
      console.error("[measure] preview failed", err);
    }
  }, 280);
}

export default function ARMeasure() {
  const device = useDevice();
  const { measurements, refresh } = useSync();
  const [params] = useSearchParams();
  const [beams, setBeams] = useState([]);
  const [beds, setBeds] = useState([]);
  const [beamId, setBeamId] = useState(params.get("beam") || "");
  const [bedId, setBedId] = useState(params.get("bed") || "");
  const [purpose, setPurpose] = useState(params.get("purpose") || "tape");
  const [running, setRunning] = useState(false);
  const [torch, setTorchOn] = useState(false);
  const [pointA, setPointA] = useState(null);
  const [live, setLive] = useState(null);
  const [samples, setSamples] = useState([]);
  const [sampling, setSampling] = useState("");
  const [shots, setShots] = useState([]);
  const [compare, setCompare] = useState(null);
  const [savedRun, setSavedRun] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [engine, setEngine] = useState(device.native ? "arkit" : "gravity");
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const orientRef = useRef({ beta: 0, gamma: 0 });
  const walkRef = useRef(0);
  const sampleKind = useRef("");
  const sampleBuf = useRef([]);
  const pointARef = useRef(null);
  const shotsRef = useRef([]);
  const previewTimer = useRef(null);
  const beamIdRef = useRef(beamId);
  const native = nativeARPlugin();

  useEffect(() => {
    pointARef.current = pointA;
  }, [pointA]);

  useEffect(() => {
    shotsRef.current = shots;
  }, [shots]);

  useEffect(() => {
    beamIdRef.current = beamId;
  }, [beamId]);

  useEffect(() => {
    api.get("/beams").then((r) => {
      setBeams(r.data || []);
      setBeamId((cur) => cur || r.data?.[0]?.id || "");
    }).catch((err) => {
      console.error("[measure] beams failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load beams");
    });
    api.get("/beds").then((r) => {
      setBeds(r.data || []);
      setBedId((cur) => cur || r.data?.[0]?.id || "");
    }).catch((err) => console.error("[measure] beds failed", err));
  }, []);

  useEffect(() => {
    const onOrient = (e) => { orientRef.current = { beta: e.beta || 0, gamma: e.gamma || 0 }; };
    window.addEventListener("deviceorientation", onOrient);
    return () => window.removeEventListener("deviceorientation", onOrient);
  }, []);

  const appendShot = (shot) => {
    const next = [...shotsRef.current, shot];
    shotsRef.current = next;
    setShots(next);
    setSavedRun(null);
    scheduleTapePreview(previewTimer, next, beamIdRef.current, setCompare);
  };

  useEffect(() => {
    if (!running || native) return undefined;
    const t = setInterval(() => {
      walkRef.current += 0.04;
      const pose = gravityPose(orientRef.current, walkRef.current);
      setLive(pose);
      if (!sampleKind.current) return;
      sampleBuf.current = [...sampleBuf.current, pose];
      const pts = sampleBuf.current;
      setSamples(pts);
      if (pts.length >= SAMPLE_TARGET) {
        sampleBuf.current = [];
        const kind = sampleKind.current;
        sampleKind.current = "";
        setSampling("");
        const avg = averagePoints(pts);
        const conf = confidenceFromSamples(pts);
        if (kind === "A") {
          setPointA(avg);
          walkRef.current = 0;
          shotsRef.current = [];
          setShots([]);
          setCompare(null);
          haptic(true);
          toast.success("Origin set on the header / marked end — walk the beam");
          return;
        }
        const origin = pointARef.current || avg;
        const m = metrics(origin, avg);
        if (!m.level && kind !== "FORCE") {
          haptic(false);
          toast.error(`Off level ${m.delta_height_in > 0 ? "+" : ""}${m.delta_height_in}" — wait for the green laser line or force-snap`);
          return;
        }
        haptic(m.level);
        const shot = {
          ...m,
          point_a: origin,
          point_b: avg,
          confidence: conf,
          sample_count: pts.length,
          forced: kind === "FORCE",
          lidar: false,
          engine: "gravity",
          warning: !m.level && kind === "FORCE" ? "Force-snapped off-level" : "",
          station_index: shotsRef.current.length + 1,
        };
        const next = [...shotsRef.current, shot];
        shotsRef.current = next;
        setShots(next);
        setSavedRun(null);
        scheduleTapePreview(previewTimer, next, beamIdRef.current, setCompare);
        toast.success(`Station ${shot.station_index} · ${m.distance_ft} ft from header`);
      }
    }, 80);
    return () => clearInterval(t);
  }, [running, native]);

  const startWeb = async () => {
    await requestMotion();
    try {
      const stream = await startCamera(videoRef.current, torch);
      streamRef.current = stream;
      setEngine("gravity");
      setRunning(true);
    } catch (err) {
      console.error("[measure] camera failed", err);
      toast.error("Camera permission is required for the digital tape");
    }
  };

  const ingestNativePayload = (payload) => {
    const origin = pointARef.current || payload.point_a;
    if (!pointARef.current && payload.point_a) {
      setPointA(payload.point_a);
      pointARef.current = payload.point_a;
    }
    const m = payload.point_a && payload.point_b
      ? metrics(origin, payload.point_b)
      : {
        distance_ft: payload.distance_ft,
        delta_height_in: payload.delta_height_in,
        level: payload.level,
      };
    const shot = {
      ...m,
      point_a: origin || payload.point_a,
      point_b: payload.point_b || origin,
      confidence: payload.confidence || 0.8,
      sample_count: payload.sample_count || SAMPLE_TARGET,
      forced: Boolean(payload.forced),
      lidar: Boolean(payload.lidar),
      engine: payload.engine || "arkit",
      warning: payload.warning || "",
      station_index: shotsRef.current.length + 1,
    };
    appendShot(shot);
    toast.success(`Station ${shot.station_index} · ${shot.distance_ft} ft from header`);
  };

  const startSession = async () => {
    setSavedRun(null);
    setPointA(null);
    pointARef.current = null;
    setLive(null);
    shotsRef.current = [];
    setShots([]);
    setCompare(null);
    walkRef.current = 0;
    if (native) {
      try {
        const caps = await native.capabilities();
        setEngine(caps.lidar ? "arkit-lidar" : "arkit");
        const payload = await native.present({ beamId, purpose });
        ingestNativePayload({ ...payload, engine: payload.engine || "arkit" });
      } catch (err) {
        if (String(err?.message || err) !== "cancelled") {
          console.error("[measure] native AR failed", err);
          toast.error("ARKit session failed — using camera fallback");
          await startWeb();
        }
      }
      return;
    }
    await startWeb();
  };

  const snapNativeNext = async () => {
    if (!native) return;
    try {
      const payload = await native.present({ beamId, purpose, origin: pointARef.current });
      ingestNativePayload({ ...payload, engine: payload.engine || engine });
    } catch (err) {
      if (String(err?.message || err) !== "cancelled") {
        console.error("[measure] native next failed", err);
        toast.error("ARKit snap failed");
      }
    }
  };

  const stopSession = () => {
    setRunning(false);
    stopCamera(streamRef.current);
    streamRef.current = null;
  };

  const toggleTorch = async () => {
    const next = !torch;
    setTorchOn(next);
    if (native) {
      try { await native.setTorch({ on: next }); } catch (err) { console.error("[measure] torch", err); }
      return;
    }
    await setTorch(streamRef.current, next);
  };

  const snap = (kind) => {
    sampleKind.current = kind;
    sampleBuf.current = [];
    setSamples([]);
    setSampling(kind);
  };

  const dropShot = (index) => {
    const next = shotsRef.current.filter((_, i) => i !== index).map((s, i) => ({ ...s, station_index: i + 1 }));
    shotsRef.current = next;
    setShots(next);
    scheduleTapePreview(previewTimer, next, beamIdRef.current, setCompare);
    toast.message("Station dropped — walk back and snap it again on green");
  };

  const liveMetrics = pointA && live ? metrics(pointA, live) : null;
  const green = Boolean(liveMetrics?.level);

  const finishRun = async () => {
    if (!shotsRef.current.length) {
      toast.error("Snap at least one station after the origin");
      return;
    }
    setBusy("save");
    try {
      stopSession();
      const { data } = await api.post("/ar-tape-runs", {
        beam_id: beamId || null,
        bed_id: bedId || null,
        purpose: purpose || "tape",
        origin_label: "header",
        point_a: pointARef.current || shotsRef.current[0]?.point_a,
        shots: shotsRef.current.map((s, i) => ({
          station_index: s.station_index || i + 1,
          point_b: s.point_b,
          distance_ft: s.distance_ft,
          station_ft: s.distance_ft,
          delta_height_in: s.delta_height_in,
          level: s.level,
          forced: s.forced,
          confidence: s.confidence,
          sample_count: s.sample_count || SAMPLE_TARGET,
          warning: s.warning || "",
        })),
        engine: shotsRef.current[0]?.engine || engine,
        device_class: device.field ? "field" : "command",
        device_model: device.model,
        lidar: Boolean(shotsRef.current[0]?.lidar),
        note,
      });
      setSavedRun(data);
      setCompare(data.compare || compare);
      toast.success(data.compare?.rescan_count ? "Run saved — AI flagged stations to rescan" : "Tape run saved and matched to the twin");
      refresh?.();
    } catch (err) {
      console.error("[measure] finish run failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to save tape run");
    } finally {
      setBusy("");
    }
  };

  const matchFor = (shot) => (compare?.matches || []).find((m) => m.station_index === shot.station_index);
  const history = measurements.filter((m) => !beamId || m.beam_id === beamId);
  const statusLine = savedRun
    ? `SAVED · ${savedRun.shot_count} pts · ${savedRun.compare?.rescan_count || 0} rescan`
    : liveMetrics
      ? `${green ? "LEVEL — SNAP" : "WALK"} · ${liveMetrics.distance_ft} ft · Δ${liveMetrics.delta_height_in}"`
      : running
        ? (pointA ? "WALK THE BEAM — SNAP ON GREEN" : "AIM AT THE HEADER / MARKED END")
        : "START DIGITAL TAPE";

  return (
    <Layout>
      <PageHeader
        title="Digital tape measure"
        subtitle="One QC tech. Flashlight + self-level. Plot the header, walk, snap on green. Multi-point vs the twin."
      />
      <div className="p-4 sm:p-6 lg:p-8 grid grid-cols-1 xl:grid-cols-[1.2fr_380px] gap-4">
        <div className={`${cardClass} overflow-hidden`}>
          <div className="relative bg-black min-h-[420px] sm:min-h-[560px]" data-testid="ar-viewport">
            <video ref={videoRef} className="absolute inset-0 w-full h-full object-cover" playsInline muted autoPlay />
            <div className="absolute inset-0 pointer-events-none" style={{ background: green ? "rgba(0,230,118,0.16)" : "transparent" }} />
            <div
              className="absolute left-0 right-0 top-[42%] h-[2px] pointer-events-none"
              style={{
                background: green ? "#00E676" : "#2979FF",
                boxShadow: green ? "0 0 18px #00E676" : "0 0 10px #2979FF",
                opacity: running || shots.length ? 1 : 0.35,
              }}
              data-testid="ar-laser-line"
            />
            <div
              className="absolute left-1/2 top-[42%] -translate-x-1/2 -translate-y-1/2 w-7 h-7 border-[3px] pointer-events-none"
              style={{ borderColor: green ? "#00E676" : "#2979FF" }}
            />
            <div className="absolute top-3 left-3 right-3 space-y-2 pointer-events-none">
              <div className="font-mono text-lg sm:text-2xl font-bold" style={{ color: green ? "#00E676" : "#FFFFFF" }}>
                {statusLine}
              </div>
              <div className="text-[10px] font-mono text-muted-foreground">
                {engine.toUpperCase()} · level ±{LEVEL_TOLERANCE_IN}" · {shots.length} station{shots.length === 1 ? "" : "s"}
                {sampling ? ` · sampling ${samples.length}/${SAMPLE_TARGET}` : ""}
              </div>
              {(running || liveMetrics) && (
                <LevelGauge deltaIn={liveMetrics?.delta_height_in || 0} level={green} />
              )}
              <div className="h-2 bg-white/10">
                <div className="h-2 bg-[#00E676]" style={{ width: `${Math.round((sampling ? samples.length / SAMPLE_TARGET : (shots[shots.length - 1]?.confidence || 0.2)) * 100)}%` }} />
              </div>
            </div>
            <div className="absolute bottom-3 left-3 right-3 grid grid-cols-2 sm:grid-cols-4 gap-2 pointer-events-auto">
              {!running && !shots.length && (
                <button type="button" data-testid="ar-start" onClick={startSession} className="col-span-2 sm:col-span-4 min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest">
                  <ScanLine className="w-5 h-5 inline mr-2" /> Start digital tape
                </button>
              )}
              {running && (
                <>
                  <button type="button" onClick={toggleTorch} className="min-h-14 border border-[#1C2230] bg-[#0F1218]/90 font-mono text-xs uppercase" data-testid="ar-torch">
                    <Flashlight className="w-4 h-4 inline mr-1" /> {torch ? "Light on" : "Flashlight"}
                  </button>
                  <button type="button" data-testid="ar-set-a" onClick={() => snap("A")} className="min-h-14 bg-[#2979FF] text-white font-display font-bold uppercase">
                    {pointA ? "Reset origin" : "Set origin"}
                  </button>
                  <button type="button" data-testid="ar-set-b" disabled={!pointA} onClick={() => snap("B")} className="min-h-14 bg-[#00E676] text-black font-display font-bold uppercase disabled:opacity-40">
                    Snap station
                  </button>
                  <button type="button" data-testid="ar-force" disabled={!pointA} onClick={() => snap("FORCE")} className="min-h-14 bg-[#FFD600] text-black font-display font-bold uppercase disabled:opacity-40">
                    Force
                  </button>
                  <button type="button" data-testid="ar-finish" disabled={!shots.length || busy === "save"} onClick={finishRun} className="col-span-2 min-h-12 bg-white text-black font-display font-bold uppercase disabled:opacity-40">
                    {busy === "save" ? <Loader2 className="w-4 h-4 animate-spin inline" /> : "Finish run"}
                  </button>
                  <button type="button" data-testid="ar-stop" onClick={stopSession} className="col-span-2 min-h-12 border border-[#1C2230] bg-[#0F1218]/90 font-mono text-xs uppercase">
                    End camera
                  </button>
                </>
              )}
              {!running && native && shots.length > 0 && !savedRun && (
                <>
                  <button type="button" onClick={snapNativeNext} className="col-span-2 min-h-14 bg-[#00E676] text-black font-display font-bold uppercase">
                    Snap next
                  </button>
                  <button type="button" data-testid="ar-finish-native" disabled={busy === "save"} onClick={finishRun} className="col-span-2 min-h-14 bg-white text-black font-display font-bold uppercase">
                    Finish run
                  </button>
                </>
              )}
              {!running && shots.length > 0 && (
                <button type="button" onClick={startSession} className="col-span-2 sm:col-span-4 min-h-14 border border-primary text-primary font-display font-bold uppercase">
                  New run
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className={`${cardClass} p-4 space-y-3`}>
            <Field label="Beam">
              <select data-testid="ar-beam" className={inputClass} value={beamId} onChange={(e) => { setBeamId(e.target.value); scheduleTapePreview(previewTimer, shotsRef.current, e.target.value, setCompare); }}>
                {beams.map((b) => <option key={b.id} value={b.id}>{b.mark}</option>)}
              </select>
            </Field>
            <Field label="Bed">
              <select data-testid="ar-bed" className={inputClass} value={bedId} onChange={(e) => setBedId(e.target.value)}>
                {beds.map((b) => <option key={b.id} value={b.id}>Bed {b.bed_number}</option>)}
              </select>
            </Field>
            <Field label="Purpose">
              <select className={inputClass} value={purpose} onChange={(e) => setPurpose(e.target.value)}>
                {PURPOSES.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
              </select>
            </Field>
            <Field label="Run note">
              <textarea className={`${inputClass} py-2`} rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Header / line / pour notes" />
            </Field>
            {beamId && (
              <Link to={`/twin?beam=${beamId}`} className="min-h-12 px-3 border border-[#1C2230] flex items-center justify-center font-semibold uppercase tracking-wider text-xs hover:border-primary hover:text-primary">
                Open 3D twin / blueprints
              </Link>
            )}
            {!running && shots.length > 0 && !savedRun && (
              <button type="button" data-testid="ar-save" onClick={finishRun} disabled={busy === "save"} className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest disabled:opacity-60">
                {busy === "save" ? <Loader2 className="w-4 h-4 animate-spin inline" /> : "Save run + AI compare"}
              </button>
            )}
          </div>

          <div className={`${cardClass} p-4`} data-testid="ar-tape-list">
            <div className="font-display font-bold uppercase tracking-wider mb-1">Multi-point run</div>
            <div className="text-[10px] font-mono text-muted-foreground mb-3">Origin = header / marked end. Each green snap is a station from that origin.</div>
            {!shots.length && <div className="text-xs font-mono text-muted-foreground">No stations yet. Plot the first point on the line, walk, snap when the laser is green.</div>}
            {shots.map((s, i) => {
              const row = matchFor(s);
              return (
                <div key={`${s.station_index}-${i}`} className="border-b border-[#1C2230] py-2 flex items-start justify-between gap-2">
                  <div className="font-mono text-[11px]">
                    <div style={{ color: flagColor(row) }}>
                      #{s.station_index} · {s.distance_ft} ft · Δ{s.delta_height_in}" · {s.level ? "LEVEL" : "OFF"}
                      {s.forced ? " · FORCED" : ""}
                    </div>
                    <div className="text-muted-foreground">
                      {row?.matched
                        ? `${row.element_name} · design ${row.design_station_ft}' · Δ${row.delta_in}" / ±${row.tolerance_in}"`
                        : row
                          ? "No twin match nearby"
                          : "Waiting for twin compare"}
                    </div>
                  </div>
                  {!savedRun && (
                    <button type="button" data-testid={`ar-rescan-${i}`} onClick={() => dropShot(i)} className="shrink-0 min-h-10 px-2 border border-[#1C2230] font-mono text-[10px] uppercase hover:border-[#FF3366] hover:text-[#FF3366]">
                      Rescan
                    </button>
                  )}
                </div>
              );
            })}
          </div>

          {compare?.ai && (
            <div className={`${cardClass} p-4 space-y-2`} data-testid="ar-ai-summary" style={{ borderColor: compare.rescan_count ? "#FF3366" : "#1C2230" }}>
              <div className="font-display font-bold uppercase tracking-wider flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-[#C9A227]" /> AI vs twin / blueprints
              </div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-[#C9A227]">
                {compare.ai.source === "llm" ? "Assistant review" : "Local matcher"} · {compare.pass_count || 0} pass · {compare.rescan_count || 0} rescan
              </div>
              <p className="text-sm leading-relaxed text-[#D5D9E2]">{compare.ai.summary}</p>
              {(compare.ai.notes || []).map((n) => (
                <div key={n} className="text-xs font-mono text-muted-foreground">· {n}</div>
              ))}
              {(compare.unshot || []).slice(0, 8).map((u) => (
                <div key={u.id} className="text-[11px] font-mono" style={{ color: "#FFD600" }}>
                  Not shot · {u.name} @ {u.station_ft}'
                </div>
              ))}
            </div>
          )}

          <div className={`${cardClass} p-4`} data-testid="ar-history">
            <div className="font-display font-bold uppercase tracking-wider mb-3">Live history</div>
            {history.slice(0, 8).map((m) => (
              <div key={m.id} className="border-b border-[#1C2230] py-2 font-mono text-[11px]">
                <span style={{ color: m.level ? "#00E676" : "#FF3366" }}>{m.level ? "LEVEL" : "OFF"}</span>
                {" · "}{m.distance_ft} ft · Δ{m.delta_height_in}" · {m.engine}
                {m.station_index ? ` · #${m.station_index}` : ""}
              </div>
            ))}
            {history.length === 0 && <div className="text-xs font-mono text-muted-foreground">No AR shots yet. They appear here on iPad/Mac the moment a tech saves a run.</div>}
          </div>
        </div>
      </div>
    </Layout>
  );
}
