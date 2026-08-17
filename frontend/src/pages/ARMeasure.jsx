import React, { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
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
import { Flashlight, Loader2, ScanLine } from "lucide-react";

const PURPOSES = [
  { id: "level", label: "Level" },
  { id: "camber", label: "Camber" },
  { id: "layout", label: "Layout" },
];

export default function ARMeasure() {
  const device = useDevice();
  const { measurements, refresh } = useSync();
  const [params] = useSearchParams();
  const [beams, setBeams] = useState([]);
  const [beds, setBeds] = useState([]);
  const [beamId, setBeamId] = useState(params.get("beam") || "");
  const [bedId, setBedId] = useState(params.get("bed") || "");
  const [purpose, setPurpose] = useState(params.get("purpose") || "level");
  const [running, setRunning] = useState(false);
  const [torch, setTorchOn] = useState(false);
  const [pointA, setPointA] = useState(null);
  const [live, setLive] = useState(null);
  const [samples, setSamples] = useState([]);
  const [sampling, setSampling] = useState("");
  const [result, setResult] = useState(null);
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
  const native = nativeARPlugin();

  useEffect(() => {
    pointARef.current = pointA;
  }, [pointA]);

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
          haptic(true);
          toast.success("Point A set — walk the line");
          return;
        }
        const origin = pointARef.current || avg;
        const m = metrics(origin, avg);
        if (!m.level && kind !== "FORCE") {
          haptic(false);
          toast.error(`Off level ${m.delta_height_in > 0 ? "+" : ""}${m.delta_height_in}" — wait for green or force-snap`);
          return;
        }
        haptic(m.level);
        setResult({
          ...m,
          point_a: origin,
          point_b: avg,
          confidence: conf,
          sample_count: pts.length,
          forced: kind === "FORCE",
          lidar: false,
          engine: "gravity",
          warning: !m.level && kind === "FORCE" ? "Force-snapped off-level" : "",
        });
        setRunning(false);
        stopCamera(streamRef.current);
        streamRef.current = null;
      }
    }, 80);
    return () => clearInterval(t);
  }, [running, native]);

  const startSession = async () => {
    setResult(null);
    setPointA(null);
    setLive(null);
    walkRef.current = 0;
    if (native) {
      try {
        const caps = await native.capabilities();
        setEngine(caps.lidar ? "arkit-lidar" : "arkit");
        const payload = await native.present({ beamId, purpose });
        setResult({ ...payload, engine: payload.engine || "arkit" });
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

  const startWeb = async () => {
    await requestMotion();
    try {
      const stream = await startCamera(videoRef.current, torch);
      streamRef.current = stream;
      setEngine("gravity");
      setRunning(true);
    } catch (err) {
      console.error("[measure] camera failed", err);
      toast.error("Camera permission is required for AR Measure");
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

  const liveMetrics = pointA && live ? metrics(pointA, live) : null;
  const green = Boolean(liveMetrics?.level);

  const save = async () => {
    if (!result) return;
    setBusy("save");
    try {
      await api.post("/ar-measurements", {
        beam_id: beamId || null,
        bed_id: bedId || null,
        purpose,
        point_a: result.point_a,
        point_b: result.point_b,
        distance_ft: result.distance_ft,
        delta_height_in: result.delta_height_in,
        level: result.level,
        forced: result.forced,
        confidence: result.confidence,
        sample_count: result.sample_count || SAMPLE_TARGET,
        lidar: Boolean(result.lidar),
        engine: result.engine || engine,
        device_class: device.field ? "field" : "command",
        device_model: device.model,
        warning: result.warning || "",
        note,
      });
      toast.success("Measurement synced to plant");
      setResult(null);
      setNote("");
      refresh?.();
    } catch (err) {
      console.error("[measure] save failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to save measurement");
    } finally {
      setBusy("");
    }
  };

  const history = measurements.filter((m) => !beamId || m.beam_id === beamId);

  return (
    <Layout>
      <PageHeader
        title="AR Level Measure"
        subtitle="Point A → walk the line → green + vibe when level → snap B"
      />
      <div className="p-4 sm:p-6 lg:p-8 grid grid-cols-1 xl:grid-cols-[1.2fr_360px] gap-4">
        <div className={`${cardClass} overflow-hidden`}>
          <div className="relative bg-black min-h-[420px] sm:min-h-[560px]" data-testid="ar-viewport">
            <video ref={videoRef} className="absolute inset-0 w-full h-full object-cover" playsInline muted autoPlay />
            <div className="absolute inset-0 pointer-events-none" style={{ background: green ? "rgba(0,230,118,0.18)" : "transparent" }} />
            <div
              className="absolute left-1/2 top-[42%] -translate-x-1/2 -translate-y-1/2 w-7 h-7 border-[3px]"
              style={{ borderColor: green ? "#00E676" : "#2979FF" }}
            />
            <div className="absolute top-3 left-3 right-3 space-y-2">
              <div className="font-mono text-lg sm:text-2xl font-bold" style={{ color: green ? "#00E676" : "#FFFFFF" }}>
                {result
                  ? `${result.level ? "LEVEL" : "OFF LEVEL"} · ${result.distance_ft} ft · Δ${result.delta_height_in}"`
                  : liveMetrics
                    ? `${green ? "LEVEL" : "WALK"} · ${liveMetrics.distance_ft} ft · Δ${liveMetrics.delta_height_in}"`
                    : running
                      ? (pointA ? "WALK TO POINT B" : "AIM POINT A")
                      : "START SESSION"}
              </div>
              <div className="text-[10px] font-mono text-muted-foreground">
                {engine.toUpperCase()} · tol ±{LEVEL_TOLERANCE_IN}" · conf {Math.round((liveMetrics ? 0.55 : result?.confidence || 0.2) * 100)}%
                {sampling ? ` · sampling ${samples.length}/${SAMPLE_TARGET}` : ""}
              </div>
              <div className="h-2 bg-white/10">
                <div className="h-2 bg-[#00E676]" style={{ width: `${Math.round((result?.confidence || (sampling ? samples.length / SAMPLE_TARGET : 0.2)) * 100)}%` }} />
              </div>
            </div>
            <div className="absolute bottom-3 left-3 right-3 grid grid-cols-2 sm:grid-cols-4 gap-2 pointer-events-auto">
              {!running && !result && (
                <button type="button" data-testid="ar-start" onClick={startSession} className="col-span-2 sm:col-span-4 min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest">
                  <ScanLine className="w-5 h-5 inline mr-2" /> Start AR
                </button>
              )}
              {running && (
                <>
                  <button type="button" onClick={toggleTorch} className="min-h-14 border border-[#1C2230] bg-[#0F1218]/90 font-mono text-xs uppercase">
                    <Flashlight className="w-4 h-4 inline mr-1" /> {torch ? "Light on" : "Light"}
                  </button>
                  <button type="button" data-testid="ar-set-a" onClick={() => snap("A")} className="min-h-14 bg-[#2979FF] text-white font-display font-bold uppercase">
                    {pointA ? "Reset A" : "Set A"}
                  </button>
                  <button type="button" data-testid="ar-set-b" disabled={!pointA} onClick={() => snap("B")} className="min-h-14 bg-[#00E676] text-black font-display font-bold uppercase disabled:opacity-40">
                    Set B
                  </button>
                  <button type="button" data-testid="ar-force" disabled={!pointA} onClick={() => snap("FORCE")} className="min-h-14 bg-[#FFD600] text-black font-display font-bold uppercase disabled:opacity-40">
                    Force
                  </button>
                  <button type="button" data-testid="ar-stop" onClick={stopSession} className="col-span-2 sm:col-span-4 min-h-12 border border-[#1C2230] bg-[#0F1218]/90 font-mono text-xs uppercase">
                    End session
                  </button>
                </>
              )}
              {result && !running && (
                <button type="button" onClick={() => { setResult(null); startSession(); }} className="col-span-2 sm:col-span-4 min-h-14 border border-primary text-primary font-display font-bold uppercase">
                  New shot
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className={`${cardClass} p-4 space-y-3`}>
            <Field label="Beam">
              <select data-testid="ar-beam" className={inputClass} value={beamId} onChange={(e) => setBeamId(e.target.value)}>
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
            {result && (
              <>
                <div className="font-mono text-sm" style={{ color: result.level ? "#00E676" : "#FF3366" }}>
                  {result.distance_ft} ft · Δ {result.delta_height_in}" · {result.level ? "LEVEL" : "OFF"}{result.forced ? " · FORCED" : ""}
                </div>
                <Field label="Note">
                  <textarea className={`${inputClass} py-2`} rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
                </Field>
                <button type="button" data-testid="ar-save" onClick={save} disabled={busy === "save"} className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest disabled:opacity-60">
                  {busy === "save" ? <Loader2 className="w-4 h-4 animate-spin inline" /> : "Save to beam"}
                </button>
              </>
            )}
          </div>
          <div className={`${cardClass} p-4`} data-testid="ar-history">
            <div className="font-display font-bold uppercase tracking-wider mb-3">Live history</div>
            {history.slice(0, 8).map((m) => (
              <div key={m.id} className="border-b border-[#1C2230] py-2 font-mono text-[11px]">
                <span style={{ color: m.level ? "#00E676" : "#FF3366" }}>{m.level ? "LEVEL" : "OFF"}</span>
                {" · "}{m.distance_ft} ft · Δ{m.delta_height_in}" · {m.engine}
              </div>
            ))}
            {history.length === 0 && <div className="text-xs font-mono text-muted-foreground">No AR shots yet. They appear here on iPad/Mac the moment a tech saves.</div>}
          </div>
        </div>
      </div>
    </Layout>
  );
}
