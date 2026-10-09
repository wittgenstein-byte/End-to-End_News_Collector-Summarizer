/**
 * monitoring.js — Frontend Monitoring & Ops Controller (ES Module)
 *
 * Responsibilities:
 * - Admin Authentication flow (Token lifecycle)
 * - Real-time metrics querying and rendering
 * - WebSocket live event stream listener
 * - Interactive actions (Trigger Scrape, Clear Caches, Test Source)
 */

import { API_BASE, SOCKET_URL } from "./config.js";

// ── State ───────────────────────────────────────────────────────────
const STORAGE_TOKEN_KEY = "newsroom_monitoring_token";
let currentToken = localStorage.getItem(STORAGE_TOKEN_KEY) || sessionStorage.getItem(STORAGE_TOKEN_KEY) || "";
let autoRefreshTimer = null;
let autoRefreshEnabled = true;
let autoScrollLogs = true;
let socketInstance = null;
const displayedLogIds = new Set();

// ── DOM References ──────────────────────────────────────────────────
const authView = document.getElementById("auth-view");
const dashboardView = document.getElementById("dashboard-view");
const authForm = document.getElementById("auth-form");
const adminKeyInput = document.getElementById("admin-key-input");
const togglePwdBtn = document.getElementById("toggle-pwd-btn");
const authError = document.getElementById("auth-error");
const authErrorMsg = document.getElementById("auth-error-msg");
const authSubmitBtn = document.getElementById("auth-submit-btn");

const autoRefreshToggle = document.getElementById("auto-refresh-toggle");
const manualRefreshBtn = document.getElementById("manual-refresh-btn");
const refreshIcon = document.getElementById("refresh-icon");
const logoutBtn = document.getElementById("logout-btn");
const triggerScrapeBtn = document.getElementById("trigger-scrape-btn");
const scrapeBtnIcon = document.getElementById("scrape-btn-icon");
const clearCacheBtn = document.getElementById("clear-cache-btn");

const wsIndicatorDot = document.getElementById("ws-indicator-dot");
const wsIndicatorLabel = document.getElementById("ws-indicator-label");

const metricUptime = document.getElementById("metric-uptime");
const metricTotalNews = document.getElementById("metric-total-news");
const metricTotalSeen = document.getElementById("metric-total-seen");
const metricTotalMd = document.getElementById("metric-total-md");

const metricScraperStatus = document.getElementById("metric-scraper-status");
const metricCyclesCount = document.getElementById("metric-cycles-count");
const metricInterval = document.getElementById("metric-interval");
const metricLastCycle = document.getElementById("metric-last-cycle");

const metricCacheRate = document.getElementById("metric-cache-rate");
const metricCache304 = document.getElementById("metric-cache-304");
const metricCache200 = document.getElementById("metric-cache-200");
const metricSummaryHits = document.getElementById("metric-summary-hits");

const metricTotalClicks = document.getElementById("metric-total-clicks");
const metricTotalSummaries = document.getElementById("metric-total-summaries");
const metricTotalBookmarks = document.getElementById("metric-total-bookmarks");
const metricEngagedCount = document.getElementById("metric-engaged-count");

const sourcesTableBody = document.getElementById("sources-table-body");
const sourcesSummaryCount = document.getElementById("sources-summary-count");

const terminalLogs = document.getElementById("terminal-logs");
const clearLogsBtn = document.getElementById("clear-logs-btn");
const autoScrollToggle = document.getElementById("auto-scroll-toggle");

const toastBar = document.getElementById("toast-bar");
const toastText = document.getElementById("toast-text");
const toastIcon = document.getElementById("toast-icon");
let toastTimeout = null;

// ── Toast Helper ────────────────────────────────────────────────────
function showToast(message, type = "info") {
  if (toastTimeout) clearTimeout(toastTimeout);

  toastText.textContent = message;
  if (type === "success") {
    toastIcon.textContent = "check_circle";
    toastIcon.className = "material-symbols-outlined text-[18px] text-emerald-500";
  } else if (type === "error") {
    toastIcon.textContent = "error";
    toastIcon.className = "material-symbols-outlined text-[18px] text-error";
  } else {
    toastIcon.textContent = "info";
    toastIcon.className = "material-symbols-outlined text-[18px] text-primary";
  }

  toastBar.classList.remove("translate-y-[-100px]", "opacity-0");
  toastBar.classList.add("translate-y-0", "opacity-100");

  toastTimeout = setTimeout(() => {
    toastBar.classList.remove("translate-y-0", "opacity-100");
    toastBar.classList.add("translate-y-[-100px]", "opacity-0");
  }, 3500);
}

