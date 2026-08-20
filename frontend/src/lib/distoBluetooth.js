/** Leica DISTO / LDM capture: Web Bluetooth where the browser allows it, iOS keyboard wedge otherwise. */

export const DISTO_SERVICE = "3ab10100-f831-4395-b29d-570977d5bf94";
export const DISTO_DISTANCE = "3ab10101-f831-4395-b29d-570977d5bf94";
export const DISTO_DISTANCE_UNIT = "3ab10102-f831-4395-b29d-570977d5bf94";
export const DISTO_COMMAND = "3ab10109-f831-4395-b29d-570977d5bf94";
export const DISTO_ENABLE = new Uint8Array([0x67]);
export const INCHES_PER_METER = 39.37007874015748;
export const INCHES_PER_FOOT = 12;

export function isWebBluetoothAvailable() {
  return typeof navigator !== "undefined" && Boolean(navigator.bluetooth && navigator.bluetooth.requestDevice);
}

export function isIosDevice() {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || "";
  const iOS = /iPad|iPhone|iPod/.test(ua);
  const iPadOs = navigator.platform === "MacIntel" && Number(navigator.maxTouchPoints || 0) > 1;
  return iOS || iPadOs;
}

export function metersToInches(meters) {
  return Number(meters) * INCHES_PER_METER;
}

export function parseDistanceToInches(raw) {
  const text = String(raw || "").trim().replace(/,/g, "");
  if (!text) return null;
  const meters = text.match(/^([+-]?\d+(?:\.\d+)?)\s*(m|meter|meters)\b/i);
  if (meters) return metersToInches(parseFloat(meters[1]));
  const feetInches = text.match(/^([+-]?\d+)\s*(?:'|ft|feet)\s*(\d+(?:\.\d+)?)\s*(?:"|in|inch|inches)?$/i);
  if (feetInches) return parseFloat(feetInches[1]) * INCHES_PER_FOOT + parseFloat(feetInches[2]);
  const feet = text.match(/^([+-]?\d+(?:\.\d+)?)\s*(?:'|ft|feet)\s*$/i);
  if (feet) return parseFloat(feet[1]) * INCHES_PER_FOOT;
  const inches = text.match(/^([+-]?\d+(?:\.\d+)?)\s*(?:"|in|inch|inches)\b/i);
  if (inches) return parseFloat(inches[1]);
  const mm = text.match(/^([+-]?\d+(?:\.\d+)?)\s*(mm|millimeter|millimeters)\b/i);
  if (mm) return parseFloat(mm[1]) / 25.4;
  const cm = text.match(/^([+-]?\d+(?:\.\d+)?)\s*(cm|centimeter|centimeters)\b/i);
  if (cm) return parseFloat(cm[1]) / 2.54;
  const bare = Number(text);
  if (Number.isFinite(bare)) {
    if (Math.abs(bare) <= 40) return metersToInches(bare);
    return bare;
  }
  return null;
}

function decodeDistanceCharacteristic(value) {
  if (!value) return null;
  try {
    if (value.byteLength >= 4) {
      const meters = value.getFloat32(0, true);
      if (Number.isFinite(meters) && meters > 0 && meters < 500) return metersToInches(meters);
    }
    const bytes = [];
    for (let i = 0; i < value.byteLength; i += 1) bytes.push(value.getUint8(i));
    const asText = new TextDecoder().decode(new Uint8Array(bytes));
    return parseDistanceToInches(asText);
  } catch (err) {
    console.error("[disto] characteristic decode failed", err);
    return null;
  }
}

export async function connectDisto({ onReading, onStatus } = {}) {
  if (!isWebBluetoothAvailable()) {
    throw new Error("Web Bluetooth is not available in this browser. Use keyboard wedge on iPhone, or Chrome/Edge on Android/desktop.");
  }
  const emit = (kind, detail) => {
    if (typeof onStatus === "function") onStatus(kind, detail);
  };
  emit("requesting", "Choose your DISTO / LDM");
  const device = await navigator.bluetooth.requestDevice({
    filters: [
      { namePrefix: "DISTO" },
      { namePrefix: "Disto" },
      { namePrefix: "Leica" },
      { services: [DISTO_SERVICE] },
    ],
    optionalServices: [DISTO_SERVICE],
  });
  emit("connecting", device.name || "DISTO");
  const server = await device.gatt.connect();
  const service = await server.getPrimaryService(DISTO_SERVICE);
  const distance = await service.getCharacteristic(DISTO_DISTANCE);
  const fire = (event) => {
    const inches = decodeDistanceCharacteristic(event.target.value);
    if (inches == null) return;
    if (typeof onReading === "function") {
      onReading({
        measured_in: inches,
        source: "bluetooth",
        device_name: device.name || "DISTO",
      });
    }
  };
  await distance.startNotifications();
  distance.addEventListener("characteristicvaluechanged", fire);
  try {
    const command = await service.getCharacteristic(DISTO_COMMAND);
    await command.writeValue(DISTO_ENABLE);
  } catch (err) {
    console.warn("[disto] command characteristic not writable", err);
  }
  emit("connected", device.name || "DISTO");
  const disconnect = async () => {
    try {
      distance.removeEventListener("characteristicvaluechanged", fire);
      await distance.stopNotifications();
    } catch (err) {
      console.warn("[disto] stop notifications failed", err);
    }
    try {
      if (device.gatt.connected) device.gatt.disconnect();
    } catch (err) {
      console.warn("[disto] disconnect failed", err);
    }
    emit("disconnected", device.name || "DISTO");
  };
  device.addEventListener("gattserverdisconnected", () => emit("disconnected", device.name || "DISTO"));
  return { device, disconnect };
}

export function startKeyboardWedge({ onReading, onBuffer } = {}) {
  let buffer = "";
  const onKeyDown = (event) => {
    const target = event.target;
    const typingField = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
    if (typingField && target.getAttribute("data-disto-wedge") !== "true") return;
    if (event.key === "Enter") {
      const inches = parseDistanceToInches(buffer);
      buffer = "";
      if (typeof onBuffer === "function") onBuffer("");
      if (inches == null) return;
      event.preventDefault();
      if (typeof onReading === "function") {
        onReading({ measured_in: inches, source: "keyboard", device_name: "DISTO keyboard" });
      }
      return;
    }
    if (event.key === "Backspace") {
      buffer = buffer.slice(0, -1);
      if (typeof onBuffer === "function") onBuffer(buffer);
      return;
    }
    if (event.key.length === 1) {
      buffer += event.key;
      if (typeof onBuffer === "function") onBuffer(buffer);
    }
  };
  window.addEventListener("keydown", onKeyDown);
  return () => window.removeEventListener("keydown", onKeyDown);
}
