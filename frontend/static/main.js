/**
 * main.js — App controller (GRASP: Controller)
 *
 * หน้าที่: เชื่อม api.js กับ ui.js
 * ไม่ fetch เอง ไม่แตะ DOM โดยตรง
 * เป็น orchestrator เท่านั้น
 */

import { fetchNews, summarizeArticle, createSocket, fetchCategories, getSocket } from "./api.js";
import * as UI from "./UI.js";

// ── PDPA & Personalization ────────────────────────────────────────
const PDPA_KEY = "pdpa_consent";
let hasConsent = localStorage.getItem(PDPA_KEY) === "true";
let personalizationData = hasConsent ? JSON.parse(localStorage.getItem("personalization") || "{}") : {};
const SEARCH_HISTORY_KEY = "search_history";
let searchHistory = hasConsent ? JSON.parse(localStorage.getItem(SEARCH_HISTORY_KEY) || "[]") : [];

function savePersonalization() {
  if (hasConsent) {
    localStorage.setItem("personalization", JSON.stringify(personalizationData));
  }
}

window.__acceptCookies = () => {
  hasConsent = true;
  localStorage.setItem(PDPA_KEY, "true");
  document.getElementById("pdpa-banner").classList.add("translate-y-full");
  applyPersonalization();
};

window.__declineCookies = () => {
  hasConsent = false;
  localStorage.setItem(PDPA_KEY, "false");
  localStorage.removeItem("personalization");
  localStorage.removeItem(SEARCH_HISTORY_KEY);
  personalizationData = {};
  searchHistory = [];
  document.getElementById("pdpa-banner").classList.add("translate-y-full");
  document.documentElement.classList.remove("dark");
  document.documentElement.classList.add("light");
};

function checkPDPA() {
  const consent = localStorage.getItem(PDPA_KEY);
  if (consent === null) {
    setTimeout(() => {
      document.getElementById("pdpa-banner").classList.remove("translate-y-full");
    }, 1000);
  } else {
    hasConsent = consent === "true";
    if (hasConsent) applyPersonalization();
  }
  document.getElementById("setting-consent-status").textContent = consent === "true" ? "Accepted" : consent === "false" ? "Declined" : "Unknown";
}

function applyPersonalization() {
  if (personalizationData.darkMode) {
    document.documentElement.classList.add("dark");
    document.documentElement.classList.remove("light");
    const dmEl = document.getElementById("setting-darkmode");
    if (dmEl) dmEl.checked = true;
  }
  if (personalizationData.fontSize) {
    document.documentElement.style.fontSize = personalizationData.fontSize;
    const fsEl = document.getElementById("setting-fontsize");
    if (fsEl) fsEl.value = personalizationData.fontSize;
  }
  if (personalizationData.layoutDensity) {
    document.body.dataset.density = personalizationData.layoutDensity;
    const ldEl = document.getElementById("setting-density");
    if (ldEl) ldEl.value = personalizationData.layoutDensity;
  }
}

window.__openSettings = () => {
  document.getElementById("settings-modal").classList.remove("hidden");
  document.getElementById("settings-modal").classList.add("flex");
};

window.__closeSettings = () => {
  document.getElementById("settings-modal").classList.add("hidden");
  document.getElementById("settings-modal").classList.remove("flex");
};

window.__toggleDarkMode = (isDark) => {
  if (isDark) {
    document.documentElement.classList.add("dark");
    document.documentElement.classList.remove("light");
  } else {
    document.documentElement.classList.remove("dark");
    document.documentElement.classList.add("light");
  }
  personalizationData.darkMode = isDark;
  savePersonalization();
};

window.__changeFontSize = (size) => {
  document.documentElement.style.fontSize = size;
  personalizationData.fontSize = size;
  savePersonalization();
};

window.__changeLayoutDensity = (density) => {
  document.body.dataset.density = density;
  personalizationData.layoutDensity = density;
  savePersonalization();
};

window.__clearPersonalizationData = () => {
  localStorage.removeItem("personalization");
  localStorage.removeItem(PDPA_KEY);
  localStorage.removeItem(SEARCH_HISTORY_KEY);
  location.reload();
};

