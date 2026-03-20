/**
 * config.js — แก้ที่นี่ที่เดียวเมื่อ deploy ไป server จริง
 *
 * วิธีใช้: window.location.origin จะคืน origin ของ page เอง
 * ถ้า FastAPI serve index.html → origin ตรงกับ backend เสมอ
 * ถ้าแยก server → เปลี่ยน API_BASE ตรงนี้ที่เดียวพอ
 */

const IS_DEV = window.location.hostname === "localhost";

export const API_BASE   = IS_DEV
  ? "http://localhost:5000"
  : window.location.origin;          // production: same origin

export const SOCKET_URL = API_BASE;
export const PAGE_SIZE  = 20;

/** Source colors — sync กับ scrapers/registry.py */
export const SOURCE_COLORS = {
  "ThaiPBS":      "#e74c3c",
  "Bangkok Post": "#3498db",
  "Matichon":     "#2ecc71",
  "101 World":    "#9b59b6",
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