import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Flashlight, Loader2, ScanLine } from "lucide-react";
import { toast } from "sonner";
import jsQR from "jsqr";
import Layout, { PageHeader, cardClass, inputClass } from "../components/Layout";
import { dossierPath, normalizeToken, parseScannedValue } from "../lib/beamQr";
import { startCamera, stopCamera, setTorch } from "../lib/arEngine";

export default function ScanBeam() {
  const navigate = useNavigate();
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const rafRef = useRef(0);
  const [running, setRunning] = useState(false);
  const [torch, setTorchOn] = useState(false);
  const [manual, setManual] = useState("");
  const [busy, setBusy] = useState(false);

  const openToken = (raw) => {
    const token = normalizeToken(raw) || normalizeToken(parseScannedValue(raw));
    if (!token) {
      toast.error("No beam QR found in that scan");
      return false;
    }
    navigate(dossierPath(token));
    return true;
  };

  const loop = () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) {
      rafRef.current = requestAnimationFrame(loop);
      return;
    }
    const w = video.videoWidth || 640;
    const h = video.videoHeight || 480;
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(video, 0, 0, w, h);
    const image = ctx.getImageData(0, 0, w, h);
    const code = jsQR(image.data, w, h, { inversionAttempts: "attemptBoth" });
    if (code?.data) {
      if (openToken(code.data)) return;
    }
    rafRef.current = requestAnimationFrame(loop);
  };

  const start = async () => {
    setBusy(true);
    try {
      const stream = await startCamera(videoRef.current, torch);
      streamRef.current = stream;
      setRunning(true);
      rafRef.current = requestAnimationFrame(loop);
    } catch (err) {
      console.error("[scan] camera failed", err);
      toast.error("Camera unavailable — use the system camera or upload a photo");
    } finally {
      setBusy(false);
    }
  };

  const stop = () => {
    cancelAnimationFrame(rafRef.current);
    stopCamera(streamRef.current);
    streamRef.current = null;
    setRunning(false);
  };

  useEffect(() => () => stop(), []);

  const toggleTorch = async () => {
    const next = !torch;
    setTorchOn(next);
    if (streamRef.current) await setTorch(streamRef.current, next);
  };

  const onFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const bitmap = await createImageBitmap(file);
      const canvas = canvasRef.current;
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      ctx.drawImage(bitmap, 0, 0);
      const image = ctx.getImageData(0, 0, bitmap.width, bitmap.height);
      const code = jsQR(image.data, bitmap.width, bitmap.height);
      if (!code?.data || !openToken(code.data)) toast.error("Could not read a beam QR from that photo");
    } catch (err) {
      console.error("[scan] photo decode failed", err);
      toast.error("Could not read that photo");
    }
  };

  return (
    <Layout>
      <PageHeader
        title="Scan Beam QR"
        subtitle="Point at a laminated tag — or use the phone camera, which opens this page automatically"
      />
      <div className="p-4 sm:p-6 lg:p-8 max-w-3xl space-y-4">
        <div className={`${cardClass} overflow-hidden relative`} data-testid="scan-stage">
          <video ref={videoRef} className="w-full aspect-[3/4] sm:aspect-video bg-black object-cover" playsInline muted />
          <canvas ref={canvasRef} className="hidden" />
          <div className="absolute inset-x-0 bottom-0 p-4 flex flex-wrap gap-2 bg-gradient-to-t from-black/80">
            {!running ? (
              <button
                type="button"
                data-testid="scan-start"
                onClick={start}
                disabled={busy}
                className="min-h-12 px-4 bg-primary text-white font-display font-bold uppercase tracking-widest flex items-center gap-2 disabled:opacity-60"
              >
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <ScanLine className="w-4 h-4" />}
                Start scanner
              </button>
            ) : (
              <button type="button" onClick={stop} className="min-h-12 px-4 border border-white/30 text-white font-semibold uppercase tracking-wider">
                Stop
              </button>
            )}
            <button type="button" onClick={toggleTorch} className="min-h-12 px-4 border border-white/30 text-white font-semibold uppercase tracking-wider flex items-center gap-2">
              <Flashlight className="w-4 h-4" /> {torch ? "Torch on" : "Torch"}
            </button>
            <label className="min-h-12 px-4 border border-white/30 text-white font-semibold uppercase tracking-wider flex items-center cursor-pointer">
              Photo
              <input type="file" accept="image/*" capture="environment" className="hidden" onChange={onFile} />
            </label>
          </div>
        </div>
        <div className={`${cardClass} p-4 sm:p-6`}>
          <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2">Paste URL or token</div>
          <form
            className="flex flex-col sm:flex-row gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              openToken(manual);
            }}
          >
            <input
              value={manual}
              onChange={(e) => setManual(e.target.value)}
              placeholder="https://…/b/token or 16-character token"
              className={inputClass}
              data-testid="scan-manual"
            />
            <button type="submit" className="min-h-12 px-4 bg-primary text-white font-display font-bold uppercase tracking-widest">
              Open
            </button>
          </form>
        </div>
      </div>
    </Layout>
  );
}
