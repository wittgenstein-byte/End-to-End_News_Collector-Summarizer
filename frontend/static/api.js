/**
 * api.js — Dedicated REST HTTP Client Layer & Data Normalization
 *
 * Responsibilities:
 * - All HTTP communication with backend REST endpoints using resolveApiBase() from config.js
 * - Standardized ApiError encapsulation (status, statusText, url, responseBody, timestamp, offline/timeout)
 * - Automatic article & story normalization (resolving relative image URLs via resolveImageUrl())
 * - Clean network timeout handling via AbortController and offline detection
 * - Zero DOM manipulation; pure data layer
 * - Strictly <800 LOC
 *
 * Note on WebSocket:
 * In Milestone 2, WebSocket connection management is isolated in ./socket.js.
 * Backward-compatible re-exports for createSocket/getSocket are provided with deprecation notices.
 */

import { resolveApiBase, resolveImageUrl } from "./config.js";
// Temporary migration bridge for unmigrated callers in main.js:
import { createSocket, getSocket } from "./socket.js";

export const DEFAULT_TIMEOUT_MS = 15000;

// ── Standardized ApiError ──────────────────────────────────────────

export class ApiError extends Error {
  /**
   * @param {object} params
   * @param {string} [params.message]
   * @param {number} [params.status=0]
   * @param {string} [params.statusText=""]
   * @param {string} [params.url=""]
   * @param {any} [params.responseBody=null]
   * @param {string} [params.timestamp]
   * @param {boolean} [params.isOffline=false]
   * @param {boolean} [params.isTimeout=false]
   */
  constructor(optionsOrMessage = {}, maybeStatus = 0, maybeStatusText = "") {
    let opts = {};
    if (typeof optionsOrMessage === "string") {
      opts = {
        message: optionsOrMessage,
        status: typeof maybeStatus === "number" ? maybeStatus : 0,
        statusText: typeof maybeStatusText === "string" ? maybeStatusText : String(maybeStatusText || ""),
      };
    } else if (optionsOrMessage && typeof optionsOrMessage === "object") {
      opts = optionsOrMessage;
    }

    const {
      message = "",
      status = 0,
      statusText = "",
      url = "",
      responseBody = null,
      timestamp = new Date().toISOString(),
      isOffline = false,
      isTimeout = false,
    } = opts;
    const defaultMsg = isOffline
      ? "อุปกรณ์ของคุณไม่ได้เชื่อมต่ออินเทอร์เน็ต (Offline)"
      : isTimeout
      ? `คำขอหมดเวลา (Request Timeout): ${url || "network"}`
      : status
      ? `HTTP ${status}: ${statusText || "Request failed"}`
      : "การเชื่อมต่อเครือข่ายล้มเหลว (Network request failed)";

    super(message || defaultMsg);
    this.name = "ApiError";
    this.status = status;
    this.statusText = statusText;
    this.url = url;
    this.responseBody = responseBody;
    this.timestamp = timestamp;
    this.isOffline = Boolean(isOffline);
    this.isTimeout = Boolean(isTimeout);

    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, ApiError);
    }
  }

  get isClientError() {
    return this.status >= 400 && this.status < 500;
  }

  get isServerError() {
    return this.status >= 500 && this.status < 600;
  }

  toJSON() {
    return {
      name: this.name,
      message: this.message,
      status: this.status,
      statusText: this.statusText,
      url: this.url,
      responseBody: this.responseBody,
      timestamp: this.timestamp,
      isOffline: this.isOffline,
      isTimeout: this.isTimeout,
    };
  }
}

// ── HTTP Core Execution & Error Extraction ─────────────────────────

async function buildHttpError(res, url = "") {
  let body = null;
  let message = "";

  try {
    const contentType = res.headers.get("content-type") || "";
    const ct = contentType.toLowerCase();
    if (ct.includes("application/json") || ct.includes("application/problem+json") || ct.includes("+json") || ct.includes("json")) {
      body = await res.json().catch(() => null);
      const detail = body?.detail ?? body?.error ?? body?.message;
      if (typeof detail === "string" && detail.trim()) {
        message = detail.trim();
      } else if (detail && typeof detail === "object") {
        message = JSON.stringify(detail);
      }
    } else {
      const text = await res.text().catch(() => "");
      if (text.trim()) {
        body = text.trim();
        message = text.trim().slice(0, 300);
      }
    }
  } catch (_e) {
    // Ignore extraction errors
  }

  return new ApiError({
    message,
    status: res.status,
    statusText: res.statusText || "",
    url: url || res.url || "",
    responseBody: body,
    timestamp: new Date().toISOString(),
  });
}