function saveSearchQuery(query) {
  if (!hasConsent || !query) return;
  searchHistory = searchHistory.filter(q => q !== query);
  searchHistory.unshift(query);
  if (searchHistory.length > 20) searchHistory.pop();
  localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(searchHistory));
}

// ── In-App Browser ────────────────────────────────────────────────
let currentTabId = null;
let browserTabs = [];
let tabStates = {};  // Cache tab states: { tabId: { html, url, title } }

// Date.now() alone can collide if the user clicks "new tab" twice within
// the same millisecond; add a random suffix so tab_id is unique enough to
// safely key server-side ownership tracking.
function makeTabId() {
  const rand = (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2)).slice(0, 8);
  return "tab_" + Date.now() + "_" + rand;
}

window.__openBrowser = () => {
  const modal = document.getElementById("browser-modal");
  modal.style.display = "flex";
  if (browserTabs.length === 0) window.__browserNewTab();
};

window.__openBrowserWithUrl = (url) => {
  if (!url) return;
  const modal = document.getElementById("browser-modal");
  const wasHidden = modal.style.display === "none" || !modal.style.display;
  modal.style.display = "flex";

  // If opening from closed state, clean start
  if (wasHidden && browserTabs.length > 0) {
    const socket = getSocket();
    if (socket) {
      browserTabs.forEach(id => socket.emit("browser_close_tab", { tab_id: id }));
    }
    browserTabs = [];
    tabStates = {};
    currentTabId = null;
  }

  // สร้าง tabId ใหม่
  const tabId = makeTabId();
  browserTabs.push(tabId);
  currentTabId = tabId;
  tabStates[tabId] = { html: "", url: url, title: "Loading..." };

  // แสดง loading ทันที
  document.getElementById("browser-iframe").srcdoc = "";
  document.getElementById("browser-url").value = url;
  document.getElementById("browser-loading").style.display = "flex";
  renderBrowserTabs();

  armBrowserLoadTimeout();

  // emit event เดียว — backend เปิด tab + navigate ในคำสั่งเดียว (ไม่มี race condition)
  const socket = getSocket();
  if (socket) {
    socket.emit("browser_open_and_navigate", { tab_id: tabId, url });
  }
};

window.__browserShowError = (msg) => {
  disarmBrowserLoadTimeout();
  const iframe = document.getElementById("browser-iframe");
  if (iframe) {
    iframe.srcdoc = `<div style="font-family:sans-serif;padding:20px;color:#b3261e;">⚠️ ${String(msg ?? "unknown error").replace(/&/g, "&amp;").replace(/</g, "&lt;")}</div>`;
  }
  const loading = document.getElementById("browser-loading");
  if (loading) loading.style.display = "none";
};

window.__browserOpenExternal = () => {
  const url = document.getElementById("browser-url").value;
  if (url) {
    window.open(url, "_blank", "noopener,noreferrer");
  }
};

window.__closeBrowser = () => {
  const modal = document.getElementById("browser-modal");
  modal.style.display = "none";
  const loading = document.getElementById("browser-loading");
  if (loading) loading.style.display = "none";
  disarmBrowserLoadTimeout();

  // Close backend tabs when user dismisses the in-app browser
  const socket = getSocket();
  if (socket && browserTabs.length > 0) {
    browserTabs.forEach(id => socket.emit("browser_close_tab", { tab_id: id }));
  }
  browserTabs = [];
  tabStates = {};
  currentTabId = null;
  const iframe = document.getElementById("browser-iframe");
  if (iframe) iframe.srcdoc = "";
  const urlInput = document.getElementById("browser-url");
  if (urlInput) urlInput.value = "";
};

window.__browserNewTab = () => {
  const tabId = makeTabId();
  browserTabs.push(tabId);
  currentTabId = tabId;
  tabStates[tabId] = { html: "", url: "", title: "New Tab" };
  const socket = getSocket();
  if (socket) socket.emit("browser_open_tab", { tab_id: tabId });
  document.getElementById("browser-iframe").srcdoc = "";
  document.getElementById("browser-url").value = "";
  document.getElementById("browser-loading").style.display = "none";
  renderBrowserTabs();
};

