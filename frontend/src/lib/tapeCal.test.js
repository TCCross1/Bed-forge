import {
  CAL_LOCK_HOURS,
  CAL_TOLERANCE_PCT,
  WEB_HONESTY_LABEL,
  applyScale,
  evaluateCalibration,
  formatRemaining,
  sanitizeEngine,
} from "./tapeCal";

test("calibration passes at ±0.15% and fails beyond", () => {
  expect(CAL_TOLERANCE_PCT).toBe(0.15);
  expect(CAL_LOCK_HOURS).toBe(24);
  const edge = evaluateCalibration(10, 10.015);
  expect(edge.passed).toBe(true);
  const over = evaluateCalibration(10, 10.016);
  expect(over.passed).toBe(false);
  expect(over.detail).toMatch(/0\.15%/);
});

test("web path never claims ARKit or LiDAR", () => {
  const web = sanitizeEngine("web", true, false);
  expect(web.lidar).toBe(false);
  expect(web.isNative).toBe(false);
  expect(web.honestyLabel).toBe(WEB_HONESTY_LABEL);
  expect(web.honestyLabel).toMatch(/not ARKit/);
  const native = sanitizeEngine("arkit-lidar", true, true);
  expect(native.isNative).toBe(true);
  expect(native.lidar).toBe(true);
  expect(native.honestyLabel).toMatch(/ARKit/);
});

test("scale applies per reading and remaining time formats", () => {
  expect(applyScale(10, 0.9985)).toBe(9.985);
  expect(formatRemaining(0)).toBe("expired");
  expect(formatRemaining(90)).toBe("1m");
  expect(formatRemaining(3661)).toBe("1h 1m");
});
