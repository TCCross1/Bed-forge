/** Web AR / gravity level engine. Native ARKit is used when Capacitor plugin is present. */
export const LEVEL_TOLERANCE_IN = 0.125;
export const SAMPLE_TARGET = 12;

export function metersToIn(m) {
  return m * 39.37007874;
}
export function metersToFt(m) {
  return m * 3.280839895;
}

export function averagePoints(points) {
  if (!points.length) return { x: 0, y: 0, z: 0 };
  const acc = points.reduce((s, p) => ({ x: s.x + p.x, y: s.y + p.y, z: s.z + p.z }), { x: 0, y: 0, z: 0 });
  return { x: acc.x / points.length, y: acc.y / points.length, z: acc.z / points.length };
}

export function metrics(a, b) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const dz = b.z - a.z;
  const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
  const deltaIn = metersToIn(dy);
  return {
    distance_ft: +metersToFt(dist).toFixed(4),
    delta_height_in: +deltaIn.toFixed(3),
    level: Math.abs(deltaIn) <= LEVEL_TOLERANCE_IN,
  };
}

export function confidenceFromSamples(points) {
  if (points.length < 3) return 0.35;
  const avg = averagePoints(points);
  const spread = points.reduce((s, p) => s + Math.hypot(p.x - avg.x, p.y - avg.y, p.z - avg.z), 0) / points.length;
  return Math.max(0.2, Math.min(1, 1 - spread * 8));
}

export async function startCamera(videoEl, torch) {
  const constraints = {
    audio: false,
    video: {
      facingMode: { ideal: "environment" },
      width: { ideal: 1280 },
      height: { ideal: 720 },
      torch: Boolean(torch),
    },
  };
  const stream = await navigator.mediaDevices.getUserMedia(constraints);
  videoEl.srcObject = stream;
  await videoEl.play();
  if (torch) await setTorch(stream, true);
  return stream;
}

export async function setTorch(stream, on) {
  const track = stream?.getVideoTracks?.()[0];
  if (!track) return false;
  const caps = track.getCapabilities?.() || {};
  if (!caps.torch) return false;
  try {
    await track.applyConstraints({ advanced: [{ torch: Boolean(on) }] });
    return true;
  } catch (err) {
    console.error("[ar] torch failed", err);
    return false;
  }
}

export function stopCamera(stream) {
  (stream?.getTracks?.() || []).forEach((t) => t.stop());
}

export function haptic(ok) {
  try {
    if (ok) navigator.vibrate?.([18, 30, 18]);
    else navigator.vibrate?.(40);
  } catch (err) {
    console.error("[ar] haptic failed", err);
  }
}

/**
 * Hit pose: WebXR hit-test when available; otherwise gravity-up along a walking vector.
 * origin is camera; we project a point `reach` meters ahead of the device, then
 * use DeviceOrientation to tilt that point. This is the non-LiDAR fallback.
 */
export function gravityPose(orientation, walkFt, reachM = 1.6) {
  const beta = ((orientation?.beta || 0) * Math.PI) / 180;
  const gamma = ((orientation?.gamma || 0) * Math.PI) / 180;
  const walkM = (Number(walkFt) || 0) / 3.280839895;
  return {
    x: Math.sin(gamma) * reachM,
    y: -Math.sin(beta) * 0.35,
    z: -walkM - Math.cos(beta) * 0.2,
  };
}

export async function requestMotion() {
  if (typeof DeviceOrientationEvent !== "undefined" && typeof DeviceOrientationEvent.requestPermission === "function") {
    try {
      await DeviceOrientationEvent.requestPermission();
    } catch (err) {
      console.error("[ar] motion permission failed", err);
    }
  }
}