export async function request(pathOrUrl, options = {}) {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options;

  // 1. Fast offline check
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    throw new ApiError({
      message: "อุปกรณ์ของคุณไม่ได้เชื่อมต่ออินเทอร์เน็ต (Offline)",
      status: 0,
      statusText: "Offline",
      url: String(pathOrUrl || ""),
      isOffline: true,
      timestamp: new Date().toISOString(),
    });
  }

  // 2. Base URL resolution using resolveApiBase()
  const base = resolveApiBase();
  const url = (typeof pathOrUrl === "string" && (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")))
    ? pathOrUrl
    : `${base}${pathOrUrl.startsWith("/") ? "" : "/"}${pathOrUrl}`;

  // 3. Timeout via AbortController
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  let signal = controller.signal;
  if (fetchOptions.signal) {
    if (fetchOptions.signal.aborted) {
      controller.abort();
    } else {
      fetchOptions.signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
  }

  try {
    const res = await fetch(url, {
      ...fetchOptions,
      signal,
    });
    clearTimeout(timeoutId);

    if (!res.ok) {
      throw await buildHttpError(res, url);
    }
    return res;
  } catch (err) {
    clearTimeout(timeoutId);

    if (err instanceof ApiError) {
      throw err;
    }

    const isTimeout = err.name === "AbortError";
    const isOffline = typeof navigator !== "undefined" && navigator.onLine === false;

    let message = err.message || "การเชื่อมต่อเครือข่ายล้มเหลว";
    if (isTimeout) {
      message = `คำขอหมดเวลาหลังจาก ${timeoutMs / 1000} วินาที: ${url}`;
    } else if (isOffline) {
      message = "อุปกรณ์ของคุณไม่ได้เชื่อมต่ออินเทอร์เน็ต (Offline)";
    }

    throw new ApiError({
      message,
      status: 0,
      statusText: isTimeout ? "Timeout" : (isOffline ? "Offline" : "NetworkError"),
      url,
      responseBody: null,
      timestamp: new Date().toISOString(),
      isOffline,
      isTimeout,
    });
  }
}

// ── Data Normalization Layer ───────────────────────────────────────

export function normalizeArticle(raw) {
  if (!raw || typeof raw !== "object") return null;

  const rawImage = raw.image_url || raw.image || "";
  const resolvedImage = resolveImageUrl(rawImage, resolveApiBase());

  return {
    ...raw,
    url: typeof raw.url === "string" ? raw.url.trim() : "",
    title: typeof raw.title === "string" ? raw.title.trim() : "",
    source: typeof raw.source === "string" && raw.source.trim() ? raw.source.trim() : "สำนักข่าว",
    summary: typeof raw.summary === "string" ? raw.summary.trim() : "",
    category: typeof raw.category === "string" && raw.category.trim() ? raw.category.trim() : "all",
    fetched_at: raw.fetched_at || raw.published_at || "",
    image_url: resolvedImage,
  };
}

export function normalizeStory(story) {
  if (!story || typeof story !== "object") return null;

  const articles = Array.isArray(story.articles)
    ? story.articles.map(normalizeArticle).filter(Boolean)
    : [];

  const rawImage = story.image_url || story.image || (articles[0] ? articles[0].image_url : "");
  const resolvedImage = resolveImageUrl(rawImage, resolveApiBase());

  let childEvents = story.child_events;
  if (Array.isArray(childEvents)) {
    childEvents = childEvents.map(normalizeStory).filter(Boolean);
  }

  let childStories = story.child_stories;
  if (Array.isArray(childStories)) {
    childStories = childStories.map(normalizeStory).filter(Boolean);
  }

  return {
    ...story,
    image_url: resolvedImage,
    articles,
    ...(childEvents ? { child_events: childEvents } : {}),
    ...(childStories ? { child_stories: childStories } : {}),
  };
}

// ── REST API Methods ───────────────────────────────────────────────

export async function fetchNews(page = 1, source = "", q = "", category = "") {
  const params = new URLSearchParams({ page: String(page) });
  if (source) params.set("source", source);
  if (q) params.set("q", q);
  if (category && category !== "all") params.set("category", category);

  const res = await request(`/api/news?${params}`);
  const data = await res.json();
  if (Array.isArray(data.news)) {
    data.news = data.news.map(normalizeArticle).filter(Boolean);
  }
  return data;
}

export async function fetchArticleContent(url) {
  if (!url || typeof url !== "string" || !url.trim()) {
    throw new ApiError({
      message: "Article URL is required to fetch article content",
      status: 400,
      statusText: "Bad Request",
    });
  }
  const params = new URLSearchParams({ url: url.trim() });
  const res = await request(`/api/news/content?${params}`);
  return await res.json();
}

export async function fetchCategories() {
  try {
    const res = await request("/api/categories");
    const data = await res.json();
    return data.categories || {};
  } catch (e) {
    console.warn("fetchCategories failed:", e.message);
    return {};
  }
}

export async function fetchSources() {
  try {
    const res = await request("/api/sources");
    const data = await res.json();
    return data.sources || {};
  } catch (e) {
    console.warn("fetchSources failed:", e.message);
    return {};
  }
}

export async function fetchTrendingNews(limit = 3, category = "") {
  const params = new URLSearchParams({ limit: String(limit) });
  if (category && category !== "all") params.set("category", category);

  try {
    const res = await request(`/api/news/trending?${params}`);
    const data = await res.json();
    if (Array.isArray(data.trending)) {
      data.trending = data.trending.map(normalizeArticle).filter(Boolean);
    }
    if (Array.isArray(data.articles)) {
      data.articles = data.articles.map(normalizeArticle).filter(Boolean);
    }
    if (Array.isArray(data.clusters)) {
      data.clusters = data.clusters.map(normalizeStory).filter(Boolean);
    }
    return data;
  } catch (e) {
    console.warn("fetchTrendingNews failed:", e.message);
    return { trending: [], articles: [], total: 0 };
  }
}

export async function fetchTrendingStories(limit = 30, category = "") {
  const params = new URLSearchParams({ limit: String(limit) });
  if (category && category !== "all") params.set("category", category);

  // 1. Prioritize Macro Trending
  try {
    const res = await request(`/api/macro-events/trending?${params}`);
    const data = await res.json();
    if (Array.isArray(data) && data.length > 0) {
      return data.map(normalizeStory).filter(Boolean);
    }
  } catch (_e) {}

  // 2. Fallback to /api/stories/trending
  try {
    const res = await request(`/api/stories/trending?${params}`);
    const data = await res.json();
    const list = Array.isArray(data) ? data : (data.stories || []);
    if (list.length > 0) {
      return list.map(normalizeStory).filter(Boolean);
    }
  } catch (_e) {}

  // 3. Fallback to /api/news/trending
  const fallback = await fetchTrendingNews(limit, category);
  if (fallback) {
    if (Array.isArray(fallback.clusters) && fallback.clusters.length > 0) {
      return fallback.clusters.map(c => {
        const primaryArt = (c.articles && c.articles[0]) || {};
        const outlets = Array.from(new Set(
          (c.articles || []).map(a => a.source).filter(Boolean)
        ));
        const primarySource = primaryArt.source || (outlets.length > 0 ? outlets[0] : "สำนักข่าว");
        return normalizeStory({
          story_id: c.cluster_id,
          macro_event_id: c.cluster_id,
          title: c.topic_title || primaryArt.title || "ประเด็นข่าวร้อน",
          headline: c.topic_title || primaryArt.title || "ประเด็นข่าวร้อน",
          summary: c.cluster_summary || primaryArt.summary || "",
          category: primaryArt.category || "all",
          source: primarySource,
          trending_score: typeof c.trend_score === "number" ? c.trend_score : (primaryArt.trending_score || 9.0),
          outlets: outlets.length > 0 ? outlets : [primarySource],
          cluster_sources: outlets.length > 0 ? outlets : [primarySource],
          articles: c.articles || [],
          article_count: (c.articles && c.articles.length) || c.article_count || 1,
          hashtags: c.hashtags || primaryArt.hashtags || [],
          image_url: primaryArt.image_url || "",
          url: primaryArt.url || "",
          fetched_at: primaryArt.fetched_at || "",
        });
      });
    }

    const rawList = fallback.trending || fallback.articles || [];
    const seenTopics = new Set();
    const deduped = [];
    for (const art of rawList) {
      const topicKey = (art.cluster_id || art.topic_title || art.title || "").trim().toLowerCase();
      if (topicKey && seenTopics.has(topicKey)) continue;
      if (topicKey) seenTopics.add(topicKey);
      deduped.push(normalizeArticle(art));
    }
    return deduped;
  }

  return [];
}

export async function fetchStoryDetail(storyId) {
  if (!storyId) return null;
  try {
    const res = await request(`/api/stories/${encodeURIComponent(storyId)}`);
    const data = await res.json();
    return normalizeStory(data);
  } catch (e) {
    console.warn("fetchStoryDetail failed:", e.message);
    return null;
  }
}

export async function fetchMacroEventDetail(macroId) {
  if (!macroId) return null;
  try {
    const res = await request(`/api/macro-events/${encodeURIComponent(macroId)}`);
    const data = await res.json();
    return normalizeStory(data);
  } catch (e) {
    console.warn("fetchMacroEventDetail failed:", e.message);
    return null;
  }
}

export async function fetchStorylineSynthesis(storyId, isMacro = true) {
  if (!storyId) return null;
  const primary = isMacro
    ? `/api/macro-events/${encodeURIComponent(storyId)}/synthesis`
    : `/api/stories/${encodeURIComponent(storyId)}/synthesis`;
  const secondary = isMacro
    ? `/api/stories/${encodeURIComponent(storyId)}/synthesis`
    : `/api/macro-events/${encodeURIComponent(storyId)}/synthesis`;

  try {
    const res = await request(primary);
    return await res.json();
  } catch (_) {}

  try {
    const res2 = await request(secondary);
    return await res2.json();
  } catch (_) {}

  return null;
}

export async function triggerStorylineSynthesis(storyId, isMacro = true, forceRefresh = true, payload = null) {
  if (!storyId) return null;
  const primary = isMacro
    ? `/api/macro-events/${encodeURIComponent(storyId)}/synthesis`
    : `/api/stories/${encodeURIComponent(storyId)}/synthesis`;
  const secondary = isMacro
    ? `/api/stories/${encodeURIComponent(storyId)}/synthesis`
    : `/api/macro-events/${encodeURIComponent(storyId)}/synthesis`;

  const bodyData = payload ? JSON.stringify(payload) : "{}";
  const headers = { "Content-Type": "application/json" };
  const query = `?force_refresh=${forceRefresh ? "true" : "false"}`;

  try {
    const res = await request(`${primary}${query}`, { method: "POST", headers, body: bodyData });
    return await res.json();
  } catch (e) {
    console.warn("Primary synthesis endpoint failed, trying fallback:", e.message);
  }

  try {
    const res2 = await request(`${secondary}${query}`, { method: "POST", headers, body: bodyData });
    return await res2.json();
  } catch (e) {
    console.warn("Fallback synthesis endpoint failed:", e.message);
  }

  return null;
}

export async function recordEngagement(url, eventType = "click") {
  if (!url) return;
  try {
    await request("/api/news/engagement", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, event_type: eventType }),
      timeoutMs: 5000,
    });
  } catch (_err) {
    // Non-blocking telemetry
  }
}

