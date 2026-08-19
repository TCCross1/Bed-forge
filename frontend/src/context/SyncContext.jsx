import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import api from "../lib/api";
import { useAuth } from "./AuthContext";
import { useDevice } from "./DeviceContext";

const SyncContext = createContext({ events: [], measurements: [], refresh: () => {} });

export function SyncProvider({ children }) {
  const { user } = useAuth();
  const device = useDevice();
  const [events, setEvents] = useState([]);
  const [measurements, setMeasurements] = useState([]);
  const sinceRef = useRef("");
  const seenRef = useRef(new Set());
  const deviceRef = useRef(device);
  deviceRef.current = device;

  useEffect(() => {
    if (!user) return undefined;
    let cancelled = false;

    const tick = async (silent) => {
      try {
        const { data } = await api.get("/sync/feed", { params: sinceRef.current ? { since: sinceRef.current } : {} });
        if (cancelled) return;
        sinceRef.current = data.server_time || sinceRef.current;
        if (data.ar_measurements?.length) {
          setMeasurements((cur) => {
            const map = new Map(cur.map((m) => [m.id, m]));
            data.ar_measurements.forEach((m) => map.set(m.id, m));
            return Array.from(map.values()).sort((a, b) => (a.created_at < b.created_at ? 1 : -1)).slice(0, 80);
          });
        }
        if (data.events?.length) {
          setEvents((cur) => {
            const map = new Map(cur.map((e) => [e.id, e]));
            data.events.forEach((e) => map.set(e.id, e));
            return Array.from(map.values()).sort((a, b) => (a.created_at < b.created_at ? 1 : -1)).slice(0, 80);
          });
          data.events.forEach((ev) => {
            if (seenRef.current.has(ev.id)) return;
            seenRef.current.add(ev.id);
            if (silent && deviceRef.current.command) {
              if (ev.type === "ar_measurement") toast.info(ev.title);
              if (ev.type === "hold") toast.error(ev.title);
            }
          });
        }
      } catch (err) {
        if (!silent) console.error("[sync] feed failed", err);
      }
    };

    tick(false);
    api.post("/devices", {
      platform: device.platform,
      device_class: device.field ? "field" : "command",
      model: device.model,
    }).catch((err) => console.error("[sync] device register failed", err));
    const t = setInterval(() => tick(true), 4000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [user, device.field, device.platform, device.model]);

  const refresh = () => {
    sinceRef.current = "";
    api.get("/sync/feed").then(({ data }) => {
      sinceRef.current = data.server_time || "";
      setMeasurements((data.ar_measurements || []).slice().reverse());
      setEvents((data.events || []).slice().reverse());
    }).catch((err) => console.error("[sync] refresh failed", err));
  };

  return (
    <SyncContext.Provider value={{ events, measurements, refresh }}>
      {children}
    </SyncContext.Provider>
  );
}

export function useSync() {
  return useContext(SyncContext);
}
