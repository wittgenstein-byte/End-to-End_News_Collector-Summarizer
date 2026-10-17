/**
 * config.js — Dynamic Client Configuration & Image Resolution
 *
 * Implements 4-tier configuration resolution hierarchy:
 *   Tier 1: Runtime Injection via window.__NEWSROOM_CONFIG__
 *   Tier 2: Build-Time / Bundler Environment (import.meta.env?.VITE_API_URL or window.__ENV__?.VITE_API_URL)
 *   Tier 3: URL Query Parameter (?api=...) or LocalStorage ("newsroom_api_base")
 *   Tier 4: Smart Dynamic Detection & Dev Port Auto-Mapping (5173, 3000, 5500, 8080 -> 5000)
 */

/**
 * Resolves the Backend REST API Base URL following the 4-tier hierarchy.
 *
 * @param {object} [options]
 * @param {Window} [options.win] - Injectable window for testing
 * @returns {string} Clean API Base URL without trailing slash
 */
export function resolveApiBase(options = {}) {
  const win = options.win || (typeof window !== "undefined" ? window : null);
  if (!win) return "http://localhost:5000";

  // Tier 1: Runtime Injection
  if (win.__NEWSROOM_CONFIG__ && typeof win.__NEWSROOM_CONFIG__.API_BASE === "string") {
    const raw = win.__NEWSROOM_CONFIG__.API_BASE.trim();
    if (raw) return raw.replace(/\/+$/, "");
  }

  // Tier 2: Build-Time / Global Environment Variables
  try {
    if (typeof import.meta !== "undefined" && import.meta?.env?.VITE_API_URL) {
      const raw = String(import.meta.env.VITE_API_URL).trim();
      if (raw) return raw.replace(/\/+$/, "");
    }
  } catch (_e) {}

  try {
    if (win.__ENV__ && typeof win.__ENV__.VITE_API_URL === "string") {
      const raw = win.__ENV__.VITE_API_URL.trim();
      if (raw) return raw.replace(/\/+$/, "");
    }
  } catch (_e) {}

  // Tier 3: Query Parameter or LocalStorage Override
  try {
    if (win.location?.search) {
      const params = new URLSearchParams(win.location.search);
      const queryApi = params.get("api");
      if (queryApi && queryApi.trim()) {
        const cleaned = queryApi.trim().replace(/\/+$/, "");
        try { win.localStorage?.setItem("newsroom_api_base", cleaned); } catch (_e) {}
        return cleaned;
      }
    }
    const storedApi = win.localStorage?.getItem("newsroom_api_base");
    if (storedApi && storedApi.trim()) {
      return storedApi.trim().replace(/\/+$/, "");
    }
  } catch (_e) {}

  // Tier 4: Dynamic Detection & Dev Port Auto-Mapping
  const hostname = win.location?.hostname || "localhost";
  const port = win.location?.port || "";
  const protocol = win.location?.protocol || "http:";
  const isLoopback = hostname === "localhost" || hostname === "127.0.0.1" || hostname === "0.0.0.0" || hostname === "[::1]";

  if (isLoopback) {
    if (port === "5000") {
      return win.location.origin;
    }
    const devPorts = ["5173", "3000", "8080", "5500", "4173", "8000", "5001"];
    if (devPorts.includes(port) || port !== "") {
      return `${protocol}//${hostname}:5000`;
    }
    return "http://localhost:5000";
  }

  return win.location?.origin || "http://localhost:5000";
}

/**
 * Resolves the Socket.IO Server URL following the 4-tier hierarchy.
 *
 * @param {string} [apiBase] - Optional pre-resolved API Base URL
 * @param {object} [options]
 * @param {Window} [options.win] - Injectable window for testing
 * @returns {string} Clean Socket.IO URL without trailing slash
 */
export function resolveSocketUrl(apiBase, options = {}) {
  const win = options.win || (typeof window !== "undefined" ? window : null);
  const base = apiBase || resolveApiBase(options);

  if (win?.__NEWSROOM_CONFIG__ && typeof win.__NEWSROOM_CONFIG__.SOCKET_URL === "string") {
    const raw = win.__NEWSROOM_CONFIG__.SOCKET_URL.trim();
    if (raw) return raw.replace(/\/+$/, "");
  }

  try {
    if (typeof import.meta !== "undefined" && import.meta?.env?.VITE_SOCKET_URL) {
      const raw = String(import.meta.env.VITE_SOCKET_URL).trim();
      if (raw) return raw.replace(/\/+$/, "");
    }
  } catch (_e) {}

  try {
    if (win?.__ENV__ && typeof win.__ENV__.VITE_SOCKET_URL === "string") {
      const raw = win.__ENV__.VITE_SOCKET_URL.trim();
      if (raw) return raw.replace(/\/+$/, "");
    }
  } catch (_e) {}

  try {
    const storedSocket = win?.localStorage?.getItem("newsroom_socket_url");
    if (storedSocket && storedSocket.trim()) {
      return storedSocket.trim().replace(/\/+$/, "");
    }
  } catch (_e) {}

  return base;
}

