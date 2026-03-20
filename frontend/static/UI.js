/**
 * ui.js — DOM manipulation & rendering
 *
 * หน้าที่: วาด UI ล้วน ๆ
 * รับ data สำเร็จรูปจาก main.js — ไม่ fetch เอง
 */

import { SOURCE_COLORS, CATEGORIES, getCategoryById } from "./config.js";

// ── Escape ────────────────────────────────────────────────────────

export function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── WS badge ──────────────────────────────────────────────────────

export function setWsBadge(connected) {
  const dot   = document.getElementById("ws-dot");
  const label = document.getElementById("ws-label");
  dot.className = "dot " + (connected ? "connected" : "error");
  label.textContent = connected ? "Live" : "ออฟไลน์";
}

// ── Stats bar ─────────────────────────────────────────────────────

export function updateStats({ total, newCount, updated }) {
  if (total   !== undefined) document.getElementById("stat-total").textContent = total;
  if (newCount !== undefined) document.getElementById("stat-new").textContent  = newCount;
  if (updated !== undefined) document.getElementById("updated-bar").textContent =
    `อัปเดตล่าสุด : ${updated}`;
}
// ── Category nav ──────────────────────────────────────────────────
 
/**
 * วาด category strip
 * @param {string}         activeId   — id ที่กำลัง active
 * @param {object}         counts     — {politics: 12, economy: 8, ...}
 */
export function renderCategoryNav(activeId, counts = {}) {
  const nav = document.getElementById("category-nav");
  nav.innerHTML = CATEGORIES.map(cat => {
    const count   = cat.id === "all" ? (counts.all ?? "") : (counts[cat.id] ?? 0);
    const isActive = cat.id === activeId;
    return `
      <button class="cat-pill ${isActive ? "active" : ""}"
              data-id="${cat.id}"
              style="${isActive
                ? `--cat-color:${cat.color};--cat-bg:${cat.bg}`
                : `--cat-color:${cat.color};--cat-bg:${cat.bg}`}"
              onclick="__categoryClick('${cat.id}')">
        <span class="cat-icon">${cat.icon}</span>
        <span class="cat-label">${cat.label}</span>
        ${count !== "" ? `<span class="cat-count">${count}</span>` : ""}
      </button>`;
  }).join("");
}
 
/** อัปเดต count badges โดยไม่ redraw ทั้งหมด */
export function updateCategoryBadges(counts = {}) {
  document.querySelectorAll(".cat-pill").forEach(btn => {
    const id    = btn.dataset.id;
    const badge = btn.querySelector(".cat-count");
    if (!badge) return;
    const count = id === "all" ? (counts.all ?? "") : (counts[id] ?? 0);
    badge.textContent = count;
  });
}
// ── Ticker ────────────────────────────────────────────────────────

export function updateTicker(titles) {
  if (!titles.length) return;
  const doubled = [...titles, ...titles];
  document.getElementById("ticker-track").innerHTML =
    doubled.map(t => `<span>${esc(t)}</span>`).join("");
}

// ── Toast ─────────────────────────────────────────────────────────

export function showToast(msg) {
  document.getElementById("toast").textContent = msg;
  document.getElementById("toast").classList.add("show");
}

export function hideToast() {
  document.getElementById("toast").classList.remove("show");
}

// ── News grid ─────────────────────────────────────────────────────

/**
 * @param {object[]} articles
 * @param {Set<string>} newUrlSet  — URLs ของข่าวใหม่ใน session นี้
 */
export function renderGrid(articles, newUrlSet = new Set()) {
  const grid = document.getElementById("news-grid");

  if (!articles.length) {
    grid.innerHTML = `<div class="loading">ไม่พบข่าว</div>`;
    return;
  }

  grid.innerHTML = articles.map((n, i) => {
    const isNew = newUrlSet.has(n.url);
    const color = SOURCE_COLORS[n.source] ?? "#1a3a6b";

    return `
      <a class="card ${isNew ? "is-new" : ""}"
         href="${esc(n.url) || "#"}" target="_blank" rel="noopener"
         style="animation-delay:${i * 25}ms">

        ${n.image_url ? `
          <div class="card-img-wrap">
            <img class="card-img" src="${esc(n.image_url)}" alt=""
                 loading="lazy" onerror="this.parentElement.style.display='none'">
          </div>` : ""}

        <div class="card-body">
          <div class="card-source">
            <span class="src-dot" style="background:${color}"></span>
            <span class="source-name">${esc(n.source)}</span>
            ${isNew ? `<span class="badge-new">NEW</span>` : ""}
          </div>
          <div class="card-title">${esc(n.title)}</div>
          <div class="card-summary">${esc(n.summary ?? "")}</div>
          <div class="card-footer">
            <span class="card-time">${esc(n.fetched_at ?? "")}</span>
            <button class="summary-btn"
                    data-url="${esc(n.url)}"
                    onclick="window.__summarize(event, this.dataset.url)">
              ⭐ สรุป
            </button>
            <span class="card-arrow">→</span>
          </div>
        </div>
      </a>`;
  }).join("");
}

