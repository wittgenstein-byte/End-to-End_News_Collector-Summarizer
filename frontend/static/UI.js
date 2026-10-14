/**
 * ui.js — DOM manipulation & rendering
 *
 * หน้าที่: วาด UI ล้วน ๆ
 * รับ data สำเร็จรูปจาก main.js — ไม่ fetch เอง
 */

import { SOURCE_COLORS, CATEGORIES, getCategoryById, getSentimentConfig, SENTIMENT_CONFIG } from "./config.js";

// ── Escape ────────────────────────────────────────────────────────

export function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ── Copyright-Safe Local Category Placeholders ──────────────────────

export function getCategoryPlaceholder(category = "") {
  const cat = (category || "").toLowerCase().trim();
  const known = ["politics", "economy", "technology", "environment", "sports", "world"];
  if (known.includes(cat)) {
    return `/frontend/static/icons/placeholder-${cat}.svg`;
  }
  return "/frontend/static/icons/placeholder-default.svg";
}

// ── WS badge ──────────────────────────────────────────────────────

export function setWsBadge(connected) {
  const dot   = document.getElementById("ws-dot");
  const label = document.getElementById("ws-label");
  if (connected) {
    dot.className = "w-2 h-2 rounded-full bg-green-500 animate-pulse";
    label.className = "text-[10px] font-bold tracking-widest text-green-600 uppercase";
    label.textContent = "ออนไลน์";
  } else {
    dot.className = "w-2 h-2 rounded-full bg-error";
    label.className = "text-[10px] font-bold tracking-widest text-error uppercase";
    label.textContent = "ออฟไลน์";
  }
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
 * @param {string}         activeId       — id ที่กำลัง active
 * @param {object}         counts         — {politics: 12, economy: 8, ...}
 * @param {object}         bookmarkedMap  — {url: article, ...}
 */
export function renderCategoryNav(activeId, counts = {}, bookmarkedMap = {}) {
  const nav = document.getElementById("category-nav");
  if (!nav) return;

  const bookmarkCount = Object.keys(bookmarkedMap || {}).length;

  // Tailwind specific styling
  const activeClasses = "bg-primary text-white border-primary shadow-sm";
  const inactiveClasses = "bg-white border-outline-variant/30 text-on-surface-variant hover:bg-surface-container";

  const isForYouActive = activeId === "for-you";
  let html = `
    <button class="cat-pill flex items-center gap-2 px-5 py-2 rounded-full border text-sm font-medium transition-colors flex-shrink-0 ${isForYouActive ? activeClasses : inactiveClasses}"
            data-id="for-you"
            onclick="__categoryClick('for-you')">
      <span class="material-symbols-outlined text-lg">auto_awesome</span>
      <span>สำหรับคุณ</span>
    </button>`;

  html += CATEGORIES.map(cat => {
    const rawCount = cat.id === "all" ? (counts.all ?? "") : counts[cat.id];
    const hasCount = rawCount !== undefined && rawCount !== "";
    const isActive = cat.id === activeId;
    
    return `
      <button class="cat-pill flex items-center gap-2 px-5 py-2 rounded-full border text-sm font-medium transition-colors flex-shrink-0 ${isActive ? activeClasses : inactiveClasses}"
              data-id="${cat.id}"
              onclick="__categoryClick('${cat.id}')">
        <span class="material-symbols-outlined text-lg">${cat.icon}</span>
        <span>${cat.label}</span>
        <span class="cat-count text-[10px] ${isActive ? 'opacity-80' : 'opacity-50'} ml-1 font-bold ${hasCount ? '' : 'hidden'}">${hasCount ? rawCount : ''}</span>
      </button>`;
  }).join("");

  // Add Bookmarks pill to category strip
  const isBookmarkActive = activeId === "bookmarks";
  html += `
    <button class="cat-pill flex items-center gap-2 px-5 py-2 rounded-full border text-sm font-medium transition-colors flex-shrink-0 ${isBookmarkActive ? activeClasses : inactiveClasses}"
            data-id="bookmarks"
            onclick="__categoryClick('bookmarks')">
      <span class="material-symbols-outlined text-lg">bookmarks</span>
      <span>ที่บันทึกไว้</span>
      <span class="cat-count text-[10px] ${isBookmarkActive ? 'opacity-80' : 'opacity-50'} ml-1 font-bold ${bookmarkCount > 0 ? '' : 'hidden'}">${bookmarkCount > 0 ? bookmarkCount : ''}</span>
    </button>
  `;

  nav.innerHTML = html;
}

/** Render the privacy-first topic picker used to start a For You feed. */
export function renderForYouOnboarding(categories = []) {
  const container = document.getElementById("for-you-onboarding");
  if (!container) return;

  container.innerHTML = `
    <div class="mb-8 rounded-2xl border border-primary/20 bg-primary/5 p-5 sm:p-6">
      <div class="flex items-start gap-3">
        <span class="material-symbols-outlined text-primary text-3xl">auto_awesome</span>
        <div>
          <h2 class="font-headline text-xl font-bold text-on-surface">ฟีดสำหรับคุณ</h2>
          <p class="mt-1 text-sm text-on-surface-variant">เลือกอย่างน้อย 3 หมวดเพื่อเริ่มต้น เราประมวลผลความสนใจบนอุปกรณ์นี้เท่านั้น</p>
        </div>
      </div>
      <div class="mt-4 flex flex-wrap gap-2">
        ${categories.map(cat => `
          <button type="button" data-topic-id="${esc(cat.id)}" onclick="__toggleForYouTopic('${esc(cat.id)}')"
            class="for-you-topic rounded-full border border-primary/25 bg-white px-3 py-1.5 text-sm font-medium text-on-surface transition-colors hover:bg-primary/10">
            ${esc(cat.icon)} ${esc(cat.label)}
          </button>`).join("")}
      </div>
      <div class="mt-4 flex flex-wrap items-center gap-3">
        <button type="button" onclick="__saveForYouTopics()" class="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white shadow-sm">สร้างฟีดของฉัน</button>
        <button type="button" onclick="__skipForYouOnboarding()" class="text-sm font-medium text-primary hover:underline">ข้ามและดูข่าวเด่น</button>
        <span id="for-you-topic-count" class="text-xs text-outline">เลือกแล้ว 0/3 หมวด</span>
      </div>
    </div>`;
}

export function hideForYouOnboarding() {
  const container = document.getElementById("for-you-onboarding");
  if (container) container.innerHTML = "";
}
 
/** อัปเดต count badges โดยไม่ redraw ทั้งหมด */
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
          btn.insertAdjacentHTML("beforeend", `<span class="cat-count text-[10px] opacity-50 ml-1 font-bold">${bookmarkCount}</span>`);
        }
      } else if (badge) {
        badge.classList.add("hidden");
        badge.textContent = "";
      }
      return;
    }
    if (!badge) {
      const rawCount = id === "all" ? (counts.all ?? "") : counts[id];
      if (rawCount !== undefined && rawCount !== "") {
        btn.insertAdjacentHTML("beforeend", `<span class="cat-count text-[10px] opacity-50 ml-1 font-bold">${rawCount}</span>`);
      }
      return;
    }
    const rawCount = id === "all" ? (counts.all ?? "") : counts[id];
    if (rawCount !== undefined && rawCount !== "") {
      badge.textContent = rawCount;
      badge.classList.remove("hidden");
    } else {
      badge.classList.add("hidden");
      badge.textContent = "";
    }
  });
}

/**
 * วาดปุ่มตัวกรองสำนักข่าวแบบ Dynamic อัตโนมัติ
 * @param {string[]} sources     — รายการสำนักข่าว
 * @param {string}   activeSource — สำนักข่าวที่เลือก ("" = ทั้งหมด)
 * @param {object}   counts       — จำนวนข่าวต่อสำนัก { "ThaiPBS": 10, ... }
 */
