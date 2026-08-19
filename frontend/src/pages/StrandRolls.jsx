import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Flashlight, Loader2, Plus, ScanBarcode, Camera, CheckCircle2, Upload } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../lib/api";
import Layout, { PageHeader, Field, inputClass, cardClass } from "../components/Layout";
import { startCamera, stopCamera, setTorch } from "../lib/arEngine";
import {
  ROLL_FIELDS, dataUrlToFile, dequeueRollJob, enqueueRollJob, isLowConfidence,
  loadQueue,
} from "../lib/strandRolls";
import { useDevice } from "../context/DeviceContext";

function emptyForm() {
  return Object.fromEntries(ROLL_FIELDS.map((f) => [f.key, ""]));
}

function formFromRoll(roll) {
  const next = emptyForm();
  ROLL_FIELDS.forEach((f) => {
    const val = roll?.[f.key];
    next[f.key] = val == null ? "" : String(val);
  });
  return next;
}

function RollThumb({ photo, tokenless }) {
  const [src, setSrc] = useState(photo?.preview || "");
  useEffect(() => {
    if (photo?.preview) {
      setSrc(photo.preview);
      return undefined;
    }
    if (!photo?.url) return undefined;
    const path = String(photo.url).replace(/^\/api/, "");
    let alive = true;
    let objectUrl = "";
    api.get(path, { responseType: "blob" })
      .then((r) => {
        objectUrl = URL.createObjectURL(r.data);
        if (alive) setSrc(objectUrl);
      })
      .catch((err) => console.error("[rolls] photo load failed", err));
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [photo?.preview, photo?.url]);
  if (!src) {
    return <div className="h-24 bg-[#0A0C10] border border-[#1C2230]" />;
  }
  return (
    <img
      src={src}
      alt={photo?.kind || "tag"}
      className="h-24 w-full object-cover border border-[#1C2230]"
      data-testid={tokenless ? undefined : "roll-photo-thumb"}
    />
  );
}

export default function StrandRolls() {
  const device = useDevice();
  const [rolls, setRolls] = useState([]);
  const [beds, setBeds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [step, setStep] = useState("list");
  const [busy, setBusy] = useState("");
  const [torch, setTorchOn] = useState(false);
  const [shots, setShots] = useState([]);
  const [kind, setKind] = useState("tag");
  const [roll, setRoll] = useState(null);
  const [form, setForm] = useState(emptyForm());
  const [queue, setQueue] = useState(() => loadQueue());
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const canvasRef = useRef(null);

  const loadRolls = useCallback(async () => {
    try {
      const [rollRes, bedRes] = await Promise.all([api.get("/strand-rolls"), api.get("/beds")]);
      setRolls(rollRes.data || []);
      setBeds(bedRes.data || []);
    } catch (err) {
      console.error("[rolls] load failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to load strand rolls");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRolls();
  }, [loadRolls]);

  const stop = useCallback(() => {
    stopCamera(streamRef.current);
    streamRef.current = null;
  }, []);

  useEffect(() => () => stop(), [stop]);

  const openScan = async () => {
    setStep("scan");
    setShots([]);
    setKind("tag");
    setRoll(null);
    setForm(emptyForm());
    try {
      const stream = await startCamera(videoRef.current, torch);
      streamRef.current = stream;
    } catch (err) {
      console.error("[rolls] camera failed", err);
      toast.error("Camera permission is required to scan mill tags");
    }
  };

  const toggleTorch = async () => {
    const next = !torch;
    setTorchOn(next);
    const ok = await setTorch(streamRef.current, next);
    if (next && !ok) toast.error("Flashlight not available on this camera");
  };

  const capture = async () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    const w = video.videoWidth || 1280;
    const h = video.videoHeight || 720;
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, w, h);
    const preview = canvas.toDataURL("image/jpeg", 0.86);
    setShots((cur) => [...cur, { preview, kind, id: `${Date.now()}-${cur.length}` }]);
    toast.success(kind === "mtc" ? "MTC photo captured" : "Tag photo captured");
  };

  const extractPhotos = async (photoList, queuedId) => {
    const files = photoList.map((shot, i) => dataUrlToFile(shot.preview, `${shot.kind || "tag"}-${i + 1}.jpg`, shot.kind));
    const body = new FormData();
    files.forEach((file) => body.append("photos", file));
    body.append("kinds", photoList.map((s) => s.kind || "tag").join(","));
    const { data } = await api.post("/strand-rolls/extract", body, { skipOfflineQueue: true });
    if (queuedId) setQueue(dequeueRollJob(queuedId));
    return data;
  };

  const runExtract = async () => {
    if (!shots.length) {
      toast.error("Take at least one photo of the mill tag");
      return;
    }
    setBusy("extract");
    try {
      stop();
      const data = await extractPhotos(shots);
      setRoll(data);
      setForm(formFromRoll(data));
      setStep("confirm");
      toast.success(data.heat_number ? "Heat number read — confirm the tag" : "Tag stored — check highlighted fields");
    } catch (err) {
      console.error("[rolls] extract failed", err);
      const job = { id: `q-${Date.now()}`, shots };
      setQueue(enqueueRollJob(job));
      toast.error("Saved offline. Will extract when the plant network returns.");
      setStep("list");
    } finally {
      setBusy("");
    }
  };

  const flushQueue = async () => {
    const pending = loadQueue();
    if (!pending.length) return;
    setBusy("queue");
    try {
      for (const job of pending) {
        try {
          await extractPhotos(job.shots || [], job.id);
        } catch (err) {
          console.error("[rolls] queue item failed", err);
        }
      }
      setQueue(loadQueue());
      await loadRolls();
      toast.success("Offline mill-tag queue flushed");
    } finally {
      setBusy("");
    }
  };

  useEffect(() => {
    if (queue.length) flushQueue();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setField = (key, value) => setForm((cur) => ({ ...cur, [key]: value }));

  const confirm = async () => {
    if (!roll?.id) return;
    if (!String(form.heat_number || "").trim()) {
      toast.error("Heat number is required");
      return;
    }
    setBusy("confirm");
    try {
      const payload = { ...form, area_in2: form.area_in2 === "" ? null : parseFloat(form.area_in2) };
      const { data } = await api.post(`/strand-rolls/${roll.id}/confirm`, payload);
      setRoll(data);
      toast.success("Roll confirmed — ready to assign");
      await loadRolls();
    } catch (err) {
      console.error("[rolls] confirm failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to confirm roll");
    } finally {
      setBusy("");
    }
  };

  const assign = async (bedId) => {
    if (!roll?.id) return;
    setBusy(`assign-${bedId}`);
    try {
      const { data } = await api.post(`/strand-rolls/${roll.id}/assign`, { bed_id: bedId });
      setRoll(data.roll);
      toast.success(`Assigned to ${beds.find((b) => b.id === bedId)?.name || "bed"}`);
      await loadRolls();
    } catch (err) {
      console.error("[rolls] assign failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to assign roll");
    } finally {
      setBusy("");
    }
  };

  const openRoll = (row) => {
    stop();
    setRoll(row);
    setForm(formFromRoll(row));
    setShots((row.photos || []).map((p) => ({ ...p, preview: "" })));
    setStep("confirm");
  };

  return (
    <Layout>
      <PageHeader
        title="Strand Rolls"
        subtitle="Photograph the mill tag. Confirm heat, reel, and spec. Then assign to a bed."
        right={
          <div className="flex flex-wrap gap-2 justify-end">
            {queue.length > 0 && (
              <button
                type="button"
                onClick={flushQueue}
                className="min-h-12 px-4 border border-[#FFD600] text-[#FFD600] font-mono text-xs uppercase"
                data-testid="rolls-flush-queue"
              >
                Flush {queue.length} offline
              </button>
            )}
            <button
              type="button"
              data-testid="scan-tag"
              onClick={openScan}
              className="min-h-12 px-4 bg-primary text-white font-display font-bold uppercase tracking-widest flex items-center gap-2"
            >
              <ScanBarcode className="w-4 h-4" /> Scan Tag
            </button>
          </div>
        }
      />

      <div className="p-4 sm:p-6 lg:p-8 space-y-4">
        {step === "scan" && (
          <div className={`${cardClass} overflow-hidden`} data-testid="roll-camera">
            <div className="relative bg-black min-h-[360px]">
              <video ref={videoRef} playsInline muted autoPlay className="w-full min-h-[360px] object-cover" />
              <canvas ref={canvasRef} className="hidden" />
              <div className="absolute inset-x-0 bottom-0 p-3 grid grid-cols-2 sm:grid-cols-4 gap-2 bg-[#0A0C10]/80">
                <button type="button" onClick={toggleTorch} className="min-h-12 border border-[#1C2230] bg-[#0F1218] font-mono text-xs uppercase flex items-center justify-center gap-2" data-testid="roll-torch">
                  <Flashlight className="w-4 h-4" /> {torch ? "Light on" : "Light"}
                </button>
                <button type="button" onClick={() => setKind("tag")} className={`min-h-12 font-mono text-xs uppercase ${kind === "tag" ? "bg-primary text-white" : "border border-[#1C2230]"}`}>Tag</button>
                <button type="button" onClick={() => setKind("mtc")} className={`min-h-12 font-mono text-xs uppercase ${kind === "mtc" ? "bg-primary text-white" : "border border-[#1C2230]"}`}>MTC</button>
                <button type="button" onClick={capture} className="min-h-12 bg-[#C9A227] text-black font-display font-bold uppercase" data-testid="roll-capture">
                  <Camera className="w-4 h-4 inline mr-1" /> Capture
                </button>
              </div>
            </div>
            <div className="p-4 space-y-3">
              <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                {shots.map((shot) => (
                  <div key={shot.id} className="relative">
                    <img src={shot.preview} alt={shot.kind} className="h-20 w-full object-cover border border-[#1C2230]" />
                    <div className="absolute bottom-1 left-1 text-[9px] font-mono bg-[#0A0C10] px-1 text-primary">{shot.kind}</div>
                  </div>
                ))}
              </div>
              <div className="flex flex-col sm:flex-row gap-2">
                <button type="button" onClick={runExtract} disabled={busy === "extract"} className="min-h-14 flex-1 bg-primary text-white font-display font-bold uppercase tracking-widest disabled:opacity-60" data-testid="roll-extract">
                  {busy === "extract" ? <Loader2 className="w-5 h-5 animate-spin inline mr-2" /> : <Upload className="w-4 h-4 inline mr-2" />}
                  Extract & review
                </button>
                <button type="button" onClick={() => { stop(); setStep("list"); }} className="min-h-14 px-4 border border-[#1C2230] font-mono text-xs uppercase">Cancel</button>
              </div>
            </div>
          </div>
        )}

        {step === "confirm" && roll && (
          <div className={`${cardClass} p-4 sm:p-6 space-y-4`} data-testid="roll-confirm">
            <div className="flex items-center justify-between gap-2">
              <div>
                <div className="font-display font-bold uppercase tracking-wider">Confirm mill tag</div>
                <div className="text-[10px] font-mono text-muted-foreground">
                  {roll.status?.toUpperCase()} · {roll.extractor || "manual"} · conf {Number(roll.extractor_confidence || 0).toFixed(2)}
                </div>
              </div>
              {roll.status === "confirmed" || roll.status === "assigned" ? (
                <span className="text-[#00E676] font-mono text-xs flex items-center gap-1"><CheckCircle2 className="w-4 h-4" /> LOGGED</span>
              ) : (
                <span className="text-[#FFD600] font-mono text-xs">CHECK HIGHLIGHTED FIELDS</span>
              )}
            </div>
            <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
              {(roll.photos || shots).map((photo, i) => (
                <RollThumb key={photo.id || photo.filename || i} photo={photo} />
              ))}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {ROLL_FIELDS.map((field) => {
                const low = isLowConfidence(roll, field.key);
                return (
                  <Field key={field.key} label={field.critical ? `${field.label} *` : field.label}>
                    <input
                      data-testid={`roll-field-${field.key}`}
                      value={form[field.key]}
                      onChange={(e) => setField(field.key, e.target.value)}
                      className={`${inputClass} ${low || (field.critical && !form[field.key]) ? "border-[#FFD600] text-[#FFD600]" : ""}`}
                    />
                  </Field>
                );
              })}
            </div>
            <button
              type="button"
              onClick={confirm}
              disabled={busy === "confirm"}
              data-testid="roll-confirm-btn"
              className="w-full min-h-14 bg-primary text-white font-display font-bold uppercase tracking-widest disabled:opacity-60"
            >
              {busy === "confirm" ? <Loader2 className="w-5 h-5 animate-spin inline mr-2" /> : null}
              Confirm & Log
            </button>
            {(roll.status === "confirmed" || roll.status === "assigned") && (
              <div>
                <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2">One-tap assign</div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {beds.map((bed) => (
                    <button
                      key={bed.id}
                      type="button"
                      data-testid={`assign-bed-${bed.bed_number}`}
                      onClick={() => assign(bed.id)}
                      disabled={Boolean(busy)}
                      className="min-h-12 border border-[#1C2230] hover:border-primary font-mono text-xs uppercase"
                    >
                      Bed {bed.bed_number}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <button type="button" onClick={() => { setStep("list"); setRoll(null); }} className="w-full min-h-12 border border-[#1C2230] font-mono text-xs uppercase">Back to rolls</button>
          </div>
        )}

        {step === "list" && (
          <div className="space-y-3" data-testid="roll-list">
            {loading ? (
              <div className="flex items-center justify-center h-40 text-muted-foreground"><Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading rolls…</div>
            ) : rolls.length === 0 ? (
              <div className={`${cardClass} p-8 text-center`}>
                <ScanBarcode className="w-8 h-8 mx-auto mb-3 text-primary" />
                <div className="font-display font-bold uppercase">No mill tags logged</div>
                <p className="text-sm text-muted-foreground mt-2">Scan a coil tag before the bed is loaded.</p>
                <button type="button" onClick={openScan} className="mt-4 min-h-14 px-6 bg-primary text-white font-display font-bold uppercase tracking-widest">
                  <Plus className="w-4 h-4 inline mr-2" /> Scan Tag
                </button>
              </div>
            ) : rolls.map((row) => (
              <button
                key={row.id}
                type="button"
                onClick={() => openRoll(row)}
                className={`${cardClass} p-4 w-full text-left hover:border-primary`}
                data-testid={`roll-card-${row.id}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-display font-bold uppercase tracking-wider">Heat {row.heat_number || "UNREAD"}</div>
                    <div className="text-xs font-mono text-muted-foreground mt-1">
                      {row.reel_number || "NO REEL"} · {row.nominal_diameter || "dia?"} · GR {row.strand_grade || "—"} · {row.astm_standard || "ASTM?"}
                    </div>
                    <div className="text-[10px] font-mono text-muted-foreground mt-1">
                      {row.logged_by} · {(row.confirmed_at || row.logged_at || "").slice(0, 16)}
                    </div>
                  </div>
                  <span className="text-[10px] font-mono uppercase tracking-widest" style={{ color: row.status === "assigned" || row.status === "confirmed" ? "#00E676" : "#FFD600" }}>
                    {row.status}
                  </span>
                </div>
                {(row.assignments || []).length > 0 && (
                  <div className="mt-2 text-[10px] font-mono text-primary">
                    {(row.assignments || []).map((a) => `BED ${a.bed_number}${a.pour_number ? ` · ${a.pour_number}` : ""}`).join("  ·  ")}
                    {(row.assignments || []).some((a) => a.beam_marks?.length) ? ` · ${(row.assignments.flatMap((a) => a.beam_marks || [])).join(", ")}` : ""}
                  </div>
                )}
              </button>
            ))}
            {device.field && (
              <Link to="/tension" className="block text-center text-[10px] font-mono uppercase tracking-widest text-muted-foreground pt-2">
                Tensioning is locked until a confirmed roll is on the bed
              </Link>
            )}
          </div>
        )}
      </div>
    </Layout>
  );
}
