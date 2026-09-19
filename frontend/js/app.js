/**
 * ForenSecure Chain — Application Controller
 * High-fidelity Digital Forensics Workstation
 * STRICT REQUIREMENT: ZERO DEMO DATA. REAL DATA ONLY.
 */

let currentAuthenticatedUser = null;
let cachedCases = [];
let activeCaseDetail = null;

document.addEventListener("DOMContentLoaded", async () => {
  // Check auth
  const token = api.getToken();
  if (!token) {
    window.location.href = "index.html";
    return;
  }

  try {
    currentAuthenticatedUser = await api.getMe();
    renderUserProfile(currentAuthenticatedUser);
  } catch (err) {
    console.error("Session verification failed:", err);
    api.clearAuth();
    window.location.href = "index.html";
    return;
  }

  // Setup UI
  setupNavigation();
  setupLiveTime();
  setupGlobalModals();
  lucide.createIcons();

  // Load initial real data
  await refreshDashboardData();
});

// User Profile Rendering
function renderUserProfile(user) {
  if (!user) return;
  const initials = user.name
    ? user.name.split(" ").map(n => n[0]).join("").toUpperCase().substring(0, 2)
    : "OP";
  
  const avatarEl = document.getElementById("userAvatarInitials");
  if (avatarEl) avatarEl.innerText = initials;

  const nameEl = document.getElementById("sidebarUserName");
  if (nameEl) nameEl.innerText = user.name;

  const roleEl = document.getElementById("sidebarUserRole");
  if (roleEl) roleEl.innerText = formatRoleName(user.role);

  const greetingEl = document.getElementById("dashboardGreeting");
  if (greetingEl) {
    greetingEl.innerText = `Welcome back, ${user.name.split(" ")[0]}. Here's what's happening with your investigations today.`;
  }

  const sName = document.getElementById("settingsUserName");
  if (sName) sName.innerText = `${user.name} (${user.email})`;
  const sRole = document.getElementById("settingsUserRole");
  if (sRole) sRole.innerText = formatRoleName(user.role);
}

function formatRoleName(role) {
  if (!role) return "Investigator";
  return role.split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}

// Live Time Pill
function setupLiveTime() {
  const el = document.getElementById("liveTimestamp");
  function updateTime() {
    const now = new Date();
    const options = { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true };
    if (el) el.innerText = now.toLocaleString('en-US', options);
  }
  updateTime();
  setInterval(updateTime, 30000);
}

// Navigation Controller
function setupNavigation() {
  document.querySelectorAll(".nav-link").forEach((link) => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      const view = link.getAttribute("data-view");
      if (view) switchView(view);
    });
  });

  document.getElementById("btnLogout")?.addEventListener("click", async () => {
    await api.logout();
    window.location.href = "index.html";
  });

  document.getElementById("btnOpenNewCaseModal")?.addEventListener("click", () => {
    openNewCaseModal();
  });
}

function switchView(viewName) {
  document.querySelectorAll(".nav-link").forEach((link) => {
    if (link.getAttribute("data-view") === viewName) {
      link.classList.add("active");
    } else {
      link.classList.remove("active");
    }
  });

  document.querySelectorAll(".content-view").forEach((view) => {
    view.style.display = "none";
    view.classList.remove("active");
  });

  const targetView = document.getElementById(`view-${viewName}`);
  if (targetView) {
    targetView.style.display = "block";
    targetView.classList.add("active");
    // GSAP entrance transition
    if (typeof gsap !== "undefined") {
      gsap.fromTo(targetView, { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.25, ease: "power1.out" });
    }
  }

  // View specific data loaders
  if (viewName === "dashboard") refreshDashboardData();
  if (viewName === "cases") loadCasesView();
  if (viewName === "evidence") loadEvidenceView();
  if (viewName === "recovery") loadRecoveryView();
  if (viewName === "sanitization") loadSanitizationView();
  if (viewName === "approvals") loadApprovalsView();
  if (viewName === "timeline") loadTimelineView();
  if (viewName === "verification") loadVerificationView();
  if (viewName === "ledger") loadLedgerView();
  if (viewName === "reports") loadReportsView();

  lucide.createIcons();
}
window.switchView = switchView;

// Global Toast Notifications
function showToast(message, type = "info") {
  const existing = document.getElementById("appToastNotification");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.id = "appToastNotification";
  toast.style.cssText = `
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: #172337;
    color: #fff;
    padding: 12px 18px;
    border-radius: 8px;
    font-size: 13px;
    z-index: 1000;
    box-shadow: 0 8px 24px rgba(0,0,0,0.2);
    border: 1px solid #D9DEE5;
    border-left: 4px solid ${type === "error" ? "#A83232" : type === "success" ? "#23734A" : "#8F234F"};
    display: flex;
    align-items: center;
    gap: 10px;
  `;
  toast.innerText = message;
  document.body.appendChild(toast);

  if (typeof gsap !== "undefined") {
    gsap.fromTo(toast, { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.2 });
  }

  setTimeout(() => {
    if (typeof gsap !== "undefined") {
      gsap.to(toast, { opacity: 0, y: 16, duration: 0.2, onComplete: () => toast.remove() });
    } else {
      toast.remove();
    }
  }, 4000);
}
window.showToast = showToast;

