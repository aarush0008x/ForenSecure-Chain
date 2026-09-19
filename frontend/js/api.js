/**
 * ForenSecure Chain — Production API Service Layer
 * Direct connection to FastAPI backend (Default: http://127.0.0.1:8000)
 * NO MOCK DATA. ZERO DEMO FABRICATION.
 */

const API_BASE = window.VITE_API_BASE_URL || "http://127.0.0.1:8000";

class ApiService {
  constructor() {
    this.supabaseClient = null;
    this.authConfig = null;
    this.configPromise = this.fetchAuthConfig();
  }

  async fetchAuthConfig() {
    try {
      const res = await fetch(`${API_BASE}/api/auth/config`);
      if (res.ok) {
        this.authConfig = await res.json();
        if (this.authConfig.supabase_enabled && window.supabase && typeof window.supabase.createClient === "function") {
          this.supabaseClient = window.supabase.createClient(
            this.authConfig.supabase_url,
            this.authConfig.supabase_anon_key
          );
        }
      }
    } catch (e) {
      console.warn("Could not retrieve auth config from backend:", e);
    }
    return this.authConfig;
  }

  async isSupabaseConfigured() {
    if (!this.authConfig) {
      await this.configPromise;
    }
    return Boolean(this.supabaseClient);
  }


  getToken() {
    return localStorage.getItem("forensecure_jwt_token");
  }

  setToken(token) {
    localStorage.setItem("forensecure_jwt_token", token);
  }

  clearAuth() {
    localStorage.removeItem("forensecure_jwt_token");
    localStorage.removeItem("forensecure_user_cache");
  }