export async function summarizeArticle(url) {
  const res = await request("/api/collect-md", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
    timeoutMs: 30000,
  });
  return await res.json();
}

export async function fetchApiHealth() {
  const res = await request("/livez");
  return await res.json();
}

// ── Deprecated Adapters & Migration Re-exports ──────────────────────

/**
 * @deprecated Dead code audit: 0 callers in frontend. Use fetchTrendingStories or fetchStoryDetail.
 */
export async function fetchStories(status = "", category = "", limit = 20, offset = 0) {
  console.warn("fetchStories is deprecated and scheduled for elimination.");
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (status && status !== "all") params.set("status", status);
  if (category && category !== "all") params.set("category", category);

  try {
    const res = await request(`/api/stories?${params}`);
    return await res.json();
  } catch (e) {
    console.warn("fetchStories request failed:", e.message);
    return { total: 0, page: 1, page_size: limit, total_pages: 1, has_next: false, has_prev: false, updated: "", stories: [] };
  }
}

/**
 * @deprecated Internal helper only; callers should use fetchTrendingStories.
 */
export async function fetchTrendingMacroEvents(limit = 7, category = "") {
  const params = new URLSearchParams({ limit: String(limit) });
  if (category && category !== "all") params.set("category", category);

  try {
    const res = await request(`/api/macro-events/trending?${params}`);
    const data = await res.json();
    return Array.isArray(data) ? data.map(normalizeStory).filter(Boolean) : [];
  } catch (e) {
    console.warn("fetchTrendingMacroEvents failed:", e.message);
    return [];
  }
}

// Re-export socket lifecycle helpers for unmigrated callers during M2 transition:
export { createSocket, getSocket };
