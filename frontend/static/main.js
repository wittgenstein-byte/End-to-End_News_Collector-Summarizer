/**
 * main.js — App controller (GRASP: Controller)
 *
 * หน้าที่: เชื่อม api.js กับ ui.js
 * ไม่ fetch เอง ไม่แตะ DOM โดยตรง
 * เป็น orchestrator เท่านั้น
 */

import { fetchNews, summarizeArticle, createSocket, fetchCategories } from "./api.js";
import * as UI from "./UI.js";

// ── State ─────────────────────────────────────────────────────────
let currentPage   = 1;
let activeSource  = "";
let activeCategory = "all";
let searchQuery   = "";
let searchTimer   = null;
let totalNew      = 0;
let newArticleSet = new Set();   // Set<url> ของข่าวใหม่ใน session

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

createSocket({
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
  },
});

// ── Filter buttons ────────────────────────────────────────────────

document.querySelectorAll(".filter-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    activeSource = btn.dataset.source ?? "";
    loadPage(1);
  });
});

// ── Search ────────────────────────────────────────────────────────

document.getElementById("search-input").addEventListener("input", e => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    searchQuery = e.target.value.trim();
    loadPage(1);
  }, 400);
});

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