/**
 * api.js — HTTP + WebSocket layer
 *
 * หน้าที่: ติดต่อ backend เท่านั้น
 * ไม่แตะ DOM, ไม่รู้จัก UI element ใด ๆ
 */

import { API_BASE, SOCKET_URL } from "./config.js";

async function buildHttpError(res) {
  const contentType = res.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    const data = await res.json().catch(() => null);
    const detail = data?.detail ?? data?.error ?? data?.message;
    if (typeof detail === "string" && detail.trim()) {
      return new Error(detail);
    }
  } else {
    const text = await res.text().catch(() => "");
    if (text.trim()) {
      return new Error(text.trim());
    }
  }

  return new Error(`HTTP ${res.status}`);
}

// ── HTTP ──────────────────────────────────────────────────────────

/**
 * ดึงรายการข่าว
 * @param {number} page
 * @param {string} source  — กรองแหล่งข่าว (ว่าง = ทั้งหมด)
 * @param {string} q       — keyword search
 */
export async function fetchNews(page = 1, source = "", q = "", category = "") {
  const params = new URLSearchParams({ page });
  if (source)   params.set("source", source);
  if (q)        params.set("q", q);
  if (category && category !== "all") params.set("category", category);

  const res = await fetch(`${API_BASE}/api/news?${params}`);
  if (!res.ok) throw await buildHttpError(res);
  return res.json();
}

/** ดึง category counts สำหรับ badge บน tabs */
export async function fetchCategories() {                                  // ← ใหม่
  const res = await fetch(`${API_BASE}/api/categories`);
  if (!res.ok) return {};
  const data = await res.json();
  return data.categories ?? {};
}

/** ดึง source counts สำหรับ filter buttons */
export async function fetchSources() {
  const res = await fetch(`${API_BASE}/api/sources`);
  if (!res.ok) return {};
  const data = await res.json();
  return data.sources ?? {};
}

/**
 * ดึงรายการข่าวที่มีแนวโน้มร้อนแรง / ยอดนิยม (Trending News)
 * @param {number} limit
 * @param {string} category
 */
export async function fetchTrendingNews(limit = 3, category = "") {
  const params = new URLSearchParams({ limit });
  if (category && category !== "all") params.set("category", category);

  try {
    const res = await fetch(`${API_BASE}/api/news/trending?${params}`);
    if (!res.ok) return { trending: [], articles: [], total: 0 };
    return await res.json();
  } catch (e) {
    console.warn("fetchTrendingNews request failed:", e.message);
    return { trending: [], articles: [], total: 0 };
  }
}

/**
 * ดึงรายการ story clusters ทั้งหมด (Persistent Stories)
 * @param {string} status   — กรองสถานะ ('active', 'dormant', หรือ '')
 * @param {string} category — กรองหมวดหมู่
 * @param {number} limit    — จำนวนรายการต่อหน้า
 * @param {number} offset   — offset สำหรับ pagination
 */
export async function fetchStories(status = "", category = "", limit = 20, offset = 0) {
  const params = new URLSearchParams({ limit, offset });
  if (status && status !== "all") params.set("status", status);
  if (category && category !== "all") params.set("category", category);

  try {
    const res = await fetch(`${API_BASE}/api/stories?${params}`);
    if (!res.ok) throw await buildHttpError(res);
    return await res.json();
  } catch (e) {
    console.warn("fetchStories request failed:", e.message);
    return { total: 0, page: 1, page_size: limit, total_pages: 1, has_next: false, has_prev: false, updated: "", stories: [] };
  }
}

/**
 * ดึงรายละเอียดของ Story Cluster ตาม story_id
 * รวม member articles ตามลำดับเวลา, timeline, citations, และคะแนน breakdown
 * @param {string} storyId
 */
export async function fetchStoryDetail(storyId) {
  if (!storyId) return null;
  try {
    const res = await fetch(`${API_BASE}/api/stories/${encodeURIComponent(storyId)}`);
    if (!res.ok) throw await buildHttpError(res);
    return await res.json();
  } catch (e) {
    console.warn("fetchStoryDetail request failed:", e.message);
    return null;
  }
}

/**
 * ดึงรายการ Trending Macro-Events (มหากาพย์ประเด็นข่าวภาพรวม)
 * @param {number} limit
 * @param {string} category
 */
export async function fetchTrendingMacroEvents(limit = 7, category = "") {
  const params = new URLSearchParams({ limit });
  if (category && category !== "all") params.set("category", category);

  try {
    const res = await fetch(`${API_BASE}/api/macro-events/trending?${params}`);
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data) && data.length > 0) {
        return data;
      }
    }
  } catch (e) {
    console.warn("fetchTrendingMacroEvents failed:", e.message);
  }
  return [];
}

