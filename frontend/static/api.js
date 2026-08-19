/**
 * api.js — HTTP + WebSocket layer
 *
 * หน้าที่: ติดต่อ backend เท่านั้น
 * ไม่แตะ DOM, ไม่รู้จัก UI element ใด ๆ
 */

import { API_BASE, SOCKET_URL } from "./config.js";

const CONSENT_KEY = "newsroom_cookie_consent";
const USER_ID_KEY = "newsroom_anon_id";

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

function setCookie(name, value, days = 365) {
 const expires = new Date(Date.now() + days * 86400 * 1000).toUTCString();
 document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
}

function getCookie(name) {
 const cookie = document.cookie
   .split("; ")
   .find((row) => row.startsWith(`${name}=`));
 return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
}

export function hasCookieConsent() {
 try {
   return localStorage.getItem(CONSENT_KEY) === "accepted" || getCookie(CONSENT_KEY) === "accepted";
 } catch {
   return getCookie(CONSENT_KEY) === "accepted";
 }
}

export function setCookieConsent(accepted) {
 const value = accepted ? "accepted" : "declined";
 try {
   localStorage.setItem(CONSENT_KEY, value);
 } catch {
   // Ignore storage failures so the app still works without persistence.
 }
 setCookie(CONSENT_KEY, value, 365);

 if (!accepted) {
   try {
     localStorage.removeItem(USER_ID_KEY);
   } catch {
     // Ignore storage failures.
   }
   document.cookie = `${USER_ID_KEY}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; SameSite=Lax`;
 }
}

export function getAnonymousUserId() {
 if (!hasCookieConsent()) {
   return null;
 }

 try {
   let userId = localStorage.getItem(USER_ID_KEY) || getCookie(USER_ID_KEY);
   if (!userId) {
     userId = (crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`);
     localStorage.setItem(USER_ID_KEY, userId);
     setCookie(USER_ID_KEY, userId, 365);
   }
   return userId;
 } catch {
   return getCookie(USER_ID_KEY) || null;
 }
}

export async function trackEvent(eventName, payload = {}) {
 if (!hasCookieConsent()) {
   return false;
 }

 const userId = getAnonymousUserId();
 if (!userId) {
   return false;
 }

 try {
   const res = await fetch(`${API_BASE}/api/events`, {
     method: "POST",
     headers: { "Content-Type": "application/json" },
     body: JSON.stringify({
       user_id: userId,
       event_name: eventName,
       ...payload,
     }),
   });
   if (!res.ok) {
     const detail = await res.text().catch(() => "");
     console.warn("Event tracking failed:", detail || `HTTP ${res.status}`);
     return false;
   }
   return true;
 } catch (error) {
   console.warn("Event tracking exception:", error);
   return false;
 }
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
export async function fetchCategories() {
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
 if (!res.ok) throw await buildHttpError(res);
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