export function renderSourceFilters(sources = [], activeSource = "", counts = {}) {
  const container = document.getElementById("source-filters");
  if (!container) return;

  // รวมสำนักข่าวจาก SOURCE_COLORS และ sources ที่ดึงจาก API/Data
  const sourceSet = new Set([...Object.keys(SOURCE_COLORS), ...sources]);
  const sourceList = Array.from(sourceSet).filter(Boolean);

  const isAllActive = !activeSource;

  let html = `
    <button class="filter-btn px-5 py-1.5 rounded-lg text-xs font-bold transition-all shadow-xs ${
      isAllActive
        ? 'bg-primary text-white hover:bg-primary-container'
        : 'bg-white border border-outline-variant/30 text-on-surface-variant hover:bg-surface-container'
    }" data-source="" onclick="window.__sourceFilterClick('')">
      ทั้งหมด
    </button>
  `;

  html += sourceList.map(src => {
    const isActive = src.toLowerCase() === (activeSource || "").toLowerCase();
    const count = counts[src];
    const color = SOURCE_COLORS[src] ?? "#1a3a6b";

    return `
      <button class="filter-btn flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs transition-all shadow-xs ${
        isActive
          ? 'bg-primary text-white font-bold hover:bg-primary-container'
          : 'bg-white border border-outline-variant/30 font-medium text-on-surface-variant hover:bg-surface-container'
      }" data-source="${esc(src)}" onclick="window.__sourceFilterClick('${esc(src)}')">
        <span class="w-2 h-2 rounded-full shrink-0" style="background:${isActive ? '#ffffff' : color}"></span>
        <span>${esc(src)}</span>
        ${count !== undefined ? `<span class="text-[10px] ${isActive ? 'opacity-80' : 'opacity-50'} ml-0.5 font-bold">(${count})</span>` : ""}
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
    const srcColor = SOURCE_COLORS[source] ?? "#1a3a6b";

    if (isActive) {
      btn.className = "filter-btn flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-bold bg-primary text-white hover:bg-primary-container transition-all shadow-xs";
      if (colorDot) colorDot.style.background = "#ffffff";
    } else {
      btn.className = "filter-btn flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-white border border-outline-variant/30 text-xs font-medium text-on-surface-variant hover:bg-surface-container transition-all shadow-xs";
      if (colorDot) colorDot.style.background = srcColor;
    }
  });
}
// ── Ticker ────────────────────────────────────────────────────────

export function updateTicker(titles) {
  if (!titles.length) return;
  const doubled = [...titles, ...titles];
  document.getElementById("ticker-track").innerHTML =
    doubled.map(t => `
        <div class="flex gap-12 items-center px-4 shrink-0">
          <span class="text-xs font-medium uppercase tracking-wider opacity-90">${esc(t)}</span>
          <span class="material-symbols-outlined text-[10px] opacity-50">diamond</span>
        </div>
    `).join("");
}

// ── Toast ─────────────────────────────────────────────────────────

export function showToast(msg) {
  const toast = document.getElementById("toast");
  document.getElementById("toast-msg").textContent = msg;
  toast.classList.remove("translate-y-full", "opacity-0");
  toast.classList.add("translate-y-0", "opacity-100");
  setTimeout(() => {
    hideToast();
  }, 3000);
}

export function hideToast() {
  const toast = document.getElementById("toast");
  toast.classList.remove("translate-y-0", "opacity-100");
  toast.classList.add("translate-y-full", "opacity-0");
}

// ── Classification Method Badge Helper ────────────────────────────

export function formatClassificationBadge(method) {
  if (!method) return "";

  const m = String(method);
  let icon = "label";
  let label = m;

  if (m.startsWith("Category Cue")) {
    icon = "tag";
    const match = m.match(/\((.*?)\)/);
    let cue = match ? match[1] : "Cue";
    if (cue.startsWith("http") || cue.startsWith("/")) {
      const parts = cue.split("/").filter(Boolean);
      cue = parts[parts.length - 1] || cue;
    }
    label = `Tag: ${cue}`;
  } else if (m.startsWith("URL Priority") || m.startsWith("URL")) {
    icon = "link";
    const match = m.match(/\((.*?)\)/);
    const cue = match ? match[1] : "URL";
    label = `URL: ${cue}`;
  } else if (m.startsWith("Hybrid:") || m.includes("WangchanBERTa")) {
    icon = "smart_toy";
    const confMatch = m.match(/conf=([\d.]+)/);
    const pct = confMatch ? ` ${Math.round(parseFloat(confMatch[1]) * 100)}%` : "";
    const isHybrid = m.startsWith("Hybrid");
    label = isHybrid ? `Hybrid${pct}` : `WangchanBERTa${pct}`;
  } else if (m.startsWith("ML")) {
    icon = "memory";
    const confMatch = m.match(/conf=([\d.]+)/);
    const pct = confMatch ? ` ${Math.round(parseFloat(confMatch[1]) * 100)}%` : "";
    label = `LinearSVC${pct}`;
  } else if (m.startsWith("Rule (") || m.startsWith("High-Specificity Rule")) {
    icon = "verified";
    const match = m.match(/\((.*?)\)/);
    const cue = match ? match[1] : "Rule";
    label = `Rule: ${cue}`;
  } else if (m.startsWith("Rule-based") || m.startsWith("Rule")) {
    icon = "rule";
    label = "Rules";
  } else {
    icon = "tune";
    label = "Default";
  }

  return `
    <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[9px] font-medium text-outline bg-surface-container/60 border border-outline-variant/20 shrink-0 max-w-[120px] truncate" title="วิธีจำแนกหมวดหมู่: ${esc(m)}">
      <span class="material-symbols-outlined text-[11px] opacity-70 shrink-0">${icon}</span>
      <span class="truncate">${esc(label)}</span>
    </span>
  `;
}

// ── Standardized Article Badges ───────────────────────────────────

/**
 * Standardize article badges priority:
 * 1. ⚡ Breaking
 * 2. 🔥 Trending
 * 3. Sentiment indicator
 * 4. Category
 * 5. Classification engine
 * 6. NEW (Session)
 */
export function renderArticleBadges(article, isNew = false) {
  if (!article) return "";

  const badges = [];

  // 1. Status badges from backend article.badges or individual flags
  if (article.badges && Array.isArray(article.badges) && article.badges.length > 0) {
    for (const badge of article.badges) {
      if (badge.includes("Breaking") || badge.includes("ด่วน")) {
        badges.push(`
          <span class="bg-error text-white font-bold text-[10px] px-2.5 py-0.5 rounded-full shadow-xs animate-pulse inline-flex items-center gap-1 shrink-0">
            <span class="material-symbols-outlined text-[12px]">bolt</span>
            <span>${esc(badge)}</span>
          </span>
        `);
      } else if (badge.includes("Top Story")) {
        badges.push(`
          <span class="bg-amber-500 text-white font-bold text-[10px] px-2.5 py-0.5 rounded-full shadow-xs inline-flex items-center gap-1 shrink-0">
            <span class="material-symbols-outlined text-[12px]" style="font-variation-settings: 'FILL' 1;">star</span>
            <span>${esc(badge)}</span>
          </span>
        `);
      } else if (badge.includes("Trending")) {
        const scoreText = (typeof article.trending_score === "number" && !isNaN(article.trending_score))
          ? ` • ${article.trending_score.toFixed(1)}`
          : "";
        badges.push(`
          <span class="bg-gradient-to-r from-amber-500 to-rose-600 text-white font-bold text-[10px] px-2.5 py-0.5 rounded-full shadow-xs inline-flex items-center gap-1 shrink-0" title="คะแนนความนิยม / แนวโน้ม">
            <span class="material-symbols-outlined text-[12px]" style="font-variation-settings: 'FILL' 1;">local_fire_department</span>
            <span>Trending${scoreText}</span>
          </span>
        `);
      } else {
        badges.push(`
          <span class="bg-surface-container text-on-surface-variant font-bold text-[10px] px-2.5 py-0.5 rounded-full shadow-xs inline-flex items-center gap-1 shrink-0">
            <span>${esc(badge)}</span>
          </span>
        `);
      }
    }
  } else {
    // Fallback status flags
    if (article.is_breaking) {
      badges.push(`
        <span class="bg-error text-white font-bold text-[10px] px-2.5 py-0.5 rounded-full shadow-xs animate-pulse inline-flex items-center gap-1 shrink-0">
          <span class="material-symbols-outlined text-[12px]">bolt</span>
          <span>ด่วน</span>
        </span>
      `);
    }

    const isTrending = article.is_trending || (article.trending_score && article.trending_score >= 4.5) || (article.cluster_count && article.cluster_count >= 2) || (article.cluster_size && article.cluster_size >= 2);
    if (isTrending) {
      const scoreText = (typeof article.trending_score === "number" && !isNaN(article.trending_score))
        ? ` • ${article.trending_score.toFixed(1)}`
        : "";
      badges.push(`
        <span class="bg-gradient-to-r from-amber-500 to-rose-600 text-white font-bold text-[10px] px-2.5 py-0.5 rounded-full shadow-xs inline-flex items-center gap-1 shrink-0" title="คะแนนความนิยม / แนวโน้ม">
          <span class="material-symbols-outlined text-[12px]" style="font-variation-settings: 'FILL' 1;">local_fire_department</span>
          <span>Trending${scoreText}</span>
        </span>
      `);
    }
  }

  // 3. Sentiment Indicator
  const sentConf = getSentimentConfig(article.sentiment);
  if (sentConf) {
    badges.push(`
      <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold border shadow-xs ${sentConf.badgeClass} shrink-0" title="ทิศทางอารมณ์ข่าว: ${sentConf.label}">
        <span class="material-symbols-outlined text-[12px]">${sentConf.icon}</span>
        <span>${sentConf.label}</span>
      </span>
    `);
  }

  // 4. Category Badge
  const catObj = getCategoryById(article.category);
  if (catObj && catObj.id !== "all") {
    badges.push(`
      <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold shrink-0" style="background:${catObj.bg}; color:${catObj.color}">
        <span>${catObj.icon}</span>
        <span>${catObj.label}</span>
      </span>
    `);
  }

  // 5. Classification Engine Badge
  if (article.classification_method) {
    badges.push(formatClassificationBadge(article.classification_method));
  }

  // 6. NEW Badge (Session)
  if (isNew) {
    badges.push(`
      <span class="px-2 py-0.5 rounded-full bg-primary/10 text-[10px] font-bold text-primary uppercase border border-primary/20 shrink-0">NEW</span>
    `);
  }

  return badges.join("");
}

// ── Floating Live Update Indicator ────────────────────────────────

export function showFloatingUpdateBanner(count) {
  const indicator = document.getElementById("new-articles-indicator");
  const countText = document.getElementById("new-articles-count-text");
  if (!indicator) return;

  if (countText) {
    countText.textContent = count && count > 0
      ? `⚡ มีข่าวใหม่ ${count} บทความ • คลิกเพื่อดู`
      : `⚡ มีข่าวใหม่เข้ามา • คลิกเพื่อดู`;
  }

  indicator.classList.remove("-translate-y-16", "opacity-0", "pointer-events-none");
  indicator.classList.add("translate-y-0", "opacity-100", "pointer-events-auto");
}

export function hideFloatingUpdateBanner() {
  const indicator = document.getElementById("new-articles-indicator");
  if (!indicator) return;

  indicator.classList.remove("translate-y-0", "opacity-100", "pointer-events-auto");
  indicator.classList.add("-translate-y-16", "opacity-0", "pointer-events-none");
}

// ── Hero / Trending Highlight Section ─────────────────────────────

// ── Hero / Trending Carousel State ───────────────────────────────
let heroTrendingArticles = [];
let heroBookmarkedMap = {};
let heroCurrentIndex = 0;
let heroAutoPlayTimer = null;

function startHeroAutoPlay() {
  stopHeroAutoPlay();
  if (heroTrendingArticles.length > 1) {
    heroAutoPlayTimer = setInterval(() => {
      heroCurrentIndex = (heroCurrentIndex + 1) % heroTrendingArticles.length;
      updateHeroTrendingSlide();
    }, 4500);
  }
}

function stopHeroAutoPlay() {
  if (heroAutoPlayTimer) {
    clearInterval(heroAutoPlayTimer);
    heroAutoPlayTimer = null;
  }
}

export function getCurrentHeroTrendingStory() {
  if (heroTrendingArticles && heroTrendingArticles.length > 0) {
    return heroTrendingArticles[heroCurrentIndex] || heroTrendingArticles[0];
  }
  return null;
}

export function getHeroTrendingArticles() {
  return heroTrendingArticles;
}

export function getHeroTrendingStoryById(id) {
  if (!id || !heroTrendingArticles.length) return null;
  const target = String(id).trim().toLowerCase();
  return heroTrendingArticles.find(s => {
    const mId = String(s.macro_event_id || "").toLowerCase();
    const sId = String(s.story_id || "").toLowerCase();
    const cId = String(s.cluster_id || "").toLowerCase();
    const t = String(s.title || "").toLowerCase();
    const h = String(s.headline || "").toLowerCase();
    return mId === target || sId === target || cId === target || t === target || h === target;
  }) || null;
}

export function renderHeroTrending(articles = [], bookmarkedMap = {}) {
  const container = document.getElementById("hero-trending");
  if (!container) return;

  if (!articles || !articles.length) {
    stopHeroAutoPlay();
    container.innerHTML = "";
    container.classList.add("hidden");
    return;
  }

  container.classList.remove("hidden");

  // Deduplicate storylines into 1 trending item per topic (No duplicate ranks)
  const seenKeys = new Map();
  const deduped = [];
  for (const item of (articles || [])) {
    const mId = item.macro_event_id || item.story_id;
    const rawT = (item.headline || item.topic_title || item.title || "").trim();
    const normT = rawT.replace(/[\s"\'“”‘’\(\)\[\]\-]+/g, "").toLowerCase();

    let matchKey = null;
    if (mId && seenKeys.has(mId)) {
      matchKey = mId;
    } else {
      for (const [k, prev] of seenKeys.entries()) {
        const prevRaw = (prev.headline || prev.topic_title || prev.title || "").trim();
        const prevNorm = prevRaw.replace(/[\s"\'“”‘’\(\)\[\]\-]+/g, "").toLowerCase();
        if (normT && prevNorm && (normT.includes(prevNorm) || prevNorm.includes(normT) || (normT.length >= 10 && normT.slice(0, 10) === prevNorm.slice(0, 10)))) {
          matchKey = k;
          break;
        }
      }
    }

    if (matchKey) {
      const existing = seenKeys.get(matchKey);
      // Combine outlets
      const outletSet = new Set(existing.outlets || existing.cluster_sources || []);
      (item.outlets || item.cluster_sources || [item.source]).filter(Boolean).forEach(o => outletSet.add(o));
      existing.outlets = Array.from(outletSet);
      existing.cluster_sources = existing.outlets;
      // Combine articles
      const existUrls = new Set((existing.articles || []).map(a => a.url));
      (item.articles || (item.url ? [item] : [])).forEach(a => {
        if (a && a.url && !existUrls.has(a.url)) {
          existUrls.add(a.url);
          if (!existing.articles) existing.articles = [];
          existing.articles.push(a);
        }
      });
      existing.article_count = (existing.articles || []).length;
      // Combine hashtags
      const tagSet = new Set(existing.hashtags || []);
      (item.hashtags || []).forEach(h => tagSet.add(h));
      existing.hashtags = Array.from(tagSet);
      // Combine child_events
      if (Array.isArray(item.child_events)) {
        if (!existing.child_events) existing.child_events = [];
        const existCids = new Set(existing.child_events.map(c => c.story_id).filter(Boolean));
        for (const ce of item.child_events) {
          if (!ce.story_id || !existCids.has(ce.story_id)) {
            existing.child_events.push(ce);
            if (ce.story_id) existCids.add(ce.story_id);
          }
        }
      }
    } else {
      const key = mId || normT;
      seenKeys.set(key, item);
      deduped.push(item);
    }
  }

  // Unlimited rank: No .slice(0, 7)! Display all macro storylines
  heroTrendingArticles = deduped;
  heroBookmarkedMap = bookmarkedMap || {};
  heroCurrentIndex = 0;

  updateHeroTrendingSlide();
  startHeroAutoPlay();
}

/**
 * กำหนดป้ายกำกับมุมมองสื่อแบบ Deterministic ตามเนื้อหาและสำนักข่าว
 */
export function getPerspectiveLabel(headline = "", outlet = "", summary = "") {
  const text = `${headline} ${summary} ${outlet}`.toLowerCase();
  
  if (text.includes("แบงก์ชาติ") || text.includes("ธปท") || text.includes("กนง") || text.includes("ดอกเบี้ย") || text.includes("เงินเฟ้อ") || text.includes("thai post")) {
    return "มุมมอง ธปท. / แบงก์ชาติ";
  }
  if (text.includes("imf") || text.includes("world bank") || text.includes("ai") || text.includes("เอไอ") || text.includes("เทคโนโลยี") || text.includes("standard")) {
    return "มุมมอง สากล & AI (IMF)";
  }
  if (text.includes("หุ้น") || text.includes("ตลาดทุน") || text.includes("โบรก") || text.includes("ดึงทุน") || text.includes("การเงิน") || text.includes("ลงทุน") || text.includes("bangkokbiz")) {
    return "มุมมอง ตลาดทุน & การลงทุน";
  }
  if (text.includes("รัฐบาล") || text.includes("นายก") || text.includes("กระทรวง") || text.includes("การเมือง") || text.includes("พรรค")) {
    return "มุมมอง นโยบาย & ภาครัฐ";
  }
  if (text.includes("ส่งออก") || text.includes("การค้า") || text.includes("พาณิชย์") || text.includes("ท่องเที่ยว")) {
    return "มุมมอง การค้า & ภาคเศรษฐกิจจริง";
  }
  return `มุมมองรายงานโดย ${outlet || "สำนักข่าว"}`;
}

/**
 * แถบสถานะ Breadcrumb เมื่อกรองข่าวตามประเด็นมหากาพย์ หรือแฮชแท็ก
 */
export function renderStorylineBreadcrumb(topicLabel) {
  const container = document.getElementById("storyline-filter-breadcrumb");
  if (!container) return;
  if (!topicLabel) {
    container.innerHTML = "";
    container.classList.add("hidden");
    return;
  }
  container.classList.remove("hidden");
  container.innerHTML = `
    <div class="p-3.5 sm:p-4 rounded-2xl bg-gradient-to-r from-purple-500/15 via-indigo-500/10 to-amber-500/15 border border-purple-300 dark:border-purple-800/60 shadow-xs flex items-center justify-between gap-3 flex-wrap">
      <div class="flex items-center gap-2.5 min-w-0">
        <div class="w-8 h-8 rounded-xl bg-purple-600 text-white flex items-center justify-center shrink-0 shadow-2xs">
          <span class="material-symbols-outlined text-[18px]">filter_alt</span>
        </div>
        <div class="min-w-0">
          <span class="text-[10px] sm:text-xs font-bold text-outline uppercase tracking-wider block">กำลังแสดงเฉพาะข่าวในประเด็น</span>
          <span class="text-xs sm:text-sm font-extrabold text-on-surface truncate block" title="${esc(topicLabel)}">
            ${esc(topicLabel)}
          </span>
        </div>
      </div>
      <button type="button" 
              class="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white dark:bg-surface-container text-xs font-bold text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-800 hover:bg-rose-50 dark:hover:bg-rose-950/40 shadow-2xs hover:shadow-xs active:scale-95 transition-all cursor-pointer shrink-0"
              onclick="window.__clearStorylineFilter()">
        <span class="material-symbols-outlined text-[15px]">close</span>
        <span>ล้างตัวกรองกลับสู่ข่าวทั้งหมด</span>
      </button>
    </div>
  `;
}

function updateHeroTrendingSlide() {
  const container = document.getElementById("hero-trending");
  if (!container || !heroTrendingArticles.length) return;

  const total = heroTrendingArticles.length;
  const n = heroTrendingArticles[heroCurrentIndex];
  const rankNum = heroCurrentIndex + 1;
  const isBookmarked = Boolean(heroBookmarkedMap && heroBookmarkedMap[n.url]);
  const imgSrc = n.image_url || getCategoryPlaceholder(n.category);
  const color = SOURCE_COLORS[n.source] ?? "#1a3a6b";
  const jsonEncoded = encodeURIComponent(JSON.stringify(n));
  const scoreVal = (typeof n.trending_score === "number" && !isNaN(n.trending_score))
    ? n.trending_score.toFixed(1)
    : "9.8";

  const isMacro = Boolean(n.is_macro || (n.child_events && n.child_events.length > 0));
  const subEventsCount = n.child_events_count || (n.child_events ? n.child_events.length : 0);

  // 1. Rank Badge
  let rankBadge = "";
  if (rankNum === 1) {
    rankBadge = `
      <span class="px-3 py-1 rounded-lg bg-gradient-to-r from-rose-600 via-amber-600 to-rose-600 text-white font-extrabold text-xs shadow-md flex items-center gap-1.5 animate-pulse">
        <span class="material-symbols-outlined text-[15px]" style="font-variation-settings: 'FILL' 1;">whatshot</span>
        <span>#1 HOT STORY</span>
      </span>
    `;
  } else if (rankNum === 2) {
    rankBadge = `
      <span class="px-3 py-1 rounded-lg bg-amber-600 text-white font-bold text-xs shadow-md flex items-center gap-1.5">
        <span class="material-symbols-outlined text-[15px]" style="font-variation-settings: 'FILL' 1;">local_fire_department</span>
        <span>#2 TRENDING</span>
      </span>
    `;
  } else if (rankNum === 3) {
    rankBadge = `
      <span class="px-3 py-1 rounded-lg bg-emerald-600 text-white font-bold text-xs shadow-md flex items-center gap-1.5">
        <span class="material-symbols-outlined text-[15px]">trending_up</span>
        <span>#3 TRENDING</span>
      </span>
    `;
  } else {
    rankBadge = `
      <span class="px-3 py-1 rounded-lg bg-black/75 text-white font-bold text-xs backdrop-blur-xs flex items-center gap-1.5">
        <span>อันดับ #${rankNum}</span>
      </span>
    `;
  }

  // 2. Multi-source Reporting Pill
  let multiSourcePill = "";
  if (isMacro && subEventsCount > 0) {
    multiSourcePill += `
      <div class="flex items-center gap-1.5 text-xs text-white font-bold bg-black/80 backdrop-blur-md px-3 py-1.5 rounded-full border border-purple-400/50 w-fit shadow-lg">
        <span class="material-symbols-outlined text-[15px] text-purple-300">hub</span>
        <span class="text-white">มหากาพย์ <span class="text-purple-300 font-extrabold">${subEventsCount}</span> เหตุการณ์ย่อย</span>
      </div>
    `;
  }
  if (n.cluster_sources && Array.isArray(n.cluster_sources) && n.cluster_sources.length > 1) {
    const srcCount = n.cluster_sources.length;
    const displayedSources = srcCount > 3
      ? `${n.cluster_sources.slice(0, 3).join(", ")} +${srcCount - 3} สำนักข่าว`
      : n.cluster_sources.join(", ");
    multiSourcePill += `
      <div class="flex items-center gap-1.5 text-xs text-white font-bold bg-black/80 backdrop-blur-md px-3 py-1.5 rounded-full border border-white/40 w-fit shadow-lg" title="${esc(n.cluster_sources.join(', '))}">
        <span class="material-symbols-outlined text-[15px] text-amber-400">newspaper</span>
        <span class="text-white">รายงานจาก ${srcCount} สำนักข่าว: <span class="text-amber-300 font-semibold">${esc(displayedSources)}</span></span>
      </div>
    `;
  } else if (n.outlets && Array.isArray(n.outlets) && n.outlets.length > 1) {
    const srcCount = n.outlets.length;
    const displayedSources = srcCount > 3
      ? `${n.outlets.slice(0, 3).join(", ")} +${srcCount - 3} สำนักข่าว`
      : n.outlets.join(", ");
    multiSourcePill += `
      <div class="flex items-center gap-1.5 text-xs text-white font-bold bg-black/80 backdrop-blur-md px-3 py-1.5 rounded-full border border-white/40 w-fit shadow-lg" title="${esc(n.outlets.join(', '))}">
        <span class="material-symbols-outlined text-[15px] text-amber-400">newspaper</span>
        <span class="text-white">รายงานจาก ${srcCount} สำนักข่าว: <span class="text-amber-300 font-semibold">${esc(displayedSources)}</span></span>
      </div>
    `;
  } else if (n.cluster_size && n.cluster_size > 1) {
    multiSourcePill += `
      <div class="flex items-center gap-1.5 text-xs text-white font-bold bg-black/80 backdrop-blur-md px-3 py-1.5 rounded-full border border-white/40 w-fit shadow-lg">
        <span class="material-symbols-outlined text-[15px] text-amber-400">hub</span>
        <span class="text-white">ประเด็นตรงกัน ${n.cluster_size} สำนักข่าว</span>
      </div>
    `;
  }

  // 3. Quick-Switch Trending Strip (Horizontal Scroll Capsule Strip)
  const quickSwitchStripHtml = heroTrendingArticles.length > 0 ? `
    <div class="trending-quick-strip mb-4 flex items-center gap-2.5 overflow-x-auto pb-2 scrollbar-none"
         onmouseenter="window.__pauseTrendingAutoPlay()"
         onmouseleave="window.__resumeTrendingAutoPlay()">
      <div class="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-purple-600/10 text-purple-700 dark:text-purple-300 text-xs font-extrabold shrink-0 border border-purple-500/20 shadow-2xs">
        <span class="material-symbols-outlined text-[16px] text-purple-600 animate-pulse">schema</span>
        <span>มหากาพย์ประเด็นยอดนิยม:</span>
      </div>
      <div class="flex items-center gap-2 flex-nowrap">
        ${heroTrendingArticles.map((art, idx) => {
          const isCurrent = idx === heroCurrentIndex;
          const rank = idx + 1;
          const rankIcon = rank === 1 ? 'whatshot' : (rank === 2 ? 'local_fire_department' : 'trending_up');
          const titleShort = esc(art.headline || art.topic_title || art.title || `ประเด็น #${rank}`);
          const srcCount = art.child_events_count || (art.outlets ? art.outlets.length : (art.cluster_size || 1));
          
          return `
            <button type="button" 
                    class="trending-quick-card shrink-0 flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all duration-200 cursor-pointer shadow-xs active:scale-95 ${
                      isCurrent 
                        ? 'bg-gradient-to-r from-purple-700 via-indigo-700 to-primary text-white shadow-md ring-2 ring-purple-400 scale-[1.02]' 
                        : 'bg-white dark:bg-surface-container border border-outline-variant/30 text-on-surface hover:border-purple-300 dark:hover:border-purple-600 hover:bg-surface-container-high'
                    }"
                    onclick="window.__goToTrendingSlide(${idx})"
                    title="${titleShort}">
              <span class="flex items-center gap-1 font-extrabold ${isCurrent ? 'text-amber-300' : 'text-purple-600 dark:text-purple-400'}">
                <span class="material-symbols-outlined text-[15px]">${rankIcon}</span>
                <span>#${rank}</span>
              </span>
              <span class="max-w-[130px] sm:max-w-[180px] lg:max-w-[220px] truncate text-left">${titleShort}</span>
              <span class="text-[10px] px-1.5 py-0.5 rounded-md font-extrabold ${
                isCurrent ? 'bg-white/20 text-white' : 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300'
              }">
                ${srcCount} สื่อ
              </span>
            </button>
          `;
        }).join("")}
      </div>
    </div>
  ` : "";

  // 4. Progress Segments (Auto-play indicators)
  const indicatorsHtml = heroTrendingArticles.map((_, idx) => {
    const isCurrent = idx === heroCurrentIndex;
    return `
      <button type="button" 
              class="hero-progress-segment ${isCurrent ? 'hero-progress-segment-active' : ''}" 
              onclick="window.__goToTrendingSlide(${idx})" 
              title="อันดับที่ #${idx + 1}">
        ${isCurrent ? '<div class="hero-progress-bar-fill hero-progress-active"></div>' : ''}
      </button>
    `;
  }).join("");

  // 5. Global Hashtags Bar
  const allTrendingHashtags = Array.from(new Set(
    heroTrendingArticles.flatMap(a => Array.isArray(a.hashtags) ? a.hashtags : [])
  )).slice(0, 10);

  const hashtagsBarHtml = allTrendingHashtags.length > 0 ? `
    <div class="trending-hashtags-bar mb-3 flex items-center gap-2 overflow-x-auto py-1.5 scrollbar-none">
      <div class="flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/10 text-amber-800 dark:text-amber-300 text-xs font-extrabold shrink-0 border border-amber-500/20 shadow-2xs">
        <span class="material-symbols-outlined text-[15px] text-amber-500" style="font-variation-settings: 'FILL' 1;">local_fire_department</span>
        <span>#แท็กยอดนิยม:</span>
      </div>
      <div class="flex items-center gap-1.5 flex-nowrap">
        ${allTrendingHashtags.map(tag => `
          <button type="button" 
                  class="trending-hashtag-pill text-xs font-bold text-amber-900 dark:text-amber-200 bg-amber-100/80 hover:bg-amber-400 hover:text-black dark:bg-amber-950/50 dark:hover:bg-amber-400 dark:hover:text-black border border-amber-300/70 dark:border-amber-700/60 px-3 py-1 rounded-full transition-all cursor-pointer shadow-2xs active:scale-95 shrink-0"
                  onclick="window.__filterByHashtag('${esc(tag)}')"
                  title="กรองข่าวประเด็น ${esc(tag)}">
            ${esc(tag)}
          </button>
        `).join("")}
      </div>
    </div>
  ` : "";

  // 5. Publisher Outlets Bar (แหล่งข่าวที่รายงานในมหากาพย์นี้)
  const outletMap = new Map();
  (n.articles || []).forEach(a => {
    if (a && a.source) {
      if (!outletMap.has(a.source)) outletMap.set(a.source, []);
      outletMap.get(a.source).push(a);
    }
  });
  (n.child_events || []).forEach(ce => {
    (ce.articles || []).forEach(a => {
      if (a && a.source) {
        if (!outletMap.has(a.source)) outletMap.set(a.source, []);
        if (!outletMap.get(a.source).some(ea => ea.url === a.url)) {
          outletMap.get(a.source).push(a);
        }
      }
    });
  });
  if (outletMap.size === 0 && n.source) {
    outletMap.set(n.source, n.url ? [n] : []);
  }
  (n.outlets || n.cluster_sources || []).forEach(src => {
    if (!outletMap.has(src)) outletMap.set(src, []);
  });

  const publisherPillsHtml = Array.from(outletMap.entries()).map(([outlet, arts]) => {
    const brandColor = SOURCE_COLORS[outlet] ?? "#6366f1";
    const count = arts.length;
    return `
      <button type="button"
              class="hero-publisher-pill flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-black/75 hover:bg-black/95 text-white border border-white/30 hover:border-white/60 backdrop-blur-md shadow-md text-xs font-bold transition-all duration-200 cursor-pointer active:scale-95 group/pub shrink-0"
              onclick="event.stopPropagation(); window.__openOutletArticle('${esc(outlet)}')"
              title="คลิกอ่านรายงานข่าวจาก ${esc(outlet)} (${count} ข่าว)">
        <span class="w-2.5 h-2.5 rounded-full shrink-0 shadow-xs" style="background:${brandColor}"></span>
        <span class="group-hover/pub:text-amber-300 transition-colors">${esc(outlet)}</span>
        ${count > 0 ? `<span class="text-[10px] px-1.5 py-0.2 rounded-md font-extrabold bg-white/20 text-white/90">${count}</span>` : ""}
        <span class="material-symbols-outlined text-[13px] opacity-60 group-hover/pub:opacity-100 transition-opacity">open_in_new</span>
      </button>
    `;
  }).join("");

  // 6. Consolidated Hashtags for this Storyline
  const storylineHashtags = Array.from(new Set([
    ...(Array.isArray(n.hashtags) ? n.hashtags : []),
    ...((n.child_events || []).flatMap(ce => Array.isArray(ce.hashtags) ? ce.hashtags : [])),
    ...((n.articles || []).flatMap(a => Array.isArray(a.hashtags) ? a.hashtags : [])),
  ])).filter(Boolean).slice(0, 10);

  const storylineHashtagsHtml = storylineHashtags.length > 0 ? `
    <div class="flex items-center gap-1.5 flex-wrap pt-1">
      <span class="text-xs font-extrabold text-amber-300 flex items-center gap-1 shrink-0 drop-shadow-sm">
        <span class="material-symbols-outlined text-[14px]">tag</span>
        <span>#แฮชแท็ก:</span>
      </span>
      <div class="flex items-center gap-1.5 flex-wrap">
        ${storylineHashtags.map(tag => {
          const clean = tag.startsWith("#") ? tag.slice(1) : tag;
          return `
            <button type="button"
                    class="hero-hashtag-pill text-xs font-bold text-amber-200 bg-black/65 hover:bg-amber-400 hover:text-black hover:border-amber-400 border border-amber-300/40 px-3 py-1 rounded-full transition-all duration-200 cursor-pointer backdrop-blur-md shadow-xs active:scale-95 flex items-center gap-0.5"
                    onclick="event.stopPropagation(); window.__filterByHashtag('${esc(clean)}')"
                    title="กรองข่าวประเด็น #${esc(clean)}">
              <span>#</span><span>${esc(clean)}</span>
            </button>
          `;
        }).join("")}
      </div>
    </div>
  ` : "";

  container.innerHTML = `
    <!-- 1. Quick-Switch Trending Strip -->
    ${quickSwitchStripHtml}

    <!-- 2. Global Trending Hashtags Bar -->
    ${hashtagsBarHtml}

    <!-- 3. Header Title -->
    <div class="mb-3 flex items-center justify-between gap-4">
      <div class="flex items-center gap-2.5">
        <div class="w-8 h-8 rounded-xl bg-gradient-to-tr from-rose-500 via-amber-500 to-purple-600 flex items-center justify-center text-white shadow-sm shrink-0">
          <span class="material-symbols-outlined text-[18px]" style="font-variation-settings: 'FILL' 1;">whatshot</span>
        </div>
        <div class="flex items-center gap-2 flex-wrap">
          <h2 class="font-headline font-extrabold text-base sm:text-lg lg:text-xl text-on-surface tracking-tight">⚡ มหากาพย์ประเด็นข่าวร้อน & เรื่องเด่น (Macro Storylines & Trending)</h2>
          <span class="hidden sm:inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 text-[11px] font-bold border border-purple-200 dark:border-purple-800/40">
            <span class="material-symbols-outlined text-[13px]">schema</span>
            <span>Macro Storyline Hub</span>
          </span>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <span class="text-xs font-bold text-outline bg-surface-container px-3 py-1 rounded-full border border-outline-variant/30">
          อันดับ ${rankNum} / ${total}
        </span>
      </div>
    </div>

    <!-- 4. Single Clean Hero Card Banner -->
    <div class="hero-carousel-container group"
         onmouseenter="window.__pauseTrendingAutoPlay()"
         onmouseleave="window.__resumeTrendingAutoPlay()">
      
      <!-- Background Image -->
      <img src="${esc(imgSrc)}" 
           alt="${esc(n.title)}" 
           class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700 opacity-100 cursor-pointer"
           onclick="window.__openPreview('${esc(n.url)}')"
           onerror="this.onerror=null; this.src='${getCategoryPlaceholder(n.category)}';" 
           loading="eager" />

      <!-- Left Navigation Arrow -->
      <button type="button" 
               class="hero-nav-btn hero-nav-btn-left"
               onclick="window.__prevTrendingSlide(event)"
               title="ก่อนหน้า">
        <span class="material-symbols-outlined text-[28px]">chevron_left</span>
      </button>

      <!-- Right Navigation Arrow -->
      <button type="button" 
               class="hero-nav-btn hero-nav-btn-right"
               onclick="window.__nextTrendingSlide(event)"
               title="ถัดไป">
        <span class="material-symbols-outlined text-[28px]">chevron_right</span>
      </button>

      <!-- Dark Gradient Overlay with Text and Badges -->
      <div class="hero-gradient-overlay">
        <!-- Top Status Row -->
        <div class="flex items-center justify-between gap-2 pointer-events-auto">
          <div class="flex items-center gap-2 flex-wrap">
            ${rankBadge}
            ${isMacro ? `
              <span class="px-2.5 py-1 rounded-lg bg-gradient-to-r from-purple-700 to-indigo-700 text-white font-bold text-xs shadow-md flex items-center gap-1 border border-purple-400/40">
                <span class="material-symbols-outlined text-[14px]">schema</span>
                <span>มหากาพย์ข่าว</span>
              </span>
            ` : ""}
            <span class="px-2.5 py-1 rounded-lg bg-black/75 text-white backdrop-blur-md text-xs font-bold border border-white/30 shadow-md">
              🔥 Trending • ${scoreVal}
            </span>
          </div>
          <div class="flex items-center gap-2 bg-black/75 backdrop-blur-md px-3 py-1 rounded-lg border border-white/30 shadow-md">
            <span class="w-2.5 h-2.5 rounded-full shadow-xs" style="background:${color}"></span>
            <span class="text-xs font-bold text-white uppercase tracking-wider drop-shadow-md">${esc(n.source || (n.outlets && n.outlets[0]) || "รวมสำนักข่าว")}</span>
          </div>
        </div>

        <!-- Bottom Content Row -->
        <div class="space-y-3 pointer-events-auto pb-4">
          <div class="space-y-2">
            <div class="flex items-center gap-2 flex-wrap">
              ${multiSourcePill}
              ${n.topic_title && n.topic_title !== n.title ? `
                <div class="inline-flex items-center gap-1 text-xs text-amber-300 font-bold bg-black/70 backdrop-blur-md px-3 py-1.5 rounded-full border border-amber-400/40 w-fit shadow-lg">
                  <span class="material-symbols-outlined text-[14px]">topic</span>
                  <span>ประเด็น: ${esc(n.topic_title)}</span>
                </div>
              ` : ""}
            </div>
            
            <h1 class="text-lg sm:text-2xl md:text-3xl font-headline font-bold hero-headline leading-tight drop-shadow-lg group-hover:text-amber-200 transition-colors line-clamp-2 cursor-pointer"
                onclick="window.__openPreview('${esc(n.url)}')">
              ${esc(n.title)}
            </h1>

            ${n.summary ? `
              <p class="text-xs sm:text-sm text-white/90 line-clamp-2 leading-relaxed drop-shadow-md hidden sm:block font-body max-w-4xl"
                 onclick="window.__openPreview('${esc(n.url)}')">
                <span class="text-amber-300 font-bold">บทสรุปสังเคราะห์:</span> ${esc(n.summary)}
              </p>
            ` : ""}

            <!-- Publisher Outlets Row (แหล่งข่าวให้กดดู) -->
            ${publisherPillsHtml ? `
              <div class="flex items-center gap-2 flex-wrap pt-1">
                <span class="text-xs font-extrabold text-amber-300 flex items-center gap-1 shrink-0 drop-shadow-sm">
                  <span class="material-symbols-outlined text-[15px]">newspaper</span>
                  <span>แหล่งข่าว:</span>
                </span>
                <div class="flex items-center gap-1.5 flex-wrap">
                  ${publisherPillsHtml}
                </div>
              </div>
            ` : ""}

            <!-- Consolidated Hashtags Row (รวม # ไว้) -->
            ${storylineHashtagsHtml}
          </div>

          <div class="flex items-center justify-between gap-4 flex-wrap pt-2">
            <span class="text-xs font-bold text-white/90 uppercase tracking-wider drop-shadow-md">${esc(n.fetched_at || "")}</span>
            <div class="flex items-center gap-2 flex-wrap" onclick="event.stopPropagation()">
              <button type="button" 
                      class="p-2 rounded-xl border border-white/40 bg-black/60 text-white hover:bg-white hover:text-slate-900 backdrop-blur-md active:scale-95 transition-all shadow-md cursor-pointer"
                      onclick="window.__toggleArticleBookmark(event, '${jsonEncoded}')" 
                      title="${isBookmarked ? 'ลบบุ๊กมาร์ก' : 'บันทึกบทความ'}">
                <span class="material-symbols-outlined text-[18px] text-white" style="${isBookmarked ? "font-variation-settings: 'FILL' 1; color: #f59e0b;" : ""}">
                  ${isBookmarked ? 'bookmark' : 'bookmark_border'}
                </span>
              </button>
              <button type="button" 
                      class="flex items-center gap-1.5 bg-white hover:bg-slate-100 text-slate-900 px-4 py-2 rounded-xl font-bold text-xs shadow-md active:scale-95 transition-all cursor-pointer" 
                      onclick="window.__openPreview('${esc(n.url)}')">
                <span class="material-symbols-outlined text-[16px] text-slate-900">visibility</span>
                <span class="text-slate-900 font-bold">อ่านสรุปย่อ</span>
              </button>
              <button type="button" 
                      class="flex items-center gap-1.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white px-3.5 py-2 rounded-xl font-bold text-xs shadow-md active:scale-95 transition-all cursor-pointer border border-purple-300/40 backdrop-blur-md" 
                      onclick="window.__openStoryline('${esc(n.macro_event_id || n.story_id)}', '${esc(n.headline || n.title)}')">
                <span class="material-symbols-outlined text-[16px] text-purple-200">filter_alt</span>
                <span class="text-white font-bold">ดูข่าวทั้งหมดในประเด็นนี้</span>
              </button>
              <button type="button" 
                      class="flex items-center gap-1.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white px-4 py-2 rounded-xl font-bold text-xs shadow-md active:scale-95 transition-all cursor-pointer border border-white/20" 
                      onclick="window.__openPreviewAndSummarize('${esc(n.url)}')">
                <span class="material-symbols-outlined text-[16px] text-amber-300" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
                <span class="text-white font-bold">สรุป AI ทันที</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Bottom Progress Indicator Bar Segments -->
      <div class="hero-progress-container">
        ${indicatorsHtml}
      </div>
    </div>
  `;
}

/// Safe stubs for legacy timeline/subevent toggles (cleaned up)
window.__toggleTimelinePanel = () => {};
window.__togglePerspectiveQuote = () => {};
window.__scrollToStoryTimeline = () => {};
window.__scrollToSubEvents = () => {};
window.__scrollToSubEvent = () => {};
window.__toggleSubEventArticles = () => {};

// Global Carousel Actions
window.__prevTrendingSlide = (event) => {
  if (event) event.stopPropagation();
  if (!heroTrendingArticles.length) return;
  heroCurrentIndex = (heroCurrentIndex - 1 + heroTrendingArticles.length) % heroTrendingArticles.length;
  updateHeroTrendingSlide();
  startHeroAutoPlay();
};

window.__nextTrendingSlide = (event) => {
  if (event) event.stopPropagation();
  if (!heroTrendingArticles.length) return;
  heroCurrentIndex = (heroCurrentIndex + 1) % heroTrendingArticles.length;
  updateHeroTrendingSlide();
  startHeroAutoPlay();
};

window.__goToTrendingSlide = (index) => {
  if (index >= 0 && index < heroTrendingArticles.length) {
    heroCurrentIndex = index;
    updateHeroTrendingSlide();
    startHeroAutoPlay();
  }
};

window.__pauseTrendingAutoPlay = () => {
  stopHeroAutoPlay();
};

window.__resumeTrendingAutoPlay = () => {
  startHeroAutoPlay();
};

// ── News grid ─────────────────────────────────────────────────────

/**
 * @param {object[]} articles
 * @param {Set<string>} newUrlSet     — URLs ของข่าวใหม่ใน session นี้
 * @param {object}      bookmarkedMap — { [url]: articleObj }
 */
export function renderGrid(articles, newUrlSet = new Set(), bookmarkedMap = {}) {
  const grid = document.getElementById("news-grid");
  if (!grid) return;

  if (!articles || !articles.length) {
    grid.innerHTML = `<div class="col-span-1 md:col-span-2 lg:col-span-3 text-center py-16 text-on-surface-variant">ไม่พบข่าวในหมวดหมู่ หรือคำค้นหานี้</div>`;
    return;
  }

  grid.innerHTML = articles.map((n, i) => {
    const isNew = newUrlSet && newUrlSet.has(n.url);
    const isBookmarked = Boolean(bookmarkedMap && bookmarkedMap[n.url]);
    const color = SOURCE_COLORS[n.source] ?? "#1a3a6b";
    const placeholder = getCategoryPlaceholder(n.category);
    const imgSrc = n.image_url || placeholder;
    const articleJsonEncoded = encodeURIComponent(JSON.stringify(n));

    return `
      <article class="bg-white rounded-xl overflow-hidden flex flex-col border border-outline-variant/20 transition-all duration-300 group hover:shadow-lg hover:-translate-y-1" style="animation: fadeUp 0.4s ease-out ${i * 0.04}s both;">
        <div class="flex flex-col flex-1 cursor-pointer" data-url="${esc(n.url)}" onclick="window.__openPreview(this.dataset.url)">
          <!-- Card Thumbnail -->
          <div class="aspect-[16/9] overflow-hidden relative shrink-0 bg-surface-container-low">
            <img alt="thumbnail" class="object-cover w-full h-full transition-transform duration-500 group-hover:scale-105" src="${esc(imgSrc)}" onerror="this.onerror=null; this.src='${placeholder}';" loading="lazy" />
            <div class="absolute bottom-2 left-2 right-2 flex items-center justify-between">
              <span class="text-[10px] font-bold px-2 py-0.5 rounded-md bg-black/60 text-white backdrop-blur-xs flex items-center gap-1">
                <span class="w-1.5 h-1.5 rounded-full shrink-0" style="background:${color}"></span>
                <span>${esc(n.source)}</span>
              </span>
              ${n.category ? `<span class="text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-black/60 text-white backdrop-blur-xs">${esc(n.category)}</span>` : ""}
            </div>
          </div>

          <!-- Card Content (Headlines + Source + Badges) -->
          <div class="p-4 pb-2 flex flex-col flex-1">
            <!-- Source & Badges Row -->
            <div class="flex items-center justify-between gap-2 mb-2">
              <div class="flex items-center gap-1.5 min-w-0">
                <span class="w-2 h-2 rounded-full shrink-0" style="background:${color}"></span>
                <span class="text-xs font-bold text-on-surface-variant uppercase tracking-wider truncate">${esc(n.source)}</span>
              </div>
              <div class="flex items-center gap-1.5 shrink-0 flex-wrap">
                ${renderArticleBadges(n, isNew)}
              </div>
            </div>

            <h2 class="text-base sm:text-[17px] font-headline font-bold leading-snug transition-colors group-hover:text-primary line-clamp-2">
              ${esc(n.title)}
            </h2>
          </div>
        </div>

        <!-- Card Footer Actions -->
        <div class="px-4 pb-3 pt-2.5 mt-auto border-t border-outline-variant/10 flex items-center justify-between gap-2">
          <span class="text-[10px] font-bold text-outline uppercase shrink-0">${esc(n.fetched_at ?? "")}</span>
          <div class="flex items-center gap-1.5 shrink-0" onclick="event.stopPropagation()">
            ${n.url ? `
            <button type="button"
                    class="h-8 w-8 flex items-center justify-center rounded-lg border border-outline-variant/30 ${isBookmarked ? 'bg-primary/10 text-primary border-primary/30' : 'text-on-surface-variant hover:text-primary hover:bg-surface-container'} active:scale-95 transition-all cursor-pointer"
                    onclick="window.__toggleArticleBookmark(event, '${articleJsonEncoded}')"
                    title="${isBookmarked ? 'ลบบุ๊กมาร์ก' : 'บันทึกบทความ'}">
              <span class="material-symbols-outlined text-[16px]" style="${isBookmarked ? "font-variation-settings: 'FILL' 1; color: #2e4d83;" : ""}">
                ${isBookmarked ? 'bookmark' : 'bookmark_border'}
              </span>
            </button>` : ""}

            ${n.url ? `
            <button type="button"
                    class="h-8 w-8 flex items-center justify-center rounded-lg text-on-surface-variant hover:bg-surface-container hover:text-error active:scale-95 transition-all cursor-pointer"
                    onclick="window.__showLessLikeThis(event, '${articleJsonEncoded}')"
                    title="สนใจน้อยลง">
              <span class="material-symbols-outlined text-[16px]">visibility_off</span>
            </button>` : ""}

            <button type="button" 
                    class="h-8 px-3 flex items-center justify-center gap-1.5 bg-surface-container text-on-surface hover:bg-surface-container-high rounded-lg font-bold text-xs active:scale-95 transition-all cursor-pointer"
                    data-url="${esc(n.url)}"
                    onclick="window.__openPreview(this.dataset.url)"
                    title="เปิดหน้า Preview">
              <span class="material-symbols-outlined text-[14px]">visibility</span>
              <span>อ่านย่อ</span>
            </button>

            <button type="button" 
                    class="h-8 px-3.5 flex items-center justify-center gap-1.5 bg-primary text-white hover:bg-primary-container rounded-lg font-bold text-xs shadow-xs active:scale-95 transition-all cursor-pointer"
                    data-url="${esc(n.url)}"
                    onclick="window.__openPreviewAndSummarize(this.dataset.url)"
                    title="เปิด Preview พร้อมสรุป AI ทันที">
              <span class="material-symbols-outlined text-[14px]" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
              <span>สรุป AI</span>
            </button>
          </div>
        </div>
      </article>
    `;
  }).join("");

  // Add the keyframe animation directly if not using tailwind classes
  if (!document.getElementById('fadeUpKeyframes')) {
    const style = document.createElement('style');
    style.id = 'fadeUpKeyframes';
    style.innerHTML = `
      @keyframes fadeUp {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
      }
    `;
    document.head.appendChild(style);
  }
}

export function showGridLoading() {
  document.getElementById("news-grid").innerHTML = `
    <div class="col-span-1 md:col-span-2 lg:col-span-3 text-center py-16 flex flex-col items-center justify-center opacity-60">
      <svg class="animate-spin h-10 w-10 text-primary mb-4" fill="none" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <circle class="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"></circle>
        <path class="opacity-80" d="M12 2a10 10 0 0110 10" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="2"></path>
      </svg>
      <span class="font-headline italic text-lg text-primary">กำลังโหลดข้อมูล...</span>
    </div>
  `;
}

export function showGridError(msg = "เชื่อมต่อ API ไม่ได้") {
  document.getElementById("news-grid").innerHTML = `
    <div class="col-span-1 md:col-span-2 lg:col-span-3 text-center py-16 flex flex-col items-center justify-center">
        <span class="material-symbols-outlined text-error text-4xl mb-4">error</span>
        <span class="text-error font-medium">${esc(msg)}</span>
    </div>
  `;
}

// ── Pagination ────────────────────────────────────────────────────

/**
 * @param {object} meta  — {page, total_pages, total}
 */
export function renderPagination(meta) {
  const pg = document.getElementById("pagination");
  const { page, total_pages: totalPages, total } = meta;

  if (totalPages <= 1) { pg.innerHTML = ""; return; }

  const btnClasses = "w-10 h-10 rounded-lg border border-outline-variant/30 font-bold text-sm flex items-center justify-center transition-colors";
  const activeClasses = "bg-primary text-white border-primary shadow-md";
  const inactiveClasses = "bg-white text-on-surface-variant hover:bg-surface-container";
  const disabledClasses = "bg-surface-container-highest text-outline-variant border-transparent cursor-not-allowed opacity-50";

  const btn = (p, label, disabled = false, active = false) => {
      let cls = disabled ? disabledClasses : (active ? activeClasses : inactiveClasses);
      return `<button class="${btnClasses} ${cls}"
             onclick="__loadPage(${p})"
             ${disabled ? "disabled" : ""}>${label}</button>`;
  }

  let html = btn(page - 1, "‹", page <= 1);

  const start = Math.max(1, page - 2);
  const end   = Math.min(totalPages, start + 4);

  if (start > 1)       html += btn(1, "1") + `<span class="px-2 text-outline">…</span>`;
  for (let p = start; p <= end; p++) html += btn(p, p, false, p === page);
  if (end < totalPages) html += `<span class="px-2 text-outline">…</span>` + btn(totalPages, totalPages);

  html += btn(page + 1, "›", page >= totalPages);
  html += `<span class="ml-4 text-xs font-bold text-outline uppercase tracking-widest hidden sm:inline">${total} บทความ</span>`;

  pg.innerHTML = html;
}

// ── Summary Modal ─────────────────────────────────────────────────

export function openModal() {
  const modal = document.getElementById("summary-modal");
  const content = document.getElementById("modal-content-wrap");
  
  modal.classList.remove("opacity-0", "pointer-events-none");
  modal.classList.add("opacity-100", "pointer-events-auto");
  
  setTimeout(() => {
     content.classList.remove("translate-y-4", "scale-95");
     content.classList.add("translate-y-0", "scale-100");
  }, 10);
  
  document.body.style.overflow = "hidden"; // Prevent background scroll
}

export function closeModal() {
  const modal = document.getElementById("summary-modal");
  const content = document.getElementById("modal-content-wrap");
  
  content.classList.remove("translate-y-0", "scale-100");
  content.classList.add("translate-y-4", "scale-95");
  
  setTimeout(() => {
    modal.classList.remove("opacity-100", "pointer-events-auto");
    modal.classList.add("opacity-0", "pointer-events-none");
    document.body.style.overflow = ""; // Restore background scroll
  }, 300);
}

export function showModalLoading() {
  document.getElementById("summary-loading").style.display = "block";
  document.getElementById("summary-result").style.display  = "none";
  document.getElementById("summary-result").innerHTML      = "";
}

export function showModalResult(summary, originalUrl = "") {
  const s = summary;
  document.getElementById("summary-loading").style.display = "none";
  const result = document.getElementById("summary-result");
  result.style.display = "block";

  const bullets  = (s.bullets  ?? []).map((b, i) => `
    <li class="takeaways-item flex items-start space-x-4">
        <span class="text-primary mt-1 text-sm md:text-base font-bold opacity-80 shrink-0">0${i+1}.</span>
        <span class="text-on-surface leading-relaxed">${esc(b)}</span>
    </li>
  `).join("");
  
  const keywords = (s.keywords ?? []).map(k => `
    <span class="px-3 py-1 bg-surface-container-high text-primary text-[10px] font-bold uppercase tracking-widest rounded-full border border-outline-variant/20 hover:bg-primary hover:text-white transition-colors cursor-pointer">#${esc(k)}</span>
  `).join("");

  result.innerHTML = `
    <!-- Modal Inner Results -->
    <header class="space-y-4">
        <div class="flex items-center justify-between flex-wrap gap-2">
            <div class="flex items-center space-x-2 flex-wrap gap-1">
                ${s.category ? `<span class="px-3 py-1 bg-primary/10 text-primary text-[10px] font-bold uppercase tracking-widest rounded-full border border-primary/20">${esc(s.category)}</span>` : ""}
                ${formatClassificationBadge(s.classification_method)}
                <span class="text-on-surface-variant/70 text-[10px] uppercase font-bold tracking-widest">• OVERVIEW</span>
            </div>
            ${s.sentiment ? `
            <div class="flex items-center space-x-1 text-[10px] font-bold uppercase tracking-widest">
                <span class="text-outline">Sentiment:</span>
                <span class="${s.sentiment.toLowerCase().includes('positive') ? 'text-green-600' : (s.sentiment.toLowerCase().includes('negative') ? 'text-error' : 'text-primary')}">${esc(s.sentiment)}</span>
            </div>` : ""}
        </div>
        
        <h1 class="summary-title text-primary-container font-extrabold tracking-tight">
            ${esc(s.title ?? "ไม่มีหัวข้อ")}
        </h1>
    </header>

    <section class="relative my-7 md:my-8">
        <div class="absolute -left-4 md:-left-6 top-0 bottom-0 w-1 bg-primary-container/20 rounded-full"></div>
        <p class="summary-lead text-on-surface italic opacity-90 pl-2">
            ${esc(s.summary ?? "")}
        </p>
    </section>

    ${bullets ? `
    <section class="space-y-4">
        <div class="takeaways-card bg-surface-container-lowest rounded-xl shadow-sm border border-outline-variant/20">
            <h3 class="takeaways-title font-bold uppercase text-primary flex items-center space-x-2">
                <span class="material-symbols-outlined text-sm">list_alt</span>
                <span>Key Takeaways</span>
            </h3>
            <ul class="takeaways-list flex flex-col">
                ${bullets}
            </ul>
        </div>
    </section>
    ` : ""}

    ${keywords ? `
    <section class="pt-6">
        <div class="flex flex-wrap gap-2">
            ${keywords}
        </div>
    </section>
    ` : ""}

    <footer class="mt-12 pt-8 border-t border-outline-variant/20 flex flex-wrap justify-between items-center gap-4 text-xs font-bold text-outline uppercase tracking-widest">
        <span>Generated: ${new Date().toLocaleTimeString()}</span>
        ${originalUrl ? `
        <a href="${esc(originalUrl)}" target="_blank" rel="noopener noreferrer"
           class="inline-flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg text-xs font-bold hover:bg-primary-container transition-colors shadow-sm normal-case tracking-normal">
          <span>อ่านข่าวต้นฉบับเต็ม</span>
          <span class="material-symbols-outlined text-[16px]">open_in_new</span>
        </a>` : ""}
        <span>ID: ${Math.random().toString(36).substr(2, 6)}</span>
    </footer>
  `;
}

export function showModalError(msg) {
  document.getElementById("summary-loading").style.display = "none";
  const result = document.getElementById("summary-result");
  result.style.display = "block";
  result.innerHTML = `
    <div class="flex flex-col items-center justify-center py-16 text-center">
        <div class="w-16 h-16 bg-error/10 text-error rounded-full flex items-center justify-center mb-6">
            <span class="material-symbols-outlined text-3xl">error</span>
        </div>
        <h3 class="font-headline text-2xl font-bold text-error mb-2">Error Processing Summary</h3>
        <p class="text-on-surface-variant max-w-md mx-auto">
          ❌ ${esc(msg)}
        </p>
        <button class="mt-8 px-6 py-2 border border-outline-variant rounded-full text-sm font-bold text-on-surface hover:bg-surface-container" onclick="document.getElementById('modal-close-btn').click()">
            Close
        </button>
    </div>`;
}

// ── PWA View Switching ────────────────────────────────────────────

export function switchView(viewName = "feed") {
  const feedView = document.getElementById("feed-view");
  const previewView = document.getElementById("preview-view");
  const storylineView = document.getElementById("storyline-view");
  const tickerContainer = document.getElementById("ticker-container");

  if (viewName === "preview") {
    if (feedView) feedView.classList.add("hidden");
    if (storylineView) storylineView.classList.add("hidden");
    if (previewView) previewView.classList.remove("hidden");
    if (tickerContainer) tickerContainer.classList.add("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  } else if (viewName === "storyline") {
    if (feedView) feedView.classList.add("hidden");
    if (previewView) previewView.classList.add("hidden");
    if (storylineView) storylineView.classList.remove("hidden");
    if (tickerContainer) tickerContainer.classList.add("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  } else {
    if (previewView) previewView.classList.add("hidden");
    if (storylineView) storylineView.classList.add("hidden");
    if (feedView) feedView.classList.remove("hidden");
    if (tickerContainer) tickerContainer.classList.remove("hidden");
  }
}

// ── Preview Sub-View Rendering ────────────────────────────────────

export function renderInlineSummary(summary) {
  const s = summary;
  const bullets = (s.bullets ?? []).map((b, i) => `
    <li class="flex items-start space-x-3 text-sm leading-relaxed text-on-surface">
      <span class="text-primary font-bold text-xs mt-0.5 shrink-0 bg-primary/10 w-5 h-5 rounded-full flex items-center justify-center">0${i+1}</span>
      <span>${esc(b)}</span>
    </li>
  `).join("");

  const keywords = (s.keywords ?? []).map(k => `
    <span class="px-2.5 py-0.5 bg-primary/10 text-primary text-[10px] font-bold rounded-md">#${esc(k)}</span>
  `).join("");

  return `
    <div class="p-6 bg-surface-container-lowest rounded-2xl border border-primary/20 shadow-xs space-y-4 animate-fade-in">
      <div class="flex items-center justify-between flex-wrap gap-2 border-b border-outline-variant/10 pb-3">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-primary text-lg" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
          <h3 class="font-headline font-bold text-base text-primary">บทวิเคราะห์และสรุปประเด็นโดย AI</h3>
        </div>
        ${s.sentiment ? `
          <span class="text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full ${s.sentiment.toLowerCase().includes('positive') ? 'bg-emerald-100 text-emerald-800' : (s.sentiment.toLowerCase().includes('negative') ? 'bg-rose-100 text-rose-800' : 'bg-blue-100 text-blue-800')}">
            Sentiment: ${esc(s.sentiment)}
          </span>
        ` : ""}
      </div>

      ${s.summary ? `
        <p class="text-sm text-on-surface-variant leading-relaxed">
          ${esc(s.summary)}
        </p>
      ` : ""}

      ${bullets ? `
        <div class="space-y-2 pt-2">
          <h4 class="text-xs font-bold uppercase tracking-widest text-outline">Key Takeaways</h4>
          <ul class="space-y-2">
            ${bullets}
          </ul>
        </div>
      ` : ""}

      ${keywords ? `
        <div class="flex flex-wrap gap-1.5 pt-2">
          ${keywords}
        </div>
      ` : ""}
    </div>
  `;
}

export function showInlineSummaryLoading() {
  const section = document.getElementById("preview-ai-section");
  if (!section) return;
  section.innerHTML = `
    <div class="p-8 bg-surface-container-lowest rounded-2xl border border-outline-variant/20 text-center space-y-3">
      <div class="inline-flex items-center justify-center">
        <svg class="animate-spin h-8 w-8 text-primary" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3"></circle>
          <path class="opacity-80" d="M12 2a10 10 0 0110 10" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="3"></path>
        </svg>
      </div>
      <p class="text-sm font-bold text-primary">AI กำลังสังเคราะห์และวิเคราะห์ประเด็นข่าว...</p>
      <p class="text-xs text-outline">กรุณารอสักครู่ ระบบกำลังดึงประเด็นสำคัญและประเมินทิศทางข่าว</p>
    </div>
  `;
}

export function showInlineSummaryError(msg, articleUrl) {
  const section = document.getElementById("preview-ai-section");
  if (!section) return;
  section.innerHTML = `
    <div class="p-6 bg-rose-50 border border-rose-200 rounded-2xl text-center space-y-3">
      <span class="material-symbols-outlined text-rose-600 text-2xl">error</span>
      <p class="text-sm text-rose-800 font-bold">${esc(msg)}</p>
      <button class="px-4 py-1.5 bg-rose-600 text-white rounded-lg text-xs font-bold hover:bg-rose-700 transition-colors"
              onclick="window.__runPreviewAiSummary('${esc(articleUrl)}')">
        ลองใหม่อีกครั้ง
      </button>
    </div>
  `;
}

export function renderPreviewView(article, isBookmarked = false, cachedSummary = null) {
  const preview = document.getElementById("preview-view");
  if (!preview) return;

  const color = SOURCE_COLORS[article.source] ?? "#1a3a6b";
  const placeholder = getCategoryPlaceholder(article.category);
  const imgSrc = article.image_url || placeholder;
  const articleJsonEncoded = encodeURIComponent(JSON.stringify(article));

  const textLen = (article.summary || "").length + (article.title || "").length;
  const readMins = Math.max(1, Math.round(textLen / 250));

  preview.innerHTML = `
    <!-- Top Bar Navigation -->
    <div class="flex items-center justify-between gap-4 mb-6 sticky top-[72px] z-30 bg-surface/95 backdrop-blur py-3 border-b border-outline-variant/20">
      <button class="inline-flex items-center gap-2 px-4 py-2 bg-white hover:bg-surface-container text-on-surface rounded-xl text-sm font-bold transition-all active:scale-95 shadow-sm border border-outline-variant/30"
              onclick="window.__backToFeed()">
        <span class="material-symbols-outlined text-[18px]">arrow_back</span>
        <span>กลับหน้ารวมข่าว</span>
      </button>

      <div class="flex items-center gap-2">
        <button class="flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-outline-variant/30 ${isBookmarked ? 'bg-primary/10 text-primary border-primary/40' : 'bg-white text-on-surface-variant hover:text-primary hover:bg-surface-container'} text-xs font-bold transition-all active:scale-95 shadow-sm"
                onclick="window.__toggleArticleBookmark(event, '${articleJsonEncoded}')"
                title="${isBookmarked ? 'ลบบุ๊กมาร์ก' : 'บันทึกบทความ'}">
          <span class="material-symbols-outlined text-[18px]" style="${isBookmarked ? "font-variation-settings: 'FILL' 1; color: #1a3a6b;" : ""}">
            ${isBookmarked ? 'bookmark' : 'bookmark_border'}
          </span>
          <span class="hidden sm:inline">${isBookmarked ? 'บันทึกแล้ว' : 'บันทึกไว้อ่าน'}</span>
        </button>

        <button class="p-2 bg-white hover:bg-surface-container text-on-surface-variant rounded-xl border border-outline-variant/30 transition-colors shadow-sm"
                onclick="window.__shareArticle('${esc(article.title)}', '${esc(article.url)}')"
                title="แชร์ลิงก์ข่าว">
          <span class="material-symbols-outlined text-[18px]">share</span>
        </button>
      </div>
    </div>

    <!-- Article Container -->
    <article class="bg-white rounded-2xl border border-outline-variant/20 overflow-hidden shadow-sm">
      <!-- Thumbnail -->
      <div class="relative w-full aspect-[16/9] md:aspect-[21/9] bg-slate-900 overflow-hidden">
        <img src="${esc(imgSrc)}" 
             alt="${esc(article.title)}" 
             class="w-full h-full object-cover"
             onerror="this.onerror=null; this.src='${placeholder}';"
             loading="eager" />
        <div class="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent"></div>
        <div class="absolute bottom-4 left-4 right-4 flex items-center justify-between text-white text-xs font-bold flex-wrap gap-2">
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full" style="background:${color}"></span>
            <span class="bg-black/50 backdrop-blur px-3 py-1 rounded-md uppercase tracking-wider">${esc(article.source)}</span>
          </div>
          <span class="bg-black/50 backdrop-blur px-3 py-1 rounded-md">${esc(article.fetched_at || "ล่าสุด")}</span>
        </div>
      </div>

      <div class="p-6 md:p-10 space-y-6">
        <!-- Badges -->
        <div class="flex items-center gap-2 flex-wrap text-xs">
          ${article.category ? `<span class="px-3 py-1 bg-primary/10 text-primary font-bold uppercase tracking-widest rounded-full border border-primary/20">${esc(article.category)}</span>` : ""}
          <span class="text-outline flex items-center gap-1">
            <span class="material-symbols-outlined text-[14px]">schedule</span>
            <span>เวลาอ่านประมาณ ${readMins} นาที</span>
          </span>
        </div>

        <!-- Title -->
        <h1 class="text-2xl md:text-4xl font-headline font-extrabold text-on-surface leading-tight">
          ${esc(article.title)}
        </h1>

        <!-- Short Excerpt / Snippet Block (2-3 lines) -->
        <div class="p-5 bg-surface-container-lowest rounded-xl border-l-4 border-primary shadow-xs space-y-2">
          <div class="flex items-center gap-2 text-primary font-bold text-xs uppercase tracking-wider">
            <span class="material-symbols-outlined text-[16px]">subject</span>
            <span>บทคัดย่อโดยสังเขป (Snippet)</span>
          </div>
          <p class="text-base text-on-surface-variant leading-relaxed font-body italic">
            ${esc(article.summary || "ไม่มีบทคัดย่อสำหรับข่าวนี้ สามารถกดอ่านรายละเอียดฉบับเต็มได้ที่ปุ่มด้านล่าง")}
          </p>
        </div>

        <!-- AI Summary On-Demand Section -->
        <div id="preview-ai-section" class="pt-2">
          ${cachedSummary ? renderInlineSummary(cachedSummary) : `
            <div class="p-6 bg-gradient-to-br from-primary/5 via-surface to-primary-container/5 rounded-2xl border border-primary/20 text-center space-y-3">
              <div class="w-12 h-12 bg-primary/10 text-primary rounded-xl flex items-center justify-center mx-auto">
                <span class="material-symbols-outlined text-2xl" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
              </div>
              <div>
                <h3 class="font-headline font-bold text-lg text-primary">สรุปใจความสำคัญด้วย AI</h3>
                <p class="text-xs text-outline max-w-md mx-auto mt-1">วิเคราะห์ประเด็นหลัก ดึง Key Takeaways และประเมิน Sentiment จากเนื้อหาข่าว</p>
              </div>
              <button class="inline-flex items-center gap-2 px-6 py-2.5 bg-primary text-white text-sm font-bold rounded-xl hover:bg-primary-container active:scale-95 transition-all shadow-sm"
                      onclick="window.__runPreviewAiSummary('${esc(article.url)}')">
                <span class="material-symbols-outlined text-[18px]">bolt</span>
                <span>สรุปเนื้อหาด้วย AI (On-Demand)</span>
              </button>
            </div>
          `}
        </div>

        <!-- Action Section & External Full News Link -->
        <div class="pt-8 border-t border-outline-variant/20 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div class="text-xs text-outline flex items-center gap-2">
            <span class="material-symbols-outlined text-emerald-600 text-[18px]">verified_user</span>
            <span>เปิดลิงก์แบบปลอดภัย • ทำความสะอาดพารามิเตอร์ติดตาม (No Tracking)</span>
          </div>

          <button class="w-full sm:w-auto inline-flex items-center justify-center gap-2.5 px-6 py-3 bg-primary hover:bg-primary-container text-white font-bold text-sm rounded-xl shadow-md transition-all active:scale-95"
                  onclick="window.__openExternalSourceClean('${esc(article.url)}')">
            <span>อ่านข่าวฉบับเต็มบนเว็บต้นฉบับ</span>
            <span class="material-symbols-outlined text-[18px]">open_in_new</span>
          </button>
        </div>

      </div>
    </article>
  `;
}

// ── Offline & PWA Banner Helpers ──────────────────────────────────

export function showOfflineStatus(isOffline) {
  const bar = document.getElementById("offline-bar");
  if (!bar) return;
  if (isOffline) {
    bar.classList.remove("-translate-y-full");
    bar.classList.add("translate-y-0");
  } else {
    bar.classList.remove("translate-y-0");
    bar.classList.add("-translate-y-full");
  }
}

export function showPwaInstallBanner(onInstall, onDismiss) {
  const banner = document.getElementById("pwa-install-banner");
  const installBtn = document.getElementById("pwa-install-btn");
  if (!banner) return;

  if (installBtn && onInstall) {
    installBtn.onclick = onInstall;
  }

  banner.classList.remove("translate-y-32", "opacity-0", "pointer-events-none");
  banner.classList.add("translate-y-0", "opacity-100", "pointer-events-auto");
}

export function hidePwaInstallBanner() {
  const banner = document.getElementById("pwa-install-banner");
  if (!banner) return;
  banner.classList.remove("translate-y-0", "opacity-100", "pointer-events-auto");
  banner.classList.add("translate-y-32", "opacity-0", "pointer-events-none");
}

// ── History & Bookmarks Modal ─────────────────────────────────────

export function openHistoryModal(title = "ประวัติการอ่าน", icon = "history") {
  const modal = document.getElementById("history-modal");
  const titleEl = document.getElementById("history-modal-title");
  const iconEl = document.getElementById("history-modal-icon");
  if (!modal) return;

  if (titleEl) titleEl.textContent = title;
  if (iconEl) iconEl.textContent = icon;

  modal.classList.remove("hidden");
  modal.classList.add("flex");
}

export function closeHistoryModal() {
  const modal = document.getElementById("history-modal");
  if (!modal) return;
  modal.classList.remove("flex");
  modal.classList.add("hidden");
}

export function renderHistoryList(items = [], type = "history", bookmarkedMap = {}) {
  const content = document.getElementById("history-modal-content");
  const clearBtn = document.getElementById("history-clear-btn");
  if (!content) return;

  if (clearBtn) {
    clearBtn.style.display = (items.length > 0 && type === "history") ? "inline-block" : "none";
  }

  if (!items || items.length === 0) {
    content.innerHTML = `
      <div class="text-center py-12 text-outline">
        <span class="material-symbols-outlined text-4xl mb-2">${type === 'history' ? 'history_toggle_off' : 'bookmarks'}</span>
        <p class="text-sm font-medium">ยังไม่มีรายการ${type === 'history' ? 'ประวัติการอ่าน' : 'บุ๊กมาร์ก'}</p>
      </div>
    `;
    return;
  }

  content.innerHTML = items.map((item) => {
    const isBookmarked = Boolean(bookmarkedMap && bookmarkedMap[item.url]);
    const placeholder = getCategoryPlaceholder(item.category);
    const imgSrc = item.image_url || placeholder;
    const itemEncoded = encodeURIComponent(JSON.stringify(item));

    return `
      <div class="flex items-center gap-3 p-3 bg-surface-container-low hover:bg-surface-container rounded-xl border border-outline-variant/20 transition-all cursor-pointer group"
           onclick="window.__closeHistoryModal(); window.__openPreview('${esc(item.url)}')">
        <div class="w-16 h-16 rounded-lg overflow-hidden bg-surface-container-highest shrink-0">
          <img src="${esc(imgSrc)}" alt="thumb" class="w-full h-full object-cover" onerror="this.onerror=null; this.src='${placeholder}';" loading="lazy">
        </div>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 text-[10px] font-bold text-outline uppercase tracking-wider mb-0.5">
            <span class="text-primary font-bold">${esc(item.source || "")}</span>
            ${item.category ? `<span>• ${esc(item.category)}</span>` : ""}
            <span>• ${esc(item.viewed_at || item.fetched_at || "")}</span>
          </div>
          <h4 class="text-sm font-bold text-on-surface line-clamp-1 group-hover:text-primary transition-colors">${esc(item.title)}</h4>
          <p class="text-xs text-outline line-clamp-1 mt-0.5">${esc(item.summary || "")}</p>
        </div>
        <div class="shrink-0 flex items-center gap-1" onclick="event.stopPropagation()">
          <button class="p-1.5 text-on-surface-variant hover:text-primary rounded-lg transition-colors"
                  onclick="window.__toggleArticleBookmark(event, '${itemEncoded}')"
                  title="${isBookmarked ? 'ลบบุ๊กมาร์ก' : 'บันทึกบทความ'}">
            <span class="material-symbols-outlined text-[18px]" style="${isBookmarked ? "font-variation-settings: 'FILL' 1; color: #1a3a6b;" : ""}">
              ${isBookmarked ? 'bookmark' : 'bookmark_border'}
            </span>
          </button>
        </div>
      </div>
    `;
  }).join("");
}

// ── Dedicated Storyline View (หน้าเจาะลึกมหากาพย์ประเด็นข่าว) ────────

export function showStorylineLoading() {
  const container = document.getElementById("storyline-view");
  if (!container) return;
  container.innerHTML = `
    <div class="py-24 text-center flex flex-col items-center justify-center space-y-4">
      <div class="inline-flex items-center justify-center">
        <svg class="animate-spin h-10 w-10 text-purple-600" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3"></circle>
          <path class="opacity-80" d="M12 2a10 10 0 0110 10" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="3"></path>
        </svg>
      </div>
      <p class="text-base font-extrabold text-purple-900 dark:text-purple-200">กำลังโหลดมหากาพย์ประเด็นข่าว...</p>
      <p class="text-xs text-outline">รวบรวมเหตุการณ์และบทความจากสำนักข่าวทั้งหมด</p>
    </div>
  `;
}

export function showStorylineError(msg = "ไม่สามารถโหลดข้อมูลประเด็นข่าวนี้ได้") {
  const container = document.getElementById("storyline-view");
  if (!container) return;
  container.innerHTML = `
    <div class="max-w-2xl mx-auto py-16 px-6 text-center space-y-4">
      <div class="w-14 h-14 mx-auto rounded-2xl bg-rose-100 dark:bg-rose-950/40 text-rose-600 flex items-center justify-center">
        <span class="material-symbols-outlined text-3xl">error</span>
      </div>
      <h3 class="font-headline font-bold text-lg text-on-surface">เกิดข้อผิดพลาดในการโหลดประเด็นข่าว</h3>
      <p class="text-sm text-outline">${esc(msg)}</p>
      <div class="pt-2 flex items-center justify-center gap-3">
        <button class="px-5 py-2 bg-primary text-white rounded-xl text-xs font-bold hover:bg-primary-container transition-all active:scale-95 shadow-xs cursor-pointer"
                onclick="window.__backFromStoryline()">
          กลับสู่ฟีดรวมข่าว
        </button>
      </div>
    </div>
  `;
}

export function showStorylineAiLoading() {
  const section = document.getElementById("storyline-ai-section");
  if (!section) return;
  section.innerHTML = `
    <div class="p-6 mt-4 bg-purple-500/10 dark:bg-purple-950/30 rounded-2xl border border-purple-400/30 text-center space-y-3 animate-fade-in">
      <div class="inline-flex items-center justify-center">
        <svg class="animate-spin h-7 w-7 text-purple-600 dark:text-purple-400" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3"></circle>
          <path class="opacity-80" d="M12 2a10 10 0 0110 10" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="3"></path>
        </svg>
      </div>
      <p class="text-sm font-bold text-purple-900 dark:text-purple-200">AI กำลังสังเคราะห์ภาพรวมมหากาพย์ประเด็นนี้...</p>
      <p class="text-xs text-outline">วิเคราะห์มุมมองร่วม ความขัดแย้ง และพัฒนาการสำคัญจากทุกสำนักข่าว</p>
    </div>
  `;
}

export function renderStorylineAiSummary(summaryData) {
  const section = document.getElementById("storyline-ai-section");
  if (!section) return;
  const s = summaryData;
  const bullets = (s.bullets ?? []).map((b, i) => `
    <li class="flex items-start space-x-3 text-sm leading-relaxed text-on-surface">
      <span class="text-purple-600 dark:text-purple-400 font-bold text-xs mt-0.5 shrink-0 bg-purple-100 dark:bg-purple-900/40 w-5 h-5 rounded-full flex items-center justify-center">0${i+1}</span>
      <span>${esc(b)}</span>
    </li>
  `).join("");

  const keywords = (s.keywords ?? []).map(k => {
    const clean = String(k).replace(/^#/, "");
    return `
      <span class="px-2.5 py-0.5 bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 text-[10px] font-bold rounded-md">#${esc(clean)}</span>
    `;
  }).join("");

  section.innerHTML = `
    <div class="p-6 mt-4 bg-white dark:bg-surface-container-low rounded-2xl border border-purple-300/60 dark:border-purple-800/60 shadow-xs space-y-4 animate-fade-in">
      <div class="flex items-center justify-between flex-wrap gap-2 border-b border-purple-100 dark:border-purple-900/30 pb-3">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-purple-600 dark:text-purple-400 text-lg" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
          <h3 class="font-headline font-bold text-base text-purple-900 dark:text-purple-200">บทวิเคราะห์สังเคราะห์ประเด็นข้ามสำนักข่าว (AI Deep Synthesis)</h3>
        </div>
        ${s.sentiment ? `
          <span class="text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full ${s.sentiment.toLowerCase().includes('positive') ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300' : (s.sentiment.toLowerCase().includes('negative') ? 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300' : 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300')}">
            Sentiment: ${esc(s.sentiment)}
          </span>
        ` : ""}
      </div>

      ${s.summary ? `
        <p class="text-sm text-on-surface leading-relaxed">
          ${esc(s.summary)}
        </p>
      ` : ""}

      ${bullets ? `
        <div class="space-y-2 pt-2">
          <h4 class="text-xs font-bold uppercase tracking-widest text-outline">Key Story Developments (ลำดับความคืบหน้าสำคัญ)</h4>
          <ul class="space-y-2">
            ${bullets}
          </ul>
        </div>
      ` : ""}

      ${keywords ? `
        <div class="flex flex-wrap gap-1.5 pt-2">
          ${keywords}
        </div>
      ` : ""}
    </div>
  `;
}

export function renderStorylineView(storyData, activeSourceFilter = "", bookmarkedMap = {}) {
  const container = document.getElementById("storyline-view");
  if (!container || !storyData) return;

  const storyId = storyData.macro_event_id || storyData.story_id || storyData.cluster_id || "";
  const headline = storyData.headline || storyData.title || "มหากาพย์ประเด็นข่าว";
  const category = storyData.category || "general";
  const catObj = getCategoryById(category);
  const rawArticles = Array.isArray(storyData.articles) ? storyData.articles : [];

  // Sort articles chronologically (earliest to latest for story timeline)
  const sortedArticles = [...rawArticles].sort((a, b) => {
    const timeA = new Date(a.fetched_at || a.created_at || 0).getTime();
    const timeB = new Date(b.fetched_at || b.created_at || 0).getTime();
    return timeA - timeB;
  });

  // Calculate article counts per publisher outlet
  const outletCounts = {};
  sortedArticles.forEach(a => {
    const src = a.source || "สำนักข่าว";
    outletCounts[src] = (outletCounts[src] || 0) + 1;
  });
  const outlets = Object.keys(outletCounts);

  // Filter articles by activeSourceFilter
  const filteredArticles = activeSourceFilter
    ? sortedArticles.filter(a => (a.source || "").toLowerCase() === activeSourceFilter.toLowerCase())
    : sortedArticles;

  // Build Publisher Filter Pills
  const allIsActive = !activeSourceFilter;
  let publisherPillsHtml = `
    <button type="button" 
            class="storyline-publisher-pill flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all shadow-2xs cursor-pointer shrink-0 ${
              allIsActive 
                ? 'bg-purple-600 text-white shadow-xs' 
                : 'bg-white dark:bg-surface-container text-on-surface-variant hover:bg-surface-container-high border border-outline-variant/30'
            }"
            onclick="window.__filterStorylinePublisher('')">
      <span>ทั้งหมด</span>
      <span class="text-[10px] px-1.5 py-0.2 rounded-md ${allIsActive ? 'bg-white/20 text-white font-extrabold' : 'bg-surface-container-highest text-outline'}">
        ${sortedArticles.length}
      </span>
    </button>
  `;

  publisherPillsHtml += outlets.map(outlet => {
    const isActive = outlet.toLowerCase() === activeSourceFilter.toLowerCase();
    const count = outletCounts[outlet] || 0;
    const color = SOURCE_COLORS[outlet] ?? "#1a3a6b";
    return `
      <button type="button" 
              class="storyline-publisher-pill flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs transition-all shadow-2xs cursor-pointer shrink-0 ${
                isActive 
                  ? 'bg-purple-600 text-white font-bold shadow-xs' 
                  : 'bg-white dark:bg-surface-container text-on-surface-variant hover:bg-surface-container-high border border-outline-variant/30 font-medium'
              }"
              onclick="window.__filterStorylinePublisher('${esc(outlet)}')">
        <span class="w-2 h-2 rounded-full shrink-0" style="background:${isActive ? '#ffffff' : color}"></span>
        <span>${esc(outlet)}</span>
        <span class="text-[10px] px-1.5 py-0.2 rounded-md ${isActive ? 'bg-white/20 text-white font-extrabold' : 'bg-surface-container-highest text-outline'}">
          ${count}
        </span>
      </button>
    `;
  }).join("");

  // Consolidated Hashtags
  const storylineHashtags = Array.from(new Set([
    ...(Array.isArray(storyData.hashtags) ? storyData.hashtags : []),
    ...(Array.isArray(storyData.entities) ? storyData.entities : []),
    ...((storyData.child_events || []).flatMap(ce => Array.isArray(ce.hashtags) ? ce.hashtags : [])),
    ...(sortedArticles.flatMap(a => Array.isArray(a.hashtags) ? a.hashtags : [])),
  ])).filter(Boolean).slice(0, 10);

  const storylineHashtagsHtml = storylineHashtags.length > 0 ? `
    <div class="flex items-center gap-2 flex-wrap pt-2">
      <span class="text-xs font-bold text-outline flex items-center gap-1 shrink-0">
        <span class="material-symbols-outlined text-[14px]">tag</span>
        <span>หัวข้อที่เกี่ยวข้อง:</span>
      </span>
      <div class="flex items-center gap-1.5 flex-wrap">
        ${storylineHashtags.map(tag => {
          const clean = tag.startsWith("#") ? tag.slice(1) : tag;
          return `
            <button type="button"
                    class="hero-hashtag-pill text-xs font-semibold px-2.5 py-0.5 rounded-md bg-surface-container hover:bg-purple-100 dark:hover:bg-purple-900/40 text-on-surface-variant hover:text-purple-700 dark:hover:text-purple-300 border border-outline-variant/30 transition-all cursor-pointer"
                    onclick="window.__filterByHashtag('${esc(clean)}')">
              #${esc(clean)}
            </button>
          `;
        }).join("")}
      </div>
    </div>
  ` : "";

  // Articles Grid
  const articlesGridHtml = filteredArticles.length > 0 ? `
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      ${filteredArticles.map((art, idx) => {
        const color = SOURCE_COLORS[art.source] ?? "#1a3a6b";
        const placeholder = getCategoryPlaceholder(art.category);
        const imgSrc = art.image_url || placeholder;
        const isBookmarked = Boolean(bookmarkedMap && bookmarkedMap[art.url]);
        const artJsonEncoded = encodeURIComponent(JSON.stringify(art));
        const perspective = getPerspectiveLabel(art.title, art.source, art.summary);

        return `
          <article class="storyline-card flex flex-col bg-white dark:bg-surface-container-low rounded-2xl border border-outline-variant/20 overflow-hidden shadow-xs hover:shadow-md transition-all group">
            <!-- Card Image -->
            <div class="relative w-full aspect-[16/10] overflow-hidden bg-surface-container-highest cursor-pointer"
                 onclick="window.__openPreview('${esc(art.url)}')">
              <img src="${esc(imgSrc)}" 
                   alt="${esc(art.title)}" 
                   class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                   onerror="this.onerror=null; this.src='${placeholder}';"
                   loading="lazy">
              <div class="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent"></div>
              
              <!-- Source Badge on Image -->
              <div class="absolute bottom-3 left-3 flex items-center gap-1.5 bg-black/75 backdrop-blur-md px-2.5 py-1 rounded-lg border border-white/20">
                <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
                <span class="text-[11px] font-bold text-white uppercase tracking-wider">${esc(art.source || "ข่าว")}</span>
              </div>

              <!-- Chronological Step Indicator -->
              <div class="absolute top-3 right-3 bg-black/60 backdrop-blur-md text-white/90 text-[10px] font-extrabold px-2 py-0.5 rounded-full border border-white/20">
                ลำดับ #${idx + 1}
              </div>
            </div>

            <!-- Card Content -->
            <div class="p-5 flex-1 flex flex-col space-y-2.5">
              <!-- Perspective & Badges -->
              <div class="flex items-center gap-1.5 flex-wrap">
                <span class="px-2 py-0.5 rounded-md bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 text-[10px] font-bold border border-purple-200 dark:border-purple-800/40 inline-flex items-center gap-1">
                  <span class="material-symbols-outlined text-[12px]">view_in_ar</span>
                  <span>${esc(perspective)}</span>
                </span>
                ${renderArticleBadges(art, false)}
              </div>

              <!-- Title -->
              <h3 class="font-headline font-bold text-base text-on-surface line-clamp-2 group-hover:text-primary transition-colors cursor-pointer leading-snug"
                  onclick="window.__openPreview('${esc(art.url)}')">
                ${esc(art.title)}
              </h3>

              <!-- Summary -->
              <p class="text-xs text-on-surface-variant line-clamp-3 leading-relaxed">
                ${esc(art.summary || "")}
              </p>

              <!-- Footer with time and actions -->
              <div class="pt-3 mt-auto border-t border-outline-variant/10 flex items-center justify-between gap-2">
                <span class="text-[10px] font-bold text-outline uppercase">${esc(art.fetched_at || "")}</span>
                <div class="flex items-center gap-1.5" onclick="event.stopPropagation()">
                  <button type="button"
                          class="h-7 w-7 flex items-center justify-center rounded-lg border border-outline-variant/30 ${isBookmarked ? 'bg-primary/10 text-primary border-primary/30' : 'text-on-surface-variant hover:text-primary hover:bg-surface-container'} active:scale-95 transition-all cursor-pointer"
                          onclick="window.__toggleArticleBookmark(event, '${artJsonEncoded}')"
                          title="${isBookmarked ? 'ลบบุ๊กมาร์ก' : 'บันทึกบทความ'}">
                    <span class="material-symbols-outlined text-[15px]" style="${isBookmarked ? "font-variation-settings: 'FILL' 1; color: #2e4d83;" : ""}">
                      ${isBookmarked ? 'bookmark' : 'bookmark_border'}
                    </span>
                  </button>

                  <button type="button"
                          class="h-7 px-2.5 flex items-center justify-center gap-1 bg-surface-container text-on-surface hover:bg-surface-container-high rounded-lg font-bold text-xs active:scale-95 transition-all cursor-pointer"
                          onclick="window.__openPreview('${esc(art.url)}')">
                    <span class="material-symbols-outlined text-[13px]">visibility</span>
                    <span>อ่านย่อ</span>
                  </button>

                  <button type="button"
                          class="h-7 px-2.5 flex items-center justify-center gap-1 bg-primary text-white hover:bg-primary-container rounded-lg font-bold text-xs shadow-2xs active:scale-95 transition-all cursor-pointer"
                          onclick="window.__openPreviewAndSummarize('${esc(art.url)}')">
                    <span class="material-symbols-outlined text-[13px]" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
                    <span>สรุป AI</span>
                  </button>
                </div>
              </div>
            </div>
          </article>
        `;
      }).join("")}
    </div>
  ` : `
    <div class="text-center py-16 bg-white dark:bg-surface-container-low rounded-2xl border border-outline-variant/20 p-8 space-y-3">
      <span class="material-symbols-outlined text-4xl text-outline">search_off</span>
      <p class="text-sm font-bold text-on-surface">ไม่พบบทความจากสำนักข่าว "${esc(activeSourceFilter)}" ในมหากาพย์นี้</p>
      <button class="px-4 py-1.5 bg-purple-600 text-white rounded-lg text-xs font-bold hover:bg-purple-700 transition-colors cursor-pointer"
              onclick="window.__filterStorylinePublisher('')">
        ดูข่าวจากทุกสำนักข่าว (${sortedArticles.length})
      </button>
    </div>
  `;

  container.innerHTML = `
    <!-- 1. Top Navigation Bar -->
    <div class="flex items-center justify-between gap-4 mb-6 sticky top-[72px] z-30 bg-surface/95 dark:bg-[#121316]/95 backdrop-blur py-3 border-b border-outline-variant/20">
      <button type="button"
              class="inline-flex items-center gap-2 px-4 py-2 bg-white dark:bg-surface-container hover:bg-surface-container-high text-on-surface rounded-xl text-sm font-bold transition-all active:scale-95 shadow-xs border border-outline-variant/30 cursor-pointer"
              onclick="window.__backFromStoryline()">
        <span class="material-symbols-outlined text-[18px]">arrow_back</span>
        <span>กลับสู่ฟีดรวมข่าว</span>
      </button>

      <div class="flex items-center gap-2 flex-wrap">
        <span class="px-3 py-1 rounded-full bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 text-xs font-bold border border-purple-200 dark:border-purple-800/50 flex items-center gap-1.5">
          <span class="material-symbols-outlined text-[15px]">schema</span>
          <span>มหากาพย์ประเด็นข่าว</span>
        </span>
        ${catObj ? `
          <span class="px-3 py-1 rounded-full text-xs font-bold border flex items-center gap-1" style="background:${catObj.bg}; color:${catObj.color}; border-color:${catObj.color}30;">
            <span>${catObj.icon}</span>
            <span>${catObj.label}</span>
          </span>
        ` : ""}
      </div>
    </div>

    <!-- 2. Storyline Header Hero Card -->
    <div class="mb-8 space-y-4">
      <div class="space-y-2">
        <h1 class="text-2xl sm:text-4xl font-headline font-extrabold text-on-surface leading-tight tracking-tight">
          ${esc(headline)}
        </h1>
        <div class="flex items-center gap-3 text-xs text-outline font-medium flex-wrap">
          <span class="flex items-center gap-1">
            <span class="material-symbols-outlined text-[14px]">newspaper</span>
            <span>ครอบคลุม ${outlets.length} สำนักข่าว</span>
          </span>
          <span>•</span>
          <span class="flex items-center gap-1">
            <span class="material-symbols-outlined text-[14px]">article</span>
            <span>ทั้งหมด ${sortedArticles.length} รายงานข่าว</span>
          </span>
          ${storyData.updated_at ? `
            <span>•</span>
            <span class="flex items-center gap-1">
              <span class="material-symbols-outlined text-[14px]">schedule</span>
              <span>อัปเดตล่าสุด ${esc(storyData.updated_at)}</span>
            </span>
          ` : ""}
        </div>
      </div>

      <!-- Synthesized Overview Box -->
      <div class="p-5 sm:p-6 rounded-2xl bg-gradient-to-br from-purple-50/80 via-white to-indigo-50/60 dark:from-purple-950/20 dark:via-surface-container-low dark:to-indigo-950/20 border border-purple-200/70 dark:border-purple-900/40 shadow-xs space-y-3">
        <div class="flex items-center justify-between gap-3 flex-wrap border-b border-purple-100 dark:border-purple-900/30 pb-3">
          <div class="flex items-center gap-2 text-purple-900 dark:text-purple-200 font-bold text-sm sm:text-base">
            <span class="material-symbols-outlined text-[20px] text-purple-600 dark:text-purple-400">auto_stories</span>
            <span>ภาพรวมสังเคราะห์ของประเด็น (Synthesized Overview)</span>
          </div>
          <button type="button"
                  id="storyline-ai-btn"
                  class="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white text-xs font-bold shadow-xs active:scale-95 transition-all cursor-pointer"
                  onclick="window.__runStorylineAiSummary('${esc(storyId)}')">
            <span class="material-symbols-outlined text-[15px]">auto_awesome</span>
            <span>สรุปภาพรวมประเด็นด้วย AI</span>
          </button>
        </div>

        <p class="text-sm sm:text-base text-on-surface leading-relaxed font-body">
          ${esc(storyData.summary || "ประมวลภาพรวมความคืบหน้าของเหตุการณ์จากทุกสำนักข่าว เพื่อให้เห็นทิศทางและการเปลี่ยนแปลงที่สำคัญ")}
        </p>

        <!-- Container for AI Summary when generated -->
        <div id="storyline-ai-section"></div>

        <!-- Consolidated Hashtags -->
        ${storylineHashtagsHtml}
      </div>
    </div>

    <!-- 3. Publisher Filter Strip -->
    <div class="mb-6 space-y-2">
      <div class="flex items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-purple-600 dark:text-purple-400 text-lg">filter_list</span>
          <h2 class="font-headline font-bold text-sm sm:text-base text-on-surface">กรองตามสำนักข่าวที่รายงาน</h2>
        </div>
        <span class="text-xs text-outline font-medium">
          แสดง ${filteredArticles.length} จาก ${sortedArticles.length} ข่าว
        </span>
      </div>

      <div class="flex items-center gap-2 overflow-x-auto pb-2 custom-scrollbar">
        ${publisherPillsHtml}
      </div>
    </div>

    <!-- 4. Chronological Articles Grid -->
    <div class="space-y-4">
      <div class="flex items-center justify-between gap-2 border-b border-outline-variant/15 pb-2">
        <h2 class="font-headline font-bold text-base sm:text-lg text-on-surface flex items-center gap-2">
          <span class="material-symbols-outlined text-primary text-xl">timeline</span>
          <span>บทความและลำดับเหตุการณ์ในมหากาพย์</span>
        </h2>
      </div>

      ${articlesGridHtml}
    </div>
  `;
}