// ── Time & Formatting Helpers ───────────────────────────────────────
function formatUptime(seconds) {
  if (!seconds || seconds < 0) return "0s";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;

  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// ── Auth Handling ───────────────────────────────────────────────────
function showAuthView() {
  authView.classList.remove("hidden");
  dashboardView.classList.add("hidden");
  dashboardView.classList.remove("flex");
  stopAutoRefresh();
  if (adminKeyInput) adminKeyInput.focus();
}

function showDashboardView() {
  authView.classList.add("hidden");
  dashboardView.classList.remove("hidden");
  dashboardView.classList.add("flex");
  initSocket();
  loadStats();
  startAutoRefresh();
}

async function verifyToken(token) {
  if (!token) return false;
  try {
    const res = await fetch(`${API_BASE}/api/monitoring/verify`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return res.ok;
  } catch (e) {
    return false;
  }
}

async function handleLogin() {
  const key = adminKeyInput.value.trim();
  if (!key) return;

  authSubmitBtn.disabled = true;
  authSubmitBtn.innerHTML = `
    <span class="inline-block animate-spin material-symbols-outlined text-[18px]">progress_activity</span>
    <span>กำลังตรวจสอบ...</span>
  `;
  authError.classList.add("hidden");

  try {
    const res = await fetch(`${API_BASE}/api/monitoring/auth`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key }),
    });

    const data = await res.json();
    if (res.ok && data.token) {
      currentToken = data.token;
      localStorage.setItem(STORAGE_TOKEN_KEY, currentToken);
      showToast("เข้าสู่ระบบเรียบร้อยแล้ว", "success");
      showDashboardView();
    } else {
      authErrorMsg.textContent = data.detail || "รหัสผ่านไม่ถูกต้อง";
      authError.classList.remove("hidden");
    }
  } catch (err) {
    authErrorMsg.textContent = "เชื่อมต่อระบบไม่ได้: " + err.message;
    authError.classList.remove("hidden");
  } finally {
    authSubmitBtn.disabled = false;
    authSubmitBtn.innerHTML = `
      <span class="material-symbols-outlined text-[18px]">lock_open</span>
      <span>เข้าสู่ระบบคอนโซล</span>
    `;
  }
}

function handleLogout() {
  currentToken = "";
  localStorage.removeItem(STORAGE_TOKEN_KEY);
  sessionStorage.removeItem(STORAGE_TOKEN_KEY);
  if (socketInstance) {
    socketInstance.disconnect();
    socketInstance = null;
  }
  showToast("ออกจากระบบแล้ว", "info");
  showAuthView();
}

// ── Metrics & Stats Fetching ────────────────────────────────────────
async function loadStats() {
  if (!currentToken) return;

  refreshIcon.classList.add("animate-spin");
  try {
    const res = await fetch(`${API_BASE}/api/monitoring/stats`, {
      headers: { Authorization: `Bearer ${currentToken}` },
    });

    if (res.status === 401) {
      handleLogout();
      return;
    }

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    renderStats(data);
  } catch (e) {
    console.warn("Failed to load monitoring stats:", e);
    showToast("ดึงสถิติล้มเหลว: " + e.message, "error");
  } finally {
    setTimeout(() => refreshIcon.classList.remove("animate-spin"), 400);
  }
}

