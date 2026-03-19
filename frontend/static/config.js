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