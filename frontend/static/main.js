/**
 * main.js — App controller (GRASP: Controller)
 *
 * หน้าที่: เชื่อม api.js กับ ui.js
 * ไม่ fetch เอง ไม่แตะ DOM โดยตรง
 * เป็น orchestrator เท่านั้น
 */

import { fetchNews, summarizeArticle, createSocket, fetchCategories, fetchSources, getSocket, fetchTrendingNews, fetchTrendingStories, recordEngagement, fetchMacroEventDetail, fetchStoryDetail, fetchStorylineSynthesis, triggerStorylineSynthesis } from "./api.js";
import { CATEGORIES, TRENDING_LIMIT } from "./config.js";
import * as UI from "./UI.js";

// ── PDPA & Personalization ────────────────────────────────────────
const PDPA_KEY = "pdpa_consent";
const PDPA_PERMISSIONS_KEY = "pdpa_permissions";
const PERSONALIZATION_KEY = "personalization";
const SEARCH_HISTORY_KEY = "search_history";
const NEWS_CACHE_KEY = "news_cache";
const AFFINITY_VERSION = "1.0";
const FOR_YOU_POOL_PAGES = 5;
const FOR_YOU_LIMIT = 20;

let hasConsent = localStorage.getItem(PDPA_KEY) === "true";
let privacyPermissions = {
  ui: true,
  bookmarks: true,
  cache: true,
};

try {
  const savedPerms = localStorage.getItem(PDPA_PERMISSIONS_KEY);
  if (savedPerms) {
    privacyPermissions = Object.assign(privacyPermissions, JSON.parse(savedPerms));
  }
} catch (e) {
  console.warn("Failed to parse privacy permissions:", e);
}

let personalizationData = hasConsent ? JSON.parse(localStorage.getItem(PERSONALIZATION_KEY) || "{}") : {};
let searchHistory = (hasConsent && privacyPermissions.cache) ? JSON.parse(localStorage.getItem(SEARCH_HISTORY_KEY) || "[]") : [];
let unreadArticlesQueue = [];

// ── PWA Article Map, Reading History & AI Cache ────────────────────
const currentArticleMap = new Map();
const READING_HISTORY_KEY = "newsroom_reading_history";
const AI_SUMMARIES_CACHE_KEY = "newsroom_ai_summaries";
const STORYLINE_SYNTHESIS_CACHE_KEY = "newsroom_storyline_synthesis_cache";

let readingHistory = [];
let cachedAiSummaries = {};
let cachedStorylineSyntheses = {};
let returnViewHash = "#/";
let currentStorylineData = null;
let activeStorylineSourceFilter = "";
let activeSportDisciplineFilter = "";
let activeSportContentTypeFilter = "";

try {
  readingHistory = JSON.parse(localStorage.getItem(READING_HISTORY_KEY) || "[]");
  cachedAiSummaries = JSON.parse(localStorage.getItem(AI_SUMMARIES_CACHE_KEY) || "{}");
  cachedStorylineSyntheses = JSON.parse(localStorage.getItem(STORYLINE_SYNTHESIS_CACHE_KEY) || "{}");
} catch (e) {
  console.warn("Storage parse error for history/cache:", e);
}

function computeArticlesContentSig(articles) {
  if (!Array.isArray(articles) || articles.length === 0) return "";
  return articles
    .map(a => (a && a.url ? a.url.trim().split("#")[0].toLowerCase() : (a && a.title ? a.title.trim().toLowerCase() : "")))
    .filter(Boolean)
    .sort()
    .join("|");
}

function getStorylineCache(storyId, articles) {
  if (!cachedStorylineSyntheses) return null;
  // 1. By storyId directly
  if (storyId && cachedStorylineSyntheses[storyId]) {
    return cachedStorylineSyntheses[storyId];
  }
  // 2. By content signature (independent of cluster ID!)
  const sig = computeArticlesContentSig(articles);
  if (sig && cachedStorylineSyntheses[`sig_${sig}`]) {
    return cachedStorylineSyntheses[`sig_${sig}`];
  }
  // 3. By Jaccard / Overlap (resilient when cluster ID shifts or groups evolve!)
  if (Array.isArray(articles) && articles.length > 0) {
    const currentUrls = new Set(
      articles.map(a => (a && a.url ? a.url.trim().split("#")[0].toLowerCase() : "")).filter(Boolean)
    );
    if (currentUrls.size > 0) {
      for (const [key, cached] of Object.entries(cachedStorylineSyntheses)) {
        if (!cached || !Array.isArray(cached._member_urls) || cached._member_urls.length === 0) continue;
        const cachedUrls = new Set(cached._member_urls);
        let common = 0;
        for (const u of currentUrls) {
          if (cachedUrls.has(u)) common++;
        }
        const minSize = Math.min(currentUrls.size, cachedUrls.size);
        if (common >= 2 || (minSize === 1 && common === 1) || (common / minSize >= 0.5)) {
          if (storyId) cachedStorylineSyntheses[storyId] = cached;
          return cached;
        }
      }
    }
  }
  return null;
}

function saveStorylineCache(storyId, articles, synthesis) {
  if (!synthesis) return;
  const urls = (articles || []).map(a => (a && a.url ? a.url.trim().split("#")[0].toLowerCase() : "")).filter(Boolean);
  const toSave = { ...synthesis, _member_urls: urls, _saved_at: Date.now() };
  if (storyId) {
    cachedStorylineSyntheses[storyId] = toSave;
  }
  const sig = computeArticlesContentSig(articles);
  if (sig) {
    cachedStorylineSyntheses[`sig_${sig}`] = toSave;
  }
  try {
    localStorage.setItem(STORYLINE_SYNTHESIS_CACHE_KEY, JSON.stringify(cachedStorylineSyntheses));
  } catch (e) {
    console.warn("Failed to persist storyline synthesis cache:", e);
  }
}

function savePersonalization() {
  if (hasConsent) {
    try {
      const dataToSave = {};
      if (privacyPermissions.ui) {
        if (personalizationData.darkMode !== undefined) dataToSave.darkMode = personalizationData.darkMode;
        if (personalizationData.fontSize) dataToSave.fontSize = personalizationData.fontSize;
        if (personalizationData.layoutDensity) dataToSave.layoutDensity = personalizationData.layoutDensity;
      }
      if (privacyPermissions.bookmarks) {
        if (personalizationData.bookmarkedArticles) dataToSave.bookmarkedArticles = personalizationData.bookmarkedArticles;
        if (personalizationData.bookmarks) dataToSave.bookmarks = personalizationData.bookmarks;
        if (personalizationData.preferredCategory) dataToSave.preferredCategory = personalizationData.preferredCategory;
        if (personalizationData.preferredSource) dataToSave.preferredSource = personalizationData.preferredSource;
        if (personalizationData.affinity) dataToSave.affinity = personalizationData.affinity;
      }
      localStorage.setItem(PERSONALIZATION_KEY, JSON.stringify(dataToSave));
    } catch (e) {
      console.warn("Failed to save personalization to localStorage:", e);
    }
  }
}

function canPersonalizeFeed() {
  return hasConsent && privacyPermissions.bookmarks;
}

function getAffinity() {
  if (!canPersonalizeFeed()) return null;
  const current = personalizationData.affinity;
  if (current && current.affinity_version === AFFINITY_VERSION) return current;
  const affinity = {
    affinity_version: AFFINITY_VERSION,
    categories: {}, preferred_sources: {}, frequent_keywords: [],
    read_article_urls: [], hidden_article_urls: [], last_active: new Date().toISOString(),
  };
  personalizationData.affinity = affinity;
  return affinity;
}

function articleTokens(article) {
  const text = `${article.title || ""} ${article.summary || ""}`.toLowerCase();
  try {
    if ("Segmenter" in Intl) {
      return [...new Intl.Segmenter("th", { granularity: "word" }).segment(text)]
        .filter(part => part.isWordLike && part.segment.length > 1)
        .map(part => part.segment.trim())
        .filter(word => !/^\d+$/.test(word));
    }
  } catch (error) {
    console.warn("Thai word segmentation unavailable:", error);
  }
  return text.match(/[a-z0-9]+|[\u0E00-\u0E7F]{2,}/g) || [];
}

function updateAffinity(article, weight) {
  const affinity = getAffinity();
  if (!affinity || !article) return;
  const category = article.category;
  const source = article.source;
  if (category) affinity.categories[category] = (affinity.categories[category] || 0) + weight;
  if (source) affinity.preferred_sources[source] = (affinity.preferred_sources[source] || 0) + weight;

  const keywords = new Map((affinity.frequent_keywords || []).map(item => [item.word, item.weight]));
  [...new Set(articleTokens(article))].slice(0, 12).forEach(word => {
    keywords.set(word, (keywords.get(word) || 0) + (weight * 0.35));
  });
  affinity.frequent_keywords = [...keywords.entries()]
    .map(([word, keywordWeight]) => ({ word, weight: Math.round(keywordWeight * 10) / 10 }))
    .sort((a, b) => b.weight - a.weight).slice(0, 60);
  affinity.last_active = new Date().toISOString();
  savePersonalization();
}

