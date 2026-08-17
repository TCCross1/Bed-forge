/** IndexedDB-backed offline queue for plant-floor writes. Never drop a measurement or photo. */

export const OFFLINE_DB = "bedforge-offline";
export const OFFLINE_STORE = "queue";
export const FIELD_WRITE_RE = /\/(inspections|tension-reports|camber-readings|finish-sheets|pre-delivery|ar-measurements|ar-tape-runs|maturity\/samples|strand-rolls)$/;

function openDb() {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB unavailable"));
      return;
    }
    const req = indexedDB.open(OFFLINE_DB, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(OFFLINE_STORE)) {
        db.createObjectStore(OFFLINE_STORE, { keyPath: "id" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function memoryFallback() {
  if (!window.__bfOfflineMem) window.__bfOfflineMem = [];
  return window.__bfOfflineMem;
}

export async function listQueue() {
  try {
    const db = await openDb();
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(OFFLINE_STORE, "readonly");
      const req = tx.objectStore(OFFLINE_STORE).getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
  } catch (err) {
    console.error("[offline] list failed", err);
    return [...memoryFallback()];
  }
}

export async function enqueueAction(item) {
  const rec = {
    id: item.id || `off-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    method: (item.method || "post").toLowerCase(),
    url: item.url,
    data: item.data,
    headers: item.headers || {},
    created_at: new Date().toISOString(),
    tries: item.tries || 0,
    label: item.label || item.url,
  };
  try {
    const db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(OFFLINE_STORE, "readwrite");
      tx.objectStore(OFFLINE_STORE).put(rec);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch (err) {
    console.error("[offline] enqueue idb failed, using memory", err);
    const mem = memoryFallback();
    mem.push(rec);
    try {
      localStorage.setItem("bf_offline_queue_meta", String(mem.length));
    } catch (e) {
      console.error("[offline] meta save failed", e);
    }
  }
  window.dispatchEvent(new CustomEvent("bf-offline-queue"));
  return rec;
}

export async function removeAction(id) {
  try {
    const db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(OFFLINE_STORE, "readwrite");
      tx.objectStore(OFFLINE_STORE).delete(id);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch (err) {
    const mem = memoryFallback();
    window.__bfOfflineMem = mem.filter((x) => x.id !== id);
    console.error("[offline] remove failed", err);
  }
  window.dispatchEvent(new CustomEvent("bf-offline-queue"));
}

export function isFieldWrite(url = "", method = "get") {
  const verb = String(method).toLowerCase();
  if (verb !== "post" && verb !== "patch") return false;
  const path = String(url).split("?")[0];
  if (FIELD_WRITE_RE.test(path)) return true;
  if (/\/strand-rolls\/[^/]+\/(confirm|assign)$/.test(path)) return true;
  if (/\/beam-specs\/[^/]+\/strands\/[^/]+\/tension$/.test(path)) return true;
  if (/\/beam-specs\/[^/]+\/hold-downs\/[^/]+\/check$/.test(path)) return true;
  if (/\/beams\/[^/]+$/.test(path) && verb === "patch") return true;
  if (path.includes("/ar-tape-runs")) return true;
  if (path.includes("/cylinders/") && path.includes("/crush")) return true;
  return false;
}

export function shouldQueueError(err) {
  if (!err) return false;
  if (!err.response && (err.code === "ERR_NETWORK" || err.message === "Network Error" || !navigator.onLine)) return true;
  if (err.response?.status >= 500) return false;
  return false;
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("read failed"));
    reader.readAsDataURL(blob);
  });
}

function dataUrlToBlob(dataUrl, filename, type) {
  const [meta, body] = String(dataUrl || "").split(",");
  const mime = type || (meta.match(/data:(.*?);/) || [])[1] || "application/octet-stream";
  const binary = atob(body || "");
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new File([bytes], filename || "upload.bin", { type: mime });
}

export async function serializeRequestBody(raw) {
  if (raw == null) return raw;
  if (typeof FormData !== "undefined" && raw instanceof FormData) {
    const entries = [];
    for (const [name, value] of raw.entries()) {
      if (typeof Blob !== "undefined" && value instanceof Blob) {
        const dataUrl = await blobToDataUrl(value);
        entries.push({
          name,
          filename: value.name || "upload.bin",
          type: value.type || "application/octet-stream",
          dataUrl,
        });
      } else {
        entries.push({ name, value: String(value) });
      }
    }
    return { __formData: true, entries };
  }
  if (typeof raw === "string") {
    try {
      return JSON.parse(raw);
    } catch (err) {
      return raw;
    }
  }
  return raw;
}

export function reviveRequestBody(data) {
  if (data && data.__formData && Array.isArray(data.entries)) {
    const fd = new FormData();
    data.entries.forEach((entry) => {
      if (entry.dataUrl) {
        fd.append(entry.name, dataUrlToBlob(entry.dataUrl, entry.filename, entry.type));
      } else {
        fd.append(entry.name, entry.value);
      }
    });
    return fd;
  }
  return data;
}

let flushing = false;

export async function flushQueue(api) {
  if (flushing || !navigator.onLine) return { flushed: 0, left: (await listQueue()).length };
  flushing = true;
  let flushed = 0;
  try {
    const items = await listQueue();
    for (const item of items) {
      try {
        await api.request({
          method: item.method,
          url: item.url,
          data: reviveRequestBody(item.data),
          headers: item.headers,
          skipOfflineQueue: true,
        });
        await removeAction(item.id);
        flushed += 1;
      } catch (err) {
        console.error("[offline] flush item failed id=%s", item.id, err);
        if (shouldQueueError(err)) break;
        const status = err.response?.status;
        if (status === 409) {
          continue;
        }
        item.tries = (item.tries || 0) + 1;
        if (item.tries >= 8 && status && status >= 400 && status < 500) {
          await removeAction(item.id);
        } else {
          try {
            await enqueueAction(item);
          } catch (saveErr) {
            console.error("[offline] retry save failed", saveErr);
          }
        }
      }
    }
  } finally {
    flushing = false;
    window.dispatchEvent(new CustomEvent("bf-offline-queue"));
  }
  const left = (await listQueue()).length;
  return { flushed, left };
}
