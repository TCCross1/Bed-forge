import React, { useEffect, useState } from "react";
import { CloudOff, RefreshCw, Wifi } from "lucide-react";
import api from "../lib/api";
import { flushQueue, listQueue } from "../lib/offlineQueue";

export default function OfflineBanner() {
  const [online, setOnline] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  const [pending, setPending] = useState(0);
  const [syncing, setSyncing] = useState(false);

  const refresh = async () => {
    const items = await listQueue();
    setPending(items.length);
  };

  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    window.addEventListener("bf-offline-queue", refresh);
    refresh();
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
      window.removeEventListener("bf-offline-queue", refresh);
    };
  }, []);

  useEffect(() => {
    if (!online || pending === 0) return undefined;
    let cancelled = false;
    setSyncing(true);
    flushQueue(api).finally(() => {
      if (!cancelled) {
        setSyncing(false);
        refresh();
      }
    });
    return () => { cancelled = true; };
  }, [online, pending]);

  const state = !online ? "offline" : syncing ? "syncing" : pending ? "queued" : "synced";
  const color = state === "offline" ? "#FF3366" : state === "synced" ? "#00E676" : "#FFD600";
  const label = state === "offline"
    ? "OFFLINE — shots and forms queue on this device"
    : state === "syncing"
      ? `SYNCING ${pending} queued action${pending === 1 ? "" : "s"}`
      : pending
        ? `${pending} waiting to sync`
        : "SYNCED";

  return (
    <div
      className="px-4 sm:px-6 min-h-9 flex items-center justify-between gap-3 border-b border-[#1C2230] bg-[#0C0E13]"
      data-testid="offline-banner"
      style={{ borderLeft: `3px solid ${color}` }}
    >
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest" style={{ color }}>
        {state === "offline" ? <CloudOff className="w-3.5 h-3.5" /> : state === "syncing" ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Wifi className="w-3.5 h-3.5" />}
        {label}
      </div>
      {pending > 0 && online && (
        <button
          type="button"
          className="min-h-8 px-2 text-[10px] font-mono uppercase tracking-widest hover:text-primary"
          onClick={() => { setSyncing(true); flushQueue(api).finally(() => { setSyncing(false); refresh(); }); }}
        >
          Retry
        </button>
      )}
    </div>
  );
}