function markArticleRead(article, weight = 1.5) {
  const affinity = getAffinity();
  if (!affinity || !article?.url) return;
  const urls = affinity.read_article_urls || [];
  const wasRead = urls.includes(article.url);
  affinity.read_article_urls = [article.url, ...urls.filter(url => url !== article.url)].slice(0, 250);
  updateAffinity(article, wasRead ? 2.0 : weight);
}

window.__acceptCookies = () => {
  hasConsent = true;
  privacyPermissions = { ui: true, bookmarks: true, cache: true };
  localStorage.setItem(PDPA_KEY, "true");
  localStorage.setItem(PDPA_PERMISSIONS_KEY, JSON.stringify(privacyPermissions));
  document.getElementById("pdpa-banner")?.classList.add("translate-y-full");
  const consentEl = document.getElementById("setting-consent-status");
  if (consentEl) consentEl.textContent = "Accepted (All)";
  applyPersonalization();
  UI.renderCategoryNav(activeCategory, {}, personalizationData.bookmarkedArticles || {});
  UI.showToast("บันทึกความยินยอม PDPA (ยินยอมทั้งหมด) เรียบร้อย");
};

window.__declineCookies = () => {
  hasConsent = false;
  privacyPermissions = { ui: false, bookmarks: false, cache: false };
  localStorage.setItem(PDPA_KEY, "false");
  localStorage.removeItem(PDPA_PERMISSIONS_KEY);
  localStorage.removeItem(PERSONALIZATION_KEY);
  localStorage.removeItem(SEARCH_HISTORY_KEY);
  localStorage.removeItem(NEWS_CACHE_KEY);
  personalizationData = {};
  searchHistory = [];
  document.getElementById("pdpa-banner")?.classList.add("translate-y-full");
  const consentEl = document.getElementById("setting-consent-status");
  if (consentEl) consentEl.textContent = "Declined";
  document.documentElement.classList.remove("dark");
  document.documentElement.classList.add("light");
  document.documentElement.style.fontSize = "";
  delete document.body.dataset.density;

  if (activeCategory === "bookmarks" || activeCategory === "for-you") {
    activeCategory = "all";
  }
  UI.renderCategoryNav(activeCategory, {}, {});
  loadPage(1);
  UI.showToast("ปฏิเสธการใช้คุกกี้ — ลบข้อมูลการตั้งค่าส่วนบุคคลทั้งหมดแล้ว");
};

window.__openPrivacyModal = () => {
  const modal = document.getElementById("privacy-modal");
  if (!modal) return;
  modal.classList.remove("hidden");
  modal.classList.add("flex");

  const uiCb = document.getElementById("privacy-pref-ui");
  const bmCb = document.getElementById("privacy-pref-bookmarks");
  const cacheCb = document.getElementById("privacy-pref-cache");

  if (uiCb) uiCb.checked = Boolean(privacyPermissions.ui);
  if (bmCb) bmCb.checked = Boolean(privacyPermissions.bookmarks);
  if (cacheCb) cacheCb.checked = Boolean(privacyPermissions.cache);
};

