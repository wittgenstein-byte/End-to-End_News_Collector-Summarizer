/**
 * frontend/static/issues/issues-main.js
 * ─────────────────────────────────────────────────────────────────
 * Main controller for Issue Explorer.
 * Coordinates input events, URL query params sync, API calls, and UI rendering.
 * ─────────────────────────────────────────────────────────────────
 */

import { searchIssues } from "./issues-api.js";
import { DEBOUNCE_DELAY_MS, ISSUES_VERSION } from "./issues-config.js";
import {
    exportData,
    renderArticles,
    renderClusters,
    renderPossiblyUnrelated,
    renderRelatedTerms,
    renderStats,
    renderSynonyms,
    renderTimeline,
} from "./issues-ui.js";

console.log(`[IssueExplorer] Loaded v${ISSUES_VERSION}`);

// ── Application State ─────────────────────────────────────────────
const state = {
  query: "",
  expand: true,
  category: "",
  source: "",
  dateFrom: "",
  dateTo: "",
  selectedClusterId: null,
  clusterSort: "size",
  lastResult: null,
  isSearching: false,
};

let currentAbortController = null;
let debounceTimer = null;

// ── DOM References ────────────────────────────────────────────────
const DOM = {
  searchForm: document.getElementById("search-form"),
  searchInput: document.getElementById("search-input"),
  clearSearchBtn: document.getElementById("clear-search-btn"),
  expandToggle: document.getElementById("expand-toggle"),
  categorySelect: document.getElementById("category-select"),
  sourceSelect: document.getElementById("source-select"),
  dateFromInput: document.getElementById("date-from-input"),
  dateToInput: document.getElementById("date-to-input"),
  resetFiltersBtn: document.getElementById("reset-filters-btn"),
  themeToggleBtn: document.getElementById("theme-toggle-btn"),

  exportJsonBtn: document.getElementById("export-json-btn"),
  exportCsvBtn: document.getElementById("export-csv-btn"),

  statsContainer: document.getElementById("stats-container"),
  synonymsContainer: document.getElementById("synonyms-container"),
  timelineContainer: document.getElementById("timeline-container"),
  clustersContainer: document.getElementById("clusters-container"),
  relatedTermsContainer: document.getElementById("related-terms-container"),
  articlesContainer: document.getElementById("articles-container"),
  possiblyUnrelatedContainer: document.getElementById("possibly-unrelated-container"),

  loadingIndicator: document.getElementById("loading-indicator"),
  emptyState: document.getElementById("empty-state"),
  errorState: document.getElementById("error-state"),
  errorMessage: document.getElementById("error-message"),
  resultsSection: document.getElementById("results-section"),
};

// ── Search Execution ──────────────────────────────────────────────
async function executeSearch(updateUrl = true) {
  if (DOM.searchInput && DOM.searchInput.value !== undefined) {
    state.query = DOM.searchInput.value;
  }
  const query = state.query.trim();
  if (!query) {
    showEmptyView();
    if (updateUrl) syncUrl();
    return;
  }

  // Cancel any ongoing fetch
  if (currentAbortController) {
    currentAbortController.abort();
  }
  currentAbortController = new AbortController();
  const signal = currentAbortController.signal;

  setLoading(true);
  hideError();

  if (updateUrl) {
    syncUrl();
  }

  try {
    const params = {
      q: query,
      expand: state.expand,
      category: state.category,
      source: state.source,
      date_from: state.dateFrom,
      date_to: state.dateTo,
      limit: 200,
    };

    const data = await searchIssues(params, signal);
    state.lastResult = data;
    state.selectedClusterId = null;

    renderResults(data);
  } catch (err) {
    if (err.name === "AbortError") {
      // Intentionally aborted
      return;
    }
    console.error("[IssueExplorer] Search error:", err);
    showErrorView(err.message);
  } finally {
    setLoading(false);
  }
}

// ── Render Views ──────────────────────────────────────────────────
function renderResults(data) {
  DOM.emptyState.classList.add("hidden");
  DOM.errorState.classList.add("hidden");
  DOM.resultsSection.classList.remove("hidden");

  // Populate dynamic sources & categories dropdowns if not already set
  populateFilters(data.sources, data.categories);

  // 1. Stats Bar
  renderStats(DOM.statsContainer, data.stats, data.query);

  // 2. Synonyms
  renderSynonyms(DOM.synonymsContainer, data.query?.expanded_terms || [], () => {
    state.expand = !state.expand;
    if (DOM.expandToggle) DOM.expandToggle.checked = state.expand;
    executeSearch();
  });

  // 3. Timeline
  renderTimeline(DOM.timelineContainer, data.timeline || []);

  // 4. Clusters with dynamic sorting
  renderCurrentClusters();

  // 5. Related Terms
  renderRelatedTerms(DOM.relatedTermsContainer, data.related_terms || [], (term) => {
    handleAppendQuery(term);
  });

  // 6. Articles
  updateArticleList();

  // 7. Possibly Unrelated
  renderPossiblyUnrelated(DOM.possiblyUnrelatedContainer, data.possibly_unrelated || []);
}

