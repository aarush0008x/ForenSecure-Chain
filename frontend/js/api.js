const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export const API_BASE_URL = (window.FORENSECURE_API_URL || DEFAULT_API_BASE_URL).replace(/\/$/, "");

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), options.timeout || 30000);
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers, signal: controller.signal });
    const text = await response.text();
    let payload = null;
    try { payload = text ? JSON.parse(text) : null; } catch { payload = text; }
    if (!response.ok) {
      const detail = payload && typeof payload === "object" && payload.detail ? payload.detail : `Request failed (${response.status})`;
      throw new Error(detail);
    }
    return payload;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("The API request timed out. Check that the backend is running.");
    if (error instanceof TypeError) throw new Error(`Cannot reach the backend at ${API_BASE_URL}. Start FastAPI and try again.`);
    throw error;
  } finally { window.clearTimeout(timeoutId); }
}

export const api = {
  health: () => request("/api/files"),
  listFiles: () => request("/api/files"),
  getFile: (fileId) => request(`/api/files/${encodeURIComponent(fileId)}`),
  uploadFile: (file) => { const form = new FormData(); form.append("upload", file); return request("/api/files/upload", { method: "POST", body: form, timeout: 120000 }); },
  eraseFile: (fileId) => request(`/api/erasure/${encodeURIComponent(fileId)}`, { method: "POST", timeout: 120000 }),
  getCertificate: (fileId) => request(`/api/erasure/${encodeURIComponent(fileId)}/certificate`),
  scanRecovery: (fileId) => request("/api/recovery/scan", { method: "POST", body: JSON.stringify({ file_id: fileId }), timeout: 120000 }),
  getRecovery: (recoveryId) => request(`/api/recovery/results/${encodeURIComponent(recoveryId)}`),
  verifyFile: (fileId) => request(`/api/verification/${encodeURIComponent(fileId)}`, { timeout: 120000 }),
  listBlocks: () => request("/api/blockchain"),
  verifyChain: () => request("/api/blockchain/verify"),
  fileBlocks: (fileId) => request(`/api/blockchain/file/${encodeURIComponent(fileId)}`),
  auditTrail: (fileId) => request(`/api/audit/${encodeURIComponent(fileId)}`),
  report: (fileId) => request(`/api/reports/${encodeURIComponent(fileId)}`),
  reportDownloadUrl: (fileId) => `${API_BASE_URL}/api/reports/${encodeURIComponent(fileId)}/download`,
};