/**
 * ดึงรายละเอียดของ Macro-Event ตาม macro_id
 * รวม child events (sub-events), ความสัมพันธ์, ไทม์ไลน์
 * @param {string} macroId
 */
export async function fetchMacroEventDetail(macroId) {
  if (!macroId) return null;
  try {
    const res = await fetch(`${API_BASE}/api/macro-events/${encodeURIComponent(macroId)}`);
    if (!res.ok) throw await buildHttpError(res);
    return await res.json();
  } catch (e) {
    console.warn("fetchMacroEventDetail request failed:", e.message);
    return null;
  }
}


/**
 * ดึงรายการ Trending Stories จาก persistent layer (Macro-First ค่าเริ่มต้น)
 * @param {number} limit
 * @param {string} category
 */
export async function fetchTrendingStories(limit = 30, category = "") {
  // 1. Prioritize Macro Trending (มหากาพย์ประเด็นใหญ่เป็นค่าเริ่มต้น)
  const macroTrending = await fetchTrendingMacroEvents(limit, category);
  if (Array.isArray(macroTrending) && macroTrending.length > 0) {
    return macroTrending;
  }

  // 2. Fallback to /api/stories/trending
  const params = new URLSearchParams({ limit });
  if (category && category !== "all") params.set("category", category);

  try {
    const res = await fetch(`${API_BASE}/api/stories/trending?${params}`);
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data) && data.length > 0) {
        return data;
      }
    }
  } catch (e) {
    // Fall back to /api/news/trending
  }

  // 3. Fallback to /api/news/trending (Consolidate by Cluster/Topic, never duplicate individual articles)
  const fallback = await fetchTrendingNews(limit, category);
  if (fallback) {
    if (Array.isArray(fallback.clusters) && fallback.clusters.length > 0) {
      return fallback.clusters.map(c => {
        const primaryArt = (c.articles && c.articles[0]) || {};
        const outlets = Array.from(new Set(
          (c.articles || []).map(a => a.source).filter(Boolean)
        ));
        return {
          story_id: c.cluster_id,
          macro_event_id: c.cluster_id,
          title: c.topic_title || primaryArt.title || "ประเด็นข่าวร้อน",
          headline: c.topic_title || primaryArt.title || "ประเด็นข่าวร้อน",
          summary: c.cluster_summary || primaryArt.summary || "",
          category: primaryArt.category || "all",
          trending_score: typeof c.trend_score === "number" ? c.trend_score : (primaryArt.trending_score || 9.0),
          outlets: outlets.length > 0 ? outlets : (primaryArt.source ? [primaryArt.source] : []),
          cluster_sources: outlets,
          articles: c.articles || [],
          article_count: (c.articles && c.articles.length) || c.article_count || 1,
          hashtags: c.hashtags || primaryArt.hashtags || [],
          image_url: primaryArt.image_url || "",
          url: primaryArt.url || "",
          fetched_at: primaryArt.fetched_at || "",
        };
      });
    }

    const rawList = fallback.trending || fallback.articles || [];
    // Deduplicate raw articles by topic_title or cluster_id
    const seenTopics = new Set();
    const deduped = [];
    for (const art of rawList) {
      const topicKey = (art.cluster_id || art.topic_title || art.title || "").trim().toLowerCase();
      if (topicKey && seenTopics.has(topicKey)) continue;
      if (topicKey) seenTopics.add(topicKey);
      deduped.push(art);
    }
    return deduped;
  }

  return [];
}

/**
 * บันทึกสถิติ engagement ของผู้อ่าน (click, summary, bookmark)
 * @param {string} url
 * @param {"click"|"summary"|"bookmark"} eventType
 */
export async function recordEngagement(url, eventType = "click") {
  if (!url) return;
  try {
    await fetch(`${API_BASE}/api/news/engagement`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, event_type: eventType }),
    });
  } catch (err) {
    // Non-blocking telemetry
  }
}

/**
 * ส่ง URL ให้ backend ดึงเนื้อหา + สรุปด้วย AI
 * @param {string} url
 * @returns {Promise<{ok: boolean, summary?: object, error?: string}>}
 */
export async function summarizeArticle(url) {
  const res = await fetch(`${API_BASE}/api/collect-md`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ url }),
  });
  if (!res.ok) throw await buildHttpError(res);
  return res.json();
}

// ── WebSocket ────────────────────────────────────────────────────
let globalSocket = null;

export function createSocket(handlers) {
  /* global io */
  const socket = io(SOCKET_URL);
  globalSocket = socket;

  socket.on("connect",      ()     => handlers.onConnect?.());
  socket.on("disconnect",   ()     => handlers.onDisconnect?.());
  socket.on("init",         data   => handlers.onInit?.(data));
  socket.on("new_articles", data   => handlers.onNewArticles?.(data));

  return socket;
}

export function getSocket() {
  return globalSocket;
}