// -------------------------------------------------------------
// 1. Dashboard View (REAL DATA ONLY - NO HARDCODED PLACEHOLDERS)
// -------------------------------------------------------------
async function refreshDashboardData() {
  try {
    const cases = await api.listCases();
    cachedCases = cases;
    document.getElementById("statActiveCases").innerText = cases.length;

    // Count evidence files across real storage
    const filesData = await api.listFiles();
    const totalEvidence = filesData.total || (filesData.items ? filesData.items.length : 0);
    document.getElementById("statEvidenceItems").innerText = totalEvidence;

    // Fetch real approvals
    const approvals = await api.listApprovals();
    const pendingCount = approvals.filter(a => a.status.startsWith("pending_")).length;
    document.getElementById("statPendingApprovals").innerText = pendingCount;

    const badge = document.getElementById("pendingApprovalsBadge");
    if (badge) {
      if (pendingCount > 0) {
        badge.style.display = "inline";
        badge.innerText = pendingCount;
      } else {
        badge.style.display = "none";
      }
    }

    // Fetch real ledger blocks
    const ledgerData = await api.getLedgerBlocks();
    const blocks = ledgerData.blocks || [];
    // Count recovery operations from real ledger
    const recoveryCount = blocks.filter(b => b.action.includes("recovery")).length;
    document.getElementById("statRecoveryJobs").innerText = recoveryCount;

    // Sync time
    const syncEl = document.getElementById("lastSyncTime");
    if (syncEl) syncEl.innerText = new Date().toLocaleTimeString();

    // Check system status
    const health = await api.getHealth();
    const ledgerVerify = await api.verifyLedgerChain();
    const ledgerPill = document.getElementById("ledgerStatusPill");
    if (ledgerPill) {
      if (ledgerVerify.valid) {
        ledgerPill.className = "status-indicator online";
        ledgerPill.innerHTML = '<span class="dot"></span> <span>Valid</span>';
      } else {
        ledgerPill.className = "status-indicator";
        ledgerPill.style.color = "var(--color-danger)";
        ledgerPill.innerHTML = '<span class="dot" style="background:var(--color-danger)"></span> <span>Tampered</span>';
      }
    }

    // Render Recent Cases table
    renderDashboardCasesTable(cases);

    // Render Recent Case Activity Feed from real ledger blocks
    renderDashboardActivityFeed(blocks);

    // Update dossier panel status
    const dossierRef = document.getElementById("dossierCaseRef");
    if (dossierRef) {
      dossierRef.innerText = cases.length > 0 ? cases[0].case_number : "READY FOR INGEST";
    }
  } catch (err) {
    console.error("Dashboard refresh error:", err);
    showToast(`Error connecting to backend: ${err.message}`, "error");
  } finally {
    lucide.createIcons();
  }
}
window.refreshDashboardData = refreshDashboardData;

