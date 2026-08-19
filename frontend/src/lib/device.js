/** Device class: iPhone field vs iPad/Mac command. */
export function detectDevice() {
  if (typeof navigator === "undefined") {
    return { iPhone: false, iPad: false, mac: false, field: false, command: true, platform: "web", model: "server" };
  }
  const ua = navigator.userAgent || "";
  const iPhone = /iPhone/.test(ua);
  const iPad = /iPad/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const mac = /Macintosh/.test(ua) && !iPad;
  const native = Boolean(window.Capacitor?.isNativePlatform?.() || window.Capacitor?.Plugins);
  const width = window.innerWidth || 1200;
  const field = iPhone || (!iPad && !mac && width < 768);
  const command = !field;
  let platform = "web";
  if (iPhone) platform = "ios";
  else if (iPad) platform = "ipados";
  else if (mac) platform = "macos";
  return {
    iPhone,
    iPad,
    mac,
    field,
    command,
    native,
    platform,
    model: (navigator.userAgentData?.model || ua).slice(0, 80),
  };
}

export function nativeARPlugin() {
  return window.Capacitor?.Plugins?.ARMeasure || null;
}

export function deviceId() {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem("bf_device");
  if (!id) {
    id = (crypto.randomUUID && crypto.randomUUID()) || `dev-${Date.now()}`;
    localStorage.setItem("bf_device", id);
  }
  return id;
}
