/**
 * api.js — HTTP + WebSocket layer
 *
 * หน้าที่: ติดต่อ backend เท่านั้น
 * ไม่แตะ DOM, ไม่รู้จัก UI element ใด ๆ
 */

import { API_BASE, SOCKET_URL } from "./config.js";

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
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/** ดึง category counts สำหรับ badge บน tabs */
export async function fetchCategories() {                                  // ← ใหม่
  const res = await fetch(`${API_BASE}/api/categories`);
  if (!res.ok) return {};
  const data = await res.json();
  return data.categories ?? {};
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
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── WebSocket ────────────────────────────────────────────────────
export function createSocket(handlers) {
  /* global io */
  const socket = io(SOCKET_URL);

  socket.on("connect",      ()     => handlers.onConnect?.());
  socket.on("disconnect",   ()     => handlers.onDisconnect?.());
  socket.on("init",         data   => handlers.onInit?.(data));
  socket.on("new_articles", data   => handlers.onNewArticles?.(data));

  return socket;
}