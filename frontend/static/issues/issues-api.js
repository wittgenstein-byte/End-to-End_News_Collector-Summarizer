/**
 * frontend/static/issues/issues-api.js
 * ─────────────────────────────────────────────────────────────────
 * API layer for Issue Explorer with AbortController signal support.
 * ─────────────────────────────────────────────────────────────────
 */

import { API_BASE } from "./issues-config.js";

/**
 * Perform issue drill-down search with query parameters and abort signal.
 * @param {Object} params - Query parameters (q, expand, date_from, date_to, source, category, limit)
 * @param {AbortSignal} [signal] - Optional AbortSignal to cancel in-flight requests
 * @returns {Promise<Object>} API search response
 */
export async function searchIssues(params, signal = null) {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      qs.append(key, String(value));
    }
  }

  const url = `${API_BASE}/api/issues/search?${qs.toString()}`;
  const options = {
    method: "GET",
    headers: {
      "Accept": "application/json"
    }
  };
  if (signal) {
    options.signal = signal;
  }

  const res = await fetch(url, options);
  if (!res.ok) {
    if (res.status === 429) {
      throw new Error("ส่งคำค้นหาบ่อยเกินไป กรุณารอสักครู่ (Rate limit 30 req/min)");
    }
    if (res.status === 503) {
      throw new Error("ระบบฐานข้อมูลไม่พร้อมใช้งาน หรือไม่ได้รันด้วย SQLite");
    }
    if (res.status === 422) {
      throw new Error("กรุณาระบุคำค้นหาที่ถูกต้อง (ความยาว 1-100 ตัวอักษร)");
    }
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `เกิดข้อผิดพลาดในการค้นหา (${res.status})`);
  }

  return await res.json();
}