function renderStats(data) {
  // 1. System & Storage
  metricUptime.textContent = formatUptime(data.system?.uptime_seconds);
  metricTotalNews.textContent = (data.system?.total_news_articles ?? 0).toLocaleString();
  metricTotalSeen.textContent = (data.system?.total_seen_urls ?? 0).toLocaleString();
  metricTotalMd.textContent = (data.system?.collected_md_count ?? 0).toLocaleString();

  // 2. Scraper Engine
  const isScraping = data.scraper?.is_scraping;
  if (isScraping) {
    metricScraperStatus.innerHTML = `
      <span class="w-3 h-3 rounded-full bg-amber-500 animate-ping"></span>
      <span class="text-lg text-amber-600">กำลังดึงข่าว...</span>
    `;
  } else {
    metricScraperStatus.innerHTML = `
      <span class="w-3 h-3 rounded-full bg-emerald-500"></span>
      <span class="text-lg text-emerald-600">พร้อมทำงาน (Idle)</span>
    `;
  }
  metricCyclesCount.textContent = (data.scraper?.total_cycles_completed ?? 0).toLocaleString();
  metricInterval.textContent = `${data.scraper?.interval_minutes ?? 15} นาที`;
  metricLastCycle.textContent = data.scraper?.last_cycle_finished_at || data.scraper?.last_cycle_started_at || "—";

  // 3. Cache Performance
  const httpStats = data.caches?.http_cache || {};
  const cache304 = httpStats.hits_304 || 0;
  const cache200 = httpStats.fetches_200 || 0;
  const totalHttp = cache304 + cache200;
  const hitRate = totalHttp > 0 ? Math.round((cache304 / totalHttp) * 100) : 0;

  metricCacheRate.textContent = `${hitRate}%`;
  metricCache304.textContent = cache304.toLocaleString();
  metricCache200.textContent = cache200.toLocaleString();

  const summaryStats = data.caches?.summary_cache || {};
  const sumHits = summaryStats.hits || 0;
  const sumMisses = summaryStats.misses || 0;
  metricSummaryHits.textContent = `${sumHits.toLocaleString()} / ${sumMisses.toLocaleString()}`;

  // 4. Reader Engagement
  const eng = data.engagement || {};
  metricTotalClicks.textContent = (eng.total_clicks ?? 0).toLocaleString();
  metricTotalSummaries.textContent = (eng.total_summaries ?? 0).toLocaleString();
  metricTotalBookmarks.textContent = (eng.total_bookmarks ?? 0).toLocaleString();
  metricEngagedCount.textContent = (eng.top_articles?.length ?? 0).toLocaleString();

  // 5. Sources Table
  renderSourcesTable(data.scraper?.sources || []);

  // 6. Recent Logs
  if (data.scraper?.recent_logs && Array.isArray(data.scraper.recent_logs)) {
    data.scraper.recent_logs.forEach(log => appendTerminalLog(log));
  }
}

function renderSourcesTable(sources) {
  if (!sources || sources.length === 0) {
    sourcesTableBody.innerHTML = `
      <tr>
        <td colspan="7" class="py-6 text-center text-outline">ไม่พบข้อมูลสำนักข่าว</td>
      </tr>
    `;
    return;
  }

  sourcesSummaryCount.textContent = `ทั้งหมด ${sources.length} แหล่งข่าว`;

  sourcesTableBody.innerHTML = sources.map(src => {
    // Status Badge
    let statusBadge = "";
    if (src.status === "success") {
      statusBadge = `
        <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-700 font-bold text-[11px]">
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> ปกติ (Success)
        </span>
      `;
    } else if (src.status === "not_modified") {
      statusBadge = `
        <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-700 font-bold text-[11px]">
          <span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span> 304 ไม่เปลี่ยน
        </span>
      `;
    } else if (src.status === "error") {
      statusBadge = `
        <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-error-container text-on-error-container font-bold text-[11px]">
          <span class="w-1.5 h-1.5 rounded-full bg-error"></span> มีข้อผิดพลาด
        </span>
      `;
    } else {
      statusBadge = `
        <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-surface-container text-outline font-bold text-[11px]">
          <span class="w-1.5 h-1.5 rounded-full bg-outline"></span> รอทำงาน
        </span>
      `;
    }

    const lastTime = src.last_scraped_at || "—";
    const freshCount = src.last_fresh_count ?? 0;
    const latency = src.last_duration_ms ? `${src.last_duration_ms} ms` : "—";
    const errorText = src.last_error ? `<span class="text-error font-mono text-[11px]">${escapeHtml(src.last_error)}</span>` : `<span class="text-outline">ปกติ</span>`;

    return `
      <tr class="hover:bg-surface-container-low transition-colors">
        <td class="py-3 px-5">
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" style="background-color: ${escapeHtml(src.color || '#3b82f6')}"></span>
            <div>
              <span class="font-bold text-on-surface block">${escapeHtml(src.name)}</span>
              <a href="${escapeHtml(src.url)}" target="_blank" rel="noopener noreferrer" class="text-[10px] text-outline hover:text-primary underline truncate max-w-[180px] block">
                ${escapeHtml(src.url)}
              </a>
            </div>
          </div>
        </td>
        <td class="py-3 px-4">${statusBadge}</td>
        <td class="py-3 px-4 text-outline font-mono">${lastTime}</td>
        <td class="py-3 px-4 text-center font-bold font-mono ${freshCount > 0 ? 'text-primary' : 'text-outline'}">
          ${freshCount > 0 ? `+${freshCount}` : '0'}
        </td>
        <td class="py-3 px-4 text-center text-outline font-mono">${latency}</td>
        <td class="py-3 px-4 max-w-xs truncate">${errorText}</td>
        <td class="py-3 px-5 text-right">
          <button
            class="test-source-btn px-2.5 py-1 bg-surface-container-high hover:bg-primary hover:text-on-primary text-[11px] font-semibold rounded-lg border border-outline-variant/30 transition-all inline-flex items-center gap-1 active:scale-95"
            data-source="${escapeHtml(src.name)}"
          >
            <span class="material-symbols-outlined text-[13px]">play_arrow</span>
            <span>Test</span>
          </button>
        </td>
      </tr>
    `;
  }).join("");

  // Attach test click listeners
  sourcesTableBody.querySelectorAll(".test-source-btn").forEach(btn => {
    btn.addEventListener("click", () => handleTestSource(btn.dataset.source, btn));
  });
}