window.__browserSwitchTab = (tabId) => {
  // Save current tab state before switching
  if (currentTabId && tabStates[currentTabId]) {
    tabStates[currentTabId].html = document.getElementById("browser-iframe").srcdoc || "";
    tabStates[currentTabId].url = document.getElementById("browser-url").value || "";
  }
  currentTabId = tabId;
  renderBrowserTabs();
  // Restore cached state for the new tab
  const cached = tabStates[tabId];
  if (cached) {
    document.getElementById("browser-iframe").srcdoc = cached.html;
    document.getElementById("browser-url").value = cached.url;
  } else {
    document.getElementById("browser-iframe").srcdoc = "";
    document.getElementById("browser-url").value = "";
  }
  document.getElementById("browser-loading").style.display = "none";
};

window.__browserCloseTab = (tabId, event) => {
  event.stopPropagation();
  browserTabs = browserTabs.filter(id => id !== tabId);
  delete tabStates[tabId];
  const socket = getSocket();
  if (socket) socket.emit("browser_close_tab", { tab_id: tabId });
  if (currentTabId === tabId) {
    if (browserTabs.length > 0) {
      window.__browserSwitchTab(browserTabs[browserTabs.length - 1]);
    } else {
      window.__closeBrowser();
    }
  } else {
    renderBrowserTabs();
  }
};

window.__browserNavigate = (urlOverride) => {
  if (!currentTabId) return;
  let url = urlOverride || document.getElementById("browser-url").value;
  if (!url.startsWith("http")) url = "https://" + url;
  document.getElementById("browser-url").value = url;
  const socket = getSocket();
  if (socket) socket.emit("browser_navigate", { tab_id: currentTabId, url });
};

window.__browserBack = () => {
  if (!currentTabId) return;
  const socket = getSocket();
  if (socket) socket.emit("browser_go_back", { tab_id: currentTabId });
};

window.__browserForward = () => {
  if (!currentTabId) return;
  const socket = getSocket();
  if (socket) socket.emit("browser_go_forward", { tab_id: currentTabId });
};

window.__browserRefresh = () => {
  if (!currentTabId) return;
  const socket = getSocket();
  if (socket) socket.emit("browser_refresh", { tab_id: currentTabId });
};

window.__browserAddBookmark = () => {
  if (!hasConsent || !currentTabId) return;
  const url = document.getElementById("browser-url").value;
  if (!url) return;
  personalizationData.bookmarks = personalizationData.bookmarks || [];
  if (!personalizationData.bookmarks.includes(url)) {
    personalizationData.bookmarks.push(url);
    savePersonalization();
    document.getElementById("browser-bookmark-icon").textContent = "bookmark";
  } else {
    personalizationData.bookmarks = personalizationData.bookmarks.filter(u => u !== url);
    savePersonalization();
    document.getElementById("browser-bookmark-icon").textContent = "bookmark_border";
  }
};

function renderBrowserTabs() {
  const container = document.getElementById("browser-tabs");
  // Keep the add button
  const addButtonHtml = `<button class="p-1 hover:bg-surface-container rounded" onclick="window.__browserNewTab()"><span class="material-symbols-outlined text-sm">add</span></button>`;
  
  let tabsHtml = browserTabs.map((id, index) => {
    const isActive = id === currentTabId;
    return `
      <div class="flex items-center gap-2 px-3 py-1 rounded-t-lg border-t border-x border-outline-variant/30 text-sm cursor-pointer ${isActive ? 'bg-white' : 'bg-surface-container-low opacity-70 hover:opacity-100'}" onclick="window.__browserSwitchTab('${id}')">
        <span>Tab ${index + 1}</span>
        <span class="material-symbols-outlined text-[14px] hover:bg-surface-container rounded-full" onclick="window.__browserCloseTab('${id}', event)">close</span>
      </div>
    `;
  }).join("");
  
  container.innerHTML = tabsHtml + addButtonHtml;
}

// Handle iframe internal links
window.addEventListener("message", (event) => {
  const iframe = document.getElementById("browser-iframe");
  // Only accept this message if it actually came from our own sandboxed
  // iframe — otherwise any window holding a reference to this tab (e.g.
  // one opened via window.open) could forge a BROWSER_NAVIGATE message.
  // (Sandboxed srcdoc content has an opaque "null" origin, so we check
  // event.source rather than event.origin.)
  if (!iframe || event.source !== iframe.contentWindow) return;
  if (event.data?.type === "BROWSER_NAVIGATE" && event.data.url) {
    window.__browserNavigate(event.data.url);
  } else if (event.data?.type === "BROWSER_OPEN_EXTERNAL") {
    window.__browserOpenExternal();
  }
});