export function showGridLoading() {
  document.getElementById("news-grid").innerHTML =
    `<div class="loading"><div class="spinner"></div>กำลังโหลด...</div>`;
}

export function showGridError(msg = "เชื่อมต่อ API ไม่ได้") {
  document.getElementById("news-grid").innerHTML =
    `<div class="loading">❌ ${esc(msg)}</div>`;
}

// ── Pagination ────────────────────────────────────────────────────

/**
 * @param {object} meta  — {page, total_pages, total}
 */
export function renderPagination(meta) {
  const pg = document.getElementById("pagination");
  const { page, total_pages: totalPages, total } = meta;

  if (totalPages <= 1) { pg.innerHTML = ""; return; }

  const btn = (p, label, disabled = false, active = false) =>
    `<button class="page-btn${active ? " active" : ""}"
             onclick="__loadPage(${p})"
             ${disabled ? "disabled" : ""}>${label}</button>`;

  let html = btn(page - 1, "‹", page <= 1);

  const start = Math.max(1, page - 2);
  const end   = Math.min(totalPages, start + 4);

  if (start > 1)       html += btn(1, "1") + `<span class="page-info">…</span>`;
  for (let p = start; p <= end; p++) html += btn(p, p, false, p === page);
  if (end < totalPages) html += `<span class="page-info">…</span>` + btn(totalPages, totalPages);

  html += btn(page + 1, "›", page >= totalPages);
  html += `<span class="page-info">${total} บทความ</span>`;

  pg.innerHTML = html;
}

// ── Summary Modal ─────────────────────────────────────────────────

export function openModal() {
  document.getElementById("summary-modal").classList.add("active");
}

export function closeModal() {
  document.getElementById("summary-modal").classList.remove("active");
}

export function showModalLoading() {
  document.getElementById("summary-loading").style.display = "block";
  document.getElementById("summary-result").style.display  = "none";
  document.getElementById("summary-result").innerHTML      = "";
}

export function showModalResult(summary) {
  const s = summary;
  document.getElementById("summary-loading").style.display = "none";
  const result = document.getElementById("summary-result");
  result.style.display = "block";

  const bullets  = (s.bullets  ?? []).map(b => `<li>${esc(b)}</li>`).join("");
  const keywords = (s.keywords ?? []).map(k => `<span class="summary-tag">#${esc(k)}</span>`).join("");

  result.innerHTML = `
    <div class="summary-meta">
      ${s.category  ? `<span class="summary-tag">${esc(s.category)}</span>`  : ""}
      ${s.sentiment ? `<span class="summary-tag">${esc(s.sentiment)}</span>` : ""}
      <span>${esc(s.published_at ?? "")}</span>
    </div>
    <h2 class="summary-title">${esc(s.title ?? "ไม่มีหัวข้อ")}</h2>
    <div class="summary-body">
      <p><strong>สรุป:</strong> ${esc(s.summary ?? "")}</p>
      ${bullets  ? `<ul class="summary-bullets">${bullets}</ul>`           : ""}
      ${keywords ? `<div style="margin-top:1.5rem;display:flex;gap:.5rem;flex-wrap:wrap">${keywords}</div>` : ""}
    </div>`;
}

export function showModalError(msg) {
  document.getElementById("summary-loading").style.display = "none";
  const result = document.getElementById("summary-result");
  result.style.display = "block";
  result.innerHTML = `
    <div style="color:#e74c3c;text-align:center;padding:2rem">
      ❌ ${esc(msg)}
    </div>`;
}