  getUserCache() {
    try {
      const raw = localStorage.getItem("forensecure_user_cache");
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  setUserCache(user) {
    try {
      localStorage.setItem("forensecure_user_cache", JSON.stringify(user));
    } catch {}
  }

  async request(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const headers = options.headers || {};

    const token = this.getToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    try {
      const response = await fetch(url, { ...options, headers });

      if (response.status === 401 && !endpoint.includes("/auth/login") && !endpoint.includes("/auth/signup")) {
        this.clearAuth();
        if (!window.location.pathname.endsWith("index.html") && !window.location.pathname.endsWith("/")) {
          window.location.href = "index.html";
        }
        throw new Error("Session expired. Please authenticate.");
      }

      if (!response.ok) {
        let errMessage = `HTTP ${response.status}: ${response.statusText}`;
        try {
          const json = await response.json();
          if (json.detail) {
            errMessage = typeof json.detail === "string" ? json.detail : JSON.stringify(json.detail);
          }
        } catch {}
        throw new Error(errMessage);
      }

      const contentType = response.headers.get("content-type");
      if (contentType && contentType.includes("application/json")) {
        return await response.json();
      }
      return response;
    } catch (err) {
      if (err.message.includes("Failed to fetch") || err.name === "TypeError") {
        throw new Error(`Unable to connect to backend at ${API_BASE}. Ensure the FastAPI server is running.`);
      }
      throw err;
    }
  }

  // Real Authentication: Supabase Cloud Auth + Local Cryptographic Ledger Synchronization
  async login(email, password) {
    const isConfigured = await this.isSupabaseConfigured();
    if (isConfigured && this.supabaseClient) {
      const { data, error } = await this.supabaseClient.auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (error) {
        throw new Error(`Supabase Auth Error: ${error.message}`);
      }
      if (data && data.user) {
        // Synchronize authenticated Supabase user profile into local ledger & database
        const syncRes = await this.request("/api/auth/supabase-sync", {
          method: "POST",
          body: JSON.stringify({
            supabase_id: data.user.id,
            email: data.user.email,
            name: data.user.user_metadata?.name || data.user.email.split("@")[0],
            role: data.user.user_metadata?.role || "investigator",
          }),
        });
        this.setToken(syncRes.access_token);
        this.setUserCache(syncRes.user);
        return syncRes;
      }
    }

    // Direct backend authentication fallback
    const res = await this.request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: email.trim(), password }),
    });
    this.setToken(res.access_token);
    this.setUserCache(res.user);
    return res;
  }

  async signUp({ name, email, password, role }) {
    const isConfigured = await this.isSupabaseConfigured();
    if (isConfigured && this.supabaseClient) {
      const { data, error } = await this.supabaseClient.auth.signUp({
        email: email.trim(),
        password,
        options: {
          data: {
            name: name.trim(),
            role: role || "investigator",
          },
        },
      });


      if (error) {
        throw new Error(`Supabase Signup Error: ${error.message}`);
      }

      if (data && data.user) {
        // Synchronize created Supabase user to ForenSecure Chain ledger
        const syncRes = await this.request("/api/auth/supabase-sync", {
          method: "POST",
          body: JSON.stringify({
            supabase_id: data.user.id,
            email: data.user.email,
            name: name.trim() || data.user.email.split("@")[0],
            role: role || "investigator",
          }),
        });
        this.setToken(syncRes.access_token);
        this.setUserCache(syncRes.user);
        return syncRes;
      }
    }

    // Direct backend cryptographic registration
    const res = await this.request("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({
        name: name.trim(),
        email: email.trim(),
        password,
        role: role || "investigator",
      }),
    });
    this.setToken(res.access_token);
    this.setUserCache(res.user);
    return res;
  }

  async logout() {
    if (this.isSupabaseConfigured()) {
      try {
        await this.supabaseClient.auth.signOut();
      } catch (e) {}
    }
    try {
      await this.request("/api/auth/logout", { method: "POST" });
    } catch {}
    this.clearAuth();
  }


  async getMe() {
    const user = await this.request("/api/auth/me");
    this.setUserCache(user);
    return user;
  }

  // System Health
  async getHealth() {
    try {
      return await this.request("/api/health");
    } catch (e) {
      return { status: "offline", error: e.message };
    }
  }

  // Cases
  async listCases() {
    return await this.request("/api/cases");
  }

  async getCase(caseId) {
    return await this.request(`/api/cases/${caseId}`);
  }

  async createCase(caseData) {
    return await this.request("/api/cases", {
      method: "POST",
      body: JSON.stringify(caseData),
    });
  }

  async updateLegalHold(caseId, legalHold) {
    return await this.request(`/api/cases/${caseId}/legal-hold?legal_hold=${legalHold}`, {
      method: "PATCH",
    });
  }

  async registerDevice(caseId, deviceData) {
    return await this.request(`/api/cases/${caseId}/devices`, {
      method: "POST",
      body: JSON.stringify(deviceData),
    });
  }

  async acquireEvidence(caseId, deviceId, file) {
    const formData = new FormData();
    formData.append("upload", file);
    let url = `/api/cases/${caseId}/evidence`;
    if (deviceId) url += `?device_id=${encodeURIComponent(deviceId)}`;
    return await this.request(url, {
      method: "POST",
      body: formData,
    });
  }

  async getCaseTimeline(caseId) {
    return await this.request(`/api/cases/${caseId}/timeline`);
  }

  async getCaseReport(caseId) {
    return await this.request(`/api/cases/${caseId}/report`);
  }

  getCaseReportPdfUrl(caseId) {
    return `${API_BASE}/api/cases/${encodeURIComponent(caseId)}/report/pdf`;
  }

  // Evidence Files
  async listFiles() {
    return await this.request("/api/files");
  }

  async getFile(fileId) {
    return await this.request(`/api/files/${fileId}`);
  }

  async uploadFile(file) {
    const formData = new FormData();
    formData.append("upload", file);
    return await this.request("/api/files/upload", {
      method: "POST",
      body: formData,
    });
  }

  // File Recovery
  async scanRecovery(fileId) {
    return await this.request(`/api/recovery/scan/${fileId}`, {
      method: "POST",
    });
  }

  async getRecoveryResults(recoveryId) {
    return await this.request(`/api/recovery/results/${recoveryId}`);
  }

  // Two-Person Approvals
  async listApprovals() {
    return await this.request("/api/approvals");
  }

  async requestApproval(caseId, targetId, method, targetType = "file", note = "") {
    return await this.request(`/api/cases/${caseId}/approval-request`, {
      method: "POST",
      body: JSON.stringify({
        target_id: targetId,
        target_type: targetType,
        sanitization_method: method,
        note,
      }),
    });
  }

  async approve(approvalId, note = "") {
    return await this.request(`/api/approvals/${approvalId}/approve`, {
      method: "POST",
      body: JSON.stringify({ note }),
    });
  }

  async reject(approvalId, note = "") {
    return await this.request(`/api/approvals/${approvalId}/reject`, {
      method: "POST",
      body: JSON.stringify({ note }),
    });
  }

  // Sanitization & Verification
  async executeSanitization(approvalId) {
    return await this.request(`/api/sanitization/${approvalId}/execute`, {
      method: "POST",
    });
  }

  async getCertificate(id) {
    return await this.request(`/api/sanitization/${id}/certificate`);
  }

  getCertificatePdfUrl(id) {
    return `${API_BASE}/api/sanitization/${encodeURIComponent(id)}/certificate/pdf`;
  }

  async verifyToken(token) {
    return await this.request(`/api/sanitization/verify/${encodeURIComponent(token)}`);
  }

  async verifyFileHash(fileId) {
    return await this.request(`/api/verification/${fileId}`, {
      method: "POST",
    });
  }

  // Ledger
  async getLedgerBlocks() {
    return await this.request("/api/blockchain/blocks");
  }

  async verifyLedgerChain() {
    return await this.request("/api/blockchain/verify");
  }
}

window.api = new ApiService();
