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

  let html = CATEGORIES.map(cat => {
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
    }, 3500);
  }
}

function stopHeroAutoPlay() {
  if (heroAutoPlayTimer) {
    clearInterval(heroAutoPlayTimer);
    heroAutoPlayTimer = null;
  }
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
  heroTrendingArticles = articles.slice(0, 7);
  heroBookmarkedMap = bookmarkedMap || {};
  heroCurrentIndex = 0;

  updateHeroTrendingSlide();
  startHeroAutoPlay();
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

  let rankBadge = "";
  if (rankNum === 1) {
    rankBadge = `
      <span class="px-3 py-1 rounded-lg bg-gradient-to-r from-rose-600 to-amber-600 text-white font-extrabold text-xs shadow-md flex items-center gap-1.5 animate-pulse">
        <span class="material-symbols-outlined text-[15px]">whatshot</span>
        <span>#1 HOT STORY</span>
      </span>
    `;
  } else if (rankNum === 2) {
    rankBadge = `
      <span class="px-3 py-1 rounded-lg bg-amber-600 text-white font-bold text-xs shadow-md flex items-center gap-1.5">
        <span class="material-symbols-outlined text-[15px]">local_fire_department</span>
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

  let multiSourcePill = "";
  if (n.cluster_sources && Array.isArray(n.cluster_sources) && n.cluster_sources.length > 1) {
    multiSourcePill = `
      <div class="flex items-center gap-1.5 text-xs text-white font-bold bg-black/70 backdrop-blur-md px-3 py-1.5 rounded-full border border-white/40 w-fit shadow-lg">
        <span class="material-symbols-outlined text-[15px] text-amber-400">hub</span>
        <span class="text-white">รายงานจาก ${n.cluster_sources.length} สำนักข่าว: <span class="text-amber-300 font-semibold">${esc(n.cluster_sources.join(", "))}</span></span>
      </div>
    `;
  } else if (n.cluster_size && n.cluster_size > 1) {
    multiSourcePill = `
      <div class="flex items-center gap-1.5 text-xs text-white font-bold bg-black/70 backdrop-blur-md px-3 py-1.5 rounded-full border border-white/40 w-fit shadow-lg">
        <span class="material-symbols-outlined text-[15px] text-amber-400">hub</span>
        <span class="text-white">ประเด็นตรงกัน ${n.cluster_size} สำนักข่าว</span>
      </div>
    `;
  }

  // Generate 7 indicator progress bars at the bottom with 3.5s animation only on the current slide
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

  container.innerHTML = `
    <!-- Header Title -->
    <div class="mb-3 flex items-center justify-between gap-4">
      <div class="flex items-center gap-2.5">
        <div class="w-7 h-7 rounded-lg bg-gradient-to-tr from-rose-500 to-amber-500 flex items-center justify-center text-white shadow-sm shrink-0">
          <span class="material-symbols-outlined text-[16px]" style="font-variation-settings: 'FILL' 1;">local_fire_department</span>
        </div>
        <div>
          <h2 class="font-headline font-extrabold text-base sm:text-lg lg:text-xl text-on-surface tracking-tight">เกาะติดประเด็นร้อน (Trending Highlights)</h2>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <span class="text-xs font-bold text-outline bg-surface-container px-3 py-1 rounded-full border border-outline-variant/30">
          อันดับ ${rankNum} / ${total}
        </span>
      </div>
    </div>

    <!-- Single Frame Modal/Banner Carousel -->
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
          <div class="flex items-center gap-2">
            ${rankBadge}
            <span class="px-2.5 py-1 rounded-lg bg-black/75 text-white backdrop-blur-md text-xs font-bold border border-white/30 shadow-md">
              🔥 Trending • ${scoreVal}
            </span>
          </div>
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full shadow-xs" style="background:${color}"></span>
            <span class="text-xs font-bold text-white uppercase tracking-wider drop-shadow-md">${esc(n.source)}</span>
          </div>
        </div>

        <!-- Bottom Content Row -->
        <div class="space-y-3 pointer-events-auto pb-4">
          <div class="space-y-2">
            ${multiSourcePill}
            <h1 class="text-lg sm:text-2xl md:text-3xl font-headline font-bold hero-headline leading-tight drop-shadow-lg group-hover:text-amber-200 transition-colors line-clamp-2 cursor-pointer"
                onclick="window.__openPreview('${esc(n.url)}')">
              ${esc(n.title)}
            </h1>
          </div>

          <div class="flex items-center justify-between gap-4 flex-wrap pt-2">
            <span class="text-xs font-bold text-white/90 uppercase tracking-wider drop-shadow-md">${esc(n.fetched_at || "")}</span>
            <div class="flex items-center gap-2" onclick="event.stopPropagation()">
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
                <span class="text-slate-900 font-bold">อ่านย่อ</span>
              </button>
              <button type="button" 
                      class="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-xl font-bold text-xs shadow-md active:scale-95 transition-all cursor-pointer border border-white/20" 
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
  const tickerContainer = document.getElementById("ticker-container");

  if (viewName === "preview") {
    if (feedView) feedView.classList.add("hidden");
    if (previewView) previewView.classList.remove("hidden");
    if (tickerContainer) tickerContainer.classList.add("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  } else {
    if (previewView) previewView.classList.add("hidden");
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

