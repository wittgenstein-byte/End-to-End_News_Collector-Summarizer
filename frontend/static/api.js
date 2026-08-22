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