window.__closePrivacyModal = () => {
  const modal = document.getElementById("privacy-modal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.classList.remove("flex");
};

window.__saveCustomPrivacy = () => {
  const uiCb = document.getElementById("privacy-pref-ui");
  const bmCb = document.getElementById("privacy-pref-bookmarks");
  const cacheCb = document.getElementById("privacy-pref-cache");

  privacyPermissions = {
    ui: uiCb ? uiCb.checked : true,
    bookmarks: bmCb ? bmCb.checked : true,
    cache: cacheCb ? cacheCb.checked : true,
  };

  hasConsent = true;
  localStorage.setItem(PDPA_KEY, "true");
  localStorage.setItem(PDPA_PERMISSIONS_KEY, JSON.stringify(privacyPermissions));

  // Purge disallowed stores immediately
  if (!privacyPermissions.ui) {
    delete personalizationData.darkMode;
    delete personalizationData.fontSize;
    delete personalizationData.layoutDensity;
    document.documentElement.classList.remove("dark");
    document.documentElement.classList.add("light");
    document.documentElement.style.fontSize = "";
    delete document.body.dataset.density;
  }
  if (!privacyPermissions.bookmarks) {
    delete personalizationData.bookmarkedArticles;
    delete personalizationData.bookmarks;
    delete personalizationData.preferredCategory;
    delete personalizationData.preferredSource;
    delete personalizationData.affinity;
    if (activeCategory === "bookmarks" || activeCategory === "for-you") activeCategory = "all";
  }
  if (!privacyPermissions.cache) {
    searchHistory = [];
    localStorage.removeItem(SEARCH_HISTORY_KEY);
    localStorage.removeItem(NEWS_CACHE_KEY);
  }

  savePersonalization();

  document.getElementById("pdpa-banner")?.classList.add("translate-y-full");
  window.__closePrivacyModal();

  const consentEl = document.getElementById("setting-consent-status");
  if (consentEl) consentEl.textContent = "Customized";

  applyPersonalization();
  UI.renderCategoryNav(activeCategory, {}, personalizationData.bookmarkedArticles || {});
  loadPage(currentPage);
  UI.showToast("บันทึกการตั้งค่าความเป็นส่วนตัวเรียบร้อย");
};

function checkPDPA() {
  const consent = localStorage.getItem(PDPA_KEY);
  if (consent === null) {
    setTimeout(() => {
      document.getElementById("pdpa-banner")?.classList.remove("translate-y-full");
    }, 1000);
  } else {
    hasConsent = consent === "true";
    if (hasConsent) applyPersonalization();
  }
  const consentEl = document.getElementById("setting-consent-status");
  if (consentEl) {
    const isCustom = localStorage.getItem(PDPA_PERMISSIONS_KEY) !== null;
    consentEl.textContent = consent === "true" ? (isCustom ? "Customized" : "Accepted") : consent === "false" ? "Declined" : "Unknown";
  }
}

function applyPersonalization() {
  if (!hasConsent) return;

  if (privacyPermissions.ui) {
    if (personalizationData.darkMode) {
      document.documentElement.classList.add("dark");
      document.documentElement.classList.remove("light");
      const dmEl = document.getElementById("setting-darkmode");
      if (dmEl) dmEl.checked = true;
    } else {
      document.documentElement.classList.remove("dark");
      document.documentElement.classList.add("light");
      const dmEl = document.getElementById("setting-darkmode");
      if (dmEl) dmEl.checked = false;
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

  // Restore category and source filter preferences
  if (privacyPermissions.bookmarks) {
    if (personalizationData.preferredCategory && personalizationData.preferredCategory !== "bookmarks") {
      activeCategory = personalizationData.preferredCategory;
    }
    if (personalizationData.preferredSource !== undefined) {
      activeSource = personalizationData.preferredSource;
    }
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
  if (hasConsent && privacyPermissions.ui) {
    savePersonalization();
  } else {
    try {
      localStorage.setItem("theme_pref", isDark ? "dark" : "light");
    } catch (e) {}
  }
};

window.__toggleThemeDirectly = () => {
  const isDarkNow = document.documentElement.classList.contains("dark");
  const newDark = !isDarkNow;
  window.__toggleDarkMode(newDark);
  const dmEl = document.getElementById("setting-darkmode");
  if (dmEl) dmEl.checked = newDark;
  if (typeof UI !== "undefined" && UI.showToast) {
    UI.showToast(newDark ? "เปิดโหมดมืด (Dark Mode)" : "เปิดโหมดสว่าง (Light Mode)");
  }
};

window.__changeFontSize = (size) => {
  document.documentElement.style.fontSize = size;
  if (hasConsent && privacyPermissions.ui) {
    personalizationData.fontSize = size;
    savePersonalization();
  }
};

window.__changeLayoutDensity = (density) => {
  document.body.dataset.density = density;
  if (hasConsent && privacyPermissions.ui) {
    personalizationData.layoutDensity = density;
    savePersonalization();
  }
};

window.__clearPersonalizationData = () => {
  localStorage.removeItem(PERSONALIZATION_KEY);
  localStorage.removeItem(PDPA_KEY);
  localStorage.removeItem(PDPA_PERMISSIONS_KEY);
  localStorage.removeItem(SEARCH_HISTORY_KEY);
  localStorage.removeItem(NEWS_CACHE_KEY);

  hasConsent = false;
  privacyPermissions = { ui: true, bookmarks: true, cache: true };
  personalizationData = {};
  searchHistory = [];
  unreadArticlesQueue = [];
  activeCategory = "all";
  activeSource = "";
  searchQuery = "";

  document.documentElement.classList.remove("dark");
  document.documentElement.classList.add("light");
  document.documentElement.style.fontSize = "";
  delete document.body.dataset.density;

  const dmEl = document.getElementById("setting-darkmode");
  if (dmEl) dmEl.checked = false;
  const fsEl = document.getElementById("setting-fontsize");
  if (fsEl) fsEl.value = "16px";
  const ldEl = document.getElementById("setting-density");
  if (ldEl) ldEl.value = "comfortable";
  const consentEl = document.getElementById("setting-consent-status");
  if (consentEl) consentEl.textContent = "Cleared / None";

  const searchInputEl = document.getElementById("search-input");
  if (searchInputEl) searchInputEl.value = "";

  window.__closeSettings();
  UI.hideFloatingUpdateBanner();
  UI.renderCategoryNav("all", {}, {});
  UI.updateSourceFilters("");
  loadPage(1);

  setTimeout(() => {
    document.getElementById("pdpa-banner")?.classList.remove("translate-y-full");
  }, 400);

  UI.showToast("ล้างข้อมูลและประวัติการใช้งานทั้งหมดเรียบร้อยแล้ว");
};

function saveSearchQuery(query) {
  if (!hasConsent || !privacyPermissions.cache || !query) return;
  searchHistory = searchHistory.filter(q => q !== query);
  searchHistory.unshift(query);
  if (searchHistory.length > 20) searchHistory.pop();
  try {
    localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(searchHistory));
  } catch (e) {
    console.warn("Failed to save search history to localStorage:", e);
  }
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
  window.location.hash = "#/";
};

window.__openBrowserWithUrl = (url) => {
  if (!url) return;
  window.__openPreview(url);
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
let selectedForYouTopics = new Set();

function syncForYouTopicPicker() {
  document.querySelectorAll(".for-you-topic").forEach(button => {
    const selected = selectedForYouTopics.has(button.dataset.topicId);
    button.classList.toggle("bg-primary", selected);
    button.classList.toggle("text-white", selected);
    button.classList.toggle("border-primary", selected);
    button.classList.toggle("bg-white", !selected);
    button.classList.toggle("text-on-surface", !selected);
  });
  const count = document.getElementById("for-you-topic-count");
  if (count) count.textContent = `เลือกแล้ว ${selectedForYouTopics.size}/3 หมวด`;
}

window.__toggleForYouTopic = (category) => {
  if (selectedForYouTopics.has(category)) selectedForYouTopics.delete(category);
  else selectedForYouTopics.add(category);
  syncForYouTopicPicker();
};

window.__saveForYouTopics = () => {
  if (selectedForYouTopics.size < 3) {
    UI.showToast("เลือกอย่างน้อย 3 หมวดเพื่อเริ่มต้นฟีดสำหรับคุณ");
    return;
  }
  const affinity = getAffinity();
  if (!affinity) return;
  selectedForYouTopics.forEach(category => {
    affinity.categories[category] = Math.max(3, affinity.categories[category] || 0);
  });
  savePersonalization();
  UI.hideForYouOnboarding();
  loadPage(1);
};

window.__skipForYouOnboarding = () => {
  const affinity = getAffinity();
  if (affinity) {
    affinity.onboarding_skipped = true;
    savePersonalization();
  }
  UI.hideForYouOnboarding();
  loadPage(1);
};

function articleAgeHours(article) {
  const parsed = Date.parse(article.fetched_at || "");
  return Number.isNaN(parsed) ? 0 : Math.max(0, (Date.now() - parsed) / 3600000);
}

function tokenSimilarity(article, keywords) {
  const tokens = new Set(articleTokens(article));
  return (keywords || []).reduce((score, item) => (
    tokens.has(item.word) ? score + Math.max(0, item.weight || 0) : score
  ), 0);
}

function isNearDuplicate(article, picked) {
  const tokens = new Set(articleTokens(article));
  return picked.some(existing => {
    const other = new Set(articleTokens(existing));
    const union = new Set([...tokens, ...other]).size;
    return union > 0 && [...tokens].filter(token => other.has(token)).length / union >= 0.55;
  });
}

function rankForYou(articles, trendingUrls) {
  const affinity = getAffinity();
  if (!affinity) return [];
  const seen = new Set(affinity.read_article_urls || []);
  const hidden = new Set(affinity.hidden_article_urls || []);
  const ranked = articles.filter(article => article?.url && !seen.has(article.url) && !hidden.has(article.url)).map(article => {
    const categoryScore = affinity.categories[article.category] || 0;
    const sourceScore = affinity.preferred_sources[article.source] || 0;
    const keywordScore = tokenSimilarity(article, affinity.frequent_keywords);
    const freshness = Math.pow(2, -articleAgeHours(article) / 18);
    const trendingBoost = trendingUrls.has(article.url) ? 3 : 0;
    return { article, score: ((categoryScore * 1.2) + (sourceScore * 0.8) + (keywordScore * 0.35)) * freshness + trendingBoost };
  }).sort((a, b) => b.score - a.score);

  const result = [];
  const personalCount = Math.max(1, Math.ceil(FOR_YOU_LIMIT * 0.8));
  for (const item of ranked) {
    if (result.length >= personalCount) break;
    if (!isNearDuplicate(item.article, result)) result.push(item.article);
  }

  // Reserve ~20% for strong, fresh stories outside the user's usual categories.
  const discovery = ranked.filter(item => (affinity.categories[item.article.category] || 0) <= 0);
  for (const item of discovery) {
    if (result.length >= FOR_YOU_LIMIT) break;
    if (!result.some(article => article.url === item.article.url) && !isNearDuplicate(item.article, result)) {
      result.push({ ...item.article, for_you_discovery: true });
    }
  }
  for (const item of ranked) {
    if (result.length >= FOR_YOU_LIMIT) break;
    if (!result.some(article => article.url === item.article.url) && !isNearDuplicate(item.article, result)) result.push(item.article);
  }
  return result;
}

async function loadForYouFeed() {
  document.getElementById("hero-trending")?.classList.add("hidden");
  UI.showGridLoading();
  const affinity = getAffinity();
  if (!affinity) {
    UI.showGridError("กรุณายินยอมการจัดเก็บข้อมูลการตั้งค่า เพื่อใช้ฟีดสำหรับคุณ");
    return;
  }
  if (!Object.keys(affinity.categories || {}).length && !affinity.onboarding_skipped) {
    UI.renderForYouOnboarding(CATEGORIES.filter(category => category.id !== "all"));
    syncForYouTopicPicker();
  } else {
    UI.hideForYouOnboarding();
  }
  try {
    const [pages, trendingData] = await Promise.all([
      Promise.all(Array.from({ length: FOR_YOU_POOL_PAGES }, (_, i) => fetchNews(i + 1, activeSource, searchQuery))),
      fetchTrendingNews(FOR_YOU_LIMIT),
    ]);
    const articles = pages.flatMap(data => data.news || []);
    const trending = (trendingData.trending || trendingData.articles || []);
    const feed = rankForYou(articles, new Set(trending.map(article => article.url)));
    feed.forEach(article => currentArticleMap.set(article.url, article));
    UI.renderGrid(feed, newArticleSet, personalizationData.bookmarkedArticles || {});
    UI.renderPagination({ page: 1, total_pages: 1, total: feed.length });
    UI.updateStats({ total: feed.length, updated: "จัดอันดับบนอุปกรณ์นี้" });
    UI.updateTicker(feed.slice(0, 15).map(article => article.title));
  } catch (error) {
    UI.showGridError(error.message);
  }
}

// ── Browser loading guard ────────────────────────────────────────
// ถ้า server ไม่ตอบกลับ snapshot ในเวลา X → ซ่อน spinner กันค้าง forever
let browserLoadTimer = null;

function armBrowserLoadTimeout() {
  clearTimeout(browserLoadTimer);
  browserLoadTimer = setTimeout(() => {
    const loading = document.getElementById("browser-loading");
    if (loading && loading.style.display !== "none") {
      loading.style.display = "none";
      window.__browserShowError("ไม่มี response จาก server (timeout) — ตรวจสอบว่า Playwright ทำงานอยู่");
    }
  }, 20000);
}

function disarmBrowserLoadTimeout() {
  clearTimeout(browserLoadTimer);
}

// ── Bookmarks View & Article Bookmark Handler ─────────────────────

window.__toggleArticleBookmark = (event, articleJsonStr) => {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  if (!hasConsent) {
    UI.showToast("กรุณายินยอมให้ใช้คุกกี้เพื่อใช้งานระบบบันทึกข่าว (PDPA)");
    return;
  }
  try {
    const article = typeof articleJsonStr === "string" ? JSON.parse(decodeURIComponent(articleJsonStr)) : articleJsonStr;
    if (!article || !article.url) return;

    personalizationData.bookmarkedArticles = personalizationData.bookmarkedArticles || {};
    personalizationData.bookmarks = personalizationData.bookmarks || [];

    const isCurrentlyBookmarked = Boolean(personalizationData.bookmarkedArticles[article.url]);
    const nextBookmarked = !isCurrentlyBookmarked;

    if (isCurrentlyBookmarked) {
      delete personalizationData.bookmarkedArticles[article.url];
      personalizationData.bookmarks = personalizationData.bookmarks.filter(u => u !== article.url);
      savePersonalization();
      UI.showToast("ลบบุ๊กมาร์กเรียบร้อย");
    } else {
      article.bookmarked_at = new Date().toISOString();
      personalizationData.bookmarkedArticles[article.url] = article;
      if (!personalizationData.bookmarks.includes(article.url)) {
        personalizationData.bookmarks.push(article.url);
      }
      savePersonalization();
      updateAffinity(article, 5.0);
      recordEngagement(article.url, "bookmark");
      UI.showToast("บันทึกบทความเรียบร้อย 🔖");
    }

    const bCount = Object.keys(personalizationData.bookmarkedArticles).length;
    UI.updateCategoryBadges({}, bCount);

    if (activeCategory === "bookmarks") {
      renderBookmarkedArticles();
      return;
    }

    // In-place UI update without full-feed reload
    const updateBtn = (btn) => {
      const icon = btn.querySelector(".material-symbols-outlined");
      const textSpan = btn.querySelector("span:not(.material-symbols-outlined)");

      if (nextBookmarked) {
        btn.classList.add("active");
        btn.setAttribute("title", "ลบบุ๊กมาร์ก");
        if (icon) {
          icon.textContent = "bookmark";
          icon.style.fontVariationSettings = "'FILL' 1";
          if (btn.classList.contains("hero-bookmark-btn")) {
            icon.style.color = "#f59e0b";
          }
        }
        if (textSpan && textSpan.textContent.includes("บันทึก")) {
          textSpan.textContent = "บันทึกแล้ว";
        }
        if (btn.classList.contains("modal-bookmark-btn")) {
          btn.classList.remove("bg-white", "text-on-surface");
          btn.classList.add("bg-[#141413]", "text-white");
        }
      } else {
        btn.classList.remove("active");
        btn.setAttribute("title", "บันทึกบทความ");
        if (icon) {
          icon.textContent = "bookmark_border";
          icon.style.fontVariationSettings = "'FILL' 0";
          icon.style.color = "";
        }
        if (textSpan && textSpan.textContent.includes("บันทึก")) {
          textSpan.textContent = "บันทึก";
        }
        if (btn.classList.contains("modal-bookmark-btn")) {
          btn.classList.remove("bg-[#141413]", "text-white");
          btn.classList.add("bg-white", "text-on-surface");
        }
      }
    };

    if (event?.currentTarget) {
      updateBtn(event.currentTarget);
    }

    try {
      const escapedUrl = CSS.escape(article.url);
      document.querySelectorAll(`button.bookmark-btn[data-url="${escapedUrl}"]`).forEach(btn => {
        if (btn !== event?.currentTarget) updateBtn(btn);
      });
    } catch (_) {}
  } catch (err) {
    console.error("Failed to toggle article bookmark:", err);
  }
};

window.__showLessLikeThis = (event, articleJsonStr) => {
  event?.preventDefault();
  event?.stopPropagation();
  try {
    const article = typeof articleJsonStr === "string" ? JSON.parse(decodeURIComponent(articleJsonStr)) : articleJsonStr;
    if (!article || !article.url) return;

    // Immediately animate and collapse the target card
    const btn = event?.currentTarget;
    let card = btn ? btn.closest("article") : null;
    if (!card) {
      try {
        card = document.querySelector(`article[data-url="${CSS.escape(article.url)}"]`);
      } catch (_) {}
    }

    if (card) {
      card.style.transition = "opacity 0.3s ease, transform 0.3s ease, max-height 0.35s ease, margin 0.35s ease, padding 0.35s ease";
      card.style.opacity = "0";
      card.style.transform = "scale(0.94) translateY(-6px)";
      setTimeout(() => {
        card.style.display = "none";
      }, 320);
    }

    const affinity = getAffinity();
    if (affinity) {
      affinity.hidden_article_urls = [article.url, ...(affinity.hidden_article_urls || []).filter(url => url !== article.url)].slice(0, 250);
      if (article.category) {
        affinity.categories[article.category] = (affinity.categories[article.category] || 0) - 10.0;
      }
      affinity.last_active = new Date().toISOString();
      savePersonalization();
    }

    UI.showToast("ซ่อนข่าวนี้แล้ว และจะลดเนื้อหาลักษณะนี้ลง");
    if (activeCategory === "for-you") {
      setTimeout(() => loadPage(1), 350);
    }
  } catch (error) {
    console.warn("Failed to update show-less feedback:", error);
  }
};

function renderBookmarkedArticles() {
  activeCategory = "bookmarks";
  document.getElementById("hero-trending")?.classList.add("hidden");

  const bookmarksObj = personalizationData.bookmarkedArticles || {};
  let articles = Object.values(bookmarksObj);

  // Sort latest bookmarked first
  articles.sort((a, b) => new Date(b.bookmarked_at || 0) - new Date(a.bookmarked_at || 0));

  // Filter by active source if any
  if (activeSource) {
    articles = articles.filter(a => a.source && a.source.toLowerCase() === activeSource.toLowerCase());
  }

  // Filter by search query if any
  if (searchQuery) {
    const q = searchQuery.toLowerCase();
    articles = articles.filter(a =>
      (a.title && a.title.toLowerCase().includes(q)) ||
      (a.summary && a.summary.toLowerCase().includes(q)) ||
      (a.source && a.source.toLowerCase().includes(q))
    );
  }

  UI.renderCategoryNav("bookmarks", {}, personalizationData.bookmarkedArticles || {});
  UI.updateSourceFilters(activeSource);

  if (articles.length === 0) {
    const totalSaved = Object.keys(bookmarksObj).length;
    if (totalSaved === 0) {
      document.getElementById("news-grid").innerHTML = `
        <div class="col-span-1 md:col-span-2 lg:col-span-3 text-center py-16 text-on-surface-variant flex flex-col items-center justify-center">
          <span class="material-symbols-outlined text-outline text-5xl mb-3">bookmark_border</span>
          <span class="font-bold text-lg text-on-surface mb-1">ยังไม่มีบทความที่บันทึกไว้</span>
          <span class="text-sm text-outline">คลิกที่ไอคอนบุ๊กมาร์กบนการ์ดข่าวเพื่อบันทึกไว้อ่านภายหลัง</span>
        </div>
      `;
    } else {
      document.getElementById("news-grid").innerHTML = `
        <div class="col-span-1 md:col-span-2 lg:col-span-3 text-center py-16 text-on-surface-variant">
          ไม่พบบทความที่บันทึกไว้ตรงกับคำค้นหาหรือตัวกรอง
        </div>
      `;
    }
  } else {
    UI.renderGrid(articles, newArticleSet, personalizationData.bookmarkedArticles || {});
  }

  UI.renderPagination({ page: 1, total_pages: 1, total: articles.length });
  UI.updateStats({ total: articles.length });
}

window.__showBookmarks = () => {
  if (!hasConsent) {
    UI.showToast("กรุณายินยอมให้ใช้คุกกี้เพื่อใช้งานระบบบันทึกข่าว (PDPA)");
    return;
  }
  renderBookmarkedArticles();
};

// ── Page fetch ────────────────────────────────────────────────────

async function loadPage(page = 1) {
  if (activeCategory === "bookmarks") {
    document.getElementById("hero-trending")?.classList.add("hidden");
    renderBookmarkedArticles();
    return;
  }
  if (activeCategory === "for-you") {
    await loadForYouFeed();
    return;
  }

  UI.hideForYouOnboarding();

  currentPage = page;
  const shouldShowTrending = page === 1 && (!activeCategory || activeCategory === "all" || activeCategory === "sports") && !searchQuery && !activeSource;
  if (!shouldShowTrending) {
    document.getElementById("hero-trending")?.classList.add("hidden");
  }

  UI.showGridLoading();

  try {
    const data = await fetchNews(page, activeSource, searchQuery, activeCategory);
    UI.setWsBadge(true);
    UI.showOfflineStatus(false);
    if (data.news && Array.isArray(data.news)) {
      data.news.forEach(a => { if (a.url) currentArticleMap.set(a.url, a); });
    }

    // Save to offline news cache if default page 1 feed and consent granted
    if (hasConsent && privacyPermissions.cache && page === 1 && !activeSource && !searchQuery && (activeCategory === "all" || !activeCategory)) {
      try {
        localStorage.setItem(NEWS_CACHE_KEY, JSON.stringify({
          timestamp: Date.now(),
          articles: data.news,
          total: data.total,
          updated: data.updated
        }));
      } catch (cacheErr) {
        console.warn("Failed to cache news feed to localStorage:", cacheErr);
      }
    }

    const affinity = getAffinity();
    const hiddenSet = new Set((affinity && affinity.hidden_article_urls) || []);
    const visibleNews = (data.news || []).filter(a => !hiddenSet.has(a.url));

    UI.renderGrid(visibleNews, newArticleSet, personalizationData.bookmarkedArticles || {});
    UI.renderPagination(data);
    UI.updateStats({ total: data.total, updated: data.updated });
    UI.updateTicker(data.news.slice(0, 15).map(n => n.title));

    // Load Hero Trending Highlights asynchronously AFTER main feed is rendered
    if (shouldShowTrending) {
      fetchTrendingStories(TRENDING_LIMIT, activeCategory)
        .then(trendingList => {
          if (Array.isArray(trendingList) && trendingList.length > 0) {
            trendingList.forEach(a => {
              if (a.url) currentArticleMap.set(a.url, a);
              if (Array.isArray(a.articles)) {
                a.articles.forEach(subArt => {
                  if (subArt.url) currentArticleMap.set(subArt.url, subArt);
                });
              }
              if (Array.isArray(a.child_events)) {
                a.child_events.forEach(ce => {
                  if (Array.isArray(ce.articles)) {
                    ce.articles.forEach(subArt => {
                      if (subArt.url) currentArticleMap.set(subArt.url, subArt);
                    });
                  }
                });
              }
            });
            UI.renderHeroTrending(trendingList, personalizationData.bookmarkedArticles || {});
          } else {
            document.getElementById("hero-trending")?.classList.add("hidden");
          }
        })
        .catch(tErr => {
          console.warn("Failed to load trending highlights:", tErr);
          document.getElementById("hero-trending")?.classList.add("hidden");
        });
    }
  } catch (e) {
    console.warn("fetchNews failed, attempting offline cache fallback:", e.message);
    // Offline fallback
    const cachedRaw = localStorage.getItem(NEWS_CACHE_KEY);
    if (cachedRaw) {
      try {
        const cached = JSON.parse(cachedRaw);
        const CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours
        if (cached && Array.isArray(cached.articles) && (Date.now() - (cached.timestamp || 0) < CACHE_TTL_MS)) {
          let articles = cached.articles;
          if (activeCategory && activeCategory !== "all") {
            articles = articles.filter(a => a.category === activeCategory);
          }
          if (activeSource) {
            articles = articles.filter(a => a.source && a.source.toLowerCase() === activeSource.toLowerCase());
          }
          if (searchQuery) {
            const q = searchQuery.toLowerCase();
            articles = articles.filter(a =>
              (a.title && a.title.toLowerCase().includes(q)) ||
              (a.summary && a.summary.toLowerCase().includes(q)) ||
              (a.source && a.source.toLowerCase().includes(q))
            );
          }

          UI.renderGrid(articles, newArticleSet, personalizationData.bookmarkedArticles || {});
          UI.renderPagination({ page: 1, total_pages: 1, total: articles.length });
          UI.updateStats({ total: cached.total || articles.length, updated: cached.updated ? `${cached.updated} (ออฟไลน์)` : "แคชออฟไลน์" });
          UI.updateTicker(articles.slice(0, 15).map(n => n.title));
          UI.showToast("⚡ กำลังแสดงข่าวจากแคชออฟไลน์ (เชื่อมต่อเซิร์ฟเวอร์ไม่ได้)");
          return;
        } else if (cached && Date.now() - (cached.timestamp || 0) >= CACHE_TTL_MS) {
          localStorage.removeItem(NEWS_CACHE_KEY);
        }
      } catch (parseErr) {
        localStorage.removeItem(NEWS_CACHE_KEY);
      }
    }
    UI.showGridError(e.message);
  }
}

// ── Category handler ──────────────────────────────────────────────

function handleCategoryClick(id) {
  if (id === "bookmarks") {
    window.__showBookmarks();
    return;
  }
  if (id === "for-you" && !canPersonalizeFeed()) {
    UI.showToast("กรุณายินยอมการจัดเก็บข้อมูลการตั้งค่า เพื่อใช้ฟีดสำหรับคุณ");
    return;
  }
  activeCategory = id;
  if (hasConsent && privacyPermissions.bookmarks) {
    personalizationData.preferredCategory = id;
    savePersonalization();
  }
  UI.renderCategoryNav(id, {}, personalizationData.bookmarkedArticles || {});
  loadPage(1);
  refreshCategoryCounts();
}

async function refreshCategoryCounts() {
  try {
    const counts = await fetchCategories();
    const bCount = Object.keys(personalizationData.bookmarkedArticles || {}).length;
    UI.updateCategoryBadges(counts, bCount);
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

  recordEngagement(url, "summary");
  updateAffinity(currentArticleMap.get(url), 3.5);

  UI.openModal();
  UI.showModalLoading();

  try {
    const data = await summarizeArticle(url);
    if (data.ok && data.summary) {
      UI.showModalResult(data.summary, url);
    } else {
      throw new Error(data.error ?? "เกิดข้อผิดพลาดในการสรุปข่าว");
    }
  } catch (err) {
    UI.showModalError(err.message);
  }
}

// expose ให้ onclick attribute ใน ui.js เรียกได้
window.__summarize = handleSummarize;

// ── Floating Live Update Actions ──────────────────────────────────

window.__loadUnreadArticles = () => {
  window.scrollTo({ top: 0, behavior: "smooth" });
  unreadArticlesQueue = [];
  UI.hideFloatingUpdateBanner();
  loadPage(1);
};

window.__dismissNewArticlesBanner = (event) => {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  UI.hideFloatingUpdateBanner();
};

// ── WebSocket ─────────────────────────────────────────────────────

let initialLoadStarted = false;

const socket = createSocket({
  onConnect() {
    UI.setWsBadge(true);
  },
  onDisconnect() {
    UI.setWsBadge(false);
  },
  onInit(data) {
    UI.setWsBadge(true);
    UI.updateStats({ total: data.total, updated: data.updated });
    if (!initialLoadStarted) {
      initialLoadStarted = true;
      loadPage(1);
    }
    refreshCategoryCounts();
    refreshSourceFilters();
  },
  onNewArticles(data) {
    totalNew += data.count;
    if (data.articles && Array.isArray(data.articles)) {
      data.articles.forEach(a => {
        newArticleSet.add(a.url);
        unreadArticlesQueue.push(a);
      });
    }
    UI.updateStats({ total: data.total, newCount: totalNew, updated: data.updated });
    if (data.articles && data.articles.length) {
      UI.updateTicker(data.articles.map(a => a.title));
    }
    // Show non-intrusive floating indicator without resetting scroll or feed
    UI.showFloatingUpdateBanner(unreadArticlesQueue.length);
    refreshCategoryCounts();
    refreshSourceFilters();
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

// ── Source Filter handler ──────────────────────────────────────────

function handleSourceFilterClick(source) {
  activeSource = source ?? "";
  if (hasConsent && privacyPermissions.bookmarks) {
    personalizationData.preferredSource = activeSource;
    savePersonalization();
  }
  UI.updateSourceFilters(activeSource);
  if (activeCategory === "bookmarks") {
    renderBookmarkedArticles();
  } else {
    loadPage(1);
  }
}

async function refreshSourceFilters() {
  try {
    const counts = await fetchSources();
    const sources = Object.keys(counts);
    UI.renderSourceFilters(sources, activeSource, counts);
  } catch (e) {
    console.warn("Failed to fetch source counts:", e.message);
    UI.renderSourceFilters([], activeSource, {});
  }
}

window.__sourceFilterClick = handleSourceFilterClick;

// ── Search ────────────────────────────────────────────────────────

const searchInput = document.getElementById("search-input");
searchInput.addEventListener("input", e => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    searchQuery = e.target.value.trim();
    if (searchQuery) {
      saveSearchQuery(searchQuery);
    } else {
      UI.renderStorylineBreadcrumb("");
    }
    if (activeCategory === "bookmarks") {
      renderBookmarkedArticles();
    } else {
      loadPage(1);
    }
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
    item.innerHTML = `<span class="material-symbols-outlined text-[16px] text-outline">history</span>${UI.esc(q)}`;
    item.addEventListener("mousedown", (e) => {
      e.preventDefault();
      searchInput.value = q;
      searchQuery = q;
      if (activeCategory === "bookmarks") {
        renderBookmarkedArticles();
      } else {
        loadPage(1);
      }
      container.remove();
    });
    container.appendChild(item);
  });
  searchInput.parentElement.appendChild(container);
}

// ── Toast dismiss ─────────────────────────────────────────────────

document.getElementById("toast").addEventListener("click", () => {
  UI.hideToast();
  if (activeCategory === "bookmarks") {
    renderBookmarkedArticles();
  } else {
    loadPage(1);
  }
});

// ── Modal close ───────────────────────────────────────────────────

document.getElementById("summary-modal").addEventListener("click", e => {
  if (e.target === e.currentTarget) UI.closeModal();
});
document.getElementById("modal-close-btn").addEventListener("click", () => UI.closeModal());

// ── PWA Router & Preview Sub-View Controller ──────────────────────

export function cleanTrackingParams(rawUrl) {
  try {
    const u = new URL(rawUrl);
    const trackingKeys = [
      "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
      "fbclid", "gclid", "dclid", "msclkid", "ref", "source", "igshid", "_hsenc", "_hsmi"
    ];
    trackingKeys.forEach(k => u.searchParams.delete(k));
    return u.toString();
  } catch (e) {
    return rawUrl;
  }
}

function showPreviewByUrl(url, autoSummarize = false) {
  if (!url) {
    UI.switchView("feed");
    return;
  }

  // Lookup in currentArticleMap, bookmarks, or reading history
  let article = currentArticleMap.get(url);
  if (!article && personalizationData.bookmarkedArticles && personalizationData.bookmarkedArticles[url]) {
    article = personalizationData.bookmarkedArticles[url];
  }
  if (!article) {
    article = readingHistory.find(h => h.url === url);
  }

  if (!article) {
    article = {
      url: url,
      title: "บทความข่าว",
      summary: "คลิกปุ่มสรุปเนื้อหาด้วย AI หรือกดอ่านข่าวฉบับเต็มจากเว็บไซต์ต้นฉบับ",
      source: "เว็บข่าวต้นทาง",
      fetched_at: "ล่าสุด",
      category: "general"
    };
  }

  markArticleRead(article, 1.5);
  window.setTimeout(() => {
    if (window.location.hash.includes(encodeURIComponent(url))) updateAffinity(article, 1.0);
  }, 15000);

  // Record to reading history
  const historyItem = {
    url: article.url,
    title: article.title,
    summary: article.summary,
    source: article.source,
    image_url: article.image_url,
    category: article.category,
    viewed_at: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  };

  readingHistory = [historyItem, ...readingHistory.filter(h => h.url !== article.url)].slice(0, 100);
  try {
    localStorage.setItem(READING_HISTORY_KEY, JSON.stringify(readingHistory));
  } catch (e) {
    console.warn("Failed to persist reading history:", e);
  }

  const isBookmarked = Boolean(personalizationData.bookmarkedArticles && personalizationData.bookmarkedArticles[article.url]);
  const cachedSummary = cachedAiSummaries[article.url] || null;

  UI.renderPreviewView(article, isBookmarked, cachedSummary);
  UI.switchView("preview");

  // If requested with auto-summarize and not yet cached, trigger AI summarize immediately
  if (autoSummarize && !cachedSummary) {
    window.__runPreviewAiSummary(article.url);
  }
}

function handleHashRouting() {
  const hash = window.location.hash || "#/";
  if (hash.startsWith("#/storyline/")) {
    const rawPart = hash.replace("#/storyline/", "");
    const [encodedId, queryStr] = rawPart.split("?");
    const storyId = decodeURIComponent(encodedId || "");
    loadStorylineView(storyId);
  } else if (hash.startsWith("#/preview/")) {
    const rawPart = hash.replace("#/preview/", "");
    const [encodedUrl, queryStr] = rawPart.split("?");
    const articleUrl = decodeURIComponent(encodedUrl || "");
    const params = new URLSearchParams(queryStr || "");
    const autoSummarize = params.get("summarize") === "1" || params.get("summarize") === "true";
    showPreviewByUrl(articleUrl, autoSummarize);
  } else {
    UI.switchView("feed");
  }
}

window.addEventListener("hashchange", handleHashRouting);

// ── Global Window Handlers for PWA Sub-View ───────────────────────

window.__openPreview = (url) => {
  if (!url) return;
  if (window.location.hash.startsWith("#/storyline/")) {
    returnViewHash = window.location.hash;
  } else {
    returnViewHash = "#/";
  }
  window.location.hash = `#/preview/${encodeURIComponent(url)}`;
};

window.__openPreviewAndSummarize = (url) => {
  if (!url) return;
  if (window.location.hash.startsWith("#/storyline/")) {
    returnViewHash = window.location.hash;
  } else {
    returnViewHash = "#/";
  }
  window.location.hash = `#/preview/${encodeURIComponent(url)}?summarize=1`;
};

window.__backToFeed = () => {
  window.location.hash = returnViewHash || "#/";
};

window.__openStoryline = (id, headline) => {
  let targetId = id;
  if (!targetId || targetId === "undefined" || targetId === "null") {
    targetId = headline || "";
  }
  if (!targetId || targetId === "undefined" || targetId === "null") {
    const currentHero = UI.getCurrentHeroTrendingStory();
    if (currentHero) {
      targetId = currentHero.macro_event_id || currentHero.story_id || currentHero.cluster_id || currentHero.headline || currentHero.title || "";
    }
  }
  if (!targetId) return;

  const targetHash = `#/storyline/${encodeURIComponent(targetId)}`;
  if (window.location.hash !== targetHash) {
    window.location.hash = targetHash;
  }
  // Call loadStorylineView immediately so navigation happens without waiting
  loadStorylineView(targetId);
};

window.__openCurrentHeroStoryline = () => {
  const currentHero = UI.getCurrentHeroTrendingStory();
  if (!currentHero) return;
  const targetId = currentHero.macro_event_id || currentHero.story_id || currentHero.cluster_id || currentHero.headline || currentHero.title || "";
  const headline = currentHero.headline || currentHero.topic_title || currentHero.title || "";
  window.__openStoryline(targetId, headline);
};

window.__backFromStoryline = () => {
  window.location.hash = "#/";
};

window.__filterStorylinePublisher = (source) => {
  activeStorylineSourceFilter = (activeStorylineSourceFilter === source) ? "" : (source || "");
  if (currentStorylineData) {
    UI.renderStorylineView(
      currentStorylineData,
      activeStorylineSourceFilter,
      personalizationData.bookmarkedArticles || {},
      activeSportDisciplineFilter,
      activeSportContentTypeFilter
    );
  }
};

window.__filterSportDiscipline = (discipline) => {
  activeSportDisciplineFilter = (activeSportDisciplineFilter === discipline) ? "" : (discipline || "");
  if (currentStorylineData) {
    UI.renderStorylineView(
      currentStorylineData,
      activeStorylineSourceFilter,
      personalizationData.bookmarkedArticles || {},
      activeSportDisciplineFilter,
      activeSportContentTypeFilter
    );
  }
};

window.__filterSportContentType = (ctype) => {
  activeSportContentTypeFilter = (activeSportContentTypeFilter === ctype) ? "" : (ctype || "");
  if (currentStorylineData) {
    UI.renderStorylineView(
      currentStorylineData,
      activeStorylineSourceFilter,
      personalizationData.bookmarkedArticles || {},
      activeSportDisciplineFilter,
      activeSportContentTypeFilter
    );
  }
};

window.__openHeroSportDiscipline = (discipline) => {
  activeSportDisciplineFilter = discipline || "";
  window.__openCurrentHeroStoryline();
};

window.__runStorylineAiSummary = async (storyId) => {
  UI.showStorylineAiLoading();
  try {
    const isMacro = Boolean(currentStorylineData?.macro_event_id);
    const articles = currentStorylineData?.articles || [];
    const articleUrls = articles.map(a => a.url).filter(Boolean);
    const payload = {
      title: currentStorylineData?.headline || currentStorylineData?.title || "",
      headline: currentStorylineData?.headline || currentStorylineData?.title || "",
      articles: articles,
      article_urls: articleUrls,
    };

    let synthesis = null;
    try {
      synthesis = await triggerStorylineSynthesis(storyId, isMacro, true, payload);
    } catch (apiErr) {
      console.warn("triggerStorylineSynthesis failed, trying fallback:", apiErr);
    }

    if (synthesis && (synthesis.executive_summary || synthesis.progression_timeline)) {
      if (currentStorylineData) {
        currentStorylineData.synthesis = synthesis;
      }
      saveStorylineCache(storyId, articles, synthesis);
      UI.renderStorylineAiSynthesis(synthesis);
      // Re-render storyline view so article cards receive outlier warnings and active styles
      if (currentStorylineData) {
        UI.renderStorylineView(
          currentStorylineData,
          activeStorylineSourceFilter,
          personalizationData.bookmarkedArticles || {},
          activeSportDisciplineFilter,
          activeSportContentTypeFilter
        );
      }
      UI.showToast("สังเคราะห์ความคืบหน้าของเหตุการณ์เรียบร้อยแล้ว");
      return;
    }

    // 2. Fallback: Summarize the primary article using existing on-demand LLM service
    if (currentStorylineData && Array.isArray(currentStorylineData.articles) && currentStorylineData.articles.length > 0) {
      const firstArticle = currentStorylineData.articles[0];
      const sumRes = await summarizeArticle(firstArticle.url);
      if (sumRes.ok && sumRes.summary) {
        UI.renderStorylineAiSummary(sumRes.summary);
        return;
      }
    }

    // 3. Fallback: Deterministic synthesized summary (Guaranteed no crash, decoupled LLM)
    const fallbackBullets = (currentStorylineData && Array.isArray(currentStorylineData.articles))
      ? currentStorylineData.articles.slice(0, 4).map(a => `${a.source || 'ข่าว'}: ${a.title}`)
      : ["มีการรายงานความเคลื่อนไหวอย่างต่อเนื่องจากสำนักข่าวชั้นนำ", "ประเด็นมีความสำคัญและมีผลกระทบในวงกว้าง"];

    UI.renderStorylineAiSummary({
      summary: (currentStorylineData && currentStorylineData.summary)
        ? currentStorylineData.summary
        : "ประเด็นนี้อยู่ระหว่างการติดตามอย่างใกล้ชิดจากหลายสำนักข่าว โดยมีประเด็นสำคัญที่เชื่อมโยงถึงกันอย่างต่อเนื่อง",
      bullets: fallbackBullets,
      keywords: (currentStorylineData && (currentStorylineData.hashtags || currentStorylineData.entities)) || [],
      sentiment: "Neutral",
    });
  } catch (e) {
    console.warn("AI summary error for storyline:", e);
    UI.renderStorylineAiSummary({
      summary: (currentStorylineData && currentStorylineData.summary) || "สรุปภาพรวมประเด็นข่าว",
      bullets: [],
      keywords: [],
    });
  }
};

async function loadStorylineView(storyId) {
  let targetId = storyId;
  if (!targetId || targetId === "undefined" || targetId === "null") {
    const currentHero = UI.getCurrentHeroTrendingStory();
    if (currentHero) {
      targetId = currentHero.macro_event_id || currentHero.story_id || currentHero.cluster_id || currentHero.headline || currentHero.title || "";
    }
  }

  if (!targetId) {
    UI.showStorylineError("ไม่พบรหัสประเด็นข่าว");
    UI.switchView("storyline");
    return;
  }

  UI.showStorylineLoading();
  UI.switchView("storyline");
  activeStorylineSourceFilter = "";
  activeSportDisciplineFilter = "";
  activeSportContentTypeFilter = "";

  try {
    // 1. First attempt: fetch macro-event detail from API
    let storyData = await fetchMacroEventDetail(targetId);

    // 2. Second attempt: if not macro, fetch story detail from API
    if (!storyData) {
      storyData = await fetchStoryDetail(targetId);
    }

    // 3. Third attempt: In-memory lookup from hero carousel
    if (!storyData) {
      const heroStory = UI.getHeroTrendingStoryById(targetId);
      if (heroStory) {
        storyData = { ...heroStory };
      }
    }

    // 4. Fourth attempt: Match by keywords or cluster in currentArticleMap
    if (!storyData) {
      const matchingArticles = [];
      const lowerTarget = targetId.toLowerCase();
      for (const [url, art] of currentArticleMap.entries()) {
        const titleLower = (art.title || "").toLowerCase();
        const summaryLower = (art.summary || "").toLowerCase();
        const clusterStr = String(art.cluster_id || "").toLowerCase();
        if (titleLower.includes(lowerTarget) || summaryLower.includes(lowerTarget) || clusterStr === lowerTarget) {
          matchingArticles.push(art);
        }
      }

      if (matchingArticles.length > 0) {
        storyData = {
          macro_event_id: targetId,
          cluster_id: targetId,
          title: matchingArticles[0].title,
          headline: matchingArticles[0].title,
          summary: matchingArticles[0].summary || "รวมข่าวในประเด็นนี้",
          category: matchingArticles[0].category || "general",
          articles: matchingArticles,
          outlets: Array.from(new Set(matchingArticles.map(a => a.source).filter(Boolean))),
        };
      }
    }

    if (!storyData) {
      // 5. Final fallback: Use current hero story if available
      const heroStory = UI.getCurrentHeroTrendingStory();
      if (heroStory) {
        storyData = { ...heroStory };
      }
    }

    if (!storyData) {
      UI.showStorylineError(`ไม่พบข้อมูลสำหรับประเด็น "${targetId}"`);
      return;
    }

    // Assemble member articles list
    let memberArticles = Array.isArray(storyData.articles) ? [...storyData.articles] : [];

    // If child_events exist, extract nested articles or URLs
    if (Array.isArray(storyData.child_events)) {
      storyData.child_events.forEach(ce => {
        if (Array.isArray(ce.articles)) {
          memberArticles.push(...ce.articles);
        }
        if (Array.isArray(ce.article_urls)) {
          ce.article_urls.forEach(u => {
            const mapped = currentArticleMap.get(u);
            if (mapped) memberArticles.push(mapped);
          });
        }
      });
    }

    // Cross-match member articles by cluster_id from currentArticleMap
    const effectiveClusterId = storyData.cluster_id || storyData.macro_event_id || storyData.story_id;
    if (effectiveClusterId) {
      const clusterTarget = String(effectiveClusterId).toLowerCase();
      for (const [u, art] of currentArticleMap.entries()) {
        if (art.cluster_id && String(art.cluster_id).toLowerCase() === clusterTarget) {
          memberArticles.push(art);
        }
      }
    }

    // If few articles found, cross-match relevant articles from currentArticleMap
    if (memberArticles.length <= 1) {
      const targetKeywords = (storyData.headline || storyData.title || "")
        .split(/\s+/)
        .filter(w => w.length > 2);

      for (const [u, art] of currentArticleMap.entries()) {
        const text = `${art.title || ""} ${art.summary || ""}`;
        if (targetKeywords.some(kw => text.includes(kw))) {
          memberArticles.push(art);
        }
      }
    }

    // Deduplicate articles by URL and sync to currentArticleMap
    const seenUrls = new Set();
    const dedupedArticles = [];
    for (const a of memberArticles) {
      if (a && a.url && !seenUrls.has(a.url)) {
        seenUrls.add(a.url);
        currentArticleMap.set(a.url, a);
        dedupedArticles.push(a);
      }
    }

    storyData.articles = dedupedArticles;
    if (!storyData.outlets || storyData.outlets.length === 0) {
      storyData.outlets = Array.from(new Set(dedupedArticles.map(a => a.source).filter(Boolean)));
    }

    // If synthesis is not attached yet, try to load cached/heuristic synthesis from backend or local cache
    if (!storyData.synthesis && targetId) {
      // 1. Check local client cache first (0ms, resilient to cluster ID changes via URL signature & overlap)
      const localCached = getStorylineCache(targetId, storyData.articles);
      if (localCached && (localCached.executive_summary || localCached.progression_timeline)) {
        storyData.synthesis = localCached;
      } else {
        try {
          const isMacro = Boolean(storyData.macro_event_id);
          const cachedSynth = await fetchStorylineSynthesis(targetId, isMacro);
          if (cachedSynth && (cachedSynth.executive_summary || cachedSynth.progression_timeline)) {
            storyData.synthesis = cachedSynth;
            saveStorylineCache(targetId, storyData.articles, cachedSynth);
          }
        } catch (_) {}
      }
    } else if (storyData.synthesis && (storyData.synthesis.executive_summary || storyData.synthesis.progression_timeline)) {
      saveStorylineCache(targetId, storyData.articles, storyData.synthesis);
    }

    currentStorylineData = storyData;

    UI.renderStorylineView(
      storyData,
      activeStorylineSourceFilter,
      personalizationData.bookmarkedArticles || {},
      activeSportDisciplineFilter,
      activeSportContentTypeFilter
    );
  } catch (err) {
    console.error("Failed to load storyline view:", err);
    UI.showStorylineError(err.message || "เกิดข้อผิดพลาดในการโหลดประเด็นข่าว");
  }
}

window.__openExternalSourceClean = (url) => {
  if (!url) return;
  const cleanUrl = cleanTrackingParams(url);
  recordEngagement(url, "external_read");
  window.open(cleanUrl, "_blank", "noopener,noreferrer");
};

window.__runPreviewAiSummary = async (url) => {
  if (!url) return;
  UI.showInlineSummaryLoading();
  recordEngagement(url, "summary");
  updateAffinity(currentArticleMap.get(url), 3.5);

  try {
    const data = await summarizeArticle(url);
    if (data.ok && data.summary) {
      cachedAiSummaries[url] = data.summary;
      try {
        localStorage.setItem(AI_SUMMARIES_CACHE_KEY, JSON.stringify(cachedAiSummaries));
      } catch (e) {
        console.warn("Failed to cache AI summary:", e);
      }
      const section = document.getElementById("preview-ai-section");
      if (section) {
        section.innerHTML = UI.renderInlineSummary(data.summary);
      }
    } else {
      throw new Error(data.error || "เกิดข้อผิดพลาดในการสังเคราะห์ข้อมูล");
    }
  } catch (err) {
    UI.showInlineSummaryError(err.message, url);
  }
};

window.__shareArticle = async (title, url) => {
  const cleanUrl = cleanTrackingParams(url);
  if (navigator.share) {
    try {
      await navigator.share({
        title: title || "NEWSROOM Briefing",
        text: title,
        url: cleanUrl
      });
    } catch (e) {
      // User cancelled share
    }
  } else if (navigator.clipboard) {
    navigator.clipboard.writeText(cleanUrl).then(() => {
      UI.showToast("คัดลอกลิงก์เรียบร้อยแล้ว");
    });
  }
};

// ── History & Bookmarks Modals ────────────────────────────────────

window.__showHistory = () => {
  UI.openHistoryModal("ประวัติการอ่าน (Reading History)", "history");
  UI.renderHistoryList(readingHistory, "history", personalizationData.bookmarkedArticles || {});
};

window.__showBookmarksModal = () => {
  const bookmarksList = Object.values(personalizationData.bookmarkedArticles || {});
  UI.openHistoryModal("บทความที่บันทึกไว้ (Bookmarks)", "bookmarks");
  UI.renderHistoryList(bookmarksList, "bookmarks", personalizationData.bookmarkedArticles || {});
};

window.__closeHistoryModal = () => {
  UI.closeHistoryModal();
};

window.__clearHistoryList = () => {
  readingHistory = [];
  try {
    localStorage.removeItem(READING_HISTORY_KEY);
  } catch (e) {
    console.warn("Failed to clear reading history:", e);
  }
  UI.renderHistoryList([], "history", personalizationData.bookmarkedArticles || {});
  UI.showToast("ล้างประวัติการอ่านเรียบร้อยแล้ว");
};

// ── Service Worker & PWA Install Lifecycle ────────────────────────

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js", { scope: "/" })
      .then(reg => console.log("[PWA] Service Worker registered:", reg.scope))
      .catch(err => console.warn("[PWA] Service Worker registration failed:", err));
  });
}

// Offline connection detection
window.addEventListener("online", () => {
  UI.showOfflineStatus(false);
  UI.showToast("🟢 กลับมาออนไลน์แล้ว");
});
window.addEventListener("offline", () => {
  UI.showOfflineStatus(true);
  UI.showToast("🟠 เข้าสู่โหมดออฟไลน์ (กำลังอ่านจากแคชบนเครื่อง)");
});
if (!navigator.onLine) {
  UI.showOfflineStatus(true);
}

// PWA Install prompt handling
let deferredPrompt = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredPrompt = e;
  UI.showPwaInstallBanner(async () => {
    if (deferredPrompt) {
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      console.log("[PWA] User choice:", outcome);
      deferredPrompt = null;
      UI.hidePwaInstallBanner();
    }
  });
});

window.__dismissPwaInstall = () => {
  UI.hidePwaInstallBanner();
};

window.__openOutletArticle = (outlet) => {
  if (!outlet) return;

  const currentStory = (typeof UI.getCurrentHeroTrendingStory === "function")
    ? UI.getCurrentHeroTrendingStory()
    : null;

  let targetUrl = "";

  if (currentStory) {
    // 1. Direct match in story.articles
    const matchingArt = (currentStory.articles || []).find(a =>
      a.source && a.source.toLowerCase() === outlet.toLowerCase()
    );
    if (matchingArt && matchingArt.url) {
      targetUrl = matchingArt.url;
    }

    // 2. Direct match in story.child_events
    if (!targetUrl && Array.isArray(currentStory.child_events)) {
      for (const ce of currentStory.child_events) {
        const ceArt = (ce.articles || []).find(a =>
          a.source && a.source.toLowerCase() === outlet.toLowerCase()
        );
        if (ceArt && ceArt.url) {
          targetUrl = ceArt.url;
          break;
        }
      }
    }
  }

  // 3. Fallback match in cached article map
  if (!targetUrl && currentStory) {
    const rawHeadline = (currentStory.headline || currentStory.title || "").toLowerCase();
    for (const [u, art] of currentArticleMap.entries()) {
      if (art.source && art.source.toLowerCase() === outlet.toLowerCase()) {
        const artTitle = (art.title || "").toLowerCase();
        if (rawHeadline && artTitle && (rawHeadline.includes(artTitle.slice(0, 10)) || artTitle.includes(rawHeadline.slice(0, 10)))) {
          targetUrl = u;
          break;
        }
      }
    }
  }

  if (targetUrl) {
    UI.showToast(`กำลังเปิดรายงานข่าวจาก ${outlet}`);
    window.__openPreview(targetUrl);
  } else {
    // Fallback: filter news feed by this source
    UI.showToast(`กำลังกรองข่าวจาก ${outlet}`);
    window.__sourceFilterClick(outlet);
  }
};

window.__filterByHashtag = (tag) => {
  if (!tag) return;
  const cleanTag = tag.startsWith("#") ? tag.slice(1) : tag;
  if (activeCategory === "bookmarks" || activeCategory === "for-you") {
    activeCategory = "all";
    UI.renderCategoryNav("all", {}, personalizationData.bookmarkedArticles || {});
  }
  activeSource = "";
  UI.updateSourceFilters("");
  const searchInput = document.getElementById("search-input");
  if (searchInput) {
    searchInput.value = cleanTag;
    searchQuery = cleanTag;
    UI.renderStorylineBreadcrumb(`#${cleanTag}`);
    loadPage(1);
    const grid = document.getElementById("news-grid-section") || document.getElementById("news-grid");
    if (grid) {
      grid.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      searchInput.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    UI.showToast(`กำลังกรองข่าวประเด็น #${cleanTag}`);
  }
};

window.__filterByStoryline = (macroId, headline, tag) => {
  if (macroId || headline) {
    window.__openStoryline(macroId, headline);
    return;
  }
  const filterText = tag || "";
  if (!filterText) return;
  if (activeCategory === "bookmarks" || activeCategory === "for-you") {
    activeCategory = "all";
    UI.renderCategoryNav("all", {}, personalizationData.bookmarkedArticles || {});
  }
  activeSource = "";
  UI.updateSourceFilters("");

  // Determine query string
  let cleanKw = filterText;
  if (filterText.startsWith("#")) {
    cleanKw = filterText.slice(1);
  } else if (filterText.includes("จีดีพี") || filterText.includes("GDP")) {
    cleanKw = "GDP";
  } else if (filterText.includes("แบงก์ชาติ") || filterText.includes("ธปท")) {
    cleanKw = "แบงก์ชาติ";
  } else if (filterText.includes("IMF")) {
    cleanKw = "IMF";
  } else {
    cleanKw = filterText.slice(0, 20).trim();
  }

  const searchInput = document.getElementById("search-input");
  if (searchInput) {
    searchInput.value = cleanKw;
    searchQuery = cleanKw;
    UI.renderStorylineBreadcrumb(headline || tag || cleanKw);
    loadPage(1);
    const grid = document.getElementById("news-grid-section") || document.getElementById("news-grid") || document.getElementById("toolbar");
    if (grid) {
      grid.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    UI.showToast(`กำลังกรองข่าวในมหากาพย์: ${cleanKw}`);
  }
};

window.__clearStorylineFilter = () => {
  const searchInput = document.getElementById("search-input");
  if (searchInput) {
    searchInput.value = "";
  }
  searchQuery = "";
  UI.renderStorylineBreadcrumb("");
  loadPage(1);
  UI.showToast("ล้างตัวกรองกลับสู่ข่าวทั้งหมดเรียบร้อย");
};

// ── Init: draw category nav & source filters ──────────────────────

if (hasConsent) {
  applyPersonalization();
}

UI.renderCategoryNav(activeCategory, {}, personalizationData.bookmarkedArticles || {});
UI.renderSourceFilters([], activeSource, {});
initialLoadStarted = true;
loadPage(1);
refreshCategoryCounts();
refreshSourceFilters();
checkPDPA();

// ── Storyline Scroll Management (Auto-hide top bar on scroll-down, floating back button) ──
let lastStorylineScrollY = window.scrollY;
let storylineScrollTicking = false;

function onStorylineWindowScroll() {
  const currentY = window.scrollY;
  const isStorylineActive = window.location.hash.startsWith("#/storyline/") ||
    (document.getElementById("storyline-view") && !document.getElementById("storyline-view").classList.contains("hidden"));

  const floatingBtn = document.getElementById("storyline-floating-back");
  const topBar = document.getElementById("storyline-top-bar");

  if (!isStorylineActive) {
    if (floatingBtn) floatingBtn.classList.add("hidden-fade");
    if (topBar) topBar.classList.remove("is-hidden");
    lastStorylineScrollY = currentY;
    return;
  }

  // Show floating back button when scrolled down past header
  if (currentY > 80) {
    if (floatingBtn) floatingBtn.classList.remove("hidden-fade");
  } else {
    if (floatingBtn) floatingBtn.classList.add("hidden-fade");
  }

  // Auto-hide top bar when scrolling down, show when scrolling up
  if (topBar) {
    if (currentY > 80 && currentY > lastStorylineScrollY + 6) {
      topBar.classList.add("is-hidden");
    } else if (currentY < lastStorylineScrollY - 6 || currentY <= 80) {
      topBar.classList.remove("is-hidden");
    }
  }

  lastStorylineScrollY = currentY;
}

window.addEventListener("scroll", () => {
  if (!storylineScrollTicking) {
    window.requestAnimationFrame(() => {
      onStorylineWindowScroll();
      storylineScrollTicking = false;
    });
    storylineScrollTicking = true;
  }
}, { passive: true });

// Handle initial route on startup
handleHashRouting();
