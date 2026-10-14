/**
 * ui.js — DOM manipulation & rendering (Editorial Redesign v3.3)
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
  if (!dot || !label) return;
  if (connected) {
    dot.className = "w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse";
    label.className = "text-[10px] font-mono font-bold tracking-widest text-green-400 uppercase";
    label.textContent = "LIVE";
  } else {
    dot.className = "w-1.5 h-1.5 rounded-full bg-error";
    label.className = "text-[10px] font-mono font-bold tracking-widest text-error uppercase";
    label.textContent = "OFFLINE";
  }
}

// ── Stats bar ─────────────────────────────────────────────────────

export function updateStats({ total, newCount, updated }) {
  const totalEl = document.getElementById("stat-total");
  const newEl = document.getElementById("stat-new");
  const updatedEl = document.getElementById("updated-bar");
  if (total !== undefined && totalEl) totalEl.textContent = total;
  if (newCount !== undefined && newEl) newEl.textContent = newCount;
  if (updated !== undefined && updatedEl) updatedEl.textContent = `อัปเดต: ${updated}`;
}

// ── Category nav ──────────────────────────────────────────────────

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
        <span class="w-1.5 h-1.5 rounded-full shrink-0" style="background:${isActive ? '#ffffff' : color}"></span>
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

// ── Ticker ────────────────────────────────────────────────────────

export function updateTicker(titles) {
  if (!titles || !titles.length) return;
  const doubled = [...titles, ...titles];
  const track = document.getElementById("ticker-track");
  if (!track) return;
  track.innerHTML = doubled.map(t => `
    <div class="flex gap-6 items-center px-3 shrink-0">
      <span class="text-[11px] font-normal tracking-wide text-white/90">${esc(t)}</span>
      <span class="text-white/30 text-[10px]">•</span>
    </div>
  `).join("");
}

// ── Toast ─────────────────────────────────────────────────────────

export function showToast(msg) {
  const toast = document.getElementById("toast");
  const msgEl = document.getElementById("toast-msg");
  if (!toast || !msgEl) return;
  msgEl.textContent = msg;
  toast.classList.remove("translate-y-full", "opacity-0");
  toast.classList.add("translate-y-0", "opacity-100");
  setTimeout(() => hideToast(), 3000);
}

export function hideToast() {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.classList.remove("translate-y-0", "opacity-100");
  toast.classList.add("translate-y-full", "opacity-0");
}

// ── Classification Method Badge Helper ────────────────────────────

export function formatClassificationBadge(method) {
  if (!method) return "";

  const m = String(method);
  let label = m;

  if (m.startsWith("Category Cue")) {
    const match = m.match(/\((.*?)\)/);
    let cue = match ? match[1] : "Cue";
    if (cue.startsWith("http") || cue.startsWith("/")) {
      const parts = cue.split("/").filter(Boolean);
      cue = parts[parts.length - 1] || cue;
    }
    label = `CUE:${cue}`;
  } else if (m.startsWith("URL Priority") || m.startsWith("URL")) {
    const match = m.match(/\((.*?)\)/);
    const cue = match ? match[1] : "URL";
    label = `URL:${cue}`;
  } else if (m.startsWith("Hybrid:") || m.includes("WangchanBERTa")) {
    const confMatch = m.match(/conf=([\d.]+)/);
    const pct = confMatch ? ` ${Math.round(parseFloat(confMatch[1]) * 100)}%` : "";
    label = m.startsWith("Hybrid") ? `HYBRID${pct}` : `BERT${pct}`;
  } else if (m.startsWith("ML")) {
    const confMatch = m.match(/conf=([\d.]+)/);
    const pct = confMatch ? ` ${Math.round(parseFloat(confMatch[1]) * 100)}%` : "";
    label = `SVC${pct}`;
  } else if (m.startsWith("Rule")) {
    label = "RULE";
  } else {
    label = "AUTO";
  }

  return `
    <span class="editorial-tech-badge" title="วิธีจำแนกหมวดหมู่: ${esc(m)}">
      ${esc(label)}
    </span>
  `;
}

// ── Standardized Article Badges ───────────────────────────────────

export function renderArticleBadges(article, isNew = false) {
  if (!article) return "";
  const badges = [];

  if (article.is_breaking || (Array.isArray(article.badges) && article.badges.some(b => b.includes("Breaking") || b.includes("ด่วน")))) {
    badges.push(`<span class="editorial-badge editorial-badge-breaking">BREAKING</span>`);
  }

  const isTrending = article.is_trending || (article.trending_score && article.trending_score >= 4.5) || (article.cluster_count && article.cluster_count >= 2) || (article.cluster_size && article.cluster_size >= 2);
  if (isTrending) {
    const scoreText = (typeof article.trending_score === "number" && !isNaN(article.trending_score))
      ? ` ${article.trending_score.toFixed(1)}`
      : "";
    badges.push(`<span class="editorial-badge editorial-badge-trending" title="คะแนนความนิยม">TRENDING${scoreText}</span>`);
  }

  const sentConf = getSentimentConfig(article.sentiment);
  if (sentConf) {
    badges.push(`
      <span class="editorial-badge editorial-badge-neutral" title="ทิศทางอารมณ์ข่าว: ${sentConf.label}">
        ${esc(sentConf.label)}
      </span>
    `);
  }

  if (article.classification_method) {
    badges.push(formatClassificationBadge(article.classification_method));
  }

  if (isNew) {
    badges.push(`<span class="editorial-badge editorial-badge-new">NEW</span>`);
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
      ? `มีข่าวใหม่ ${count} บทความ • คลิกเพื่ออัปเดต`
      : `มีข่าวใหม่เข้ามา • คลิกเพื่ออัปเดต`;
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
    }, 5500);
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
      const outletSet = new Set(existing.outlets || existing.cluster_sources || []);
      (item.outlets || item.cluster_sources || [item.source]).filter(Boolean).forEach(o => outletSet.add(o));
      existing.outlets = Array.from(outletSet);
      existing.cluster_sources = existing.outlets;

      const existUrls = new Set((existing.articles || []).map(a => a.url));
      (item.articles || (item.url ? [item] : [])).forEach(a => {
        if (a && a.url && !existUrls.has(a.url)) {
          existUrls.add(a.url);
          if (!existing.articles) existing.articles = [];
          existing.articles.push(a);
        }
      });
      existing.article_count = (existing.articles || []).length;

      const tagSet = new Set(existing.hashtags || []);
      (item.hashtags || []).forEach(h => tagSet.add(h));
      existing.hashtags = Array.from(tagSet);

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

  heroTrendingArticles = deduped;
  heroBookmarkedMap = bookmarkedMap || {};
  heroCurrentIndex = 0;

  updateHeroTrendingSlide();
  startHeroAutoPlay();
}

export function getPerspectiveLabel(headline = "", outlet = "", summary = "") {
  const text = `${headline} ${summary} ${outlet}`.toLowerCase();
  if (text.includes("แบงก์ชาติ") || text.includes("ธปท") || text.includes("กนง") || text.includes("ดอกเบี้ย") || text.includes("เงินเฟ้อ")) {
    return "มุมมองนโยบายการเงิน / ธปท.";
  }
  if (text.includes("imf") || text.includes("world bank") || text.includes("ai") || text.includes("เอไอ") || text.includes("เทคโนโลยี")) {
    return "มุมมองเทคโนโลยี & สากล";
  }
  if (text.includes("หุ้น") || text.includes("ตลาดทุน") || text.includes("โบรก") || text.includes("การเงิน") || text.includes("ลงทุน")) {
    return "มุมมองตลาดทุน & การลงทุน";
  }
  if (text.includes("รัฐบาล") || text.includes("นายก") || text.includes("กระทรวง") || text.includes("การเมือง") || text.includes("พรรค")) {
    return "มุมมองนโยบาย & ภาครัฐ";
  }
  if (text.includes("ส่งออก") || text.includes("การค้า") || text.includes("พาณิชย์") || text.includes("ท่องเที่ยว")) {
    return "มุมมองภาคเศรษฐกิจจริง";
  }
  return `รายงานโดย ${outlet || "สำนักข่าว"}`;
}

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
    <div class="px-4 py-3 rounded-lg bg-white border border-outline-variant/50 flex items-center justify-between gap-3 flex-wrap shadow-2xs">
      <div class="flex items-center gap-3 min-w-0">
        <span class="px-2 py-0.5 rounded bg-[#141413] text-white font-mono text-[10px] font-bold uppercase tracking-wider shrink-0">ACTIVE FILTER</span>
        <span class="text-sm font-bold text-on-surface truncate" title="${esc(topicLabel)}">
          ${esc(topicLabel)}
        </span>
      </div>
      <button type="button" 
              class="flex items-center gap-1 px-3 py-1 rounded-md text-xs font-bold text-error hover:bg-error/10 transition-colors cursor-pointer shrink-0"
              onclick="window.__clearStorylineFilter()">
        <span class="material-symbols-outlined text-[15px]">close</span>
        <span>ล้างตัวกรอง</span>
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
  const color = SOURCE_COLORS[n.source] ?? "#1d3557";
  const jsonEncoded = encodeURIComponent(JSON.stringify(n));
  const scoreVal = (typeof n.trending_score === "number" && !isNaN(n.trending_score))
    ? n.trending_score.toFixed(1)
    : "9.8";

  // 1. Editorial Index Strip (Replaces the loud purple quick-switch strip)
  const quickSwitchStripHtml = heroTrendingArticles.length > 0 ? `
    <div class="editorial-index-strip mb-4"
         onmouseenter="window.__pauseTrendingAutoPlay()"
         onmouseleave="window.__resumeTrendingAutoPlay()">
      <div class="flex items-center gap-2 overflow-x-auto custom-scrollbar py-1">
        <span class="font-mono text-[10px] font-bold uppercase tracking-widest text-secondary shrink-0 pr-2 border-r border-outline-variant/50 flex items-center gap-1">
          <span class="w-1.5 h-1.5 rounded-full bg-secondary"></span>
          <span>LEAD STORIES</span>
        </span>
        ${heroTrendingArticles.map((art, idx) => {
          const isCurrent = idx === heroCurrentIndex;
          const rank = idx + 1;
          const titleShort = esc(art.headline || art.topic_title || art.title || `ประเด็น #${rank}`);
          const srcCount = art.child_events_count || (art.outlets ? art.outlets.length : (art.cluster_size || 1));
          
          return `
            <button type="button" 
                    class="editorial-index-pill ${isCurrent ? 'active' : ''}"
                    onclick="window.__goToTrendingSlide(${idx})"
                    title="${titleShort}">
              <span class="font-mono text-[10px] font-bold opacity-60">0${rank}</span>
              <span class="max-w-[160px] sm:max-w-[220px] truncate">${titleShort}</span>
              <span class="font-mono text-[9px] px-1.5 py-0.2 rounded bg-black/5 dark:bg-white/10 opacity-75">${srcCount} สื่อ</span>
            </button>
          `;
        }).join("")}
      </div>
    </div>
  ` : "";

  // 2. Publisher Outlets
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

  const publisherPillsHtml = Array.from(outletMap.entries()).slice(0, 6).map(([outlet, arts]) => {
    const brandColor = SOURCE_COLORS[outlet] ?? "#6366f1";
    const count = arts.length;
    return `
      <button type="button"
              class="hero-publisher-pill inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-white/10 hover:bg-white/20 text-white border border-white/20 backdrop-blur-md text-[11px] font-medium transition-all cursor-pointer shrink-0"
              onclick="event.stopPropagation(); window.__openOutletArticle('${esc(outlet)}')"
              title="คลิกอ่านรายงานจาก ${esc(outlet)}">
        <span class="w-2 h-2 rounded-full shrink-0" style="background:${brandColor}"></span>
        <span>${esc(outlet)}</span>
        ${count > 0 ? `<span class="font-mono text-[10px] opacity-75">(${count})</span>` : ""}
      </button>
    `;
  }).join("");

  // 3. Storyline Hashtags
  const storylineHashtags = Array.from(new Set([
    ...(Array.isArray(n.hashtags) ? n.hashtags : []),
    ...((n.child_events || []).flatMap(ce => Array.isArray(ce.hashtags) ? ce.hashtags : [])),
    ...((n.articles || []).flatMap(a => Array.isArray(a.hashtags) ? a.hashtags : [])),
  ])).filter(Boolean).slice(0, 6);

  const storylineHashtagsHtml = storylineHashtags.length > 0 ? `
    <div class="flex items-center gap-1.5 flex-wrap">
      ${storylineHashtags.map(tag => {
        const clean = tag.startsWith("#") ? tag.slice(1) : tag;
        return `
          <button type="button"
                  class="text-[11px] font-mono text-white/80 hover:text-white bg-black/40 hover:bg-black/70 border border-white/15 px-2.5 py-0.5 rounded transition-colors cursor-pointer"
                  onclick="event.stopPropagation(); window.__filterByHashtag('${esc(clean)}')">
            #${esc(clean)}
          </button>
        `;
      }).join("")}
    </div>
  ` : "";

  // 4. Progress Indicators
  const indicatorsHtml = heroTrendingArticles.map((_, idx) => {
    const isCurrent = idx === heroCurrentIndex;
    return `
      <button type="button" 
              class="hero-progress-segment ${isCurrent ? 'hero-progress-segment-active' : ''}" 
              onclick="window.__goToTrendingSlide(${idx})" 
              title="ข่าวเด่นลำดับที่ ${idx + 1}">
        ${isCurrent ? '<div class="hero-progress-bar-fill hero-progress-active"></div>' : ''}
      </button>
    `;
  }).join("");

  container.innerHTML = `
    ${quickSwitchStripHtml}

    <div class="hero-carousel-container group"
         onmouseenter="window.__pauseTrendingAutoPlay()"
         onmouseleave="window.__resumeTrendingAutoPlay()">
      
      <img src="${esc(imgSrc)}" 
           alt="${esc(n.title)}" 
           class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700 cursor-pointer"
           onclick="window.__openPreview('${esc(n.url)}')"
           onerror="this.onerror=null; this.src='${getCategoryPlaceholder(n.category)}';" 
           loading="eager" />

      <button type="button" class="hero-nav-btn hero-nav-btn-left" onclick="window.__prevTrendingSlide(event)" title="ก่อนหน้า">
        <span class="material-symbols-outlined text-[22px]">chevron_left</span>
      </button>
      <button type="button" class="hero-nav-btn hero-nav-btn-right" onclick="window.__nextTrendingSlide(event)" title="ถัดไป">
        <span class="material-symbols-outlined text-[22px]">chevron_right</span>
      </button>

      <div class="hero-gradient-overlay">
        <!-- Top Telemetry Row -->
        <div class="flex items-center justify-between gap-2 pointer-events-auto">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="px-2.5 py-1 rounded bg-[#c84b31] text-white font-mono font-bold text-[10px] tracking-widest uppercase">
              FEATURED #0${rankNum}
            </span>
            <span class="px-2.5 py-1 rounded bg-black/60 text-white/90 backdrop-blur-md font-mono text-[10px] border border-white/20">
              IMPACT SCORE ${scoreVal}
            </span>
          </div>
          <div class="flex items-center gap-2 bg-black/60 backdrop-blur-md px-3 py-1 rounded border border-white/20">
            <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
            <span class="text-[11px] font-mono font-bold text-white uppercase tracking-wider">${esc(n.source || (n.outlets && n.outlets[0]) || "MULTI-SOURCE")}</span>
          </div>
        </div>

        <!-- Bottom Editorial Feature Content -->
        <div class="space-y-3 pointer-events-auto pb-3 max-w-4xl">
          <div class="space-y-2">
            <h1 class="text-xl sm:text-3xl md:text-4xl font-headline font-bold hero-headline leading-tight cursor-pointer hover:underline decoration-white/40 underline-offset-4 line-clamp-2"
                onclick="window.__openPreview('${esc(n.url)}')">
              ${esc(n.title)}
            </h1>

            ${n.summary ? `
              <p class="text-xs sm:text-sm text-white/85 line-clamp-2 leading-relaxed hidden sm:block font-body max-w-3xl cursor-pointer"
                 onclick="window.__openPreview('${esc(n.url)}')">
                ${esc(n.summary)}
              </p>
            ` : ""}

            <div class="flex items-center gap-3 flex-wrap pt-1">
              ${publisherPillsHtml}
              ${storylineHashtagsHtml}
            </div>
          </div>

          <div class="flex items-center justify-between gap-4 flex-wrap pt-2 border-t border-white/15">
            <span class="text-[11px] font-mono text-white/70 uppercase tracking-wider">${esc(n.fetched_at || "")} • STORY 0${rankNum}/0${total}</span>
            <div class="flex items-center gap-2 flex-wrap" onclick="event.stopPropagation()">
              <button type="button" 
                      class="p-2 rounded-lg border border-white/30 bg-black/50 text-white hover:bg-white hover:text-black transition-colors cursor-pointer"
                      onclick="window.__toggleArticleBookmark(event, '${jsonEncoded}')" 
                      title="${isBookmarked ? 'ลบบุ๊กมาร์ก' : 'บันทึกบทความ'}">
                <span class="material-symbols-outlined text-[17px]" style="${isBookmarked ? "font-variation-settings: 'FILL' 1; color: #f59e0b;" : ""}">
                  ${isBookmarked ? 'bookmark' : 'bookmark_border'}
                </span>
              </button>
              <button type="button" 
                      class="flex items-center gap-1.5 bg-white text-[#141413] hover:bg-white/90 px-3.5 py-2 rounded-lg font-bold text-xs transition-all cursor-pointer" 
                      onclick="window.__openPreview('${esc(n.url)}')">
                <span class="material-symbols-outlined text-[15px]">article</span>
                <span>อ่านบทคัดย่อ</span>
              </button>
              <button type="button" 
                      class="flex items-center gap-1.5 bg-black/65 hover:bg-black/85 text-white px-3.5 py-2 rounded-lg font-bold text-xs border border-white/30 backdrop-blur-md transition-all cursor-pointer" 
                      onclick="window.__openCurrentHeroStoryline()">
                <span class="material-symbols-outlined text-[15px]">account_tree</span>
                <span>เจาะลึกประเด็น (${outletMap.size} สื่อ)</span>
              </button>
              <button type="button" 
                      class="flex items-center gap-1.5 bg-[#c84b31] hover:opacity-95 text-white px-3.5 py-2 rounded-lg font-bold text-xs transition-all cursor-pointer" 
                      onclick="window.__openPreviewAndSummarize('${esc(n.url)}')">
                <span class="material-symbols-outlined text-[15px]" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
                <span>สรุป AI</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="hero-progress-container">
        ${indicatorsHtml}
      </div>
    </div>
  `;
}

// Safe stubs for legacy timeline/subevent toggles
window.__toggleTimelinePanel = () => {};
window.__togglePerspectiveQuote = () => {};
window.__scrollToStoryTimeline = () => {};
window.__scrollToSubEvents = () => {};
window.__scrollToSubEvent = () => {};
window.__toggleSubEventArticles = () => {};

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

window.__pauseTrendingAutoPlay = () => stopHeroAutoPlay();
window.__resumeTrendingAutoPlay = () => startHeroAutoPlay();

// ── News grid (Clean Editorial Cards without duplicate source tags) ──

export function renderGrid(articles, newUrlSet = new Set(), bookmarkedMap = {}) {
  const grid = document.getElementById("news-grid");
  if (!grid) return;

  if (!articles || !articles.length) {
    grid.innerHTML = `<div class="col-span-full text-center py-20 text-outline font-headline italic text-lg">ไม่พบบทความในหมวดหมู่ หรือคำค้นหานี้</div>`;
    return;
  }

  grid.innerHTML = articles.map((n, i) => {
    const isNew = newUrlSet && newUrlSet.has(n.url);
    const isBookmarked = Boolean(bookmarkedMap && bookmarkedMap[n.url]);
    const color = SOURCE_COLORS[n.source] ?? "#1d3557";
    const placeholder = getCategoryPlaceholder(n.category);
    const imgSrc = n.image_url || placeholder;
    const articleJsonEncoded = encodeURIComponent(JSON.stringify(n));
    const catObj = getCategoryById(n.category);

    return `
      <article class="editorial-card group" style="animation: fadeUp 0.35s ease-out ${Math.min(i * 0.03, 0.4)}s both;">
        <div class="flex flex-col flex-1 cursor-pointer" data-url="${esc(n.url)}" onclick="window.__openPreview(this.dataset.url)">
          <!-- Card Thumbnail -->
          <div class="aspect-[16/10] overflow-hidden relative shrink-0 bg-surface-container-low border-b border-outline-variant/25">
            <img alt="thumbnail" class="object-cover w-full h-full transition-transform duration-500 group-hover:scale-105" src="${esc(imgSrc)}" onerror="this.onerror=null; this.src='${placeholder}';" loading="lazy" />
            ${catObj && catObj.id !== "all" ? `
              <span class="absolute top-2.5 left-2.5 text-[10px] font-mono font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-black/70 text-white backdrop-blur-xs">
                ${esc(catObj.label)}
              </span>
            ` : ""}
          </div>

          <!-- Card Content -->
          <div class="p-4 sm:p-5 flex flex-col flex-1">
            <!-- Dateline: Source & Badges (Single clean row) -->
            <div class="flex items-center justify-between gap-2 mb-2.5">
              <div class="flex items-center gap-1.5 min-w-0">
                <span class="w-2 h-2 rounded-full shrink-0" style="background:${color}"></span>
                <span class="text-[11px] font-mono font-bold text-on-surface-variant uppercase tracking-wider truncate">${esc(n.source)}</span>
              </div>
              <div class="flex items-center gap-1 shrink-0 flex-wrap justify-end">
                ${renderArticleBadges(n, isNew)}
              </div>
            </div>

            <!-- Headline -->
            <h2 class="text-[17px] sm:text-[18px] font-headline font-bold text-on-surface leading-snug transition-colors group-hover:text-primary line-clamp-3 mb-2">
              ${esc(n.title)}
            </h2>

            ${n.summary ? `
              <p class="text-xs text-on-surface-variant line-clamp-2 leading-relaxed mt-auto pt-1">
                ${esc(n.summary)}
              </p>
            ` : ""}
          </div>
        </div>

        <!-- Card Footer Actions -->
        <div class="px-4 sm:px-5 py-3 mt-auto border-t border-outline-variant/25 flex items-center justify-between gap-2 bg-surface/40">
          <span class="text-[10px] font-mono text-outline uppercase truncate">${esc(n.fetched_at ?? "")}</span>
          <div class="flex items-center gap-1 shrink-0" onclick="event.stopPropagation()">
            ${n.url ? `
            <button type="button"
                    class="editorial-card-icon-btn ${isBookmarked ? 'active' : ''}"
                    onclick="window.__toggleArticleBookmark(event, '${articleJsonEncoded}')"
                    title="${isBookmarked ? 'ลบบุ๊กมาร์ก' : 'บันทึกบทความ'}">
              <span class="material-symbols-outlined text-[16px]" style="${isBookmarked ? "font-variation-settings: 'FILL' 1;" : ""}">
                ${isBookmarked ? 'bookmark' : 'bookmark_border'}
              </span>
            </button>` : ""}

            ${n.url ? `
            <button type="button"
                    class="editorial-card-icon-btn"
                    onclick="window.__showLessLikeThis(event, '${articleJsonEncoded}')"
                    title="แสดงเนื้อหาแบบนี้ให้น้อยลง">
              <span class="material-symbols-outlined text-[15px]">visibility_off</span>
            </button>` : ""}

            <button type="button" 
                    class="editorial-card-action-btn"
                    data-url="${esc(n.url)}"
                    onclick="window.__openPreview(this.dataset.url)"
                    title="อ่านบทคัดย่อ">
              <span>อ่านย่อ</span>
            </button>

            <button type="button" 
                    class="editorial-card-ai-btn"
                    data-url="${esc(n.url)}"
                    onclick="window.__openPreviewAndSummarize(this.dataset.url)"
                    title="สรุปประเด็นด้วย AI">
              <span class="material-symbols-outlined text-[13px]" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
              <span>AI</span>
            </button>
          </div>
        </div>
      </article>
    `;
  }).join("");
}

export function showGridLoading() {
  const grid = document.getElementById("news-grid");
  if (!grid) return;
  grid.innerHTML = `
    <div class="col-span-full text-center py-20 flex flex-col items-center justify-center opacity-60">
      <svg class="animate-spin h-8 w-8 text-primary mb-4" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"></circle>
        <path class="opacity-80" d="M12 2a10 10 0 0110 10" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="2"></path>
      </svg>
      <span class="font-headline italic text-base text-on-surface-variant">กำลังโหลดบทความ...</span>
    </div>
  `;
}

export function showGridError(msg = "ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ได้") {
  const grid = document.getElementById("news-grid");
  if (!grid) return;
  grid.innerHTML = `
    <div class="col-span-full text-center py-20 flex flex-col items-center justify-center">
      <span class="material-symbols-outlined text-error text-3xl mb-2">error</span>
      <span class="text-error text-sm font-medium">${esc(msg)}</span>
    </div>
  `;
}

// ── Pagination ────────────────────────────────────────────────────

export function renderPagination(meta) {
  const pg = document.getElementById("pagination");
  if (!pg) return;
  const { page, total_pages: totalPages, total } = meta;

  if (totalPages <= 1) { pg.innerHTML = ""; return; }

  const btn = (p, label, disabled = false, active = false) => {
    return `<button class="editorial-page-btn ${active ? 'active' : ''}"
           onclick="__loadPage(${p})"
           ${disabled ? "disabled" : ""}>${label}</button>`;
  };

  let html = btn(page - 1, "‹", page <= 1);
  const start = Math.max(1, page - 2);
  const end   = Math.min(totalPages, start + 4);

  if (start > 1) html += btn(1, "1") + `<span class="px-2 text-outline font-mono text-xs">…</span>`;
  for (let p = start; p <= end; p++) html += btn(p, p, false, p === page);
  if (end < totalPages) html += `<span class="px-2 text-outline font-mono text-xs">…</span>` + btn(totalPages, totalPages);

  html += btn(page + 1, "›", page >= totalPages);
  html += `<span class="ml-4 text-[11px] font-mono text-outline uppercase tracking-widest hidden sm:inline">TOTAL ${total} STORIES</span>`;

  pg.innerHTML = html;
}

// ── Summary Modal ─────────────────────────────────────────────────

export function openModal() {
  const modal = document.getElementById("summary-modal");
  const content = document.getElementById("modal-content-wrap");
  if (!modal || !content) return;
  
  modal.classList.remove("opacity-0", "pointer-events-none");
  modal.classList.add("opacity-100", "pointer-events-auto");
  
  setTimeout(() => {
    content.classList.remove("translate-y-4", "scale-95");
    content.classList.add("translate-y-0", "scale-100");
  }, 10);
  
  document.body.style.overflow = "hidden";
}

export function closeModal() {
  const modal = document.getElementById("summary-modal");
  const content = document.getElementById("modal-content-wrap");
  if (!modal || !content) return;
  
  content.classList.remove("translate-y-0", "scale-100");
  content.classList.add("translate-y-4", "scale-95");
  
  setTimeout(() => {
    modal.classList.remove("opacity-100", "pointer-events-auto");
    modal.classList.add("opacity-0", "pointer-events-none");
    document.body.style.overflow = "";
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

  const bullets = (s.bullets ?? []).map((b, i) => `
    <li class="takeaways-item flex items-start gap-3.5">
      <span class="font-mono text-xs font-bold text-secondary mt-1 shrink-0">0${i+1}</span>
      <span class="text-on-surface leading-relaxed">${esc(b)}</span>
    </li>
  `).join("");
  
  const keywords = (s.keywords ?? []).map(k => `
    <span class="px-2.5 py-1 bg-surface-container text-on-surface-variant font-mono text-[10px] font-bold uppercase tracking-wider rounded border border-outline-variant/40">#${esc(k)}</span>
  `).join("");

  result.innerHTML = `
    <header class="space-y-3 border-b border-outline-variant/30 pb-5">
      <div class="flex items-center justify-between flex-wrap gap-2">
        <div class="flex items-center gap-2 flex-wrap">
          ${s.category ? `<span class="px-2.5 py-0.5 bg-[#141413] text-white font-mono text-[10px] font-bold uppercase tracking-widest rounded">${esc(s.category)}</span>` : ""}
          ${formatClassificationBadge(s.classification_method)}
        </div>
        ${s.sentiment ? `
        <div class="font-mono text-[10px] font-bold uppercase tracking-widest">
          <span class="text-outline">TONE:</span>
          <span class="text-on-surface">${esc(s.sentiment)}</span>
        </div>` : ""}
      </div>
      <h1 class="summary-title font-headline text-on-surface">
        ${esc(s.title ?? "ไม่มีหัวข้อ")}
      </h1>
    </header>

    <section class="my-6 pl-4 border-l-2 border-secondary">
      <p class="summary-lead text-on-surface">
        ${esc(s.summary ?? "")}
      </p>
    </section>

    ${bullets ? `
    <section class="takeaways-card bg-white border border-outline-variant/40">
      <h3 class="takeaways-title font-mono uppercase text-on-surface flex items-center gap-2">
        <span class="material-symbols-outlined text-[16px]">format_list_bulleted</span>
        <span>KEY TAKEAWAYS (ประเด็นสำคัญ)</span>
      </h3>
      <ul class="takeaways-list flex flex-col">
        ${bullets}
      </ul>
    </section>
    ` : ""}

    ${keywords ? `<section class="pt-2 flex flex-wrap gap-1.5">${keywords}</section>` : ""}

    <footer class="mt-8 pt-5 border-t border-outline-variant/30 flex flex-wrap justify-between items-center gap-4 font-mono text-[10px] text-outline uppercase tracking-widest">
      <span>SYNTHESIZED AT ${new Date().toLocaleTimeString()}</span>
      ${originalUrl ? `
      <a href="${esc(originalUrl)}" target="_blank" rel="noopener noreferrer"
         class="inline-flex items-center gap-1.5 px-4 py-2 bg-[#141413] text-white rounded-lg text-xs font-body font-bold hover:opacity-90 transition-opacity normal-case tracking-normal">
        <span>อ่านบทความต้นฉบับ</span>
        <span class="material-symbols-outlined text-[15px]">open_in_new</span>
      </a>` : ""}
    </footer>
  `;
}

export function showModalError(msg) {
  document.getElementById("summary-loading").style.display = "none";
  const result = document.getElementById("summary-result");
  result.style.display = "block";
  result.innerHTML = `
    <div class="flex flex-col items-center justify-center py-12 text-center">
      <span class="material-symbols-outlined text-3xl text-error mb-3">error</span>
      <h3 class="font-headline text-xl font-bold text-on-surface mb-1">ไม่สามารถสร้างบทสรุปได้</h3>
      <p class="text-xs text-outline max-w-md mx-auto">${esc(msg)}</p>
    </div>`;
}

// ── PWA View Switching ────────────────────────────────────────────

export function switchView(viewName = "feed") {
  const feedView = document.getElementById("feed-view");
  const previewView = document.getElementById("preview-view");
  const storylineView = document.getElementById("storyline-view");

  if (viewName === "preview") {
    if (feedView) feedView.classList.add("hidden");
    if (storylineView) storylineView.classList.add("hidden");
    if (previewView) previewView.classList.remove("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  } else if (viewName === "storyline") {
    if (feedView) feedView.classList.add("hidden");
    if (previewView) previewView.classList.add("hidden");
    if (storylineView) storylineView.classList.remove("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  } else {
    if (previewView) previewView.classList.add("hidden");
    if (storylineView) storylineView.classList.add("hidden");
    if (feedView) feedView.classList.remove("hidden");
  }
}

// ── Preview Sub-View Rendering ────────────────────────────────────

export function renderInlineSummary(summary) {
  const s = summary;
  const bullets = (s.bullets ?? []).map((b, i) => `
    <li class="flex items-start gap-3 text-sm leading-relaxed text-on-surface">
      <span class="font-mono text-xs font-bold text-secondary mt-0.5 shrink-0">0${i+1}.</span>
      <span>${esc(b)}</span>
    </li>
  `).join("");

  const keywords = (s.keywords ?? []).map(k => `
    <span class="px-2 py-0.5 bg-surface-container text-on-surface-variant font-mono text-[10px] font-semibold rounded">#${esc(k)}</span>
  `).join("");

  return `
    <div class="p-6 bg-surface-container-low/60 rounded-xl border border-outline-variant/50 space-y-4 animate-fade-in">
      <div class="flex items-center justify-between flex-wrap gap-2 border-b border-outline-variant/30 pb-3">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-secondary text-[18px]" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
          <h3 class="font-headline font-bold text-base text-on-surface">บทสังเคราะห์ประเด็นสำคัญโดย AI</h3>
        </div>
        ${s.sentiment ? `
          <span class="font-mono text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded bg-white border border-outline-variant/40 text-on-surface">
            TONE: ${esc(s.sentiment)}
          </span>
        ` : ""}
      </div>

      ${s.summary ? `<p class="text-sm text-on-surface leading-relaxed">${esc(s.summary)}</p>` : ""}

      ${bullets ? `
        <div class="space-y-2 pt-2">
          <h4 class="font-mono text-[10px] font-bold uppercase tracking-widest text-outline">KEY TAKEAWAYS</h4>
          <ul class="space-y-2">${bullets}</ul>
        </div>
      ` : ""}

      ${keywords ? `<div class="flex flex-wrap gap-1.5 pt-2">${keywords}</div>` : ""}
    </div>
  `;
}

export function showInlineSummaryLoading() {
  const section = document.getElementById("preview-ai-section");
  if (!section) return;
  section.innerHTML = `
    <div class="p-8 bg-surface-container-low/50 rounded-xl border border-outline-variant/40 text-center space-y-2">
      <svg class="animate-spin h-6 w-6 text-primary mx-auto" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2.5"></circle>
        <path class="opacity-80" d="M12 2a10 10 0 0110 10" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="2.5"></path>
      </svg>
      <p class="text-xs font-bold text-on-surface">AI กำลังอ่านและสังเคราะห์ประเด็นสำคัญ...</p>
    </div>
  `;
}

export function showInlineSummaryError(msg, articleUrl) {
  const section = document.getElementById("preview-ai-section");
  if (!section) return;
  section.innerHTML = `
    <div class="p-5 bg-error/5 border border-error/20 rounded-xl text-center space-y-2">
      <p class="text-xs text-error font-bold">${esc(msg)}</p>
      <button class="px-3.5 py-1.5 bg-[#141413] text-white rounded-lg text-xs font-bold"
              onclick="window.__runPreviewAiSummary('${esc(articleUrl)}')">
        ลองใหม่อีกครั้ง
      </button>
    </div>
  `;
}

export function renderPreviewView(article, isBookmarked = false, cachedSummary = null) {
  const preview = document.getElementById("preview-view");
  if (!preview) return;

  const color = SOURCE_COLORS[article.source] ?? "#1d3557";
  const placeholder = getCategoryPlaceholder(article.category);
  const imgSrc = article.image_url || placeholder;
  const articleJsonEncoded = encodeURIComponent(JSON.stringify(article));

  const textLen = (article.summary || "").length + (article.title || "").length;
  const readMins = Math.max(1, Math.round(textLen / 250));

  preview.innerHTML = `
    <div class="flex items-center justify-between gap-4 mb-6 sticky top-[57px] z-30 bg-surface/95 backdrop-blur py-3 border-b border-outline-variant/30">
      <button class="inline-flex items-center gap-2 px-3.5 py-1.5 bg-white hover:bg-surface-container text-on-surface rounded-lg text-xs font-bold transition-colors border border-outline-variant/40 cursor-pointer"
              onclick="window.__backToFeed()">
        <span class="material-symbols-outlined text-[16px]">arrow_back</span>
        <span>กลับหน้ารวมข่าว</span>
      </button>

      <div class="flex items-center gap-2">
        <button class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-outline-variant/40 ${isBookmarked ? 'bg-[#141413] text-white' : 'bg-white text-on-surface hover:bg-surface-container'} text-xs font-bold transition-colors cursor-pointer"
                onclick="window.__toggleArticleBookmark(event, '${articleJsonEncoded}')">
          <span class="material-symbols-outlined text-[16px]" style="${isBookmarked ? "font-variation-settings: 'FILL' 1;" : ""}">
            ${isBookmarked ? 'bookmark' : 'bookmark_border'}
          </span>
          <span>${isBookmarked ? 'บันทึกแล้ว' : 'บันทึก'}</span>
        </button>

        <button class="p-1.5 bg-white hover:bg-surface-container text-on-surface rounded-lg border border-outline-variant/40 transition-colors cursor-pointer"
                onclick="window.__shareArticle('${esc(article.title)}', '${esc(article.url)}')"
                title="แชร์บทความ">
          <span class="material-symbols-outlined text-[16px]">share</span>
        </button>
      </div>
    </div>

    <article class="bg-white rounded-xl border border-outline-variant/40 overflow-hidden shadow-xs">
      <div class="p-6 sm:p-10 space-y-6">
        <!-- Editorial Dateline -->
        <div class="flex items-center justify-between flex-wrap gap-2 text-xs border-b border-outline-variant/25 pb-4">
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full" style="background:${color}"></span>
            <span class="font-mono font-bold uppercase tracking-wider text-on-surface">${esc(article.source)}</span>
            ${article.category ? `<span class="text-outline">•</span><span class="font-mono uppercase text-outline">${esc(article.category)}</span>` : ""}
          </div>
          <span class="font-mono text-[11px] text-outline">${esc(article.fetched_at || "ล่าสุด")} • อ่าน ~${readMins} นาที</span>
        </div>

        <!-- Headline -->
        <h1 class="text-2xl sm:text-3xl md:text-4xl font-headline font-bold text-on-surface leading-tight">
          ${esc(article.title)}
        </h1>

        <!-- Featured Image -->
        <div class="relative w-full aspect-[16/9] bg-surface-container-low rounded-lg overflow-hidden border border-outline-variant/20">
          <img src="${esc(imgSrc)}" 
               alt="${esc(article.title)}" 
               class="w-full h-full object-cover"
               onerror="this.onerror=null; this.src='${placeholder}';"
               loading="eager" />
        </div>

        <!-- Lead Excerpt -->
        <div class="pl-4 border-l-2 border-[#141413] space-y-1.5">
          <span class="font-mono text-[10px] font-bold uppercase tracking-widest text-outline block">ABSTRACT / SNIPPET</span>
          <p class="text-base text-on-surface leading-relaxed">
            ${esc(article.summary || "ไม่มีบทคัดย่อสำหรับข่าวนี้ สามารถกดอ่านรายละเอียดฉบับเต็มได้ที่เว็บไซต์ต้นทางด้านล่าง")}
          </p>
        </div>

        <!-- AI Summary Section -->
        <div id="preview-ai-section" class="pt-2">
          ${cachedSummary ? renderInlineSummary(cachedSummary) : `
            <div class="p-6 bg-surface-container-low/50 rounded-xl border border-outline-variant/40 flex flex-col sm:flex-row items-center justify-between gap-4">
              <div class="space-y-1 text-center sm:text-left">
                <h3 class="font-headline font-bold text-base text-on-surface flex items-center justify-center sm:justify-start gap-1.5">
                  <span class="material-symbols-outlined text-secondary text-[18px]" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
                  <span>ต้องการสรุปประเด็นสำคัญด้วย AI หรือไม่?</span>
                </h3>
                <p class="text-xs text-on-surface-variant">สังเคราะห์ใจความหลัก ดึง Key Takeaways และวิเคราะห์โทนของข่าวทันที</p>
              </div>
              <button class="shrink-0 inline-flex items-center gap-2 px-5 py-2.5 bg-[#141413] text-white text-xs font-bold rounded-lg hover:opacity-90 transition-opacity cursor-pointer"
                      onclick="window.__runPreviewAiSummary('${esc(article.url)}')">
                <span class="material-symbols-outlined text-[16px]">auto_awesome</span>
                <span>สังเคราะห์ด้วย AI</span>
              </button>
            </div>
          `}
        </div>

        <!-- External Source Footer -->
        <div class="pt-6 border-t border-outline-variant/30 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div class="text-[11px] font-mono text-outline flex items-center gap-1.5">
            <span class="material-symbols-outlined text-emerald-700 text-[16px]">verified_user</span>
            <span>CLEAN LINK • ปราศจาก Tracking Parameter</span>
          </div>

          <button class="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-primary hover:bg-primary-container text-white font-bold text-xs rounded-lg transition-colors cursor-pointer"
                  onclick="window.__openExternalSourceClean('${esc(article.url)}')">
            <span>อ่านฉบับเต็มที่ ${esc(article.source || 'เว็บต้นทาง')}</span>
            <span class="material-symbols-outlined text-[16px]">open_in_new</span>
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

export function showPwaInstallBanner(onInstall) {
  const banner = document.getElementById("pwa-install-banner");
  const installBtn = document.getElementById("pwa-install-btn");
  if (!banner) return;
  if (installBtn && onInstall) installBtn.onclick = onInstall;
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
        <span class="material-symbols-outlined text-3xl mb-2">${type === 'history' ? 'history_toggle_off' : 'bookmarks'}</span>
        <p class="text-xs font-medium">ยังไม่มีรายการ${type === 'history' ? 'ประวัติการอ่าน' : 'ที่บันทึกไว้'}</p>
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
      <div class="flex items-center gap-3.5 p-3 bg-white hover:bg-surface-container-low rounded-lg border border-outline-variant/30 transition-colors cursor-pointer group"
           onclick="window.__closeHistoryModal(); window.__openPreview('${esc(item.url)}')">
        <div class="w-16 h-14 rounded overflow-hidden bg-surface-container shrink-0">
          <img src="${esc(imgSrc)}" alt="thumb" class="w-full h-full object-cover" onerror="this.onerror=null; this.src='${placeholder}';" loading="lazy">
        </div>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 font-mono text-[10px] text-outline uppercase mb-0.5">
            <span class="text-on-surface font-bold">${esc(item.source || "")}</span>
            <span>• ${esc(item.viewed_at || item.fetched_at || "")}</span>
          </div>
          <h4 class="text-xs font-bold text-on-surface line-clamp-1 group-hover:text-primary transition-colors">${esc(item.title)}</h4>
        </div>
        <div class="shrink-0" onclick="event.stopPropagation()">
          <button class="p-1.5 text-outline hover:text-on-surface rounded-lg"
                  onclick="window.__toggleArticleBookmark(event, '${itemEncoded}')">
            <span class="material-symbols-outlined text-[18px]" style="${isBookmarked ? "font-variation-settings: 'FILL' 1; color: #141413;" : ""}">
              ${isBookmarked ? 'bookmark' : 'bookmark_border'}
            </span>
          </button>
        </div>
      </div>
    `;
  }).join("");
}

// ── Dedicated Storyline View (Executive Dossier Style) ────────────

export function showStorylineLoading() {
  const container = document.getElementById("storyline-view");
  if (!container) return;
  container.innerHTML = `
    <div class="py-24 text-center flex flex-col items-center justify-center space-y-3">
      <svg class="animate-spin h-8 w-8 text-primary" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2.5"></circle>
        <path class="opacity-80" d="M12 2a10 10 0 0110 10" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="2.5"></path>
      </svg>
      <p class="font-headline italic text-base text-on-surface">กำลังรวบรวมแฟ้มประเด็นข่าวจากทุกสำนัก...</p>
    </div>
  `;
}

export function showStorylineError(msg = "ไม่สามารถโหลดข้อมูลประเด็นข่าวนี้ได้") {
  const container = document.getElementById("storyline-view");
  if (!container) return;
  container.innerHTML = `
    <div class="max-w-xl mx-auto py-16 px-6 text-center space-y-4">
      <span class="material-symbols-outlined text-3xl text-error">error</span>
      <h3 class="font-headline font-bold text-lg text-on-surface">ไม่สามารถเปิดแฟ้มประเด็นข่าวได้</h3>
      <p class="text-xs text-outline">${esc(msg)}</p>
      <button class="px-4 py-2 bg-[#141413] text-white rounded-lg text-xs font-bold cursor-pointer"
              onclick="window.__backFromStoryline()">
        กลับสู่ฟีดรวมข่าว
      </button>
    </div>
  `;
}

export function showStorylineAiLoading() {
  const section = document.getElementById("storyline-ai-section");
  if (!section) return;
  section.innerHTML = `
    <div class="p-5 mt-4 bg-white/5 rounded-lg border border-white/15 text-center space-y-2 animate-fade-in">
      <svg class="animate-spin h-6 w-6 text-white mx-auto" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2.5"></circle>
        <path class="opacity-80" d="M12 2a10 10 0 0110 10" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="2.5"></path>
      </svg>
      <p class="text-xs font-bold text-white">AI กำลังสังเคราะห์มุมมองร่วมและลำดับเหตุการณ์...</p>
    </div>
  `;
}

export function renderStorylineAiSummary(summaryData) {
  const section = document.getElementById("storyline-ai-section");
  if (!section) return;
  const s = summaryData;
  const bullets = (s.bullets ?? []).map((b, i) => `
    <li class="flex items-start gap-3 text-xs sm:text-sm leading-relaxed text-white/90">
      <span class="font-mono text-amber-400 font-bold text-xs mt-0.5 shrink-0">0${i+1}.</span>
      <span>${esc(b)}</span>
    </li>
  `).join("");

  section.innerHTML = `
    <div class="p-5 mt-4 bg-black/40 rounded-lg border border-white/15 space-y-4 animate-fade-in">
      <div class="flex items-center justify-between flex-wrap gap-2 border-b border-white/10 pb-2.5">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-amber-400 text-[18px]" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
          <h3 class="font-headline font-bold text-sm text-white">AI Cross-Outlet Synthesis (บทสังเคราะห์ข้ามสำนักข่าว)</h3>
        </div>
        ${s.sentiment ? `<span class="font-mono text-[10px] uppercase px-2 py-0.5 rounded bg-white/10 text-white">TONE: ${esc(s.sentiment)}</span>` : ""}
      </div>
      ${s.summary ? `<p class="text-xs sm:text-sm text-white/90 leading-relaxed">${esc(s.summary)}</p>` : ""}
      ${bullets ? `<ul class="space-y-2 pt-1">${bullets}</ul>` : ""}
    </div>
  `;
}

export function renderStorylineView(storyData, activeSourceFilter = "", bookmarkedMap = {}) {
  const container = document.getElementById("storyline-view");
  if (!container || !storyData) return;

  const storyId = storyData.macro_event_id || storyData.story_id || storyData.cluster_id || "";
  const headline = storyData.headline || storyData.title || "แฟ้มเจาะลึกประเด็นข่าว";
  const rawArticles = Array.isArray(storyData.articles) ? storyData.articles : [];

  const sortedArticles = [...rawArticles].sort((a, b) => {
    const timeA = new Date(a.fetched_at || a.created_at || 0).getTime();
    const timeB = new Date(b.fetched_at || b.created_at || 0).getTime();
    return timeA - timeB;
  });

  const outletCounts = {};
  sortedArticles.forEach(a => {
    const src = a.source || "สำนักข่าว";
    outletCounts[src] = (outletCounts[src] || 0) + 1;
  });
  const outlets = Object.keys(outletCounts);

  const filteredArticles = activeSourceFilter
    ? sortedArticles.filter(a => (a.source || "").toLowerCase() === activeSourceFilter.toLowerCase())
    : sortedArticles;

  const allIsActive = !activeSourceFilter;
  let publisherPillsHtml = `
    <button type="button" 
            class="storyline-publisher-pill ${allIsActive ? 'active' : ''}"
            onclick="window.__filterStorylinePublisher('')">
      <span>ทุกสำนักข่าว</span>
      <span class="pill-count">${sortedArticles.length}</span>
    </button>
  `;

  publisherPillsHtml += outlets.map(outlet => {
    const isActive = outlet.toLowerCase() === activeSourceFilter.toLowerCase();
    const count = outletCounts[outlet] || 0;
    const color = SOURCE_COLORS[outlet] ?? "#1d3557";
    return `
      <button type="button" 
              class="storyline-publisher-pill ${isActive ? 'active' : ''}"
              onclick="window.__filterStorylinePublisher('${esc(outlet)}')">
        <span style="display:inline-block; width:7px; height:7px; border-radius:9999px; background:${isActive ? '#ffffff' : color};"></span>
        <span>${esc(outlet)}</span>
        <span class="pill-count">${count}</span>
      </button>
    `;
  }).join("");

  const storylineHashtags = Array.from(new Set([
    ...(Array.isArray(storyData.hashtags) ? storyData.hashtags : []),
    ...(Array.isArray(storyData.entities) ? storyData.entities : []),
    ...(sortedArticles.flatMap(a => Array.isArray(a.hashtags) ? a.hashtags : [])),
  ])).filter(Boolean).slice(0, 10);

  const storylineHashtagsHtml = storylineHashtags.length > 0 ? `
    <div class="storyline-tags-strip">
      <span class="font-mono text-[10px] uppercase tracking-wider text-white/60">RELATED TAGS /</span>
      <div class="flex items-center gap-1.5 flex-wrap">
        ${storylineHashtags.map(tag => {
          const clean = tag.startsWith("#") ? tag.slice(1) : tag;
          return `
            <button type="button"
                    class="storyline-tag-pill"
                    onclick="window.__filterByHashtag('${esc(clean)}')">
              #${esc(clean)}
            </button>
          `;
        }).join("")}
      </div>
    </div>
  ` : "";

  const articlesGridHtml = filteredArticles.length > 0 ? `
    <div class="storyline-grid-container">
      ${filteredArticles.map((art, idx) => {
        const color = SOURCE_COLORS[art.source] ?? "#1d3557";
        const placeholder = getCategoryPlaceholder(art.category);
        const imgSrc = art.image_url || placeholder;
        const isBookmarked = Boolean(bookmarkedMap && bookmarkedMap[art.url]);
        const artJsonEncoded = encodeURIComponent(JSON.stringify(art));
        const perspective = getPerspectiveLabel(art.title, art.source, art.summary);

        return `
          <article class="editorial-card">
            <div class="aspect-[16/10] relative overflow-hidden bg-surface-container-low cursor-pointer border-b border-outline-variant/25"
                 onclick="window.__openPreview('${esc(art.url)}')">
              <img src="${esc(imgSrc)}" alt="${esc(art.title)}" class="w-full h-full object-cover" onerror="this.onerror=null; this.src='${placeholder}';" loading="lazy">
              <div class="absolute top-2.5 left-2.5 bg-black/75 text-white font-mono text-[10px] font-bold px-2 py-0.5 rounded">
                CHRONOLOGY #0${idx + 1}
              </div>
            </div>

            <div class="p-4 sm:p-5 flex flex-col flex-1">
              <div class="flex items-center justify-between gap-2 mb-2">
                <div class="flex items-center gap-1.5">
                  <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
                  <span class="font-mono text-[11px] font-bold uppercase text-on-surface">${esc(art.source || "ข่าว")}</span>
                </div>
                <span class="font-mono text-[10px] text-secondary font-semibold">${esc(perspective)}</span>
              </div>

              <h3 class="font-headline font-bold text-base sm:text-lg text-on-surface leading-snug mb-2 cursor-pointer hover:text-primary line-clamp-2"
                  onclick="window.__openPreview('${esc(art.url)}')">
                ${esc(art.title)}
              </h3>

              <p class="text-xs text-on-surface-variant line-clamp-2 leading-relaxed mb-4">
                ${esc(art.summary || "")}
              </p>

              <div class="mt-auto pt-3 border-t border-outline-variant/25 flex items-center justify-between gap-2">
                <span class="font-mono text-[10px] text-outline uppercase">${esc(art.fetched_at || "")}</span>
                <div class="flex items-center gap-1" onclick="event.stopPropagation()">
                  <button type="button" class="editorial-card-icon-btn ${isBookmarked ? 'active' : ''}"
                          onclick="window.__toggleArticleBookmark(event, '${artJsonEncoded}')">
                    <span class="material-symbols-outlined text-[15px]">${isBookmarked ? 'bookmark' : 'bookmark_border'}</span>
                  </button>
                  <button type="button" class="editorial-card-action-btn" onclick="window.__openPreview('${esc(art.url)}')">อ่านย่อ</button>
                  <button type="button" class="editorial-card-ai-btn" onclick="window.__openPreviewAndSummarize('${esc(art.url)}')">AI</button>
                </div>
              </div>
            </div>
          </article>
        `;
      }).join("")}
    </div>
  ` : "";

  container.innerHTML = `
    <div class="storyline-container">
      <div class="storyline-top-bar">
        <button type="button" class="storyline-back-btn" onclick="window.__backFromStoryline()">
          <span class="material-symbols-outlined text-[16px]">arrow_back</span>
          <span>กลับสู่ฟีดรวมข่าว</span>
        </button>
        <span class="font-mono text-[11px] font-bold uppercase tracking-widest text-secondary">
          SPECIAL DOSSIER • ${outlets.length} PUBLISHERS
        </span>
      </div>

      <div class="storyline-hero-banner">
        <div class="font-mono text-[10px] uppercase tracking-widest text-amber-400 mb-2">EXECUTIVE STORYLINE BRIEFING</div>
        <h1 class="storyline-hero-title">${esc(headline)}</h1>
        <div class="storyline-meta-row font-mono">
          <span>${outlets.length} OUTLETS</span>
          <span>/</span>
          <span>${sortedArticles.length} REPORTS</span>
          ${storyData.updated_at ? `<span>/</span><span>UPDATED ${esc(storyData.updated_at)}</span>` : ""}
        </div>

        <div class="storyline-overview-card">
          <div class="storyline-overview-header">
            <div class="storyline-overview-title">
              <span class="material-symbols-outlined text-[18px]">description</span>
              <span>บทสรุปภาพรวมเหตุการณ์ (Executive Overview)</span>
            </div>
            <button type="button" id="storyline-ai-btn" class="storyline-ai-btn"
                    onclick="window.__runStorylineAiSummary('${esc(storyId)}')">
              <span class="material-symbols-outlined text-[15px]">auto_awesome</span>
              <span>สังเคราะห์ความคืบหน้าด้วย AI</span>
            </button>
          </div>
          <p class="storyline-overview-body">
            ${esc(storyData.summary || "รวบรวมลำดับเหตุการณ์และมุมมองการรายงานจากหลายสำนักข่าวเพื่อให้เห็นภาพรวมอย่างรอบด้าน")}
          </p>
          <div id="storyline-ai-section"></div>
          ${storylineHashtagsHtml}
        </div>
      </div>

      <div class="storyline-filter-bar">
        <div class="storyline-filter-title">
          <span class="font-mono text-xs uppercase tracking-wider">FILTER BY PUBLISHER PERSPECTIVE</span>
          <span class="font-mono text-[11px] text-outline">SHOWING ${filteredArticles.length} OF ${sortedArticles.length}</span>
        </div>
        <div class="storyline-pills-row custom-scrollbar">
          ${publisherPillsHtml}
        </div>
      </div>

      <div class="mt-6">
        ${articlesGridHtml}
      </div>
    </div>
  `;
}