const TOKEN_RE = /^[0-9a-f]{16}$/i;

export function parseScannedValue(raw) {
  const text = String(raw || "").trim();
  if (!text) return "";
  const marker = "/b/";
  const idx = text.indexOf(marker);
  if (idx >= 0) {
    return text.slice(idx + marker.length).split("?")[0].split("#")[0].replace(/\/+$/, "");
  }
  return text.replace(/^\/+|\/+$/g, "");
}

export function normalizeToken(raw) {
  const token = parseScannedValue(raw).toLowerCase();
  return TOKEN_RE.test(token) ? token : "";
}

export function dossierPath(token) {
  const clean = normalizeToken(token);
  return clean ? `/b/${clean}` : "";
}

export function drawingHref(url, backendUrl) {
  if (!url) return "";
  if (/^https?:\/\//i.test(url)) return url;
  const root = String(backendUrl || "").replace(/\/+$/, "");
  return `${root}${url.startsWith("/") ? url : `/${url}`}`;
}