function renderDashboardCasesTable(cases) {
  const tbody = document.querySelector("#dashboardCasesTable tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (!cases || cases.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7">
          <div class="empty-state">
            <div class="empty-state-icon"><i data-lucide="folder"></i></div>
            <div class="empty-state-title">No Active Cases</div>
            <p class="empty-state-desc">There are no forensic investigations registered in the database yet.</p>
            <button class="btn btn-burgundy btn-sm" onclick="openNewCaseModal()"><i data-lucide="plus"></i> Register First Case</button>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  cases.slice(0, 5).forEach((c) => {
    const tr = document.createElement("tr");
    const statusClass = getStatusBadgeClass(c.status);
    const holdBadge = c.legal_hold
      ? '<span class="badge-status badge-awaiting-approval">HOLD ACTIVE</span>'
      : '<span class="badge-status badge-sanitized">RELEASED</span>';

    tr.innerHTML = `
      <td><strong class="tag-mono" style="color:var(--color-burgundy); font-weight:600;">${escapeHtml(c.case_number)}</strong></td>
      <td>${escapeHtml(c.title)}</td>
      <td style="color:var(--text-secondary);">${c.investigator_id ? "Assigned Officer" : "Unassigned"}</td>
      <td><span class="badge-status ${statusClass}">${escapeHtml(c.status)}</span></td>
      <td>${holdBadge}</td>
      <td style="font-family:var(--font-mono); font-size:12px; color:var(--text-muted);">${new Date(c.created_at).toLocaleDateString()}</td>
      <td>
        <button class="btn btn-secondary btn-sm" onclick="openCaseDetail('${c.id}')">View Details</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function renderDashboardActivityFeed(blocks) {
  const feed = document.getElementById("dashboardActivityFeed");
  if (!feed) return;
  feed.innerHTML = "";

  if (!blocks || blocks.length === 0) {
    feed.innerHTML = `
      <div class="empty-state" style="padding: 20px;">
        <p class="empty-state-desc">No activity recorded yet in immutable ledger.</p>
      </div>
    `;
    return;
  }

  blocks.slice(-5).reverse().forEach((b) => {
    const item = document.createElement("div");
    item.className = "feed-item";
    const dateObj = new Date(b.timestamp);
    const timeStr = dateObj.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
    const isSuccess = b.action.includes("verification") || b.action.includes("sanitization") || b.action.includes("completed");

    item.innerHTML = `
      <span class="feed-time">${timeStr}</span>
      <div class="feed-icon ${isSuccess ? 'success' : 'burgundy'}">
        <i data-lucide="${isSuccess ? 'check' : 'activity'}" style="width:12px; height:12px;"></i>
      </div>
      <div class="feed-content">
        <div class="feed-title">${escapeHtml(formatActionTitle(b.action))}</div>
        <div class="feed-sub">Block #${b.block_index} • Hash: ${b.current_hash.substring(0, 12)}...</div>
      </div>
    `;
    feed.appendChild(item);
  });
}

function formatActionTitle(action) {
  return action.split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}

function getStatusBadgeClass(status) {
  const s = (status || "").toLowerCase();
  if (s.includes("open") || s.includes("investigation")) return "badge-under-investigation";
  if (s.includes("recovered") || s.includes("complete") || s.includes("verified")) return "badge-recovery-complete";
  if (s.includes("pending") || s.includes("awaiting")) return "badge-awaiting-approval";
  if (s.includes("closed") || s.includes("erased") || s.includes("rejected")) return "badge-closed";
  return "badge-under-investigation";
}

// -------------------------------------------------------------
// 2. Cases Management View
// -------------------------------------------------------------
async function loadCasesView() {
  const tbody = document.querySelector("#fullCasesTable tbody");
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:20px; color:var(--text-muted);">Querying database...</td></tr>';

  try {
    const cases = await api.listCases();
    cachedCases = cases;
    tbody.innerHTML = "";

    if (cases.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7">
            <div class="empty-state">
              <div class="empty-state-icon"><i data-lucide="folder"></i></div>
              <div class="empty-state-title">No Active Investigations</div>
              <p class="empty-state-desc">Register your first case to establish controlled chain of custody.</p>
              <button class="btn btn-burgundy btn-sm" onclick="openNewCaseModal()"><i data-lucide="plus"></i> Register New Case</button>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    cases.forEach((c) => {
      const tr = document.createElement("tr");
      const statusClass = getStatusBadgeClass(c.status);
      const holdBadge = c.legal_hold
        ? '<span class="badge-status badge-awaiting-approval">HOLD ACTIVE</span>'
        : '<span class="badge-status badge-sanitized">RELEASED</span>';

      tr.innerHTML = `
        <td><strong class="tag-mono" style="color:var(--color-burgundy);">${escapeHtml(c.case_number)}</strong></td>
        <td><strong>${escapeHtml(c.title)}</strong></td>
        <td style="color:var(--text-secondary);">${c.investigator_id ? "Assigned Officer" : "Unassigned"}</td>
        <td><span class="badge-status ${statusClass}">${escapeHtml(c.status)}</span></td>
        <td>${holdBadge}</td>
        <td style="font-family:var(--font-mono); font-size:12px; color:var(--text-muted);">${new Date(c.created_at).toISOString().replace("T", " ").substring(0, 19)}</td>
        <td style="display:flex; gap:6px;">
          <button class="btn btn-secondary btn-sm" onclick="openCaseDetail('${c.id}')">Inspect</button>
          <button class="btn btn-secondary btn-sm" onclick="toggleLegalHold('${c.id}', ${!c.legal_hold})">${c.legal_hold ? 'Release Hold' : 'Apply Hold'}</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" style="color:var(--color-danger); text-align:center; padding:20px;">${escapeHtml(err.message)}</td></tr>`;
  } finally {
    lucide.createIcons();
  }
}

async function toggleLegalHold(caseId, newState) {
  try {
    await api.updateLegalHold(caseId, newState);
    showToast(`Case legal hold set to: ${newState ? "ACTIVE" : "RELEASED"}`, "success");
    await loadCasesView();
    if (activeCaseDetail && activeCaseDetail.id === caseId) {
      await openCaseDetail(caseId);
    }
  } catch (err) {
    showToast(err.message, "error");
  }
}
window.toggleLegalHold = toggleLegalHold;

// -------------------------------------------------------------
// 3. Case Detail & Lifecycle Stepper
// -------------------------------------------------------------
async function openCaseDetail(caseId) {
  switchView("casedetail");
  try {
    const detail = await api.getCase(caseId);
    activeCaseDetail = detail;

    document.getElementById("caseDetailNumberBadge").innerText = detail.case_number;
    document.getElementById("caseDetailTitle").innerText = detail.title;
    document.getElementById("caseDetailDescription").innerText = detail.description || "No case description provided.";

    const holdBtn = document.getElementById("btnCaseToggleHold");
    if (holdBtn) {
      holdBtn.innerText = detail.legal_hold ? "Release Legal Hold" : "Apply Legal Hold";
      holdBtn.onclick = () => toggleLegalHold(detail.id, !detail.legal_hold);
    }

    const pdfBtn = document.getElementById("btnCaseDownloadPdf");
    if (pdfBtn) {
      pdfBtn.onclick = () => window.open(api.getCaseReportPdfUrl(detail.id), "_blank");
    }

    // Determine and animate lifecycle stage
    updateLifecycleStepper(detail);

    // Render devices
    renderCaseDevices(detail.devices || []);
    // Render files
    renderCaseFiles(detail.files || []);
  } catch (err) {
    showToast(`Failed to load case details: ${err.message}`, "error");
  } finally {
    lucide.createIcons();
  }
}
window.openCaseDetail = openCaseDetail;

function updateLifecycleStepper(caseDetail) {
  const nodes = document.querySelectorAll("#caseLifecycleStepper .stepper-node");
  const stages = ["registered", "acquired", "analyzed", "recovered", "reviewed", "approved", "sanitized"];
  
  // Real calculation based on case state
  let currentStageIndex = 0; // registered
  if (caseDetail.devices && caseDetail.devices.length > 0) currentStageIndex = 1; // acquired
  if (caseDetail.files && caseDetail.files.length > 0) currentStageIndex = 2; // analyzed
  if (caseDetail.files && caseDetail.files.some(f => f.status === "recovered")) currentStageIndex = 3;
  if (!caseDetail.legal_hold) currentStageIndex = 4; // reviewed
  if (caseDetail.files && caseDetail.files.some(f => f.status === "erased")) currentStageIndex = 6; // sanitized

  nodes.forEach((node, idx) => {
    node.classList.remove("active", "completed");
    if (idx < currentStageIndex) {
      node.classList.add("completed");
    } else if (idx === currentStageIndex) {
      node.classList.add("active");
      if (typeof gsap !== "undefined") {
        gsap.fromTo(node.querySelector(".stepper-circle"), { scale: 0.9 }, { scale: 1.1, repeat: 1, yoyo: true, duration: 0.3 });
      }
    }
  });
}

function renderCaseDevices(devices) {
  const tbody = document.querySelector("#caseDevicesTable tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  if (devices.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--text-muted); padding:16px;">No devices registered yet.</td></tr>';
    return;
  }
  devices.forEach(d => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${escapeHtml(d.device_type)}</strong></td>
      <td class="tag-mono">${escapeHtml(d.serial_or_identifier)}</td>
      <td><span class="hash-cell">${d.source_hash.substring(0, 16)}...</span></td>
      <td><span class="badge-status badge-valid">${escapeHtml(d.acquisition_status)}</span></td>
    `;
    tbody.appendChild(tr);
  });
}

function renderCaseFiles(files) {
  const tbody = document.querySelector("#caseFilesTable tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  if (files.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--text-muted); padding:16px;">No evidence files ingested yet.</td></tr>';
    return;
  }
  files.forEach(f => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${escapeHtml(f.original_filename)}</strong></td>
      <td style="font-size:12px; color:var(--text-secondary);">${f.file_size} bytes</td>
      <td>
        <span class="hash-cell">
          ${f.original_hash.substring(0, 16)}...
          <button class="hash-copy-btn" title="Copy full SHA-256" onclick="copyText('${f.original_hash}')"><i data-lucide="copy"></i></button>
        </span>
      </td>
      <td><span class="badge-status ${f.status === 'erased' ? 'badge-closed' : 'badge-valid'}">${escapeHtml(f.status)}</span></td>
    `;
    tbody.appendChild(tr);
  });
}

// -------------------------------------------------------------
// 4. Evidence Inventory View
// -------------------------------------------------------------
async function loadEvidenceView() {
  const tbody = document.querySelector("#fullEvidenceTable tbody");
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:20px; color:var(--text-muted);">Querying evidence storage...</td></tr>';

  try {
    const data = await api.listFiles();
    const files = data.items || [];
    tbody.innerHTML = "";

    if (files.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8">
            <div class="empty-state">
              <div class="empty-state-icon"><i data-lucide="file-search"></i></div>
              <div class="empty-state-title">No Evidence Registered</div>
              <p class="empty-state-desc">Upload a forensic image or disk dump to establish custody.</p>
              <button class="btn btn-burgundy btn-sm" onclick="openEvidenceIngestModal()"><i data-lucide="upload"></i> Ingest Evidence File</button>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    files.forEach((f) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><span class="tag-mono" style="font-size:11.5px;">${f.file_id.substring(0, 8)}...</span></td>
        <td><strong>${escapeHtml(f.original_filename)}</strong></td>
        <td><span class="badge-status badge-valid">${f.file_type || 'RAW BINARY'}</span></td>
        <td style="font-family:var(--font-mono); font-size:12px;">${f.file_size} B</td>
        <td>
          <span class="hash-cell">
            ${f.original_hash.substring(0, 16)}...
            <button class="hash-copy-btn" title="Copy full SHA-256" onclick="copyText('${f.original_hash}')"><i data-lucide="copy"></i></button>
          </span>
        </td>
        <td style="font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted);">${new Date(f.upload_timestamp).toISOString().substring(0, 16)}</td>
        <td><span class="badge-status ${f.status === 'erased' ? 'badge-closed' : 'badge-valid'}">${escapeHtml(f.status)}</span></td>
        <td style="display:flex; gap:6px;">
          <button class="btn btn-secondary btn-sm" onclick="runIntegrityCheck('${f.file_id}')">Verify</button>
          <button class="btn btn-secondary btn-sm" onclick="initiateSanitizationRequest('${f.file_id}')">Sanitize</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" style="color:var(--color-danger); text-align:center; padding:20px;">${escapeHtml(err.message)}</td></tr>`;
  } finally {
    lucide.createIcons();
  }
}

// -------------------------------------------------------------
// 5. File Recovery View (Read-Only Multi-Format Carving)
// -------------------------------------------------------------
function loadRecoveryView() {
  const form = document.getElementById("recoveryScanForm");
  if (!form) return;
  form.onsubmit = async (e) => {
    e.preventDefault();
    const fileInput = document.getElementById("recoveryDumpFileInput");
    if (!fileInput.files[0]) return;

    const btn = document.getElementById("btnRunCarverScan");
    const progressEl = document.getElementById("carvingProgressIndicator");
    const progressText = document.getElementById("carvingProgressText");

    btn.disabled = true;
    progressEl.style.display = "block";
    progressText.innerText = "Ingesting dump into controlled memory...";

    try {
      // Step 1: Real multipart upload
      const uploaded = await api.uploadFile(fileInput.files[0]);
      progressText.innerText = `Ingested (${uploaded.file_id.substring(0,8)}...). Scanning signatures (JPEG, PNG, PDF, ZIP, GIF)...`;

      // Step 2: Real scan call
      const scanRes = await api.scanRecovery(uploaded.file_id);
      renderRecoveredArtifacts(scanRes.recovered_files || []);
      showToast(`Recovery complete: ${scanRes.number_of_files_detected} artifacts carved!`, "success");
    } catch (err) {
      showToast(`Carving failure: ${err.message}`, "error");
    } finally {
      btn.disabled = false;
      progressEl.style.display = "none";
      lucide.createIcons();
    }
  };
}

function renderRecoveredArtifacts(artifacts) {
  const tbody = document.querySelector("#recoveredArtifactsTable tbody");
  const countEl = document.getElementById("carvedArtifactsCount");
  if (countEl) countEl.innerText = artifacts.length;
  if (!tbody) return;
  tbody.innerHTML = "";

  if (!artifacts || artifacts.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5">
          <div class="empty-state" style="padding:24px;">
            <p class="empty-state-desc">No recognizable file headers detected in the provided dump.</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  artifacts.forEach((art) => {
    const tr = document.createElement("tr");
    const formatLabel = art.metadata_info?.actual?.format || art.file_type;
    const boundary = art.metadata_info?.inferred?.boundary || "Signature boundary verified";

    tr.innerHTML = `
      <td><strong>${escapeHtml(art.recovered_filename)}</strong></td>
      <td><span class="badge-status badge-valid">${escapeHtml(formatLabel)}</span></td>
      <td style="font-family:var(--font-mono); font-size:12px;">${art.file_size} B</td>
      <td>
        <span class="hash-cell">
          ${art.recovered_hash.substring(0, 16)}...
          <button class="hash-copy-btn" title="Copy" onclick="copyText('${art.recovered_hash}')"><i data-lucide="copy"></i></button>
        </span>
      </td>
      <td style="font-size:12px; color:var(--text-secondary);">${escapeHtml(boundary)}</td>
    `;
    tbody.appendChild(tr);
  });
}

// -------------------------------------------------------------
// 6. Two-Person Approvals & Sanitization Queue View
// -------------------------------------------------------------
async function loadApprovalsView() {
  const tbody = document.querySelector("#dualApprovalsTable tbody");
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:20px; color:var(--text-muted);">Querying authorization queue...</td></tr>';

  try {
    const approvals = await api.listApprovals();
    tbody.innerHTML = "";

    if (approvals.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8">
            <div class="empty-state">
              <div class="empty-state-icon"><i data-lucide="shield-check"></i></div>
              <div class="empty-state-title">No Pending Approvals</div>
              <p class="empty-state-desc">There are no sanitization requests currently awaiting authorization.</p>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    approvals.forEach((a) => {
      const tr = document.createElement("tr");
      let actionHtml = "";

      if (a.status === "pending_first_approval") {
        actionHtml = `
          <button class="btn btn-burgundy btn-sm" onclick="handleApprove('${a.id}')">1st Officer Sign</button>
          <button class="btn btn-secondary btn-sm" onclick="handleReject('${a.id}')">Reject</button>
        `;
      } else if (a.status === "pending_second_approval") {
        actionHtml = `
          <button class="btn btn-burgundy btn-sm" onclick="handleApprove('${a.id}')">2nd Officer Sign</button>
          <button class="btn btn-secondary btn-sm" onclick="handleReject('${a.id}')">Reject</button>
        `;
      } else if (a.status === "approved") {
        actionHtml = `<span class="badge-status badge-valid">Dual Approved</span>`;
      } else {
        actionHtml = `<span class="badge-status badge-closed">Rejected</span>`;
      }

      tr.innerHTML = `
        <td class="tag-mono">${a.id.substring(0, 8)}...</td>
        <td><strong>${escapeHtml(a.case_id || 'Global')}</strong></td>
        <td><span class="hash-cell">${a.target_id.substring(0, 12)}...</span></td>
        <td style="color:var(--text-secondary); font-size:12px;">${a.requested_by.substring(0, 8)}...</td>
        <td>${a.first_approved_by ? `<span class="badge-status badge-valid">${a.first_approved_by.substring(0,6)}...</span>` : '<span style="color:var(--text-muted); font-size:11px;">Pending</span>'}</td>
        <td>${a.second_approved_by ? `<span class="badge-status badge-valid">${a.second_approved_by.substring(0,6)}...</span>` : '<span style="color:var(--text-muted); font-size:11px;">Pending</span>'}</td>
        <td><span class="badge-status ${getStatusBadgeClass(a.status)}">${escapeHtml(a.status)}</span></td>
        <td style="display:flex; gap:6px;">${actionHtml}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" style="color:var(--color-danger); text-align:center;">${escapeHtml(err.message)}</td></tr>`;
  } finally {
    lucide.createIcons();
  }
}

async function handleApprove(id) {
  try {
    await api.approve(id, "Forensic data sanitization authorized");
    showToast("Authorization signature recorded successfully.", "success");
    await loadApprovalsView();
  } catch (err) {
    showToast(err.message, "error");
  }
}
window.handleApprove = handleApprove;

async function handleReject(id) {
  try {
    await api.reject(id, "Rejected by reviewing officer");
    showToast("Request rejected.", "info");
    await loadApprovalsView();
  } catch (err) {
    showToast(err.message, "error");
  }
}
window.handleReject = handleReject;

// -------------------------------------------------------------
// 7. Sanitization Gate Execution View
// -------------------------------------------------------------
async function loadSanitizationView() {
  const tbody = document.querySelector("#sanitizationGateTable tbody");
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:20px; color:var(--text-muted);">Verifying dual authorizations...</td></tr>';

  try {
    const approvals = await api.listApprovals();
    tbody.innerHTML = "";

    if (approvals.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="5">
            <div class="empty-state">
              <div class="empty-state-icon"><i data-lucide="shield"></i></div>
              <div class="empty-state-title">No Sanitization Requests</div>
              <p class="empty-state-desc">Submit a sanitization request to start the two-person approval process.</p>
              <button class="btn btn-burgundy btn-sm" onclick="openRequestApprovalModal()"><i data-lucide="plus"></i> Request Sanitization Approval</button>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    approvals.forEach((a) => {
      const isApproved = a.status === "approved";
      const tr = document.createElement("tr");

      tr.innerHTML = `
        <td><strong class="tag-mono">${escapeHtml(a.target_id)}</strong></td>
        <td>${escapeHtml(a.sanitization_method)}</td>
        <td><span class="badge-status badge-sanitized">RELEASED</span></td>
        <td><span class="badge-status ${isApproved ? 'badge-valid' : 'badge-awaiting-approval'}">${isApproved ? '2 of 2 Approvals Granted' : 'Pending Authorization'}</span></td>
        <td>
          <button class="btn ${isApproved ? 'btn-burgundy' : 'btn-secondary'} btn-sm" ${!isApproved ? 'disabled title="Locked: Requires two-person sign-off"' : ''} onclick="executeSanitizationProcess('${a.id}')">
            ${isApproved ? '<i data-lucide="lock"></i> Execute Sanitization & Purge' : '🔒 Execution Locked'}
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" style="color:var(--color-danger); text-align:center;">${escapeHtml(err.message)}</td></tr>`;
  } finally {
    lucide.createIcons();
  }
}

async function executeSanitizationProcess(approvalId) {
  if (!confirm("CRITICAL WARNING:\n\nSanitization will PERMANENTLY overwrite and purge all data on this target with zero streams. This destructive action cannot be undone.\n\nProceed with execution?")) {
    return;
  }

  showToast("Executing zero-overwrite sanitization standard...", "info");
  try {
    const cert = await api.executeSanitization(approvalId);
    showToast(`Sanitization verified! Certificate issued: ${cert.certificate_number}`, "success");
    await loadSanitizationView();
    // Open reports view and offer download
    switchView("reports");
  } catch (err) {
    showToast(`Sanitization failed: ${err.message}`, "error");
  }
}
window.executeSanitizationProcess = executeSanitizationProcess;

// -------------------------------------------------------------
// 8. Activity Timeline View
// -------------------------------------------------------------
async function loadTimelineView() {
  const selector = document.getElementById("timelineCaseSelector");
  if (!selector) return;
  selector.innerHTML = "";
  cachedCases = await api.listCases();

  if (cachedCases.length === 0) {
    document.getElementById("fullTimelineContainer").innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon"><i data-lucide="clock"></i></div>
        <div class="empty-state-title">No Activity Events Available</div>
        <p class="empty-state-desc">Register a case and ingest evidence to begin timeline reconstruction.</p>
      </div>
    `;
    return;
  }

  cachedCases.forEach(c => {
    selector.innerHTML += `<option value="${c.id}">${c.case_number} - ${c.title}</option>`;
  });

  selector.onchange = (e) => fetchAndRenderTimeline(e.target.value);
  fetchAndRenderTimeline(cachedCases[0].id);
}

async function fetchAndRenderTimeline(caseId) {
  const container = document.getElementById("fullTimelineContainer");
  if (!container) return;
  container.innerHTML = "<p style='color:var(--text-muted); padding:20px;'>Querying event normalization engine...</p>";

  try {
    const data = await api.getCaseTimeline(caseId);
    const events = data.events || [];
    container.innerHTML = "";

    if (events.length === 0) {
      container.innerHTML = `
        <div class="empty-state" style="padding:20px;">
          <p class="empty-state-desc">No normalized activity events found for this investigation.</p>
        </div>
      `;
      return;
    }

    const timelineWrap = document.createElement("div");
    timelineWrap.className = "activity-feed";

    events.forEach(e => {
      const item = document.createElement("div");
      item.className = "feed-item";
      const ts = new Date(e.timestamp).toISOString().replace("T", " ").substring(0, 19);

      item.innerHTML = `
        <span class="feed-time" style="width:130px;">${ts}</span>
        <div class="feed-icon burgundy"><i data-lucide="clock" style="width:12px; height:12px;"></i></div>
        <div class="feed-content">
          <div class="feed-title"><strong>${escapeHtml(e.event_type.replace(/_/g, " ").toUpperCase())}</strong> • ${escapeHtml(e.source)}</div>
          <div class="feed-sub" style="color:var(--text-primary); font-family:var(--font-sans); font-size:13px; margin-top:2px;">${escapeHtml(e.description)}</div>
        </div>
      `;
      timelineWrap.appendChild(item);
    });
    container.appendChild(timelineWrap);
  } catch (err) {
    container.innerHTML = `<p style="color:var(--color-danger); padding:20px;">${escapeHtml(err.message)}</p>`;
  } finally {
    lucide.createIcons();
  }
}

// -------------------------------------------------------------
// 9. Hash Integrity Verification View
// -------------------------------------------------------------
function loadVerificationView() {
  const form = document.getElementById("hashVerifyForm");
  if (!form) return;

  form.onsubmit = async (e) => {
    e.preventDefault();
    const fileId = document.getElementById("verifyInputFileId").value.trim();
    const resultCard = document.getElementById("hashVerificationResultCard");
    resultCard.style.display = "block";
    resultCard.innerHTML = "<p style='color:var(--text-muted);'>Computing live SHA-256 digest from controlled disk storage...</p>";

    try {
      const res = await api.verifyFileHash(fileId);
      const isMatch = res.matches;

      resultCard.innerHTML = `
        <div style="border-left: 4px solid ${isMatch ? 'var(--color-success)' : 'var(--color-danger)'}; padding: 18px;">
          <div style="display:flex; align-items:center; gap:8px; margin-bottom:12px;">
            <i data-lucide="${isMatch ? 'check-circle' : 'alert-triangle'}" style="color:${isMatch ? 'var(--color-success)' : 'var(--color-danger)'}"></i>
            <h4 style="font-size:16px; font-weight:600; color:var(--text-primary);">${isMatch ? '✓ HASH VERIFIED — ZERO TAMPERING DETECTED' : '⚠ HASH MISMATCH DETECTED'}</h4>
          </div>
          <div style="margin-bottom:8px;">
            <span class="dossier-label">Baseline Original Hash:</span>
            <div class="tag-mono" style="font-size:12.5px; color:var(--color-primary);">${res.original_hash}</div>
          </div>
          <div style="margin-bottom:12px;">
            <span class="dossier-label">Current Storage Digest:</span>
            <div class="tag-mono" style="font-size:12.5px; color:var(--color-burgundy);">${res.current_hash}</div>
          </div>
          <p style="font-size:12.5px; color:var(--text-secondary);">
            Verification algorithm: SHA-256 (FIPS 180-4). State: <strong>${res.status}</strong>.
          </p>
        </div>
      `;
    } catch (err) {
      resultCard.innerHTML = `<p style="color:var(--color-danger);">${escapeHtml(err.message)}</p>`;
    } finally {
      lucide.createIcons();
    }
  };
}

function runIntegrityCheck(fileId) {
  switchView("verification");
  document.getElementById("verifyInputFileId").value = fileId;
  document.getElementById("hashVerifyForm").dispatchEvent(new Event("submit"));
}
window.runIntegrityCheck = runIntegrityCheck;

// -------------------------------------------------------------
// 10. Tamper-Evident Ledger View
// -------------------------------------------------------------
async function loadLedgerView() {
  const tbody = document.querySelector("#auditLedgerTable tbody");
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--text-muted);">Reading cryptographic block chain...</td></tr>';

  try {
    const data = await api.getLedgerBlocks();
    const blocks = data.blocks || [];
    tbody.innerHTML = "";

    if (blocks.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:20px;">No blocks recorded in ledger yet.</td></tr>';
      return;
    }

    blocks.forEach((b) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong class="tag-mono" style="color:var(--color-burgundy);">#${b.block_index}</strong></td>
        <td><span class="badge-status badge-valid">${escapeHtml(b.action)}</span></td>
        <td class="tag-mono" style="font-size:12px;">${b.actor_id || "System"}</td>
        <td><span class="hash-cell">${(b.previous_hash || "GENESIS_ROOT").substring(0, 16)}...</span></td>
        <td><span class="hash-cell">${b.current_hash.substring(0, 16)}...</span></td>
        <td style="font-family:var(--font-mono); font-size:12px; color:var(--text-muted);">${new Date(b.timestamp).toISOString().replace("T", " ").substring(0, 19)}</td>
      `;
      tbody.appendChild(tr);
    });

    const verifyBtn = document.getElementById("btnRecalculateChain");
    if (verifyBtn) {
      verifyBtn.onclick = async () => {
        const alertBox = document.getElementById("chainVerificationAlert");
        alertBox.style.display = "block";
        alertBox.className = "alert alert-success";
        alertBox.innerHTML = "<p>Recalculating SHA-256 block hashes from genesis block...</p>";

        try {
          const res = await api.verifyLedgerChain();
          if (res.valid) {
            alertBox.style.background = "var(--color-success-light)";
            alertBox.style.borderColor = "var(--color-success-border)";
            alertBox.style.color = "var(--color-success)";
            alertBox.innerHTML = `<strong>✓ CHAIN VERIFIED:</strong> All ${res.total_blocks} cryptographic links are unbroken. 0 integrity violations detected.`;
          } else {
            alertBox.style.background = "var(--color-danger-light)";
            alertBox.style.borderColor = "var(--color-danger-border)";
            alertBox.style.color = "var(--color-danger)";
            alertBox.innerHTML = `<strong>⚠ INTEGRITY VIOLATION DETECTED:</strong> ${res.invalid_blocks.length} corrupted or modified blocks found!`;
          }
        } catch (e) {
          alertBox.innerHTML = `<span style="color:var(--color-danger);">${e.message}</span>`;
        }
      };
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" style="color:var(--color-danger); text-align:center;">${escapeHtml(err.message)}</td></tr>`;
  }
}

// -------------------------------------------------------------
// 11. Reports & Certificates View
// -------------------------------------------------------------
async function loadReportsView() {
  const selector = document.getElementById("reportCaseSelector");
  if (!selector) return;
  selector.innerHTML = "";
  cachedCases = await api.listCases();

  cachedCases.forEach(c => {
    selector.innerHTML += `<option value="${c.id}">${c.case_number} - ${c.title}</option>`;
  });

  const btnPdf = document.getElementById("btnGenerateCaseReportPdf");
  if (btnPdf) {
    btnPdf.onclick = () => {
      const caseId = selector.value;
      if (caseId) window.open(api.getCaseReportPdfUrl(caseId), "_blank");
    };
  }

  // Token verify form
  const tokenForm = document.getElementById("tokenVerifyForm");
  if (tokenForm) {
    tokenForm.onsubmit = async (e) => {
      e.preventDefault();
      const token = document.getElementById("inputVerifyToken").value.trim();
      const resContainer = document.getElementById("tokenVerifyResult");
      resContainer.innerHTML = "<p style='color:var(--text-muted);'>Querying ledger...</p>";

      try {
        const cert = await api.verifyToken(token);
        resContainer.innerHTML = `
          <div style="background:var(--color-success-light); border:1px solid var(--color-success-border); padding:14px; border-radius:var(--radius-sm); font-size:12.5px;">
            <p style="color:var(--color-success); font-weight:600; margin-bottom:4px;">✓ VALID CERTIFICATE ANCHORED IN LEDGER</p>
            <p>Certificate No: <strong>${cert.certificate_number}</strong></p>
            <p>Target ID: <span class="tag-mono">${cert.target_id}</span></p>
            <p>Original Hash: <span class="tag-mono">${cert.original_hash.substring(0, 16)}...</span></p>
            <p>Method: <strong>${cert.method}</strong></p>
            <p>Issued: <strong>${new Date(cert.generated_at).toISOString()}</strong></p>
          </div>
        `;
      } catch (err) {
        resContainer.innerHTML = `<p style="color:var(--color-danger); font-size:12.5px;">${escapeHtml(err.message)}</p>`;
      }
    };
  }
}

// -------------------------------------------------------------
// Modals & Form Submission Helpers
// -------------------------------------------------------------
function setupGlobalModals() {
  // Create Case Form
  const caseForm = document.getElementById("formCreateCase");
  if (caseForm) {
    caseForm.onsubmit = async (e) => {
      e.preventDefault();
      try {
        const caseNumber = document.getElementById("modalCaseNumber").value.trim();
        const title = document.getElementById("modalCaseTitle").value.trim();
        const desc = document.getElementById("modalCaseDesc").value.trim();
        const legalHold = document.getElementById("modalCaseLegalHold").value === "true";

        await api.createCase({ case_number: caseNumber, title, description: desc, legal_hold: legalHold });
        showToast(`Case '${caseNumber}' registered in custody ledger!`, "success");
        closeModal("modalNewCase");
        caseForm.reset();
        await loadCasesView();
      } catch (err) {
        showToast(err.message, "error");
      }
    };
  }

  // Device Form
  const devForm = document.getElementById("formCreateDevice");
  if (devForm) {
    devForm.onsubmit = async (e) => {
      e.preventDefault();
      if (!activeCaseDetail) return;
      try {
        const devType = document.getElementById("modalDeviceType").value.trim();
        const serial = document.getElementById("modalDeviceSerial").value.trim();
        const hash = document.getElementById("modalDeviceHash").value.trim();

        await api.registerDevice(activeCaseDetail.id, {
          device_type: devType,
          serial_or_identifier: serial,
          source_hash: hash,
        });
        showToast("Evidence device & baseline hash committed.", "success");
        closeModal("modalNewDevice");
        devForm.reset();
        await openCaseDetail(activeCaseDetail.id);
      } catch (err) {
        showToast(err.message, "error");
      }
    };
  }

  // Ingest Evidence Form
  const ingestForm = document.getElementById("formIngestEvidence");
  if (ingestForm) {
    ingestForm.onsubmit = async (e) => {
      e.preventDefault();
      const caseId = document.getElementById("modalEvidenceCaseSelect").value;
      const fileInput = document.getElementById("modalEvidenceFileInput");
      if (!fileInput.files[0]) return;

      const btn = document.getElementById("btnSubmitIngest");
      btn.disabled = true;
      btn.innerText = "Hashing & Ingesting...";

      try {
        const res = await api.acquireEvidence(caseId, null, fileInput.files[0]);
        showToast(`Evidence '${res.original_filename}' ingested with SHA-256: ${res.original_hash.substring(0,12)}...`, "success");
        closeModal("modalIngestEvidence");
        ingestForm.reset();
        await loadEvidenceView();
        if (activeCaseDetail && activeCaseDetail.id === caseId) {
          await openCaseDetail(caseId);
        }
      } catch (err) {
        showToast(err.message, "error");
      } finally {
        btn.disabled = false;
        btn.innerText = "Upload & Hash Ingest";
      }
    };
  }

  // Request Approval Form
  const apprForm = document.getElementById("formRequestApproval");
  if (apprForm) {
    apprForm.onsubmit = async (e) => {
      e.preventDefault();
      const caseId = document.getElementById("modalApprovalCaseSelect").value;
      const targetId = document.getElementById("modalApprovalTargetId").value.trim();
      const method = document.getElementById("modalApprovalMethod").value;
      const note = document.getElementById("modalApprovalNote").value.trim();

      try {
        await api.requestApproval(caseId, targetId, method, "file", note);
        showToast("Sanitization request submitted for dual-officer authorization.", "success");
        closeModal("modalRequestApproval");
        apprForm.reset();
        await loadApprovalsView();
        await loadSanitizationView();
      } catch (err) {
        showToast(err.message, "error");
      }
    };
  }
}

function openNewCaseModal() {
  document.getElementById("modalNewCase")?.classList.add("open");
}
window.openNewCaseModal = openNewCaseModal;

function openDeviceRegisterModal() {
  document.getElementById("modalNewDevice")?.classList.add("open");
}
window.openDeviceRegisterModal = openDeviceRegisterModal;

function openEvidenceIngestModal() {
  const select = document.getElementById("modalEvidenceCaseSelect");
  if (select) {
    select.innerHTML = "";
    cachedCases.forEach(c => {
      select.innerHTML += `<option value="${c.id}">${c.case_number} - ${c.title}</option>`;
    });
    if (activeCaseDetail) select.value = activeCaseDetail.id;
  }
  document.getElementById("modalIngestEvidence")?.classList.add("open");
}
window.openEvidenceIngestModal = openEvidenceIngestModal;

function openRequestApprovalModal() {
  const select = document.getElementById("modalApprovalCaseSelect");
  if (select) {
    select.innerHTML = "";
    cachedCases.forEach(c => {
      select.innerHTML += `<option value="${c.id}">${c.case_number} (Hold: ${c.legal_hold ? 'ACTIVE' : 'RELEASED'})</option>`;
    });
  }
  document.getElementById("modalRequestApproval")?.classList.add("open");
}
window.openRequestApprovalModal = openRequestApprovalModal;

function openArchitectureModal() {
  document.getElementById("modalArchitecture")?.classList.add("open");
}
window.openArchitectureModal = openArchitectureModal;

function initiateSanitizationRequest(fileId) {
  openRequestApprovalModal();
  document.getElementById("modalApprovalTargetId").value = fileId;
}
window.initiateSanitizationRequest = initiateSanitizationRequest;

function closeModal(id) {
  document.getElementById(id)?.classList.remove("open");
}
window.closeModal = closeModal;

// Utility functions
function copyText(text) {
  navigator.clipboard.writeText(text);
  showToast("SHA-256 hash copied to clipboard!", "info");
}
window.copyText = copyText;

function escapeHtml(str) {
  if (!str) return "";
  return String(str).replace(/[&<>"']/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[m]);
}