function getSortedClusters(clusters, sortMode) {
  const list = [...(clusters || [])];
  if (sortMode === "time") {
    return list.sort((a, b) => (a.first_seen || "").localeCompare(b.first_seen || ""));
  }
  return list.sort((a, b) => (b.size || 0) - (a.size || 0));
}

function renderCurrentClusters() {
  const rawClusters = state.lastResult?.clusters || [];
  const clusters = getSortedClusters(rawClusters, state.clusterSort);
  renderClusters(
    DOM.clustersContainer,
    clusters,
    (clusterId) => handleClusterSelect(clusterId),
    state.clusterSort,
    (newSort) => {
      state.clusterSort = newSort;
      renderCurrentClusters();
      if (state.selectedClusterId) {
        highlightSelectedCluster(state.selectedClusterId);
      }
    }
  );
  if (state.selectedClusterId) {
    highlightSelectedCluster(state.selectedClusterId);
  }
}

function highlightSelectedCluster(clusterId) {
  const allCards = DOM.clustersContainer.querySelectorAll("[data-cluster-id]");
  allCards.forEach(card => {
    if (card.getAttribute("data-cluster-id") === clusterId) {
      card.classList.add("ring-2", "ring-primary", "bg-primary/5");
    } else {
      card.classList.remove("ring-2", "ring-primary", "bg-primary/5");
    }
  });
}

function updateArticleList() {
  if (!state.lastResult) return;

  let articles = state.lastResult.articles || [];
  if (state.selectedClusterId) {
    articles = articles.filter(a => a.cluster_id === state.selectedClusterId);
  }

  // Highlight terms = primary terms + expanded terms
  const terms = state.lastResult.query?.expanded_terms || [state.query];
  renderArticles(DOM.articlesContainer, articles, terms);
}

function handleClusterSelect(clusterId) {
  if (state.selectedClusterId === clusterId) {
    state.selectedClusterId = null; // Toggle off
  } else {
    state.selectedClusterId = clusterId;
  }
  highlightSelectedCluster(state.selectedClusterId);
  updateArticleList();
}

function handleAppendQuery(term) {
  const current = state.query.trim();
  if (!current.includes(term)) {
    state.query = `${current} ${term}`.trim();
    if (DOM.searchInput) DOM.searchInput.value = state.query;
    executeSearch();
  }
}

function populateFilters(sources = [], categories = []) {
  if (DOM.sourceSelect && DOM.sourceSelect.options.length <= 1 && sources.length > 0) {
    sources.forEach(s => {
      const opt = document.createElement("option");
      opt.value = s.name;
      opt.textContent = `${s.name} (${s.count})`;
      DOM.sourceSelect.appendChild(opt);
    });
  }

  if (DOM.categorySelect && DOM.categorySelect.options.length <= 1 && categories.length > 0) {
    categories.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c.name;
      opt.textContent = `${c.name} (${c.count})`;
      DOM.categorySelect.appendChild(opt);
    });
  }
}

// ── UI State Helpers ──────────────────────────────────────────────
function setLoading(loading) {
  state.isSearching = loading;
  if (loading) {
    DOM.loadingIndicator.classList.remove("hidden");
  } else {
    DOM.loadingIndicator.classList.add("hidden");
  }
}

function showEmptyView() {
  DOM.emptyState.classList.remove("hidden");
  DOM.errorState.classList.add("hidden");
  DOM.resultsSection.classList.add("hidden");
  state.lastResult = null;
}

function showErrorView(message) {
  DOM.emptyState.classList.add("hidden");
  DOM.errorState.classList.remove("hidden");
  DOM.resultsSection.classList.add("hidden");
  if (DOM.errorMessage) DOM.errorMessage.textContent = message;
}

function hideError() {
  DOM.errorState.classList.add("hidden");
}

// ── URL Synchronization ───────────────────────────────────────────
function syncUrl() {
  const params = new URLSearchParams();
  if (state.query) params.set("q", state.query);
  if (!state.expand) params.set("expand", "false");
  if (state.category) params.set("category", state.category);
  if (state.source) params.set("source", state.source);
  if (state.dateFrom) params.set("date_from", state.dateFrom);
  if (state.dateTo) params.set("date_to", state.dateTo);

  const qs = params.toString();
  const newUrl = qs ? `${window.location.pathname}?${qs}` : window.location.pathname;
  try {
    const historyState = {
      query: state.query,
      expand: state.expand,
      category: state.category,
      source: state.source,
      dateFrom: state.dateFrom,
      dateTo: state.dateTo,
      selectedClusterId: state.selectedClusterId,
    };
    window.history.replaceState(historyState, "", newUrl);
  } catch (err) {
    console.warn("[IssueExplorer] replaceState failed:", err);
  }
}

function loadStateFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const q = params.get("q") || "";
  state.query = q;
  state.expand = params.get("expand") !== "false";
  state.category = params.get("category") || "";
  state.source = params.get("source") || "";
  state.dateFrom = params.get("date_from") || "";
  state.dateTo = params.get("date_to") || "";

  if (DOM.searchInput) DOM.searchInput.value = state.query;
  if (DOM.expandToggle) DOM.expandToggle.checked = state.expand;
  if (DOM.categorySelect) DOM.categorySelect.value = state.category;
  if (DOM.sourceSelect) DOM.sourceSelect.value = state.source;
  if (DOM.dateFromInput) DOM.dateFromInput.value = state.dateFrom;
  if (DOM.dateToInput) DOM.dateToInput.value = state.dateTo;

  if (state.query) {
    executeSearch(false);
  } else {
    showEmptyView();
  }
}

// ── Event Bindings ────────────────────────────────────────────────
function bindEvents() {
  // 0. Search form submission (handles Enter key and search button)
  DOM.searchForm?.addEventListener("submit", (e) => {
    e.preventDefault();
    clearTimeout(debounceTimer);
    if (DOM.searchInput) {
      state.query = DOM.searchInput.value;
    }
    executeSearch();
  });

  // 1. Search input with debounce & Enter handling
  DOM.searchInput?.addEventListener("input", (e) => {
    state.query = e.target.value;
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      executeSearch();
    }, DEBOUNCE_DELAY_MS);
  });

  DOM.searchInput?.addEventListener("keydown", (e) => {
    if (e.isComposing) return;
    if (e.key === "Enter") {
      e.preventDefault();
      clearTimeout(debounceTimer);
      state.query = e.target.value;
      executeSearch();
    }
  });

  // 2. Clear button
  DOM.clearSearchBtn?.addEventListener("click", () => {
    state.query = "";
    if (DOM.searchInput) {
      DOM.searchInput.value = "";
      DOM.searchInput.focus();
    }
    showEmptyView();
    syncUrl();
  });

  // 3. Expand Toggle
  DOM.expandToggle?.addEventListener("change", (e) => {
    state.expand = e.target.checked;
    if (state.query) executeSearch();
  });

  // 4. Filters
  DOM.categorySelect?.addEventListener("change", (e) => {
    state.category = e.target.value;
    if (state.query) executeSearch();
  });

  DOM.sourceSelect?.addEventListener("change", (e) => {
    state.source = e.target.value;
    if (state.query) executeSearch();
  });

  DOM.dateFromInput?.addEventListener("change", (e) => {
    state.dateFrom = e.target.value;
    if (state.query) executeSearch();
  });

  DOM.dateToInput?.addEventListener("change", (e) => {
    state.dateTo = e.target.value;
    if (state.query) executeSearch();
  });

  DOM.resetFiltersBtn?.addEventListener("click", () => {
    state.category = "";
    state.source = "";
    state.dateFrom = "";
    state.dateTo = "";
    if (DOM.categorySelect) DOM.categorySelect.value = "";
    if (DOM.sourceSelect) DOM.sourceSelect.value = "";
    if (DOM.dateFromInput) DOM.dateFromInput.value = "";
    if (DOM.dateToInput) DOM.dateToInput.value = "";
    if (state.query) executeSearch();
  });

  // 5. Export buttons
  DOM.exportJsonBtn?.addEventListener("click", () => {
    if (state.lastResult) exportData(state.lastResult, "json");
  });

  DOM.exportCsvBtn?.addEventListener("click", () => {
    if (state.lastResult) exportData(state.lastResult, "csv");
  });

  // 6. Example query chips on empty view
  document.querySelectorAll("[data-example-query]").forEach(btn => {
    btn.addEventListener("click", () => {
      const q = btn.getAttribute("data-example-query");
      if (q) {
        state.query = q;
        if (DOM.searchInput) DOM.searchInput.value = q;
        executeSearch();
      }
    });
  });

  // 7. Popstate navigation
  window.addEventListener("popstate", () => {
    loadStateFromUrl();
  });

  // 8. Theme Toggle (Syncs with global theme_pref and personalization)
  DOM.themeToggleBtn?.addEventListener("click", () => {
    const isDark = document.documentElement.classList.contains("dark");
    const nextDark = !isDark;
    if (nextDark) {
      document.documentElement.classList.add("dark");
      document.documentElement.classList.remove("light");
    } else {
      document.documentElement.classList.remove("dark");
      document.documentElement.classList.add("light");
    }
    try {
      localStorage.setItem("theme_pref", nextDark ? "dark" : "light");
      const p = JSON.parse(localStorage.getItem("personalization") || "{}");
      p.darkMode = nextDark;
      localStorage.setItem("personalization", JSON.stringify(p));
    } catch (err) {
      console.warn("[IssueExplorer] Failed to save theme preference:", err);
    }
  });
}

// ── Initialize ────────────────────────────────────────────────────
bindEvents();
loadStateFromUrl();