// ── Interactive Operations ──────────────────────────────────────────
async function handleTriggerScrape() {
  if (!currentToken) return;

  triggerScrapeBtn.disabled = true;
  scrapeBtnIcon.classList.add("animate-spin");
  try {
    const res = await fetch(`${API_BASE}/api/monitoring/scrape-now`, {
      method: "POST",
      headers: { Authorization: `Bearer ${currentToken}` },
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, "success");
      loadStats();
    } else {
      showToast(data.detail || "สั่งดึงข่าวไม่สำเร็จ", "error");
    }
  } catch (err) {
    showToast("เกิดข้อผิดพลาด: " + err.message, "error");
  } finally {
    setTimeout(() => {
      triggerScrapeBtn.disabled = false;
      scrapeBtnIcon.classList.remove("animate-spin");
    }, 1500);
  }
}

async function handleClearCache() {
  if (!confirm("ต้องการล้าง HTTP Cache และ AI Summary Cache ทั้งหมดหรือไม่?")) return;
  if (!currentToken) return;

  clearCacheBtn.disabled = true;
  try {
    const res = await fetch(`${API_BASE}/api/monitoring/clear-cache`, {
      method: "POST",
      headers: { Authorization: `Bearer ${currentToken}` },
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, "success");
      loadStats();
    } else {
      showToast(data.detail || "ล้างแคชไม่สำเร็จ", "error");
    }
  } catch (err) {
    showToast("เกิดข้อผิดพลาด: " + err.message, "error");
  } finally {
    clearCacheBtn.disabled = false;
  }
}