/**
 * Resolves an image URL against API_BASE if it is a relative image proxy path.
 *
 * @param {string} url - Raw image URL (can be relative proxy path or external URL)
 * @param {string} [base=API_BASE] - Base URL to prepend
 * @returns {string} Fully resolved image URL
 */
export function resolveImageUrl(url, base = API_BASE) {
  if (!url || typeof url !== "string") return "";
  const trimmed = url.trim();
  if (!trimmed) return "";
  if (trimmed.startsWith("/api/image")) {
    return `${base}${trimmed}`;
  }
  if (trimmed.startsWith("api/image")) {
    return `${base}/${trimmed}`;
  }
  return trimmed;
}

export const API_BASE = resolveApiBase();
export const SOCKET_URL = resolveSocketUrl(API_BASE);
export const PAGE_SIZE  = 20;
export const TRENDING_LIMIT = 50;
export const HERO_CLUSTER_LIMIT = 12;

export const FEEDBACK_FORM_URL = "https://forms.gle/GKWw4otqQrsuqd4L7";
export const FEEDBACK_COMPLETED_KEY = "newsroom_feedback_completed";

/**
 * Sentiment visual token configurations
 */
export const SENTIMENT_CONFIG = {
  positive: {
    label: "เชิงบวก",
    icon: "sentiment_satisfied",
    emoji: "😊",
    color: "#059669",
    badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200"
  },
  neutral: {
    label: "เป็นกลาง",
    icon: "horizontal_rule",
    emoji: "😐",
    color: "#475569",
    badgeClass: "bg-slate-100 text-slate-700 border-slate-200"
  },
  negative: {
    label: "เชิงลบ",
    icon: "sentiment_dissatisfied",
    emoji: "⚠️",
    color: "#e11d48",
    badgeClass: "bg-rose-50 text-rose-700 border-rose-200"
  }
};

/** หา sentiment config จาก sentiment string */
export function getSentimentConfig(sentiment) {
  if (!sentiment) return null;
  const s = String(sentiment).toLowerCase();
  if (s.includes("positive") || s.includes("บวก")) return SENTIMENT_CONFIG.positive;
  if (s.includes("negative") || s.includes("ลบ")) return SENTIMENT_CONFIG.negative;
  if (s.includes("neutral") || s.includes("กลาง")) return SENTIMENT_CONFIG.neutral;
  return null;
}

/** Source colors — sync กับ scrapers/registry.py */
export const SOURCE_COLORS = {
  "ThaiPBS":        "#e74c3c",
  "Bangkok Post":   "#3498db",
  "Matichon":       "#2ecc71",
  "101 World":      "#9b59b6",
  "The Standard":   "#e67e22",
  "Khaosod":        "#e74c3c",
  "Thairath":       "#00b16a",
  "Komchadluek":    "#c0392b",
  "Daily News":     "#e74c3c",
  "Nation Online":  "#16a085",
  "Bangkokbiznews": "#1f3a93",
  "Thai Post":      "#d35400",
  "PPTV HD 36":     "#0088cc",
  "Techhub":        "#1abc9c",
};

/**
 * Category definitions — sync กับ backend/services/classifier_service.py
 * id ต้องตรงกับ category string ที่ backend คืนมา
 */
export const CATEGORIES = [
  { id: "all",         label: "ทั้งหมด",       icon: "📰", color: "#1a3a6b", bg: "#e8eef7" },
  { id: "politics",    label: "การเมือง",      icon: "🏛️", color: "#c0392b", bg: "#fdecea" },
  { id: "economy",     label: "เศรษฐกิจ",     icon: "📈", color: "#27ae60", bg: "#eafaf1" },
  { id: "technology",  label: "เทคโนโลยี",    icon: "💻", color: "#8e44ad", bg: "#f5eafb" },
  { id: "health",      label: "สุขภาพ",        icon: "💊", color: "#16a085", bg: "#e8f8f5" },
  { id: "environment", label: "สิ่งแวดล้อม",  icon: "🌿", color: "#2e7d32", bg: "#e8f5e9" },
  { id: "society",     label: "สังคม",         icon: "👥", color: "#d35400", bg: "#fdf2e9" },
  { id: "sports",      label: "กีฬา",          icon: "⚽", color: "#c0392b", bg: "#fdedec" },
  { id: "entertainment",label:"บันเทิง",       icon: "🎬", color: "#b7950b", bg: "#fefde7" },
  { id: "world",       label: "ต่างประเทศ",   icon: "🌍", color: "#1565c0", bg: "#e3f2fd" },
];
 
/** หา category object จาก id */
export function getCategoryById(id) {
  return CATEGORIES.find(c => c.id === id) ?? CATEGORIES[0];
}