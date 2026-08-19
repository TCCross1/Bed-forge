/** Daily tape calibration helpers. Browser tape is not ARKit. */

export const CAL_TOLERANCE_PCT = 0.15;
export const CAL_LOCK_HOURS = 24;
export const WEB_HONESTY_LABEL = "Camera / gravity tape — not ARKit, not LiDAR";
export const ARKIT_HONESTY_LABEL = "ARKit world tracking (no LiDAR)";
export const ARKIT_LIDAR_HONESTY_LABEL = "ARKit with LiDAR";

export function sanitizeEngine(engine, lidar, native) {
  const raw = String(engine || "web").trim().toLowerCase() || "web";
  if (native && (raw === "arkit" || raw === "arkit-lidar")) {
    const useLidar = Boolean(lidar) || raw === "arkit-lidar";
    return {
      engine: useLidar ? "arkit-lidar" : "arkit",
      lidar: useLidar,
      isNative: true,
      honestyLabel: useLidar ? ARKIT_LIDAR_HONESTY_LABEL : ARKIT_HONESTY_LABEL,
    };
  }
  return {
    engine: raw === "gravity" || raw === "camera" || raw === "photo" ? raw : "web",
    lidar: false,
    isNative: false,
    honestyLabel: WEB_HONESTY_LABEL,
  };
}

export function evaluateCalibration(knownLengthFt, measuredLengthFt, tolerancePct = CAL_TOLERANCE_PCT) {
  const known = Number(knownLengthFt);
  const measured = Number(measuredLengthFt);
  const tol = Number(tolerancePct);
  if (!Number.isFinite(known) || !Number.isFinite(measured) || known <= 0 || measured <= 0) {
    return {
      ok: false,
      passed: false,
      errorPct: null,
      scaleFactor: null,
      detail: "Known and measured lengths must be greater than zero",
    };
  }
  const errorPct = Number(((Math.abs(measured - known) / known) * 100).toFixed(6));
  const passed = errorPct <= tol;
  return {
    ok: true,
    passed,
    knownLengthFt: known,
    measuredLengthFt: measured,
    errorPct,
    scaleFactor: known / measured,
    tolerancePct: tol,
    detail: passed ? null : `Calibration failed — ${errorPct.toFixed(4)}% error exceeds ±${tol}%`,
  };
}

export function formatRemaining(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours <= 0 && minutes <= 0) {
    const secs = total % 60;
    return secs > 0 ? `${secs}s` : "expired";
  }
  if (hours <= 0) return `${minutes}m`;
  return `${hours}h ${minutes}m`;
}

export function applyScale(distanceFt, scaleFactor) {
  const dist = Number(distanceFt);
  const factor = Number(scaleFactor);
  if (!Number.isFinite(dist)) return 0;
  if (!Number.isFinite(factor) || factor <= 0) return Number(dist.toFixed(4));
  return Number((dist * factor).toFixed(4));
}
