/**
 * frontend/static/components/filters.js
 * ─────────────────────────────────────────────────────────────────
 * Editorial Navigation, Categories & Publisher Source Filters
 *
 * Responsibilities:
 * - Editorial category navigation bar with live unread badge pills
 * - Privacy-first "For You" personalized topic onboarding card
 * - Publisher / news outlet horizontal filter pills with brand dots
 * - Real-time active filter state synchronization
 * ─────────────────────────────────────────────────────────────────
 */

import { esc } from "../utils/common.js";
import { CATEGORIES, SOURCE_COLORS } from "../config.js";

// ── Category Navigation Bar ───────────────────────────────────────

export function renderCategoryNav(activeId, counts = {}, bookmarkedMap = {}) {
  const nav = document.getElementById("category-nav");
  if (!nav) return;

  const bookmarkCount = Object.keys(bookmarkedMap || {}).length;

  const activeClasses = "cat-pill editorial-cat-pill active";
  const inactiveClasses = "cat-pill editorial-cat-pill";

  const isForYouActive = activeId === "for-you";
  let html = `
    <button class="${isForYouActive ? activeClasses : inactiveClasses}"
            data-id="for-you"
            onclick="__categoryClick('for-you')">
      <span class="material-symbols-outlined text-[16px]">auto_awesome</span>
      <span>สำหรับคุณ</span>
    </button>`;

  html += CATEGORIES.map(cat => {
    const rawCount = cat.id === "all" ? (counts.all ?? "") : counts[cat.id];
    const hasCount = rawCount !== undefined && rawCount !== "";
    const isActive = cat.id === activeId;
    
    return `
      <button class="${isActive ? activeClasses : inactiveClasses}"
              data-id="${cat.id}"
              onclick="__categoryClick('${cat.id}')">
        <span class="material-symbols-outlined text-[16px]">${cat.icon}</span>
        <span>${cat.label}</span>
        <span class="cat-count editorial-cat-count ${hasCount ? '' : 'hidden'}">${hasCount ? rawCount : ''}</span>
      </button>`;
  }).join("");

  const isBookmarkActive = activeId === "bookmarks";
  html += `
    <button class="${isBookmarkActive ? activeClasses : inactiveClasses}"
            data-id="bookmarks"
            onclick="__categoryClick('bookmarks')">
      <span class="material-symbols-outlined text-[16px]">bookmarks</span>
      <span>ที่บันทึกไว้</span>
      <span class="cat-count editorial-cat-count ${bookmarkCount > 0 ? '' : 'hidden'}">${bookmarkCount > 0 ? bookmarkCount : ''}</span>
    </button>
  `;

  nav.innerHTML = html;
}

// ── For You Onboarding ────────────────────────────────────────────

/** Render the privacy-first topic picker used to start a For You feed. */
export function renderForYouOnboarding(categories = []) {
  const container = document.getElementById("for-you-onboarding");
  if (!container) return;

  container.innerHTML = `
    <div class="mb-8 rounded-xl border border-outline-variant/50 bg-white p-6 shadow-xs">
      <div class="flex items-start gap-3.5">
        <div class="w-10 h-10 rounded-lg bg-[#141413] text-white flex items-center justify-center shrink-0">
          <span class="material-symbols-outlined text-[20px]">auto_awesome</span>
        </div>
        <div>
          <h2 class="font-headline text-xl font-bold text-on-surface">ปรับแต่งฟีดข่าวเฉพาะคุณ (Personal Briefing)</h2>
          <p class="mt-0.5 text-xs text-on-surface-variant">เลือกอย่างน้อย 3 หมวดหมู่ที่คุณสนใจ ข้อมูลทั้งหมดจะถูกเก็บและประมวลผลบนอุปกรณ์นี้เท่านั้น</p>
        </div>
      </div>
      <div class="mt-4 flex flex-wrap gap-2">
        ${categories.map(cat => `
          <button type="button" data-topic-id="${esc(cat.id)}" onclick="__toggleForYouTopic('${esc(cat.id)}')"
            class="for-you-topic rounded-lg border border-outline-variant/50 bg-surface px-3.5 py-1.5 text-xs font-semibold text-on-surface transition-all hover:border-primary">
            ${esc(cat.icon)} ${esc(cat.label)}
          </button>`).join("")}
      </div>
      <div class="mt-5 pt-4 border-t border-outline-variant/25 flex flex-wrap items-center gap-4">
        <button type="button" onclick="__saveForYouTopics()" class="rounded-lg bg-[#141413] px-4 py-2 text-xs font-bold text-white hover:opacity-90 transition-opacity">บันทึกและสร้างฟีดของฉัน</button>
        <button type="button" onclick="__skipForYouOnboarding()" class="text-xs font-semibold text-on-surface-variant hover:text-on-surface">ข้ามไปดูข่าวเด่นทั้งหมด</button>
        <span id="for-you-topic-count" class="text-[11px] font-mono text-outline ml-auto">เลือกแล้ว 0/3 หมวด</span>
      </div>
    </div>`;
}

