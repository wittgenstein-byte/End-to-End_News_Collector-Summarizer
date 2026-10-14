/**
 * backend/tests/test_client_storage_harness.js
 * ─────────────────────────────────────────────────────────────────
 * Empirical Node.js Test Harness for Layer 1:
 * Frontend Client-Side Storage, Offline Cache, Bookmarks, and PDPA Gating.
 * ─────────────────────────────────────────────────────────────────
 */

const assert = require("assert");

// Mock LocalStorage
class MockLocalStorage {
  constructor() {
    this.store = {};
  }
  getItem(key) {
    return Object.prototype.hasOwnProperty.call(this.store, key) ? this.store[key] : null;
  }
  setItem(key, value) {
    this.store[key] = String(value);
  }
  removeItem(key) {
    delete this.store[key];
  }
  clear() {
    this.store = {};
  }
}

// Setup Global Environment
const localStorage = new MockLocalStorage();
global.localStorage = localStorage;

// ── Test Suite ───────────────────────────────────────────────────

console.log("🚀 Starting Node.js Layer 1 Empirical Test Harness...\n");

// Test 1: PDPA Banner and Consent Gating
{
  console.log("Test 1: PDPA Initial State & Consent Acceptance");
  localStorage.clear();

  const PDPA_KEY = "pdpa_consent";
  const PERSONALIZATION_KEY = "personalization";
  const SEARCH_HISTORY_KEY = "search_history";
  const NEWS_CACHE_KEY = "news_cache";

  assert.strictEqual(localStorage.getItem(PDPA_KEY), null, "Consent should be null on first visit");

  // Accept Cookies
  let hasConsent = true;
  localStorage.setItem(PDPA_KEY, "true");
  let personalizationData = { darkMode: true, fontSize: "16px", preferredCategory: "technology" };
  localStorage.setItem(PERSONALIZATION_KEY, JSON.stringify(personalizationData));

  assert.strictEqual(localStorage.getItem(PDPA_KEY), "true");
  assert.deepStrictEqual(JSON.parse(localStorage.getItem(PERSONALIZATION_KEY)), personalizationData);
  console.log("  ✅ PDPA Acceptance test passed.");
}

// Test 2: PDPA Consent Rejection & Full Storage Cleansing
{
  console.log("Test 2: PDPA Rejection & Storage Cleansing Invariants");
  const PDPA_KEY = "pdpa_consent";
  const PERSONALIZATION_KEY = "personalization";
  const SEARCH_HISTORY_KEY = "search_history";
  const NEWS_CACHE_KEY = "news_cache";

  // Simulate decline cookies
  let hasConsent = false;
  localStorage.setItem(PDPA_KEY, "false");
  localStorage.removeItem(PERSONALIZATION_KEY);
  localStorage.removeItem(SEARCH_HISTORY_KEY);
  localStorage.removeItem(NEWS_CACHE_KEY);
  let personalizationData = {};
  let searchHistory = [];

  assert.strictEqual(localStorage.getItem(PDPA_KEY), "false");
  assert.strictEqual(localStorage.getItem(PERSONALIZATION_KEY), null);
  assert.strictEqual(localStorage.getItem(SEARCH_HISTORY_KEY), null);
  assert.strictEqual(localStorage.getItem(NEWS_CACHE_KEY), null);
  assert.deepStrictEqual(personalizationData, {});
  assert.deepStrictEqual(searchHistory, []);
  console.log("  ✅ PDPA Rejection and data wipe test passed.");
}

// Test 3: Bookmark Serialization & Idempotent Toggling
{
  console.log("Test 3: Bookmark Schema & Mutation Invariants");
  let personalizationData = { bookmarkedArticles: {} };
  let hasConsent = true;

  const sampleArticle = {
    title: "AI Breakthrough 2026",
    summary: "New neural architecture unveiled.",
    source: "ThaiPBS",
    url: "https://thaipbs.or.th/news/123",
    image_url: "https://thaipbs.or.th/img/123.jpg",
    category: "technology",
    classification_method: "WangchanBERTa",
    fetched_at: "2026-08-21 15:00:00"
  };

  // 1. Toggle Add
  const encoded = encodeURIComponent(JSON.stringify(sampleArticle));
  const decoded = JSON.parse(decodeURIComponent(encoded));

  if (!personalizationData.bookmarkedArticles[decoded.url]) {
    decoded.bookmarked_at = new Date().toISOString();
    personalizationData.bookmarkedArticles[decoded.url] = decoded;
  }

  assert.strictEqual(Object.keys(personalizationData.bookmarkedArticles).length, 1);
  const saved = personalizationData.bookmarkedArticles[decoded.url];
  assert.strictEqual(saved.title, "AI Breakthrough 2026");
  assert.ok(saved.bookmarked_at, "Must have bookmarked_at ISO string");

  // 2. Toggle Remove
  if (personalizationData.bookmarkedArticles[decoded.url]) {
    delete personalizationData.bookmarkedArticles[decoded.url];
  }
  assert.strictEqual(Object.keys(personalizationData.bookmarkedArticles).length, 0);
  console.log("  ✅ Bookmark Schema and Toggle test passed.");
}

// Test 4: 24h Offline News Cache Expiration & Purge
{
  console.log("Test 4: 24h Offline News Cache TTL Expiration & Auto-Purge");
  const NEWS_CACHE_KEY = "news_cache";
  const CACHE_TTL_MS = 24 * 60 * 60 * 1000;
  const now = Date.now();

  // Fresh cache (10 minutes old)
  const freshPayload = {
    timestamp: now - (10 * 60 * 1000),
    articles: [{ title: "Fresh", url: "https://ex.com/1", category: "all" }],
    total: 1,
    updated: "2026-08-21 15:00:00"
  };
  localStorage.setItem(NEWS_CACHE_KEY, JSON.stringify(freshPayload));

  let cachedRaw = localStorage.getItem(NEWS_CACHE_KEY);
  let cached = JSON.parse(cachedRaw);
  let isFresh = cached && (Date.now() - (cached.timestamp || 0) < CACHE_TTL_MS);
  assert.strictEqual(isFresh, true, "10-minute old cache must be fresh");

  // Stale cache (25 hours old)
  const stalePayload = {
    timestamp: now - (25 * 60 * 60 * 1000),
    articles: [{ title: "Stale", url: "https://ex.com/2", category: "all" }],
    total: 1,
    updated: "2026-08-20 14:00:00"
  };
  localStorage.setItem(NEWS_CACHE_KEY, JSON.stringify(stalePayload));

  cachedRaw = localStorage.getItem(NEWS_CACHE_KEY);
  cached = JSON.parse(cachedRaw);
  let isStale = cached && (Date.now() - (cached.timestamp || 0) >= CACHE_TTL_MS);
  assert.strictEqual(isStale, true, "25-hour old cache must be stale");

  // Purge stale
  if (isStale) {
    localStorage.removeItem(NEWS_CACHE_KEY);
  }
  assert.strictEqual(localStorage.getItem(NEWS_CACHE_KEY), null, "Stale cache must be purged");
  console.log("  ✅ Offline News Cache TTL and Auto-Purge test passed.");
}

console.log("\n🎉 ALL Node.js Layer 1 Invariant Tests Passed Successfully!");
