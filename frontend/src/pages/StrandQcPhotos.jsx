import React, { useCallback, useEffect, useState } from "react";
import { Camera, Upload } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../lib/api";
import { cardClass } from "../components/Layout";
import { useOpenJob } from "../context/OpenJobContext";

const KINDS = [
  ["strand_pattern", "Strand pattern"],
  ["side_profile", "Side profile"],
  ["marked_end_profile", "Marked-end profile"],
];

function PhotoCard({ kind, label, photo, pourDate, jobId, onUploaded }) {
  const [busy, setBusy] = useState(false);
  const [src, setSrc] = useState("");

  useEffect(() => {
    if (!photo?.url) {
      setSrc("");
      return undefined;
    }
    const path = String(photo.url).replace(/^\/api/, "");
    let alive = true;
    let objectUrl = "";
    api.get(path, { responseType: "blob" })
      .then((res) => {
        objectUrl = URL.createObjectURL(res.data);
        if (alive) setSrc(objectUrl);
      })
      .catch((err) => console.error("[qc-photo] load failed", err));
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [photo?.url, photo?.id]);

  const upload = async (file) => {
    if (!file || !jobId) return;
    setBusy(true);
    try {
      const body = new FormData();
      body.append("photo", file);
      body.append("kind", kind);
      body.append("pour_date", pourDate);
      body.append("job_id", jobId);
      await api.post("/job-qc-photos", body);
      toast.success(`${label} attached for ${pourDate}`);
      onUploaded?.();
    } catch (err) {
      console.error("[qc-photo] upload failed", err);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to attach QC photo");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`${cardClass} p-4 space-y-3`} data-testid={`qc-photo-${kind}`}>
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="font-display font-bold uppercase tracking-wider text-sm">{label}</div>
          <div className="text-[10px] font-mono text-muted-foreground">One photo per job pour day</div>
        </div>
        <Camera className="w-4 h-4 text-primary" />
      </div>
      {src ? (
        <img src={src} alt={label} className="w-full h-40 object-cover border border-[#1C2230]" />
      ) : (
        <div className="h-40 border border-dashed border-[#1C2230] flex items-center justify-center text-xs font-mono text-muted-foreground">No photo for this pour day</div>
      )}
      <label className="min-h-12 border border-border flex items-center justify-center gap-2 font-mono text-xs uppercase tracking-wider cursor-pointer hover:border-primary hover:text-primary">
        <Upload className="w-4 h-4" /> {busy ? "Saving..." : "Upload / replace"}
        <input type="file" accept="image/*" className="hidden" onChange={(e) => upload(e.target.files?.[0])} />
      </label>
    </div>
  );
}

export default function StrandQcPhotos() {
  const { openJob, pourDate, setPourDate } = useOpenJob();
  const [photos, setPhotos] = useState([]);

  const load = useCallback(async () => {
    if (!openJob?.id) {
      setPhotos([]);
      return;
    }
    try {
      const { data } = await api.get("/job-qc-photos", { params: { job_id: openJob.id, pour_date: pourDate } });
      setPhotos(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("[qc-photo] list failed", err);
    }
  }, [openJob?.id, pourDate]);

  useEffect(() => {
    load();
  }, [load]);

  const byKind = Object.fromEntries(photos.map((item) => [item.kind, item]));

  return (
    <div className="space-y-4" data-testid="qc-photo-panel">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">Pour day</div>
          <input type="date" className="mt-1 min-h-12 bg-[#0A0C10] border border-[#1C2230] px-3 font-mono" value={pourDate} onChange={(e) => setPourDate(e.target.value)} />
        </div>
        <div className="text-sm text-muted-foreground">Open job {openJob?.job_number || ""} · unique by job + pour day</div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {KINDS.map(([kind, label]) => (
          <PhotoCard
            key={kind}
            kind={kind}
            label={label}
            photo={byKind[kind]}
            pourDate={pourDate}
            jobId={openJob?.id}
            onUploaded={load}
          />
        ))}
      </div>
    </div>
  );
}