export function hideForYouOnboarding() {
  const container = document.getElementById("for-you-onboarding");
  if (container) container.innerHTML = "";
}

// ── Category Unread / Badges Update ───────────────────────────────

export function updateCategoryBadges(counts = {}, bookmarkCount = 0) {
  document.querySelectorAll(".cat-pill").forEach(btn => {
    const id = btn.dataset.id;
    let badge = btn.querySelector(".cat-count");
    if (id === "bookmarks") {
      if (bookmarkCount > 0) {
        if (badge) {
          badge.textContent = bookmarkCount;
          badge.classList.remove("hidden");
        } else {
          btn.insertAdjacentHTML("beforeend", `<span class="cat-count editorial-cat-count">${bookmarkCount}</span>`);
        }
      } else if (badge) {
        badge.classList.add("hidden");
        badge.textContent = "";
      }
      return;
    }
    const rawCount = id === "all" ? (counts.all ?? "") : counts[id];
    if (!badge) {
      if (rawCount !== undefined && rawCount !== "") {
        btn.insertAdjacentHTML("beforeend", `<span class="cat-count editorial-cat-count">${rawCount}</span>`);
      }
      return;
    }
    if (rawCount !== undefined && rawCount !== "") {
      badge.textContent = rawCount;
      badge.classList.remove("hidden");
    } else {
      badge.classList.add("hidden");
      badge.textContent = "";
    }
  });
}

export function updateCategoryUnread(counts = {}, bookmarkCount = 0) {
  return updateCategoryBadges(counts, bookmarkCount);
}

// ── Source Filters ────────────────────────────────────────────────

export function renderSourceFilters(sources = [], activeSource = "", counts = {}) {
  const container = document.getElementById("source-filters");
  if (!container) return;

  const sourceSet = new Set([...Object.keys(SOURCE_COLORS), ...sources]);
  const sourceList = Array.from(sourceSet).filter(Boolean);
  const isAllActive = !activeSource;

  let html = `
    <button class="filter-btn editorial-source-chip ${isAllActive ? 'active' : ''}"
            data-source="" onclick="window.__sourceFilterClick('')">
      <span>ทั้งหมด</span>
    </button>
  `;

  html += sourceList.map(src => {
    const isActive = src.toLowerCase() === (activeSource || "").toLowerCase();
    const count = counts[src];
    const color = SOURCE_COLORS[src] ?? "#1d3557";

    return `
      <button class="filter-btn editorial-source-chip ${isActive ? 'active' : ''}"
              data-source="${esc(src)}" onclick="window.__sourceFilterClick('${esc(src)}')">
        <span class="w-2 h-2 rounded-full shrink-0" style="background:${isActive ? '#ffffff' : color}"></span>
        <span>${esc(src)}</span>
        ${count !== undefined ? `<span class="chip-count">${count}</span>` : ""}
      </button>
    `;
  }).join("");

  container.innerHTML = html;
}

export function updateSourceFilters(activeSource = "") {
  document.querySelectorAll(".filter-btn").forEach(btn => {
    const source = btn.dataset.source ?? "";
    const isActive = source.toLowerCase() === (activeSource || "").toLowerCase();
    const colorDot = btn.querySelector("span.rounded-full");
    const srcColor = SOURCE_COLORS[source] ?? "#1d3557";

    if (isActive) {
      btn.classList.add("active");
      if (colorDot) colorDot.style.background = "#ffffff";
    } else {
      btn.classList.remove("active");
      if (colorDot) colorDot.style.background = srcColor;
    }
  });
}
