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
  if (String(method).toLowerCase() !== "post" && String(method).toLowerCase() !== "patch") return false;
  const path = String(url).split("?")[0];
  return FIELD_WRITE_RE.test(path) || path.includes("/ar-tape-runs") || path.includes("/cylinders/") && path.includes("/crush");
}

export function shouldQueueError(err) {
  if (!err) return false;
  if (!err.response && (err.code === "ERR_NETWORK" || err.message === "Network Error" || !navigator.onLine)) return true;
  if (err.response?.status >= 500) return false;
  return false;
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
          data: item.data,
          headers: item.headers,
          skipOfflineQueue: true,
        });
        await removeAction(item.id);
        flushed += 1;
      } catch (err) {
        console.error("[offline] flush item failed id=%s", item.id, err);
        if (shouldQueueError(err)) break;
        item.tries = (item.tries || 0) + 1;
        if (item.tries >= 8) await removeAction(item.id);
      }
    }
  } finally {
    flushing = false;
    window.dispatchEvent(new CustomEvent("bf-offline-queue"));
  }
  const left = (await listQueue()).length;
  return { flushed, left };
}