// ── State ─────────────────────────────────────────────────────────
let currentPage   = 1;
let activeSource  = "";
let activeCategory = "all";
let searchQuery   = "";
let searchTimer   = null;
let totalNew      = 0;
let newArticleSet = new Set();   // Set<url> ของข่าวใหม่ใน session

// ── Browser loading guard ────────────────────────────────────────
// ถ้า server ไม่ตอบกลับ snapshot ในเวลา X → ซ่อน spinner กันค้าง forever
let browserLoadTimer = null;

function armBrowserLoadTimeout() {
  clearTimeout(browserLoadTimer);
  browserLoadTimer = setTimeout(() => {
    const loading = document.getElementById("browser-loading");
    if (loading && loading.style.display !== "none") {
      loading.style.display = "none";
      window.__browserShowError("ไม่มี response จาก server (timeout) — ตรวจสอบว่า Obscura/Playwright ทำงานอยู่");
    }
  }, 20000);
}

function disarmBrowserLoadTimeout() {
  clearTimeout(browserLoadTimer);
}

// ── Page fetch ────────────────────────────────────────────────────

async function loadPage(page = 1) {
  currentPage = page;
  UI.showGridLoading();

  try {
    const data = await fetchNews(page, activeSource, searchQuery, activeCategory);
    UI.renderGrid(data.news, newArticleSet);
    UI.renderPagination(data);
    UI.updateStats({ total: data.total, updated: data.updated });
    UI.updateTicker(data.news.slice(0, 15).map(n => n.title));
  } catch (e) {
    UI.showGridError(e.message);
  }
}

// ── Category handler ──────────────────────────────────────────────

function handleCategoryClick(id) {
  activeCategory = id;
  UI.renderCategoryNav(id, {});
  loadPage(1);
  refreshCategoryCounts();
}

async function refreshCategoryCounts() {
  try {
    const counts = await fetchCategories();
    UI.updateCategoryBadges(counts);
  } catch (e) {
    console.warn("Failed to fetch category counts:", e.message);
  }
}

// expose ให้ onclick ใน pagination เรียกได้
window.__loadPage = loadPage;
window.__categoryClick = handleCategoryClick;

// ── Summary Modal ─────────────────────────────────────────────────

async function handleSummarize(event, url) {
  event.preventDefault();
  event.stopPropagation();

  UI.openModal();
  UI.showModalLoading();

  try {
    const data = await summarizeArticle(url);
    if (data.ok && data.summary) {
      UI.showModalResult(data.summary);
    } else {
      throw new Error(data.error ?? "เกิดข้อผิดพลาดในการสรุปข่าว");
    }
  } catch (err) {
    UI.showModalError(err.message);
  }
}

// expose ให้ onclick attribute ใน ui.js เรียกได้
window.__summarize = handleSummarize;

// ── WebSocket ─────────────────────────────────────────────────────

const socket = createSocket({
  onConnect() {
    UI.setWsBadge(true);
  },
  onDisconnect() {
    UI.setWsBadge(false);
  },
  onInit(data) {
    UI.updateStats({ total: data.total, updated: data.updated });
    loadPage(1);
  },
  onNewArticles(data) {
    totalNew += data.count;
    data.articles.forEach(a => newArticleSet.add(a.url));
    UI.updateStats({ total: data.total, newCount: totalNew, updated: data.updated });
    UI.updateTicker(data.articles.map(a => a.title));
    UI.showToast(`✨ มีข่าวใหม่ ${data.count} บทความ — คลิกเพื่อดู`);
  }
});