async function handleTestSource(sourceName, buttonEl) {
  if (!currentToken || !sourceName) return;

  const originalContent = buttonEl.innerHTML;
  buttonEl.disabled = true;
  buttonEl.innerHTML = `<span class="inline-block animate-spin material-symbols-outlined text-[13px]">progress_activity</span>`;

  try {
    const res = await fetch(`${API_BASE}/api/monitoring/test-source`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${currentToken}`,
      },
      body: JSON.stringify({ source: sourceName }),
    });

    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`ทดสอบ ${sourceName} สำเร็จ! พบ ${data.articles_count} บทความ (${data.duration_ms}ms)`, "success");
      appendTerminalLog({
        timestamp: new Date().toISOString().replace("T", " ").substring(0, 19),
        level: "SUCCESS",
        source: sourceName,
        message: `Isolated test passed: ${data.articles_count} articles in ${data.duration_ms}ms`,
      });
      loadStats();
    } else {
      const err = data.error || data.detail || "Failed to fetch";
      showToast(`ทดสอบ ${sourceName} ล้มเหลว: ${err}`, "error");
      appendTerminalLog({
        timestamp: new Date().toISOString().replace("T", " ").substring(0, 19),
        level: "ERROR",
        source: sourceName,
        message: `Isolated test error: ${err}`,
      });
    }
  } catch (e) {
    showToast(`เกิดข้อผิดพลาดในการทดสอบ: ${e.message}`, "error");
  } finally {
    buttonEl.disabled = false;
    buttonEl.innerHTML = originalContent;
  }
}

// ── Real-Time Terminal Log Stream ───────────────────────────────────
function appendTerminalLog(log) {
  if (!log || !log.message) return;

  const logId = `${log.timestamp}-${log.source}-${log.message}`;
  if (displayedLogIds.has(logId)) return;
  displayedLogIds.add(logId);

  // Clear placeholder if first entry
  if (terminalLogs.children.length === 1 && terminalLogs.children[0].classList.contains("italic")) {
    terminalLogs.innerHTML = "";
  }

  let levelColor = "text-blue-400";
  if (log.level === "SUCCESS") levelColor = "text-emerald-400";
  else if (log.level === "WARN") levelColor = "text-amber-400";
  else if (log.level === "ERROR") levelColor = "text-red-400 font-bold";

  const row = document.createElement("div");
  row.className = "leading-relaxed break-words hover:bg-gray-900/50 px-1 py-0.5 rounded";
  row.innerHTML = `
    <span class="text-gray-500">[${escapeHtml(log.timestamp || "")}]</span>
    <span class="${levelColor} uppercase text-[11px] font-bold">[${escapeHtml(log.level || "INFO")}]</span>
    <span class="text-purple-400">&lt;${escapeHtml(log.source || "sys")}&gt;</span>
    <span class="text-gray-200">${escapeHtml(log.message)}</span>
  `;

  terminalLogs.appendChild(row);

  if (autoScrollLogs) {
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
  }
}

// ── WebSocket Integration ───────────────────────────────────────────
function initSocket() {
  if (socketInstance) return;
  /* global io */
  if (typeof io === "undefined") {
    console.warn("Socket.IO library not loaded");
    wsIndicatorDot.className = "w-2 h-2 rounded-full bg-amber-500";
    wsIndicatorLabel.textContent = "Socket Unavailable";
    return;
  }

  try {
    socketInstance = io(SOCKET_URL);

    socketInstance.on("connect", () => {
      wsIndicatorDot.className = "w-2 h-2 rounded-full bg-emerald-500 animate-pulse";
      wsIndicatorLabel.textContent = "WebSocket Live";
    });

    socketInstance.on("disconnect", () => {
      wsIndicatorDot.className = "w-2 h-2 rounded-full bg-red-500";
      wsIndicatorLabel.textContent = "Disconnected";
    });

    socketInstance.on("monitoring_log", log => {
      appendTerminalLog(log);
    });

    socketInstance.on("new_articles", data => {
      appendTerminalLog({
        timestamp: data.updated || new Date().toISOString().replace("T", " ").substring(0, 19),
        level: "SUCCESS",
        source: "scraper",
        message: `WebSocket event: Received ${data.count} new articles (Total in DB: ${data.total})`,
      });
      loadStats();
    });
  } catch (err) {
    console.warn("Socket connection failed:", err);
  }
}

// ── Polling & Auto Refresh ──────────────────────────────────────────
function startAutoRefresh() {
  stopAutoRefresh();
  if (autoRefreshEnabled) {
    autoRefreshTimer = setInterval(loadStats, 5000);
  }
}

function stopAutoRefresh() {
  if (autoRefreshTimer) {
    clearInterval(autoRefreshTimer);
    autoRefreshTimer = null;
  }
}

// ── Event Listeners & Startup ───────────────────────────────────────
function setupEvents() {
  authForm.addEventListener("submit", handleLogin);

  togglePwdBtn.addEventListener("click", () => {
    const isPwd = adminKeyInput.type === "password";
    adminKeyInput.type = isPwd ? "text" : "password";
    togglePwdBtn.querySelector("span").textContent = isPwd ? "visibility_off" : "visibility";
  });

  autoRefreshToggle.addEventListener("change", (e) => {
    autoRefreshEnabled = e.target.checked;
    if (autoRefreshEnabled) startAutoRefresh();
    else stopAutoRefresh();
  });

  manualRefreshBtn.addEventListener("click", loadStats);
  logoutBtn.addEventListener("click", handleLogout);
  triggerScrapeBtn.addEventListener("click", handleTriggerScrape);
  clearCacheBtn.addEventListener("click", handleClearCache);

  clearLogsBtn.addEventListener("click", () => {
    terminalLogs.innerHTML = `<div class="text-gray-500 italic">[Logs cleared]</div>`;
    displayedLogIds.clear();
  });

  autoScrollToggle.addEventListener("change", (e) => {
    autoScrollLogs = e.target.checked;
  });
}

async function init() {
  setupEvents();

  if (currentToken) {
    const isValid = await verifyToken(currentToken);
    if (isValid) {
      showDashboardView();
      return;
    }
  }

  showAuthView();
}

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", init);
