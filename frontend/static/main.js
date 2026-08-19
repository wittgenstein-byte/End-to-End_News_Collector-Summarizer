/**
 * main.js — App controller (GRASP: Controller)
 *
 * Purpose: bridge API and UI logic.
 */

import {
  fetchNews,
  summarizeArticle,
  createSocket,
  fetchCategories,
  trackEvent,
  hasCookieConsent,
  getAnonymousUserId,
  setCookieConsent,
} from "./api.js";
import * as UI from "./UI.js";

let currentPage = 1;
let activeSource = "";
let activeCategory = "all";
let searchQuery = "";
let searchTimer = null;
let totalNew = 0;
let newArticleSet = new Set();

function trackPageView() {
  if (!hasCookieConsent()) return;
  trackEvent("page_view", {
    category: activeCategory,
    source: activeSource,
    metadata: {
      page: currentPage,
      search_query: searchQuery,
    },
  });
}

function initCookieConsent() {
  const banner = document.getElementById("cookie-consent");
  if (!banner) return;

  const accepted = hasCookieConsent();
  banner.classList.toggle("hidden", accepted);

  if (accepted) {
    getAnonymousUserId();
  }
}

window.__acceptCookies = () => {
  setCookieConsent(true);
  const banner = document.getElementById("cookie-consent");
  if (banner) banner.classList.add("hidden");
  getAnonymousUserId();
  trackEvent("cookie_consent", {
    metadata: { choice: "accept" },
  });
};

window.__declineCookies = () => {
  setCookieConsent(false);
  const banner = document.getElementById("cookie-consent");
  if (banner) banner.classList.add("hidden");
};

async function loadPage(page = 1) {
  currentPage = page;
  UI.showGridLoading();

  try {
    const data = await fetchNews(page, activeSource, searchQuery, activeCategory);
    UI.renderGrid(data.news, newArticleSet);
    UI.renderPagination(data);
    UI.updateStats({ total: data.total, updated: data.updated });
    UI.updateTicker(data.news.slice(0, 15).map((n) => n.title));
    trackPageView();
  } catch (e) {
    UI.showGridError(e.message);
  }
}

function handleCategoryClick(id) {
  activeCategory = id;
  UI.renderCategoryNav(id, {});
  trackEvent("category_click", {
    category: id,
    source: activeSource,
    metadata: {
      page: 1,
      search_query: searchQuery,
    },
  });
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

window.__loadPage = loadPage;
window.__categoryClick = handleCategoryClick;

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
      throw new Error(data.error ?? "Summary could not be generated");
    }
  } catch (err) {
    UI.showModalError(err.message);
  }
}

window.__summarize = handleSummarize;

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
    data.articles.forEach((a) => newArticleSet.add(a.url));
    UI.updateStats({ total: data.total, newCount: totalNew, updated: data.updated });
    UI.updateTicker(data.articles.map((a) => a.title));
    UI.showToast(`New articles: ${data.count}`);
  },
});

document.querySelectorAll(".filter-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    activeSource = btn.dataset.source ?? "";
    UI.updateSourceFilters(activeSource);
    trackEvent("source_filter", {
      source: activeSource,
      category: activeCategory,
      metadata: {
        page: 1,
        search_query: searchQuery,
      },
    });
    loadPage(1);
  });
});

document.getElementById("search-input").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    searchQuery = e.target.value.trim();
    trackEvent("search", {
      category: activeCategory,
      source: activeSource,
      metadata: {
        page: 1,
        search_query: searchQuery,
      },
    });
    loadPage(1);
  }, 400);
});

document.getElementById("news-grid").addEventListener("click", (event) => {
  const link = event.target.closest("a[href]");
  if (!link || !link.href) return;

  const articleUrl = link.href;
  const title = link.dataset.title || link.querySelector("h2")?.textContent?.trim() || "";
  const source = link.dataset.source || "";
  const category = link.dataset.category || activeCategory;

  trackEvent("article_open", {
    article_url: articleUrl,
    article_title: title,
    source,
    category,
    metadata: {
      page: currentPage,
      search_query: searchQuery,
    },
  });
});

document.getElementById("toast").addEventListener("click", () => {
  UI.hideToast();
  loadPage(1);
});

document.getElementById("summary-modal").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) UI.closeModal();
});
document.getElementById("modal-close-btn").addEventListener("click", () => UI.closeModal());

UI.renderCategoryNav("all", {});
refreshCategoryCounts();
initCookieConsent();