// ── Browser Socket Handlers (registered immediately — no race condition) ──
socket.on("browser_loading", (data) => {
  if (data.tab_id === currentTabId) {
    document.getElementById("browser-loading").style.display = "flex";
    armBrowserLoadTimeout();
  }
});
socket.on("browser_snapshot", (data) => {
  // Cache tab state regardless of which tab is active
  if (tabStates[data.tab_id]) {
    tabStates[data.tab_id] = {
      html: data.html || "",
      url: data.url || "",
      title: data.title || "Tab"
    };
  }
  if (data.tab_id === currentTabId) {
    disarmBrowserLoadTimeout();
    document.getElementById("browser-loading").style.display = "none";
    if (data.error && String(data.error).startsWith("Unauthorized")) {
      // Tab ownership was lost server-side (e.g. server restarted, or the
      // socket reconnected with a new sid). Don't keep retrying — the tab
      // is gone for good; drop it and prompt the user to open a fresh one.
      browserTabs = browserTabs.filter(id => id !== data.tab_id);
      delete tabStates[data.tab_id];
      if (browserTabs.length > 0) {
        window.__browserSwitchTab(browserTabs[browserTabs.length - 1]);
      } else {
        currentTabId = null;
        document.getElementById("browser-iframe").srcdoc =
          `<div style="font-family:sans-serif;padding:20px;color:#5f6368;">
             เซสชันแท็บนี้หมดอายุ กรุณากด "+" เพื่อเปิดแท็บใหม่
           </div>`;
        renderBrowserTabs();
      }
    } else if (data.error) {
      document.getElementById("browser-iframe").srcdoc = `<div style="font-family:sans-serif;color:red;padding:20px;">Error: ${String(data.error).replace(/&/g, "&amp;").replace(/</g, "&lt;")}</div>`;
    } else {
      document.getElementById("browser-url").value = data.url;
      document.getElementById("browser-iframe").srcdoc = data.html;

      if (hasConsent && personalizationData.bookmarks && personalizationData.bookmarks.includes(data.url)) {
        document.getElementById("browser-bookmark-icon").textContent = "bookmark";
      } else {
        document.getElementById("browser-bookmark-icon").textContent = "bookmark_border";
      }
    }
  }
});
socket.on("browser_tab_opened", (data) => {
  // Tab opened confirmation from server
  console.log("Tab opened on server:", data.tab_id);
});

// ── Filter buttons ────────────────────────────────────────────────

document.querySelectorAll(".filter-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    activeSource = btn.dataset.source ?? "";
    UI.updateSourceFilters(activeSource);
    loadPage(1);
  });
});

// ── Search ────────────────────────────────────────────────────────

const searchInput = document.getElementById("search-input");
searchInput.addEventListener("input", e => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    searchQuery = e.target.value.trim();
    if (searchQuery) saveSearchQuery(searchQuery);
    loadPage(1);
  }, 400);
});

// Search history autocomplete
searchInput.addEventListener("focus", () => {
  if (hasConsent && searchHistory.length > 0 && !searchInput.value) {
    showSearchSuggestions(searchHistory.slice(0, 5));
  }
});
searchInput.addEventListener("blur", () => {
  setTimeout(() => {
    const suggestions = document.getElementById("search-suggestions");
    if (suggestions) suggestions.remove();
  }, 200);
});

function showSearchSuggestions(items) {
  let existing = document.getElementById("search-suggestions");
  if (existing) existing.remove();
  if (items.length === 0) return;
  const container = document.createElement("div");
  container.id = "search-suggestions";
  container.className = "absolute top-full left-0 right-0 bg-white border border-outline-variant/50 rounded-lg mt-1 shadow-lg z-50 overflow-hidden";
  items.forEach(q => {
    const item = document.createElement("button");
    item.className = "w-full text-left px-4 py-2 text-sm hover:bg-surface-container transition-colors flex items-center gap-2";
    item.innerHTML = `<span class="material-symbols-outlined text-[16px] text-outline">history</span>${q}`;
    item.addEventListener("mousedown", (e) => {
      e.preventDefault();
      searchInput.value = q;
      searchQuery = q;
      loadPage(1);
      container.remove();
    });
    container.appendChild(item);
  });
  searchInput.parentElement.appendChild(container);
}

// ── Toast dismiss ─────────────────────────────────────────────────

document.getElementById("toast").addEventListener("click", () => {
  UI.hideToast();
  loadPage(1);
});

// ── Modal close ───────────────────────────────────────────────────

document.getElementById("summary-modal").addEventListener("click", e => {
  if (e.target === e.currentTarget) UI.closeModal();
});
document.getElementById("modal-close-btn").addEventListener("click", () => UI.closeModal());

// ── Init: draw category nav ───────────────────────────────────────

UI.renderCategoryNav("all", {});
refreshCategoryCounts();
checkPDPA();