import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { detectDevice } from "../lib/device";

const DeviceContext = createContext(detectDevice());

export function DeviceProvider({ children }) {
  const [device, setDevice] = useState(() => detectDevice());
  useEffect(() => {
    const onResize = () => setDevice(detectDevice());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  const value = useMemo(() => device, [device]);
  return <DeviceContext.Provider value={value}>{children}</DeviceContext.Provider>;
}

export function useDevice() {
  return useContext(DeviceContext);
}
