import axios from "axios";
import { deviceId } from "./device";
import { enqueueAction, isFieldWrite, serializeRequestBody, shouldQueueError } from "./offlineQueue";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
export const API = `${BACKEND_URL}/api`;

function readToken() {
  return sessionStorage.getItem("bf_token") || localStorage.getItem("bf_token") || "";
}

const api = axios.create({ baseURL: API, withCredentials: true });

api.interceptors.request.use((config) => {
  const token = readToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  const dev = deviceId();
  if (dev) config.headers["X-Device-Id"] = dev;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const status = err.response?.status;
    const url = err.config?.url || "";
    const method = err.config?.method || "get";
    if (status === 401 && !url.includes("/auth/login") && !url.includes("/auth/public-config") && !url.includes("/auth/demo-login")) {
      sessionStorage.removeItem("bf_token");
      localStorage.removeItem("bf_token");
    }
    if (!err.config?.skipOfflineQueue && isFieldWrite(url, method) && shouldQueueError(err)) {
      try {
        const data = await serializeRequestBody(err.config?.data);
        await enqueueAction({ method, url, data, label: url });
        err.queuedOffline = true;
        err.response = {
          ...(err.response || {}),
          data: { detail: "Saved on this device — will sync when Wi-Fi returns." },
        };
      } catch (queueErr) {
        console.error("[api] offline enqueue failed", queueErr);
      }
    }
    return Promise.reject(err);
  }
);

export function storeToken(token) {
  if (token) sessionStorage.setItem("bf_token", token);
  localStorage.removeItem("bf_token");
}

export function clearToken() {
  sessionStorage.removeItem("bf_token");
  localStorage.removeItem("bf_token");
}

export function formatApiErrorDetail(detail, err) {
  if (err?.queuedOffline) return "Saved on this device — will sync when Wi-Fi returns.";
  if (detail == null) return "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).filter(Boolean).join(" ");
  if (detail && typeof detail.message === "string") return detail.message;
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

export default api;
