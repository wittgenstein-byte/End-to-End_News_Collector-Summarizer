/**
 * ui.js — DOM manipulation & rendering (Editorial Redesign v3.3)
 *
 * หน้าที่: วาด UI ล้วน ๆ
 * รับ data สำเร็จรูปจาก main.js — ไม่ fetch เอง
 */

import { SOURCE_COLORS, CATEGORIES, getCategoryById, getSentimentConfig, SENTIMENT_CONFIG, HERO_CLUSTER_LIMIT, FEEDBACK_FORM_URL, FEEDBACK_COMPLETED_KEY } from "./config.js?v=3.3.3";

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

  heroTrendingArticles = deduped.slice(0, HERO_CLUSTER_LIMIT || 12);
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
              <span class="font-mono text-[10px] font-bold opacity-60">${String(rank).padStart(2, "0")}</span>
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

  // Extract all articles belonging to this trending story
  const allSlideArticles = [];
  const seenArtUrls = new Set();
  (n.articles || []).forEach(a => {
    if (a && a.url && !seenArtUrls.has(a.url)) {
      seenArtUrls.add(a.url);
      allSlideArticles.push(a);
    }
  });
  (n.child_events || []).forEach(ce => {
    (ce.articles || []).forEach(a => {
      if (a && a.url && !seenArtUrls.has(a.url)) {
        seenArtUrls.add(a.url);
        allSlideArticles.push(a);
      }
    });
  });
  if (allSlideArticles.length === 0 && n.url) {
    allSlideArticles.push(n);
  }

  const isSportsStory = checkIsSportsCluster(n, allSlideArticles) || n.category === "sports";

  // Dedicated Sports Multi-Image Hero Montage on Main Page (contained strictly inside hero-carousel-container)
  if (isSportsStory) {
    allSlideArticles.forEach(art => {
      if (!art._sportsMeta) art._sportsMeta = classifySportsArticle(art);
    });

    const disciplineCounts = {
      football_europe: 0,
      football_thai: 0,
      volleyball: 0,
      other_sports: 0,
    };
    const contentTypeCounts = {
      result: 0,
      schedule: 0,
      general: 0,
    };
    allSlideArticles.forEach(art => {
      const meta = art._sportsMeta;
      if (disciplineCounts[meta.discipline] !== undefined) {
        disciplineCounts[meta.discipline]++;
      } else {
        disciplineCounts.other_sports++;
      }
      if (contentTypeCounts[meta.contentType] !== undefined) {
        contentTypeCounts[meta.contentType]++;
      } else {
        contentTypeCounts.general++;
      }
    });

    const discTabs = [
      { id: "", label: "ทุกกีฬา", icon: "🌟", count: allSlideArticles.length },
      { id: "football_europe", label: "บอลยุโรป & UCL", icon: "⚽", count: disciplineCounts.football_europe },
      { id: "football_thai", label: "บอลไทย & เอเชีย", icon: "🇹🇭", count: disciplineCounts.football_thai },
      { id: "volleyball", label: "วอลเลย์บอล", icon: "🏐", count: disciplineCounts.volleyball },
      { id: "other_sports", label: "กีฬาอื่นๆ", icon: "🏃", count: disciplineCounts.other_sports },
    ].filter(t => t.id === "" || t.count > 0);

    const sportsImages = [];
    const seenImageUrls = new Set();
    for (const art of allSlideArticles) {
      const img = art.image_url;
      if (img && typeof img === "string" && img.startsWith("http") && !seenImageUrls.has(img)) {
        seenImageUrls.add(img);
        sportsImages.push({
          url: img,
          title: art.title || "",
          articleUrl: art.url || "",
          source: art.source || "ข่าว",
          meta: art._sportsMeta || classifySportsArticle(art),
        });
      }
    }

    container.innerHTML = `
      ${quickSwitchStripHtml}

      <div class="hero-carousel-container group"
           onmouseenter="window.__pauseTrendingAutoPlay()"
           onmouseleave="window.__resumeTrendingAutoPlay()"
           ontouchstart="window.__heroTouchStart(event)"
           ontouchend="window.__heroTouchEnd(event)">
        
        <!-- Sports Multi-Image Split Montage (Fills 100% of hero container with no vertical expansion) -->
        ${sportsImages.length >= 2 ? `
          <div class="absolute inset-0 w-full h-full grid grid-cols-1 md:grid-cols-12 gap-1 bg-slate-950 pointer-events-auto">
            <!-- Left: Featured Main Action Photo (7 cols) -->
            <div class="relative md:col-span-7 h-full overflow-hidden cursor-pointer group/main"
                 onclick="window.__openPreview('${esc(sportsImages[0].articleUrl)}')">
              <img src="${esc(sportsImages[0].url)}" 
                   alt="${esc(sportsImages[0].title)}" 
                   class="w-full h-full object-cover group-hover/main:scale-105 transition-transform duration-700" 
                   loading="eager" />
              <div class="absolute top-12 sm:top-14 left-4 sm:left-6 flex items-center gap-1.5 z-20 flex-wrap">
                <span class="sports-tag-badge text-[9px] ${sportsImages[0].meta.leagueBadgeClass}">${sportsImages[0].meta.leagueBadge}</span>
                ${sportsImages[0].meta.scoreHighlight ? `<span class="sports-tag-badge sports-result-badge text-[9px]">🏆 ${esc(sportsImages[0].meta.scoreHighlight)}</span>` : ''}
                <span class="text-[9px] font-mono text-white/90 bg-black/60 backdrop-blur-xs px-2 py-0.5 rounded font-bold">${esc(sportsImages[0].source)}</span>
              </div>
            </div>

            <!-- Right: Secondary Stacked Photos (5 cols, 2 rows) -->
            <div class="hidden md:grid md:col-span-5 grid-rows-2 gap-1 h-full">
              ${sportsImages.slice(1, 3).map((item) => `
                <div class="relative h-full overflow-hidden cursor-pointer group/sub"
                     onclick="window.__openPreview('${esc(item.articleUrl)}')">
                  <img src="${esc(item.url)}" 
                       alt="${esc(item.title)}" 
                       class="w-full h-full object-cover group-hover/sub:scale-105 transition-transform duration-700" 
                       loading="lazy" />
                  <div class="absolute inset-0 bg-black/35 group-hover/sub:bg-black/15 transition-colors"></div>
                  <div class="absolute top-2.5 right-2.5 flex items-center gap-1 z-20">
                    <span class="sports-tag-badge text-[9px] py-0.5 px-1.5 ${item.meta.leagueBadgeClass}">${item.meta.leagueBadge}</span>
                    ${item.meta.scoreHighlight ? `<span class="sports-tag-badge sports-result-badge text-[9px] py-0.5 px-1.5">🏆 ${esc(item.meta.scoreHighlight)}</span>` : ''}
                    <span class="text-[9px] font-mono text-white/90 bg-black/70 px-1.5 py-0.5 rounded font-bold">${esc(item.source)}</span>
                  </div>
                  <div class="absolute bottom-2.5 left-2.5 right-2.5 z-20">
                    <p class="text-xs font-semibold text-white line-clamp-1 drop-shadow-md group-hover/sub:text-emerald-300 transition-colors">${esc(item.title)}</p>
                  </div>
                </div>
              `).join("")}
            </div>
          </div>
        ` : `
          <img src="${esc(imgSrc)}" 
               alt="${esc(n.title)}" 
               class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700 cursor-pointer"
               onclick="window.__openPreview('${esc(n.url)}')"
               onerror="this.onerror=null; this.src='${getCategoryPlaceholder(n.category)}';" 
               loading="eager" />
        `}

        <!-- Navigation Buttons -->
        <button type="button" class="hero-nav-btn hero-nav-btn-left" onclick="window.__prevTrendingSlide(event)" title="ก่อนหน้า">
          <span class="material-symbols-outlined text-[22px]">chevron_left</span>
        </button>
        <button type="button" class="hero-nav-btn hero-nav-btn-right" onclick="window.__nextTrendingSlide(event)" title="ถัดไป">
          <span class="material-symbols-outlined text-[22px]">chevron_right</span>
        </button>

        <!-- Gradient Scrim Overlay -->
        <div class="hero-gradient-overlay">
          <!-- Top Telemetry Row -->
          <div class="flex items-center justify-between gap-2 pointer-events-auto">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="px-2.5 py-1 rounded bg-emerald-600 text-white font-mono font-bold text-[10px] tracking-widest uppercase flex items-center gap-1">
                <span class="material-symbols-outlined text-[13px]">sports_soccer</span>
                SPORTS ROUNDUP
              </span>
              <span class="px-2.5 py-1 rounded bg-black/60 text-white/90 backdrop-blur-md font-mono text-[10px] border border-white/20">
                FEATURED #${String(rankNum).padStart(2, "0")}
              </span>
              <span class="px-2.5 py-1 rounded bg-black/60 text-white/90 backdrop-blur-md font-mono text-[10px] border border-white/20 hidden sm:inline-block">
                IMPACT SCORE ${scoreVal}
              </span>
            </div>
            <div class="flex items-center gap-2 bg-black/60 backdrop-blur-md px-3 py-1 rounded border border-white/20">
              <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              <span class="text-[11px] font-mono font-bold text-white uppercase tracking-wider">
                รวม ${allSlideArticles.length} รายงาน • ${outletMap.size} สำนักข่าว
              </span>
            </div>
          </div>

          <!-- Bottom Editorial Feature Content -->
          <div class="space-y-2 pointer-events-auto pb-3 max-w-4xl">
            <div class="space-y-1">
              <h1 class="text-xl sm:text-2xl md:text-3xl font-headline font-bold hero-headline leading-tight cursor-pointer hover:underline decoration-white/40 underline-offset-4 flex items-center gap-2 flex-wrap"
                  onclick="window.__openCurrentHeroStoryline()">
                <span>⚡ รวมข่าวกีฬาล่าสุด</span>
                <span class="text-[10px] sm:text-xs font-mono font-bold px-2.5 py-0.5 rounded-full bg-emerald-500/90 text-white border border-emerald-400/50 shadow-xs">
                  สดรอบวัน
                </span>
              </h1>

              <div class="hidden sm:block">
                <p class="text-xs sm:text-sm text-white/90 line-clamp-1 leading-relaxed font-body max-w-3xl drop-shadow cursor-pointer"
                   onclick="window.__openCurrentHeroStoryline()">
                  ${esc(n.title)} • รวบรวมไฮไลต์ ผลบอลไทย บอลยุโรป วอลเลย์บอล จาก ${outletMap.size} สำนักข่าว (${allSlideArticles.length} ข่าว)
                </p>
              </div>

              <!-- Quick Sports Discipline Pills (Frosted Glass Chips, scrollable on mobile) -->
              <div class="flex items-center gap-1.5 overflow-x-auto flex-nowrap sm:flex-wrap custom-scrollbar max-w-full pb-0.5 pt-0.5">
                ${discTabs.map(tab => `
                  <button type="button"
                          class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[10px] sm:text-[11px] font-mono font-bold bg-white/10 hover:bg-white/25 text-white border border-white/20 backdrop-blur-md transition-all cursor-pointer shadow-2xs shrink-0"
                          onclick="event.stopPropagation(); window.__openHeroSportDiscipline('${tab.id}')">
                    <span>${tab.icon}</span>
                    <span>${tab.label}</span>
                    <span class="text-emerald-400 font-bold">(${tab.count})</span>
                  </button>
                `).join("")}
                ${contentTypeCounts.result > 0 ? `
                  <button type="button"
                          class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[10px] sm:text-[11px] font-mono font-bold bg-white/10 hover:bg-white/25 text-white border border-white/20 backdrop-blur-md transition-all cursor-pointer shadow-2xs shrink-0"
                          onclick="event.stopPropagation(); window.__openHeroSportDiscipline('')">
                    <span>🏆 ผลแข่ง</span>
                    <span class="text-amber-400 font-bold">(${contentTypeCounts.result})</span>
                  </button>
                ` : ""}
              </div>
            </div>

            <div class="flex items-center justify-between gap-3 flex-wrap pt-2 border-t border-white/15 w-full">
              <span class="text-[11px] font-mono text-white/70 uppercase tracking-wider">
                ${esc(n.fetched_at || "")} • STORY ${String(rankNum).padStart(2, "0")}/${String(total).padStart(2, "0")}
              </span>
              <div class="flex items-center gap-2 flex-wrap sm:flex-nowrap w-full sm:w-auto" onclick="event.stopPropagation()">
                <div class="flex items-center gap-2 flex-1 sm:flex-initial">
                  <button type="button" 
                          class="hero-bookmark-btn bookmark-btn p-2 rounded-lg border border-white/30 bg-black/50 text-white hover:bg-white hover:text-black transition-colors cursor-pointer shrink-0 ${isBookmarked ? 'active' : ''}"
                          data-url="${esc(n.url)}"
                          onclick="window.__toggleArticleBookmark(event, '${jsonEncoded}')" 
                          title="${isBookmarked ? 'ลบบุ๊กมาร์ก' : 'บันทึกบทความ'}">
                    <span class="material-symbols-outlined text-[17px]" style="${isBookmarked ? "font-variation-settings: 'FILL' 1; color: #f59e0b;" : ""}">
                      ${isBookmarked ? 'bookmark' : 'bookmark_border'}
                    </span>
                  </button>
                  <button type="button" 
                          class="hero-read-abstract-btn flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg font-bold text-xs transition-all cursor-pointer shadow-sm" 
                          onclick="window.__openPreview('${esc(n.url)}')">
                    <span class="material-symbols-outlined text-[15px]">article</span>
                    <span>อ่านบทคัดย่อ</span>
                  </button>
                  <button type="button" 
                          class="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 bg-[#c84b31] hover:opacity-95 text-white px-3 py-2 rounded-lg font-bold text-xs transition-all cursor-pointer shadow-sm" 
                          onclick="window.__openPreviewAndSummarize('${esc(n.url)}')">
                    <span class="material-symbols-outlined text-[15px]" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
                    <span>สรุป AI</span>
                  </button>
                </div>
                <button type="button" 
                        class="hero-storyline-action-btn w-full sm:w-auto flex items-center justify-center gap-2 px-4 py-2 rounded-lg font-extrabold text-xs transition-all cursor-pointer shadow-lg bg-amber-500 hover:bg-amber-400 text-slate-950 shrink-0" 
                        onclick="window.__openCurrentHeroStoryline()"
                        title="เจาะลึกและดูรายงานทุกสำนักข่าวในประเด็นนี้">
                  <span class="material-symbols-outlined text-[16px] text-slate-950 font-bold">sports_and_outdoors</span>
                  <span>ดูข่าวกีฬาทั้งหมดในประเด็นนี้</span>
                  <span class="bg-black/25 text-slate-950 px-2 py-0.5 rounded-full text-[10px] font-mono font-extrabold tracking-wider">${outletMap.size} สื่อ</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Carousel Progress Indicators -->
        <div class="hero-progress-container">
          ${indicatorsHtml}
        </div>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    ${quickSwitchStripHtml}

    <div class="hero-carousel-container group"
         onmouseenter="window.__pauseTrendingAutoPlay()"
         onmouseleave="window.__resumeTrendingAutoPlay()"
         ontouchstart="window.__heroTouchStart(event)"
         ontouchend="window.__heroTouchEnd(event)">
      
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
        <div class="flex items-center justify-between gap-1.5 sm:gap-2 pointer-events-auto">
          <div class="flex items-center gap-1.5 sm:gap-2 flex-wrap">
            <span class="px-2 sm:px-2.5 py-0.5 sm:py-1 rounded bg-[#c84b31] text-white font-mono font-bold text-[9px] sm:text-[10px] tracking-widest uppercase">
              FEATURED #${String(rankNum).padStart(2, "0")}
            </span>
            <span class="px-2 sm:px-2.5 py-0.5 sm:py-1 rounded bg-black/60 text-white/90 backdrop-blur-md font-mono text-[9px] sm:text-[10px] border border-white/20">
              IMPACT SCORE ${scoreVal}
            </span>
          </div>
          <div class="flex items-center gap-1.5 sm:gap-2 bg-black/60 backdrop-blur-md px-2.5 sm:px-3 py-0.5 sm:py-1 rounded border border-white/20">
            <span class="w-1.5 sm:w-2 h-1.5 sm:h-2 rounded-full" style="background:${color}"></span>
            <span class="text-[10px] sm:text-[11px] font-mono font-bold text-white uppercase tracking-wider">${esc(n.source || (n.outlets && n.outlets[0]) || "MULTI-SOURCE")}</span>
          </div>
        </div>

        <!-- Bottom Editorial Feature Content -->
        <div class="space-y-2 sm:space-y-3 pointer-events-auto pb-2 sm:pb-3 max-w-4xl">
          <div class="space-y-1.5 sm:space-y-2">
            <h1 class="text-base sm:text-3xl md:text-4xl font-headline font-bold hero-headline leading-snug cursor-pointer hover:underline decoration-white/40 underline-offset-4 line-clamp-2"
                onclick="window.__openPreview('${esc(n.url)}')">
              ${esc(n.title)}
            </h1>

            ${n.summary ? `
              <div class="hidden sm:block">
                <p class="text-xs sm:text-sm text-white/85 line-clamp-2 leading-relaxed font-body max-w-3xl cursor-pointer"
                   onclick="window.__openPreview('${esc(n.url)}')">
                  ${esc(n.summary)}
                </p>
              </div>
            ` : ""}

            <div class="flex items-center gap-1.5 sm:gap-2 overflow-x-auto flex-nowrap sm:flex-wrap custom-scrollbar max-w-full pb-0.5 pt-0.5 sm:pt-1">
              ${publisherPillsHtml}
              ${storylineHashtagsHtml}
            </div>
          </div>

          <div class="flex items-center justify-between gap-2 flex-wrap pt-1.5 sm:pt-2 border-t border-white/15 w-full">
            <span class="text-[10px] sm:text-[11px] font-mono text-white/70 uppercase tracking-wider">${esc(n.fetched_at || "")} • STORY ${String(rankNum).padStart(2, "0")}/${String(total).padStart(2, "0")}</span>
            <div class="flex items-center gap-1.5 sm:gap-2 flex-wrap sm:flex-nowrap w-full sm:w-auto" onclick="event.stopPropagation()">
              <div class="flex items-center gap-1.5 sm:gap-2 flex-1 sm:flex-initial">
                <button type="button" 
                        class="hero-bookmark-btn bookmark-btn p-1.5 sm:p-2 rounded-lg border border-white/30 bg-black/50 text-white hover:bg-white hover:text-black transition-colors cursor-pointer shrink-0 ${isBookmarked ? 'active' : ''}"
                        data-url="${esc(n.url)}"
                        onclick="window.__toggleArticleBookmark(event, '${jsonEncoded}')" 
                        title="${isBookmarked ? 'ลบบุ๊กมาร์ก' : 'บันทึกบทความ'}">
                  <span class="material-symbols-outlined text-[15px] sm:text-[17px]" style="${isBookmarked ? "font-variation-settings: 'FILL' 1; color: #f59e0b;" : ""}">
                    ${isBookmarked ? 'bookmark' : 'bookmark_border'}
                  </span>
                </button>
                <button type="button" 
                        class="hero-read-abstract-btn flex-1 sm:flex-initial flex items-center justify-center gap-1 px-2.5 sm:px-3 py-1.5 sm:py-2 rounded-lg font-bold text-[11px] sm:text-xs transition-all cursor-pointer shadow-sm" 
                        onclick="window.__openPreview('${esc(n.url)}')">
                  <span class="material-symbols-outlined text-[14px] sm:text-[15px]">article</span>
                  <span>อ่านบทคัดย่อ</span>
                </button>
                <button type="button" 
                        class="flex-1 sm:flex-initial flex items-center justify-center gap-1 bg-[#c84b31] hover:opacity-95 text-white px-2.5 sm:px-3 py-1.5 sm:py-2 rounded-lg font-bold text-[11px] sm:text-xs transition-all cursor-pointer shadow-sm" 
                        onclick="window.__openPreviewAndSummarize('${esc(n.url)}')">
                  <span class="material-symbols-outlined text-[14px] sm:text-[15px]" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
                  <span>สรุป AI</span>
                </button>
              </div>
              <button type="button" 
                      class="hero-storyline-action-btn w-full sm:w-auto flex items-center justify-center gap-1.5 px-3 sm:px-4 py-1.5 sm:py-2 rounded-lg font-extrabold text-[11px] sm:text-xs transition-all cursor-pointer shadow-lg shrink-0" 
                      onclick="window.__openCurrentHeroStoryline()"
                      title="เจาะลึกและดูรายงานทุกสำนักข่าวในประเด็นนี้">
                <span class="material-symbols-outlined text-[15px] sm:text-[16px] text-slate-950 font-bold">account_tree</span>
                <span>ดูข่าวทั้งหมดในประเด็นนี้</span>
                <span class="bg-black/25 text-slate-950 px-1.5 py-0.5 rounded-full text-[9px] sm:text-[10px] font-mono font-extrabold tracking-wider">${outletMap.size} สื่อ</span>
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

// Touch swipe detection for mobile Hero Carousel
let heroTouchStartX = 0;
let heroTouchStartY = 0;

window.__heroTouchStart = (event) => {
  if (!event.touches || event.touches.length === 0) return;
  heroTouchStartX = event.touches[0].clientX;
  heroTouchStartY = event.touches[0].clientY;
  window.__pauseTrendingAutoPlay();
};

window.__heroTouchEnd = (event) => {
  if (!event.changedTouches || event.changedTouches.length === 0) return;
  const dx = event.changedTouches[0].clientX - heroTouchStartX;
  const dy = event.changedTouches[0].clientY - heroTouchStartY;
  if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) {
    if (dx < 0) {
      window.__nextTrendingSlide();
    } else {
      window.__prevTrendingSlide();
    }
  }
  window.__resumeTrendingAutoPlay();
};

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
      <article class="editorial-card group" data-url="${esc(n.url)}" style="animation: fadeUp 0.35s ease-out ${Math.min(i * 0.03, 0.4)}s both;">
        <div class="flex flex-row sm:flex-col flex-1 p-2.5 sm:p-0 cursor-pointer" data-url="${esc(n.url)}" onclick="window.__openPreview(this.dataset.url)">
          <!-- Card Thumbnail: Left on mobile (108px x 76px, rounded), Top on Desktop (compact 144px height) -->
          <div class="w-[108px] h-[76px] sm:w-full sm:h-36 overflow-hidden relative shrink-0 rounded-lg sm:rounded-none bg-surface-container-low sm:border-b sm:border-outline-variant/25">
            <img alt="thumbnail" class="object-cover w-full h-full transition-transform duration-500 group-hover:scale-105" src="${esc(imgSrc)}" onerror="this.onerror=null; this.src='${placeholder}';" loading="lazy" />
            ${catObj && catObj.id !== "all" ? `
              <span class="hidden sm:inline-block absolute top-2 left-2.5 text-[10px] font-mono font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-black/70 text-white backdrop-blur-xs">
                ${esc(catObj.label)}
              </span>
            ` : ""}
          </div>

          <!-- Card Content: Right on mobile, Below on Desktop -->
          <div class="editorial-card-body flex flex-col justify-between sm:justify-start flex-1 min-w-0">
            <!-- Dateline: Desktop top row -->
            <div class="hidden sm:flex items-center justify-between gap-2 mb-1.5">
              <div class="flex items-center gap-1.5 min-w-0">
                <span class="w-2 h-2 rounded-full shrink-0" style="background:${color}"></span>
                <span class="text-[11px] font-mono font-bold text-on-surface-variant uppercase tracking-wider truncate">${esc(n.source)}</span>
              </div>
              <div class="flex items-center gap-1 shrink-0 flex-wrap justify-end">
                ${renderArticleBadges(n, isNew)}
              </div>
            </div>

            <!-- Headline: Directly at top on mobile (matching reference image) -->
            <h2 class="text-[14px] sm:text-[15.5px] font-headline font-bold text-on-surface leading-snug transition-colors group-hover:text-primary line-clamp-2 mb-1 sm:mb-1.5">
              ${esc(n.title)}
            </h2>

            <!-- Summary excerpt (Desktop only) -->
            ${n.summary ? `
              <div class="hidden sm:block">
                <p class="text-xs text-on-surface-variant line-clamp-2 leading-relaxed">
                  ${esc(n.summary)}
                </p>
              </div>
            ` : ""}

            <!-- Mobile Dateline & Source: directly below headline (just like the user's reference screenshot) -->
            <div class="flex sm:hidden items-center justify-between gap-1 mt-auto pt-1 text-xs">
              <div class="flex items-center gap-1.5 min-w-0 text-outline">
                <span class="w-1.5 h-1.5 rounded-full shrink-0" style="background:${color}"></span>
                <span class="text-[11px] font-medium text-on-surface-variant/90 truncate">${esc(n.source)}</span>
                <span class="text-[10px] font-mono opacity-60 shrink-0">• ${esc(n.fetched_at ?? "")}</span>
              </div>
              <div class="flex items-center gap-1 shrink-0" onclick="event.stopPropagation()">
                ${n.url ? `
                <button type="button"
                        class="p-1 rounded text-outline hover:text-on-surface bookmark-btn ${isBookmarked ? 'active text-amber-500' : ''}"
                        data-url="${esc(n.url)}"
                        onclick="window.__toggleArticleBookmark(event, '${articleJsonEncoded}')"
                        title="${isBookmarked ? 'ลบบุ๊กมาร์ก' : 'บันทึกบทความ'}">
                  <span class="material-symbols-outlined text-[15px]" style="${isBookmarked ? "font-variation-settings: 'FILL' 1; color: #f59e0b;" : ""}">
                    ${isBookmarked ? 'bookmark' : 'bookmark_border'}
                  </span>
                </button>` : ""}
                <button type="button"
                        class="px-2 py-0.5 rounded bg-black/5 dark:bg-white/10 hover:bg-amber-500 hover:text-black text-[10px] font-bold text-on-surface flex items-center gap-0.5 transition-colors cursor-pointer"
                        data-url="${esc(n.url)}"
                        onclick="window.__openPreviewAndSummarize(this.dataset.url)"
                        title="สรุปประเด็นด้วย AI">
                  <span class="material-symbols-outlined text-[11px] text-amber-500" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
                  <span>AI</span>
                </button>
              </div>
            </div>

          </div>
        </div>

        <!-- Card Footer Actions (Desktop Only) -->
        <div class="hidden sm:flex px-4 py-2 mt-auto border-t border-outline-variant/25 items-center justify-between gap-2 bg-surface/40">
          <span class="text-[10px] font-mono text-outline uppercase truncate">${esc(n.fetched_at ?? "")}</span>
          <div class="flex items-center gap-1 shrink-0" onclick="event.stopPropagation()">
            ${n.url ? `
            <button type="button"
                    class="editorial-card-icon-btn bookmark-btn ${isBookmarked ? 'active' : ''}"
                    data-url="${esc(n.url)}"
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

    ${localStorage.getItem(FEEDBACK_COMPLETED_KEY) !== "true" ? `
    <div id="modal-feedback-callout" class="p-4 rounded-xl border border-amber-500/30 bg-amber-500/10 dark:bg-amber-950/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 animate-fade-in mt-4">
      <div class="flex items-center gap-2.5">
        <span class="material-symbols-outlined text-amber-600 dark:text-amber-400 text-[20px]">rate_review</span>
        <div>
          <span class="text-xs font-bold text-on-surface block">ช่วยตอบแบบประเมินโครงงาน (ประเมินคุณภาพ AI)</span>
          <span class="text-[11px] text-on-surface-variant">ตอบแบบสอบถามสั้น ๆ เพื่อพัฒนาโครงงานวิจัยนี้</span>
        </div>
      </div>
      <a href="${FEEDBACK_FORM_URL}" target="_blank" rel="noopener noreferrer" onclick="window.__handleFeedbackFormClick(event)" class="shrink-0 px-3.5 py-1.5 bg-[#141413] dark:bg-white text-white dark:text-[#141413] rounded-lg text-xs font-bold hover:opacity-90 inline-flex items-center gap-1.5 transition-all">
        <span>ทำแบบประเมิน</span>
        <span class="material-symbols-outlined text-[14px]">open_in_new</span>
      </a>
    </div>
    ` : ""}

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
  const evaluationView = document.getElementById("evaluation-view");
  const floatingBack = document.getElementById("storyline-floating-back");
  const topBar = document.getElementById("storyline-top-bar");

  if (viewName === "preview") {
    if (feedView) feedView.classList.add("hidden");
    if (storylineView) storylineView.classList.add("hidden");
    if (evaluationView) evaluationView.classList.add("hidden");
    if (previewView) previewView.classList.remove("hidden");
    if (floatingBack) floatingBack.classList.add("hidden-fade");
    if (topBar) topBar.classList.remove("is-hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  } else if (viewName === "storyline") {
    if (feedView) feedView.classList.add("hidden");
    if (previewView) previewView.classList.add("hidden");
    if (evaluationView) evaluationView.classList.add("hidden");
    if (storylineView) storylineView.classList.remove("hidden");
    if (floatingBack) floatingBack.classList.add("hidden-fade");
    if (topBar) topBar.classList.remove("is-hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  } else if (viewName === "evaluation") {
    if (feedView) feedView.classList.add("hidden");
    if (previewView) previewView.classList.add("hidden");
    if (storylineView) storylineView.classList.add("hidden");
    if (evaluationView) evaluationView.classList.remove("hidden");
    if (floatingBack) floatingBack.classList.add("hidden-fade");
    if (topBar) topBar.classList.remove("is-hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  } else {
    if (previewView) previewView.classList.add("hidden");
    if (storylineView) storylineView.classList.add("hidden");
    if (evaluationView) evaluationView.classList.add("hidden");
    if (feedView) feedView.classList.remove("hidden");
    if (floatingBack) floatingBack.classList.add("hidden-fade");
    if (topBar) topBar.classList.remove("is-hidden");
  }
}

// ── Preview Sub-View Rendering ────────────────────────────────────

export function renderInlineSummary(summary) {
  const s = summary;
  const bullets = (s.bullets ?? []).map((b, i) => `
    <li class="flex items-start gap-3 text-sm leading-relaxed text-slate-800 dark:text-slate-100 font-medium">
      <span class="preview-ai-bullet-num font-mono text-xs font-bold text-amber-600 dark:text-amber-400 mt-0.5 shrink-0">0${i+1}.</span>
      <span class="preview-ai-bullet-text">${esc(b)}</span>
    </li>
  `).join("");

  const keywords = (s.keywords ?? []).map(k => `
    <span class="preview-ai-tag px-2.5 py-1 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 font-mono text-[11px] font-semibold rounded-md">#${esc(k)}</span>
  `).join("");

  return `
    <div class="preview-ai-card p-6 rounded-xl border space-y-4 animate-fade-in">
      <div class="flex items-center justify-between flex-wrap gap-2 border-b border-amber-500/20 pb-3">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-amber-500 dark:text-amber-400 text-[20px]" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
          <h3 class="preview-ai-title font-headline font-bold text-base text-slate-900 dark:text-white">บทสังเคราะห์ประเด็นสำคัญโดย AI</h3>
        </div>
        ${s.sentiment ? `
          <span class="preview-ai-tone-badge font-mono text-[11px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-md bg-amber-100 text-amber-900 dark:bg-amber-500/20 dark:text-amber-300 border border-amber-300 dark:border-amber-500/40 shadow-xs">
            TONE: ${esc(s.sentiment)}
          </span>
        ` : ""}
      </div>

      ${s.summary ? `<p class="preview-ai-prose text-sm text-slate-800 dark:text-slate-200 leading-relaxed font-normal">${esc(s.summary)}</p>` : ""}

      ${bullets ? `
        <div class="space-y-2 pt-2">
          <h4 class="preview-ai-label font-mono text-[11px] font-bold uppercase tracking-widest text-amber-600 dark:text-amber-400 flex items-center gap-1.5">
            <span class="material-symbols-outlined text-[15px]">checklist</span>
            <span>KEY TAKEAWAYS</span>
          </h4>
          <ul class="space-y-2.5">${bullets}</ul>
        </div>
      ` : ""}

      ${keywords ? `<div class="flex flex-wrap gap-1.5 pt-2">${keywords}</div>` : ""}

      ${localStorage.getItem(FEEDBACK_COMPLETED_KEY) !== "true" ? `
      <div id="inline-feedback-callout" class="p-3.5 rounded-xl border border-amber-500/30 bg-amber-500/10 dark:bg-amber-950/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mt-4">
        <div class="flex items-center gap-2.5">
          <span class="material-symbols-outlined text-amber-600 dark:text-amber-400 text-[18px]">rate_review</span>
          <div>
            <span class="text-xs font-bold text-on-surface block">ช่วยตอบแบบประเมินโครงงาน (Google Forms)</span>
            <span class="text-[11px] text-on-surface-variant">หลังจากอ่านสรุป AI ร่วมประเมินเพื่อพัฒนาโครงงานต่อไป</span>
          </div>
        </div>
        <a href="${FEEDBACK_FORM_URL}" target="_blank" rel="noopener noreferrer" onclick="window.__handleFeedbackFormClick(event)" class="shrink-0 px-3.5 py-1.5 bg-[#141413] dark:bg-white text-white dark:text-[#141413] rounded-lg text-xs font-bold hover:opacity-90 inline-flex items-center gap-1.5 transition-all">
          <span>ทำแบบประเมิน</span>
          <span class="material-symbols-outlined text-[13px]">open_in_new</span>
        </a>
      </div>
      ` : ""}
    </div>
  `;
}

export function showInlineSummaryLoading() {
  const section = document.getElementById("preview-ai-section");
  if (!section) return;
  section.innerHTML = `
    <div class="p-8 bg-slate-50 dark:bg-slate-900/80 rounded-xl border border-amber-500/30 text-center space-y-2 shadow-sm">
      <svg class="animate-spin h-6 w-6 text-amber-500 mx-auto" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2.5"></circle>
        <path class="opacity-80" d="M12 2a10 10 0 0110 10" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="2.5"></path>
      </svg>
      <p class="text-xs font-bold text-slate-800 dark:text-slate-100">AI กำลังอ่านและสังเคราะห์ประเด็นสำคัญ...</p>
    </div>
  `;
}

export function showInlineSummaryError(msg, articleUrl) {
  const section = document.getElementById("preview-ai-section");
  if (!section) return;
  section.innerHTML = `
    <div class="p-5 bg-error/10 border border-error/30 rounded-xl text-center space-y-2">
      <p class="text-xs text-rose-600 dark:text-rose-400 font-bold">${esc(msg)}</p>
      <button class="px-4 py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 rounded-lg text-xs font-bold cursor-pointer transition-colors shadow-sm"
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
        <button class="bookmark-btn modal-bookmark-btn flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-outline-variant/40 ${isBookmarked ? 'bg-[#141413] text-white active' : 'bg-white text-on-surface hover:bg-surface-container'} text-xs font-bold transition-colors cursor-pointer"
                data-url="${esc(article.url)}"
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
            <div class="p-6 bg-slate-50 dark:bg-slate-900/80 rounded-xl border border-amber-500/25 flex flex-col sm:flex-row items-center justify-between gap-4 shadow-sm">
              <div class="space-y-1 text-center sm:text-left">
                <h3 class="font-headline font-bold text-base text-slate-900 dark:text-white flex items-center justify-center sm:justify-start gap-1.5">
                  <span class="material-symbols-outlined text-amber-500 dark:text-amber-400 text-[18px]" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
                  <span>ต้องการสรุปประเด็นสำคัญด้วย AI หรือไม่?</span>
                </h3>
                <p class="text-xs text-slate-600 dark:text-slate-300">สังเคราะห์ใจความหลัก ดึง Key Takeaways และวิเคราะห์โทนของข่าวทันที</p>
              </div>
              <button class="shrink-0 inline-flex items-center gap-2 px-5 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold rounded-lg transition-colors cursor-pointer shadow-md"
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
let currentStorylineDataCache = null;

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

// Global Handlers for Event Progression Dossier & Citation Inspection
window.__switchDossierTab = (tabName) => {
  const container = document.getElementById("storyline-ai-section");
  if (!container) return;
  container.querySelectorAll(".dossier-tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  container.querySelectorAll(".dossier-tab-panel").forEach(panel => {
    panel.classList.toggle("hidden", panel.id !== `dossier-panel-${tabName}`);
  });
};

window.__inspectCitation = (evidenceId) => {
  if (!evidenceId) return;
  const cleanId = String(evidenceId).trim().toLowerCase();
  let el = document.getElementById(`article-evidence-${cleanId}`) || document.querySelector(`[data-evidence-id="${cleanId}"]`);
  if (!el && typeof window.__filterStorylinePublisher === "function") {
    // If hidden by current publisher filter, reset filter to reveal all storyline articles
    window.__filterStorylinePublisher("");
    el = document.getElementById(`article-evidence-${cleanId}`) || document.querySelector(`[data-evidence-id="${cleanId}"]`);
  }
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.classList.add('citation-highlight-pulse');
    setTimeout(() => {
      el.classList.remove('citation-highlight-pulse');
    }, 2400);
  } else {
    console.warn("Evidence card not found in current view:", cleanId);
  }
};

window.__toggleQualityAuditPanel = () => {
  const panel = document.getElementById("dossier-audit-panel");
  if (!panel) return;
  if (panel.tagName === "DETAILS") {
    panel.open = !panel.open;
    if (panel.open) {
      panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  } else {
    panel.classList.toggle("hidden");
  }
};

const THAI_MONTHS_SHORT = [
  "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
  "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."
];

export function formatEditorialDateTime(dateStr) {
  if (!dateStr) return "";
  const str = String(dateStr).trim();
  const isoMatch = str.match(/^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T\s](\d{1,2}):(\d{1,2})(?::\d{1,2})?)?/);
  if (isoMatch) {
    const [, y, m, d, hh, mm] = isoMatch;
    const day = parseInt(d, 10);
    const month = THAI_MONTHS_SHORT[parseInt(m, 10) - 1] || m;
    if (hh !== undefined && mm !== undefined) {
      const hours = hh.padStart(2, "0");
      const mins = mm.padStart(2, "0");
      return `${day} ${month} • ${hours}:${mins} น.`;
    }
    const thaiYear = parseInt(y, 10) > 2400 ? y : parseInt(y, 10) + 543;
    return `${day} ${month} ${thaiYear}`;
  }

  const d = new Date(str);
  if (!isNaN(d.getTime())) {
    const day = d.getDate();
    const month = THAI_MONTHS_SHORT[d.getMonth()];
    const hours = String(d.getHours()).padStart(2, "0");
    const mins = String(d.getMinutes()).padStart(2, "0");
    return `${day} ${month} • ${hours}:${mins} น.`;
  }

  return str;
}

export function formatEditorialDateOnly(dateStr) {
  if (!dateStr) return "อัปเดตล่าสุด • วันนี้";
  const str = String(dateStr).trim();
  const isoMatch = str.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (isoMatch) {
    const [, y, m, d] = isoMatch;
    const day = parseInt(d, 10);
    const month = THAI_MONTHS_SHORT[parseInt(m, 10) - 1] || m;
    const thaiYear = parseInt(y, 10) > 2400 ? y : parseInt(y, 10) + 543;
    return `อัปเดตล่าสุด • ${day} ${month} ${thaiYear}`;
  }
  const d = new Date(str);
  if (!isNaN(d.getTime())) {
    const day = d.getDate();
    const month = THAI_MONTHS_SHORT[d.getMonth()];
    const thaiYear = d.getFullYear() > 2400 ? d.getFullYear() : d.getFullYear() + 543;
    return `อัปเดตล่าสุด • ${day} ${month} ${thaiYear}`;
  }
  return str.startsWith("อัปเดตล่าสุด") ? str : `อัปเดตล่าสุด • ${str}`;
}

export function renderCitations(citations = []) {
  if (!citations.length) return "";
  const visible = citations.slice(0, 3);
  const hidden = citations.slice(3);

  const renderChip = (id) => `
    <button type="button" onclick="window.__inspectCitation('${esc(id)}')" 
      class="px-2 py-0.5 text-[11px] font-mono rounded bg-slate-100 hover:bg-slate-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 text-slate-600 dark:text-zinc-300 border border-slate-200 dark:border-zinc-700 cursor-pointer">
      🔗 ${esc(id)}
    </button>`;

  if (hidden.length === 0) {
    return `<div class="flex items-center gap-1.5 flex-wrap pt-1">${visible.map(renderChip).join("")}</div>`;
  }

  return `
    <div class="flex items-center gap-1.5 flex-wrap pt-1">
      ${visible.map(renderChip).join("")}
      <details class="inline">
        <summary class="list-none inline-flex cursor-pointer px-2 py-0.5 text-[11px] font-mono font-semibold rounded bg-amber-50 dark:bg-amber-500/10 hover:bg-amber-100 dark:hover:bg-amber-500/20 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-500/30">
          + อีก ${hidden.length} แหล่งข่าว
        </summary>
        <div class="flex items-center gap-1.5 flex-wrap mt-1.5 p-2 rounded-lg bg-slate-50 dark:bg-zinc-800/80 border border-slate-200 dark:border-zinc-700">
          ${hidden.map(renderChip).join("")}
        </div>
      </details>
    </div>
  `;
}

export function showStorylineAiLoading() {
  const section = document.getElementById("storyline-ai-section");
  if (!section) return;
  section.innerHTML = `
    <div class="p-6 rounded-xl bg-slate-50 dark:bg-zinc-800/50 border border-slate-200 dark:border-zinc-700 text-center space-y-3 animate-fade-in">
      <svg class="animate-spin h-7 w-7 text-amber-500 mx-auto" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2.5"></circle>
        <path class="opacity-80" d="M12 2a10 10 0 0110 10" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="2.5"></path>
      </svg>
      <div>
        <p class="text-xs sm:text-sm font-bold text-slate-800 dark:text-zinc-200">AI กำลังสร้างแบบจำลองพัฒนาการของเหตุการณ์...</p>
        <p class="text-[11px] text-slate-500 dark:text-zinc-400 mt-0.5">คัดกรองหลักฐาน แยกข้อเท็จจริง ข้อขัดแย้ง และตรวจจับข่าวไม่เกี่ยวข้อง</p>
      </div>
    </div>
  `;
}

export function renderStorylineAiSynthesis(synthesisData) {
  const section = document.getElementById("storyline-ai-section");
  if (!section || !synthesisData) return;

  if (currentStorylineDataCache && checkIsSportsCluster(currentStorylineDataCache, currentStorylineDataCache.articles || [])) {
    return renderSportsAiDigest(synthesisData, currentStorylineDataCache.articles || []);
  }

  const s = synthesisData;
  const progressionTimeline = Array.isArray(s.progression_timeline) ? s.progression_timeline : [];
  const confirmedFacts = Array.isArray(s.confirmed_facts) ? s.confirmed_facts : [];
  const conflicts = Array.isArray(s.conflicts) ? s.conflicts : [];
  const unknowns = Array.isArray(s.unknowns) ? s.unknowns : [];
  const outliers = Array.isArray(s.irrelevant_articles) ? s.irrelevant_articles : [];
  const politicalContexts = Array.isArray(s.political_contexts) ? s.political_contexts : [];
  const metrics = s.metrics;

  const summaryText = s.executive_summary || s.summary || "";

  // Optionally update the audit text & panel if present in DOM
  const totalExcluded = outliers.length + politicalContexts.length;
  const excludedCount = metrics?.excluded_count ?? totalExcluded;
  let evidenceCount = metrics?.synthesized_evidence_count;
  if (typeof evidenceCount !== "number") {
    const usedIds = new Set();
    progressionTimeline.forEach(t => (t.evidence_ids || []).forEach(id => usedIds.add(id)));
    confirmedFacts.forEach(f => (f.evidence_ids || []).forEach(id => usedIds.add(id)));
    conflicts.forEach(c => (c.sides || []).forEach(sd => sd.evidence_id && usedIds.add(sd.evidence_id)));
    evidenceCount = usedIds.size || Math.max(1, (metrics?.candidate_count || 0) - excludedCount);
  }

  const isHalted = s.synthesis_status === "halted_mismatch";
  const isSingleSource = s.synthesis_status === "single_source" || s.is_single_source || evidenceCount === 1;

  const toggleTextEl = document.getElementById("storyline-audit-toggle-text");
  if (toggleTextEl) {
    const totalCount = metrics?.candidate_count ?? (evidenceCount + excludedCount);
    if (isHalted) {
      toggleTextEl.innerHTML = `<span class="text-amber-600 dark:text-amber-400 font-semibold">ระงับการสังเคราะห์ (Candidate Mismatch)</span> • คัดออก ${excludedCount} รายการ`;
    } else if (isSingleSource) {
      toggleTextEl.innerHTML = `สรุปจากแหล่งข่าวเดียว (<strong class="text-sky-600 dark:text-sky-400 font-semibold">1</strong>/${totalCount} ข่าว) ${excludedCount > 0 ? `(คัดออก ${excludedCount})` : ""}`;
    } else {
      toggleTextEl.innerHTML = `สังเคราะห์จาก <strong class="text-emerald-700 dark:text-emerald-400 font-semibold">${evidenceCount}</strong>/${totalCount} ข่าว ${excludedCount > 0 ? `(คัดออก ${excludedCount})` : ""}`;
    }
  }

  // ── Mode 1: Halted Mismatch Alert (Candidate Set incongruent with Headline) ──
  if (isHalted) {
    section.innerHTML = `
      <div class="p-5 sm:p-6 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-900 dark:text-amber-200 space-y-4">
        <div class="flex items-start gap-3.5">
          <span class="material-symbols-outlined text-amber-600 dark:text-amber-400 text-[26px] shrink-0 mt-0.5">warning</span>
          <div class="space-y-1.5">
            <h4 class="font-bold text-sm sm:text-base text-amber-950 dark:text-amber-100">
              ระงับการสังเคราะห์อัตโนมัติชั่วคราว (Candidate Set Mismatch)
            </h4>
            <p class="text-xs sm:text-sm text-amber-800 dark:text-amber-300/90 leading-relaxed">
              ${esc(s.status_message || "ระบบตรวจพบว่าชุดข่าวที่รวบรวมได้ ไม่สอดคล้องกับเหตุการณ์ในพาดหัว เพื่อป้องกันการสังเคราะห์ข้อมูลผิดเรื่อง ระบบจึงระงับการสร้างบทสรุปภาพรวมและไทม์ไลน์")}
            </p>
          </div>
        </div>
        <div class="pt-3 border-t border-amber-500/20 flex items-center justify-between flex-wrap gap-2 text-xs">
          <span class="text-amber-700 dark:text-amber-400 font-medium">คัดแยกข่าวที่ไม่ตรงเหตุการณ์ออกทั้งหมด ${excludedCount} รายการ</span>
          <button type="button" onclick="window.__toggleQualityAuditPanel && window.__toggleQualityAuditPanel()" class="px-3.5 py-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-900 dark:text-amber-200 font-semibold transition cursor-pointer">
            ตรวจสอบรายการข่าวที่ถูกคัดออก
          </button>
        </div>
      </div>
    `;
    return;
  }

  section.innerHTML = `
    <!-- Executive Summary: เส้นขอบดิ่งบางหรูหราแบบฉบับ Editorial -->
    <div class="pl-4 sm:pl-5 py-1 border-l-2 ${isSingleSource ? 'border-sky-500/80 dark:border-sky-400/80' : 'border-amber-600/80 dark:border-amber-400/80'} text-slate-700 dark:text-zinc-200 text-sm sm:text-base leading-relaxed">
      ${esc(summaryText || "รวบรวมและสังเคราะห์ประเด็นสำคัญจากสำนักข่าวทั้งหมด")}
    </div>

    <!-- Two-Column Content: ซ้าย = ไทม์ไลน์ (7 cols) | ขวา = จุดยืนที่ต่างกัน & สิ่งที่รอการยืนยัน (5 cols) -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 pt-2">
      <!-- คอลัมน์ซ้าย (7 ส่วน): ลำดับเหตุการณ์และข้อเท็จจริงที่ยืนยันแล้ว -->
      <div class="lg:col-span-7 space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-zinc-400 flex items-center gap-1.5">
            <span class="material-symbols-outlined text-[16px] ${isSingleSource ? 'text-sky-600 dark:text-sky-400' : 'text-amber-600 dark:text-amber-400'}">${isSingleSource ? 'feed' : 'timeline'}</span>
            ${isSingleSource ? 'ลำดับเหตุการณ์เบื้องต้น (จากรายงานแหล่งข่าวเดียว)' : 'ลำดับเหตุการณ์สำคัญ (ยืนยันตรงกันทุกสื่อ)'}
          </h3>
        </div>

        <!-- Vertical Timeline -->
        <div class="relative pl-4 border-l-2 border-slate-200 dark:border-zinc-700 space-y-5">
          ${progressionTimeline.length > 0 ? progressionTimeline.map((item, idx) => {
            const isLatest = idx === progressionTimeline.length - 1;
            const isFirst = idx === 0;
            const dotBg = isLatest 
              ? (isSingleSource ? "bg-sky-500" : "bg-emerald-500")
              : (isFirst ? "bg-amber-500" : "bg-slate-300 dark:bg-zinc-600");
            const timeFormatted = formatEditorialDateTime(item.event_time);

            return `
              <div class="relative space-y-1.5">
                <div class="absolute -left-[21px] top-1.5 w-2.5 h-2.5 rounded-full ${dotBg} ring-4 ring-white dark:ring-zinc-900"></div>
                ${timeFormatted ? `
                  <div class="flex items-center gap-2 text-xs ${isLatest ? (isSingleSource ? 'text-sky-600 dark:text-sky-400 font-semibold' : 'text-emerald-600 dark:text-emerald-400 font-semibold') : 'text-slate-400 dark:text-zinc-500'} font-mono">
                    <span>${isLatest ? 'ล่าสุด • ' : ''}${esc(timeFormatted)}</span>
                  </div>
                ` : ""}
                <p class="text-sm ${isLatest ? 'font-medium text-slate-900 dark:text-white' : 'text-slate-800 dark:text-zinc-200'} leading-relaxed">
                  ${esc(item.description)}
                </p>
                ${renderCitations(item.evidence_ids || [])}
              </div>
            `;
          }).join("") : `
            <p class="text-xs text-slate-400 dark:text-zinc-500">ยังไม่มีข้อมูลลำดับเหตุการณ์</p>
          `}
        </div>
      </div>

      <!-- คอลัมน์ขวา (5 ส่วน): มุมมองที่ต่างกัน & ประเด็นที่ยังไม่ชัดเจน -->
      <div class="lg:col-span-5 space-y-5">
        ${conflicts.length > 0 ? `
          <div class="p-4 sm:p-5 rounded-xl bg-amber-50/50 dark:bg-amber-950/15 border border-amber-200/70 dark:border-amber-500/20 space-y-3.5">
            <h3 class="text-xs font-bold uppercase tracking-wider text-amber-900 dark:text-amber-300 flex items-center gap-1.5">
              <span class="material-symbols-outlined text-[16px]">balance</span>
              จุดยืนและมุมมองที่ต่างกัน (${conflicts.length} ประเด็น)
            </h3>

            <div class="space-y-3">
              ${conflicts.map(c => `
                <div class="p-3.5 rounded-lg bg-white dark:bg-zinc-900 border border-amber-200/60 dark:border-zinc-700 space-y-2.5 shadow-2xs">
                  <div class="text-[11px] font-bold text-slate-500 dark:text-zinc-400 uppercase tracking-wide">${esc(c.topic || "ประเด็นข้อคิดเห็น")}</div>
                  <div class="space-y-2.5 text-xs">
                    ${(c.sides || []).map((sd, sIdx) => `
                      <div class="${sIdx > 0 ? 'border-t border-slate-100 dark:border-zinc-800/80 pt-2.5' : ''} space-y-1">
                        <div class="flex items-center gap-1.5 flex-wrap">
                          <span class="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0"></span>
                          <span class="font-mono font-bold text-[11px] text-slate-800 dark:text-zinc-200">${esc(sd.source || "สื่อ")}</span>
                        </div>
                        <p class="text-xs text-slate-600 dark:text-zinc-300 leading-relaxed pl-3 border-l-2 border-amber-300 dark:border-amber-500/40 break-words">
                          "${esc(sd.quote || sd.stance || "")}"
                        </p>
                      </div>
                    `).join("")}
                  </div>
                </div>
              `).join("")}
            </div>
          </div>
        ` : (isSingleSource ? `
          <div class="p-4 rounded-xl bg-sky-50/70 dark:bg-sky-950/25 border border-sky-200 dark:border-sky-500/30 text-xs text-sky-900 dark:text-sky-200 flex items-start gap-2.5">
            <span class="material-symbols-outlined text-sky-600 dark:text-sky-400 text-[18px] shrink-0 mt-0.5">info</span>
            <div>
              <div class="font-bold text-sky-950 dark:text-sky-100">ข้อมูลจากแหล่งข่าวเดียว (Single-Source Report)</div>
              <p class="text-sky-800 dark:text-sky-300/90 mt-0.5 leading-relaxed">
                รายงานนี้อ้างอิงจาก ${esc(metrics?.synthesized_publishers?.[0] || "สำนักข่าวฉบับเดียว")} เพียงแหล่งเดียว ยังไม่สามารถเปรียบเทียบหรือยืนยันความสอดคล้องข้ามสำนักข่าวได้
              </p>
            </div>
          </div>
        ` : `
          <div class="p-4 rounded-xl bg-emerald-50/60 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-500/20 text-xs text-emerald-800 dark:text-emerald-300 flex items-start gap-2.5">
            <span class="material-symbols-outlined text-emerald-600 dark:text-emerald-400 text-[18px] shrink-0 mt-0.5">verified</span>
            <div>
              <div class="font-bold">ความสอดคล้องของข้อมูลข่าว</div>
              <p class="text-emerald-700 dark:text-emerald-400/90 mt-0.5 leading-relaxed">ทุกสำนักข่าวรายงานข้อมูลสอดคล้องกัน ไม่พบจุดยืนหรือข้อเท็จจริงที่ขัดแย้งกันอย่างมีนัยสำคัญ</p>
            </div>
          </div>
        `)}

        ${unknowns.length > 0 ? `
          <div class="p-4 rounded-xl bg-rose-50/50 dark:bg-rose-950/15 border border-rose-200/70 dark:border-rose-500/20 flex items-start gap-3">
            <span class="material-symbols-outlined text-rose-500 text-[18px] mt-0.5 shrink-0">help</span>
            <div class="space-y-1 text-xs">
              <div class="font-bold text-rose-900 dark:text-rose-300">ประเด็นที่รอการยืนยัน</div>
              ${unknowns.map(u => `
                <p class="text-rose-700 dark:text-rose-200/80 leading-relaxed">• ${esc(u.question || u.why_unclear || "")}</p>
              `).join("")}
            </div>
          </div>
        ` : ""}
      </div>
    </div>
  `;
}

export function renderStorylineAiSummary(summaryData) {
  if (!summaryData) return;
  // If it's already an EventProgressionSynthesis
  if (summaryData.executive_summary || summaryData.progression_timeline || summaryData.confirmed_facts) {
    return renderStorylineAiSynthesis(summaryData);
  }
  // Convert legacy format to progression synthesis structure
  const converted = {
    event_id: "",
    headline: "บทสรุปสังเคราะห์ข้ามสำนักข่าว",
    executive_summary: summaryData.summary || "",
    overall_sentiment: summaryData.sentiment || "Neutral",
    progression_timeline: (summaryData.bullets || []).map((b, i) => ({
      phase: i === 0 ? "จุดเริ่มต้น" : (i === (summaryData.bullets.length - 1) ? "ความคืบหน้าล่าสุด" : "พัฒนาการหลัก"),
      event_time: "ล่าสุด",
      description: b,
      evidence_ids: [`art_0${i + 1}`],
      significance: "",
    })),
    confirmed_facts: (summaryData.bullets || []).slice(0, 2).map((b, i) => ({
      fact: b,
      supporting_sources: ["สำนักข่าวที่รายงาน"],
      evidence_ids: [`art_0${i + 1}`],
      confidence: "รายงานตรงกัน",
    })),
    conflicts: [],
    unknowns: [],
    irrelevant_articles: [],
    last_synthesized_at: "LIVE",
    generated_by: "ai",
  };
  return renderStorylineAiSynthesis(converted);
}

// ── Dedicated Sports Intelligence & Multi-Sport Aggregation ─────────

export function classifySportsArticle(art) {
  const title = (art.title || "").toLowerCase();
  const summary = (art.summary || "").toLowerCase();
  const url = (art.url || "").toLowerCase();
  const text = `${title} ${summary} ${url}`;

  let discipline = "other_sports";
  let disciplineLabel = "กีฬาอื่นๆ & พาราเกมส์";
  let leagueBadge = "🏃 กีฬาอื่นๆ";
  let leagueBadgeClass = "bg-slate-700 text-slate-100";

  // Check Football Europe & International
  if (/ucl|แชมเปี้ยนส์ ลีก|แชมเปียนส์ ลีก|ชปล|พรีเมียร์ลีก|premier league|ยูโรปา|europa|ลาลีกา|บุนเดสลีกา|กัลโช่|แมนฯ ซิตี้|แมนซิตี้|เปแอสเช|psg|แมนยู|แมนฯ ยูไนเต็ด|ลิเวอร์พูล|อาร์เซน่อล|อาร์เซนอล|เชลซี|สเปอร์ส|มาดริด|แอต\.มาดริด|บาร์เซโลน่า|บาเยิร์น|ดอร์ทมุนด์|ลินซ์|ลีลล์|คริสตัล พาเลซ|ลียง|โคโม|เฟเยนูร์ด|ลูกหนังยุโรป/.test(text)) {
    discipline = "football_europe";
    disciplineLabel = "ฟุตบอลยุโรป & สากล";
    if (/ucl|แชมเปี้ยนส์ ลีก|แชมเปียนส์ ลีก|ชปล/.test(text)) {
      leagueBadge = "⚽ UCL";
      leagueBadgeClass = "bg-indigo-900 text-indigo-100 border border-indigo-700/50";
    } else if (/พรีเมียร์ลีก|premier league/.test(text)) {
      leagueBadge = "⚽ พรีเมียร์ลีก";
      leagueBadgeClass = "bg-purple-900 text-purple-100 border border-purple-700/50";
    } else if (/ยูโรปา|europa/.test(text)) {
      leagueBadge = "⚽ ยูโรปาลีก";
      leagueBadgeClass = "bg-amber-900 text-amber-100 border border-amber-700/50";
    } else {
      leagueBadge = "⚽ ฟุตบอลยุโรป";
      leagueBadgeClass = "bg-blue-900 text-blue-100 border border-blue-700/50";
    }
  }
  // Check Thai Football & Asian Club
  else if (/ไทยลีก|ไทยพรีเมียร์ลีก|ช้างศึก|ทีมชาติไทย|เอเชียน คัพ|เอเชี่ยนคัพ|asian cup|คิงส์คัพ|ท่าเรือ|การท่าเรือ|บีจี ปทุม|จามจุรี|คาชิว่า|คาชิวะ|acl|เอเอฟซี|แอดิเลด|บอลนักเรียน|ฟุตบอลนักเรียน|กรมพลศึกษา|ไทย วีเมนส์ ลีก|ฟุตซอล|ฟุตบอลไทย|บอลไทย/.test(text)) {
    discipline = "football_thai";
    disciplineLabel = "ฟุตบอลไทย & บอลเอเชีย";
    if (/ไทยลีก 3/.test(text)) {
      leagueBadge = "🇹🇭 ไทยลีก 3";
    } else if (/ไทยลีก/.test(text)) {
      leagueBadge = "🇹🇭 ไทยลีก";
    } else if (/เอเชียน คัพ|เอเชี่ยนคัพ|ช้างศึก|ทีมชาติไทย|คิงส์คัพ/.test(text)) {
      leagueBadge = "🇹🇭 ช้างศึก / เอเชียนคัพ";
    } else if (/acl|เอเอฟซี|คาชิว่า|คาชิวะ|แอดิเลด/.test(text)) {
      leagueBadge = "🌏 ACL เอเชีย";
    } else if (/บอลนักเรียน|นักเรียนไทย/.test(text)) {
      leagueBadge = "🇹🇭 บอลนักเรียนโลก";
    } else {
      leagueBadge = "🇹🇭 ฟุตบอลไทย";
    }
    leagueBadgeClass = "bg-rose-900 text-rose-100 border border-rose-700/50";
  }
  // Check Volleyball
  else if (/วอลเลย์|ลูกยาง|pmyc|วอลเลย์บอล/.test(text)) {
    discipline = "volleyball";
    disciplineLabel = "วอลเลย์บอล & กีฬาในร่ม";
    if (/ชายหาด/.test(text)) {
      leagueBadge = "🏐 วอลเลย์ชายหาด";
    } else {
      leagueBadge = "🏐 ลูกยาง / PMYC";
    }
    leagueBadgeClass = "bg-amber-800 text-amber-100 border border-amber-600/50";
  }
  // Other Sports & Para Games
  else {
    discipline = "other_sports";
    disciplineLabel = "กีฬาอื่นๆ & พาราเกมส์";
    if (/พาราเกมส์|คนพิการ/.test(text)) {
      leagueBadge = "♿ เอเชี่ยนพาราเกมส์";
      leagueBadgeClass = "bg-emerald-900 text-emerald-100 border border-emerald-700/50";
    } else if (/เทนนิส|tennis/.test(text)) {
      leagueBadge = "🎾 เทนนิส";
      leagueBadgeClass = "bg-lime-900 text-lime-100 border border-lime-700/50";
    } else if (/แบดมินตัน|badminton/.test(text)) {
      leagueBadge = "🏸 แบดมินตัน";
      leagueBadgeClass = "bg-teal-900 text-teal-100 border border-teal-700/50";
    } else if (/มวย|boxing/.test(text)) {
      leagueBadge = "🥊 มวย";
      leagueBadgeClass = "bg-red-950 text-red-200 border border-red-800/50";
    } else if (/กอล์ฟ|golf/.test(text)) {
      leagueBadge = "⛳ กอล์ฟ";
      leagueBadgeClass = "bg-green-900 text-green-100 border border-green-700/50";
    } else {
      leagueBadge = "🏃 กีฬาอื่นๆ";
      leagueBadgeClass = "bg-slate-800 text-slate-200 border border-slate-700/50";
    }
  }

  // Content type
  let contentType = "general";
  let contentTypeLabel = "ข่าวทั่วไป";
  let isResult = false;
  let scoreHighlight = "";

  if (/ผลบอล|ผลการแข่งขัน|คว้าชัย|บุกชนะ|เปิดบ้านชนะ|ชนะ|พ่าย|พ่ายยับ|แพ้|ถล่ม|เสมอกัน|เสมอ|คว้าแชมป์|คว้า 3 แต้ม|แฮตทริก|ตารางคะแนน|ล้มมือวาง/.test(title)) {
    contentType = "result";
    contentTypeLabel = "ผลการแข่งขัน";
    isResult = true;
    const scoreMatch = title.match(/(\d+[\s-–]\d+|\d+\s*คน|แฮตทริก|คว้า\s*3\s*แต้ม|คว้าแชมป์)/);
    if (scoreMatch) {
      scoreHighlight = scoreMatch[1];
    }
  } else if (/โปรแกรมบอล|เปิดโปรแกรม|โปรแกรมเตะ|ดูบอลสด|วิเคราะห์บอล|ตารางแข่ง|เปิดรับสมัคร|นัดแรกฟาดแข้ง|ฟาดแข้ง\s*\d+/.test(title)) {
    contentType = "schedule";
    contentTypeLabel = "โปรแกรมแข่ง";
  }

  return {
    discipline,
    disciplineLabel,
    leagueBadge,
    leagueBadgeClass,
    contentType,
    contentTypeLabel,
    isResult,
    scoreHighlight,
  };
}

export function checkIsSportsCluster(storyData, articles = []) {
  if (storyData && storyData.category === "sports") return true;
  if (!articles || !articles.length) return false;
  const sportsKw = /ucl|ชปล|พรีเมียร์ลีก|ไทยลีก|ฟุตบอล|กีฬา|วอลเลย์บอล|ลูกยาง|ผลบอล|แข่ง|แชมป์|แต้ม|สโมสร|นักเตะ|เอเอฟซี|แชมเปียนส์|แชมเปี้ยนส์|พาราเกมส์|เทนนิส|แบดมินตัน/;
  let sportsCount = 0;
  for (const a of articles) {
    if (a.category === "sports") {
      sportsCount++;
    } else if (a.url && (a.url.includes("/sport") || a.url.includes("/football") || a.url.includes("/ผลบอล"))) {
      sportsCount++;
    } else if (sportsKw.test((a.title || "").toLowerCase())) {
      sportsCount++;
    }
  }
  return (sportsCount / articles.length) >= 0.35;
}

export function renderSportsAiDigest(synthesisData, articles = []) {
  const section = document.getElementById("storyline-ai-section");
  if (!section || !synthesisData) return;

  const summaryText = synthesisData.executive_summary || synthesisData.summary || "สรุปภาพรวมผลการแข่งขันและไฮไลต์กีฬาประจำวัน";

  // Ensure articles have sports classification
  const enrichedArticles = articles.map(a => {
    if (!a._sportsMeta) a._sportsMeta = classifySportsArticle(a);
    return a;
  });

  const euArticles = enrichedArticles.filter(a => a._sportsMeta?.discipline === "football_europe");
  const thArticles = enrichedArticles.filter(a => a._sportsMeta?.discipline === "football_thai");
  const volleyArticles = enrichedArticles.filter(a => a._sportsMeta?.discipline === "volleyball");
  const otherArticles = enrichedArticles.filter(a => a._sportsMeta?.discipline === "other_sports");

  section.innerHTML = `
    <!-- Sports Overview Card -->
    <div class="pl-4 sm:pl-5 py-1 border-l-2 border-amber-600/80 dark:border-amber-400/80 text-slate-800 dark:text-zinc-100 text-sm sm:text-base leading-relaxed space-y-1.5">
      <div class="flex items-center gap-2 font-bold text-amber-700 dark:text-amber-400 text-xs uppercase font-mono tracking-wider">
        <span class="material-symbols-outlined text-[18px]">sports_and_outdoors</span>
        <span>กระดานสรุปผลและไฮไลต์กีฬา (AI Sports Intelligence Digest)</span>
      </div>
      <p class="leading-relaxed font-normal">${esc(summaryText)}</p>
    </div>

    <!-- Sports Discipline Highlights Grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-1">
      <!-- 1. European Football -->
      ${euArticles.length > 0 ? `
        <div class="sports-digest-section-card bg-white dark:bg-zinc-900 border border-slate-200 dark:border-zinc-800 rounded-xl p-4 space-y-3 shadow-2xs">
          <div class="flex items-center justify-between border-b border-slate-100 dark:border-zinc-800 pb-2">
            <span class="font-bold text-xs text-indigo-700 dark:text-indigo-400 flex items-center gap-1.5">
              <span>⚽</span> ฟุตบอลยุโรป & UCL
            </span>
            <span class="text-[10px] font-mono font-bold bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 px-2 py-0.5 rounded-full">${euArticles.length} ข่าว</span>
          </div>
          <div class="space-y-2 text-xs">
            ${euArticles.slice(0, 4).map(a => `
              <div class="p-2 rounded-lg bg-slate-50 dark:bg-zinc-800/60 hover:bg-slate-100 dark:hover:bg-zinc-800 transition-colors cursor-pointer" onclick="window.__openPreview('${esc(a.url)}')">
                <div class="font-semibold text-slate-800 dark:text-zinc-200 line-clamp-2">${esc(a.title)}</div>
                <div class="flex items-center gap-2 mt-1.5 text-[10px] font-mono text-slate-500 dark:text-zinc-400">
                  <span class="font-bold">${esc(a.source || "ข่าว")}</span>
                  ${a._sportsMeta?.scoreHighlight ? `<span class="sports-score-highlight text-[9px]">${esc(a._sportsMeta.scoreHighlight)}</span>` : ""}
                </div>
              </div>
            `).join("")}
          </div>
        </div>
      ` : ""}

      <!-- 2. Thai Football & Asian Clubs -->
      ${thArticles.length > 0 ? `
        <div class="sports-digest-section-card bg-white dark:bg-zinc-900 border border-slate-200 dark:border-zinc-800 rounded-xl p-4 space-y-3 shadow-2xs">
          <div class="flex items-center justify-between border-b border-slate-100 dark:border-zinc-800 pb-2">
            <span class="font-bold text-xs text-rose-700 dark:text-rose-400 flex items-center gap-1.5">
              <span>🇹🇭</span> ฟุตบอลไทย & สโมสรเอเชีย
            </span>
            <span class="text-[10px] font-mono font-bold bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 px-2 py-0.5 rounded-full">${thArticles.length} ข่าว</span>
          </div>
          <div class="space-y-2 text-xs">
            ${thArticles.slice(0, 4).map(a => `
              <div class="p-2 rounded-lg bg-slate-50 dark:bg-zinc-800/60 hover:bg-slate-100 dark:hover:bg-zinc-800 transition-colors cursor-pointer" onclick="window.__openPreview('${esc(a.url)}')">
                <div class="font-semibold text-slate-800 dark:text-zinc-200 line-clamp-2">${esc(a.title)}</div>
                <div class="flex items-center gap-2 mt-1.5 text-[10px] font-mono text-slate-500 dark:text-zinc-400">
                  <span class="font-bold">${esc(a.source || "ข่าว")}</span>
                  ${a._sportsMeta?.scoreHighlight ? `<span class="sports-score-highlight text-[9px]">${esc(a._sportsMeta.scoreHighlight)}</span>` : ""}
                </div>
              </div>
            `).join("")}
          </div>
        </div>
      ` : ""}

      <!-- 3. Volleyball & Other Sports -->
      ${(volleyArticles.length > 0 || otherArticles.length > 0) ? `
        <div class="sports-digest-section-card bg-white dark:bg-zinc-900 border border-slate-200 dark:border-zinc-800 rounded-xl p-4 space-y-3 shadow-2xs">
          <div class="flex items-center justify-between border-b border-slate-100 dark:border-zinc-800 pb-2">
            <span class="font-bold text-xs text-amber-700 dark:text-amber-400 flex items-center gap-1.5">
              <span>🏐</span> วอลเลย์บอล & กีฬาอื่นๆ
            </span>
            <span class="text-[10px] font-mono font-bold bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 px-2 py-0.5 rounded-full">${volleyArticles.length + otherArticles.length} ข่าว</span>
          </div>
          <div class="space-y-2 text-xs">
            ${[...volleyArticles, ...otherArticles].slice(0, 4).map(a => `
              <div class="p-2 rounded-lg bg-slate-50 dark:bg-zinc-800/60 hover:bg-slate-100 dark:hover:bg-zinc-800 transition-colors cursor-pointer" onclick="window.__openPreview('${esc(a.url)}')">
                <div class="font-semibold text-slate-800 dark:text-zinc-200 line-clamp-2">${esc(a.title)}</div>
                <div class="flex items-center gap-2 mt-1.5 text-[10px] font-mono text-slate-500 dark:text-zinc-400">
                  <span class="font-bold">${esc(a.source || "ข่าว")}</span>
                  <span class="text-[9px] text-slate-400 font-mono">${esc(a._sportsMeta?.leagueBadge || "กีฬา")}</span>
                </div>
              </div>
            `).join("")}
          </div>
        </div>
      ` : ""}
    </div>
  `;
}

export function renderSportsStorylineView(
  storyData,
  activeSourceFilter = "",
  activeSportDisciplineFilter = "",
  activeSportContentTypeFilter = "",
  bookmarkedMap = {}
) {
  const container = document.getElementById("storyline-view");
  if (!container || !storyData) return;

  currentStorylineDataCache = storyData;

  const storyId = storyData.macro_event_id || storyData.story_id || storyData.cluster_id || "";
  const rawArticles = Array.isArray(storyData.articles) ? storyData.articles : [];

  // Sort articles by published/fetched time descending (latest sports news first!)
  const sortedArticles = [...rawArticles].sort((a, b) => {
    const timeA = new Date(a.fetched_at || a.created_at || 0).getTime();
    const timeB = new Date(b.fetched_at || b.created_at || 0).getTime();
    return timeB - timeA;
  });

  // Enrich all articles with sports classification
  sortedArticles.forEach(art => {
    art._sportsMeta = classifySportsArticle(art);
  });

  // Calculate discipline counts
  const disciplineCounts = {
    football_europe: 0,
    football_thai: 0,
    volleyball: 0,
    other_sports: 0,
  };
  const contentTypeCounts = {
    result: 0,
    schedule: 0,
    general: 0,
  };
  const outletCounts = {};

  sortedArticles.forEach(art => {
    const meta = art._sportsMeta;
    if (disciplineCounts[meta.discipline] !== undefined) {
      disciplineCounts[meta.discipline]++;
    } else {
      disciplineCounts.other_sports++;
    }
    if (contentTypeCounts[meta.contentType] !== undefined) {
      contentTypeCounts[meta.contentType]++;
    } else {
      contentTypeCounts.general++;
    }
    const src = art.source || "ข่าว";
    outletCounts[src] = (outletCounts[src] || 0) + 1;
  });

  const outlets = Object.keys(outletCounts).sort((a, b) => outletCounts[b] - outletCounts[a]);

  // Filter articles
  let filteredArticles = sortedArticles;
  if (activeSportDisciplineFilter) {
    filteredArticles = filteredArticles.filter(a => a._sportsMeta?.discipline === activeSportDisciplineFilter);
  }
  if (activeSportContentTypeFilter) {
    filteredArticles = filteredArticles.filter(a => a._sportsMeta?.contentType === activeSportContentTypeFilter);
  }
  if (activeSourceFilter) {
    filteredArticles = filteredArticles.filter(a => (a.source || "").toLowerCase() === activeSourceFilter.toLowerCase());
  }

  // Dynamic Hero Title: If it's a multi-sport collection, provide a clear sports hub title
  const activeDisciplinesCount = Object.values(disciplineCounts).filter(c => c > 0).length;
  const isMultiDiscipline = activeDisciplinesCount >= 2;
  const sportsHeroTitle = isMultiDiscipline
    ? "ศูนย์รวมข่าวกีฬาเด่น ผลบอล และความเคลื่อนไหวล่าสุด"
    : (storyData.topic_title || storyData.headline || storyData.title || "รวมรายงานข่าวกีฬาประจำวัน");

  // Sport Discipline Tabs
  const discTabs = [
    { id: "", label: "ทุกประเภทกีฬา", icon: "🌟", count: sortedArticles.length },
    { id: "football_europe", label: "ฟุตบอลยุโรป & UCL", icon: "⚽", count: disciplineCounts.football_europe },
    { id: "football_thai", label: "ฟุตบอลไทย & เอเชีย", icon: "🇹🇭", count: disciplineCounts.football_thai },
    { id: "volleyball", label: "วอลเลย์บอล & ในร่ม", icon: "🏐", count: disciplineCounts.volleyball },
    { id: "other_sports", label: "กีฬาอื่นๆ & พาราเกมส์", icon: "🏃", count: disciplineCounts.other_sports },
  ].filter(t => t.id === "" || t.count > 0);

  const disciplinePillsHtml = discTabs.map(tab => {
    const isActive = activeSportDisciplineFilter === tab.id;
    return `
      <button type="button"
              class="sports-discipline-pill ${isActive ? 'active' : ''}"
              onclick="window.__filterSportDiscipline('${tab.id}')">
        <span>${tab.icon}</span>
        <span>${tab.label}</span>
        <span class="text-[11px] font-mono font-bold opacity-75">(${tab.count})</span>
      </button>
    `;
  }).join("");

  // Content Type Filter Pills
  const ctypeTabs = [
    { id: "", label: "ทั้งหมด" },
    { id: "result", label: "🏆 ผลการแข่งขัน", count: contentTypeCounts.result },
    { id: "schedule", label: "📅 โปรแกรมแข่ง", count: contentTypeCounts.schedule },
    { id: "general", label: "📢 ข่าวทั่วไป", count: contentTypeCounts.general },
  ].filter(t => t.id === "" || t.count > 0);

  const contentTypePillsHtml = ctypeTabs.map(tab => {
    const isActive = activeSportContentTypeFilter === tab.id;
    return `
      <button type="button"
              class="sports-type-pill ${isActive ? 'active' : ''}"
              onclick="window.__filterSportContentType('${tab.id}')">
        <span>${tab.label}</span>
        ${tab.count !== undefined ? `<span class="opacity-75">(${tab.count})</span>` : ""}
      </button>
    `;
  }).join("");

  // Publisher Filter Pills
  const allPublishersActive = !activeSourceFilter;
  let publisherPillsHtml = `
    <button type="button" 
            class="storyline-publisher-pill ${allPublishersActive ? 'active' : ''}"
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

  // Sports News Articles Grid HTML (No CHRONOLOGY #01, #02...!)
  const articlesGridHtml = filteredArticles.length > 0 ? `
    <div class="storyline-grid-container">
      ${filteredArticles.map((art) => {
        const color = SOURCE_COLORS[art.source] ?? "#1d3557";
        const placeholder = getCategoryPlaceholder("sports");
        const imgSrc = art.image_url || placeholder;
        const isBookmarked = Boolean(bookmarkedMap && bookmarkedMap[art.url]);
        const artJsonEncoded = encodeURIComponent(JSON.stringify(art));
        const perspective = getPerspectiveLabel(art.title, art.source, art.summary);
        const meta = art._sportsMeta || classifySportsArticle(art);

        return `
          <article class="editorial-card transition-all duration-300"
                   data-url="${esc(art.url)}">
            <div class="flex flex-row sm:flex-col flex-1 p-2.5 sm:p-0 cursor-pointer" data-url="${esc(art.url)}" onclick="window.__openPreview(this.dataset.url)">
              <!-- Thumbnail: Left on mobile (108px x 76px), Top on Desktop (compact 144px) -->
              <div class="w-[108px] h-[76px] sm:w-full sm:h-36 relative overflow-hidden shrink-0 rounded-lg sm:rounded-none bg-surface-container-low sm:border-b sm:border-outline-variant/25">
                <img src="${esc(imgSrc)}" alt="${esc(art.title)}" class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" onerror="this.onerror=null; this.src='${placeholder}';" loading="lazy">
                
                <!-- Desktop Only: Sport Discipline / League Badge -->
                <div class="hidden sm:flex absolute top-2 left-2.5 items-center gap-1.5 flex-wrap">
                  <span class="sports-tag-badge ${meta.leagueBadgeClass}">
                    ${meta.leagueBadge}
                  </span>
                </div>

                <!-- Desktop Only: Content Type Badge / Score Callout -->
                <div class="hidden sm:flex absolute top-2 right-2.5 items-center gap-1.5 flex-wrap">
                  ${meta.isResult ? `
                    <span class="sports-tag-badge sports-result-badge">
                      🏆 ผลแข่ง ${meta.scoreHighlight ? `• ${esc(meta.scoreHighlight)}` : ''}
                    </span>
                  ` : (meta.contentType === "schedule" ? `
                    <span class="sports-tag-badge sports-schedule-badge">
                      📅 โปรแกรมแข่ง
                    </span>
                  ` : `
                    <span class="sports-tag-badge sports-general-badge">
                      📢 ความเคลื่อนไหว
                    </span>
                  `)}
                </div>
              </div>

              <!-- Content: Right on mobile, Below on Desktop -->
              <div class="editorial-card-body flex flex-col justify-between sm:justify-start flex-1 min-w-0">
                <!-- Dateline: Desktop top row -->
                <div class="hidden sm:flex items-center justify-between gap-2 mb-1.5">
                  <div class="flex items-center gap-1.5">
                    <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
                    <span class="font-mono text-[11px] font-bold uppercase text-on-surface">${esc(art.source || "ข่าวกีฬา")}</span>
                  </div>
                  <span class="font-mono text-[10px] text-secondary font-semibold">${esc(perspective)}</span>
                </div>

                <!-- Headline -->
                <h3 class="text-[14px] sm:text-[15.5px] font-headline font-bold text-on-surface leading-snug transition-colors group-hover:text-primary line-clamp-2 mb-1 sm:mb-1.5">
                  ${esc(art.title)}
                </h3>

                <!-- Summary (Desktop only) -->
                <div class="hidden sm:block">
                  <p class="text-xs text-on-surface-variant line-clamp-2 leading-relaxed">
                    ${esc(art.summary || "")}
                  </p>
                </div>

                <!-- Mobile Dateline & Source: directly below headline -->
                <div class="flex sm:hidden items-center justify-between gap-1 mt-auto pt-1 text-xs">
                  <div class="flex items-center gap-1.5 min-w-0 text-outline">
                    <span class="w-1.5 h-1.5 rounded-full shrink-0" style="background:${color}"></span>
                    <span class="text-[11px] font-medium text-on-surface-variant/90 truncate">${esc(art.source || "กีฬา")}</span>
                    ${meta.scoreHighlight ? `<span class="text-[10px] font-mono font-bold text-emerald-600 dark:text-emerald-400 shrink-0">🏆 ${esc(meta.scoreHighlight)}</span>` : ''}
                  </div>
                  <div class="flex items-center gap-1 shrink-0" onclick="event.stopPropagation()">
                    <button type="button" 
                            class="p-1 rounded text-outline hover:text-on-surface bookmark-btn ${isBookmarked ? 'active text-amber-500' : ''}"
                            data-url="${esc(art.url)}"
                            onclick="window.__toggleArticleBookmark(event, '${artJsonEncoded}')"
                            title="${isBookmarked ? 'ลบบุ๊กมาร์ก' : 'บันทึกบทความ'}">
                      <span class="material-symbols-outlined text-[15px]" style="${isBookmarked ? "font-variation-settings: 'FILL' 1; color: #f59e0b;" : ""}">
                        ${isBookmarked ? 'bookmark' : 'bookmark_border'}
                      </span>
                    </button>
                    <button type="button" 
                            class="px-2 py-0.5 rounded bg-black/5 dark:bg-white/10 hover:bg-amber-500 hover:text-black text-[10px] font-bold text-on-surface flex items-center gap-0.5 transition-colors cursor-pointer"
                            onclick="window.__openPreviewAndSummarize('${esc(art.url)}')">
                      <span class="material-symbols-outlined text-[11px] text-amber-500" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
                      <span>AI</span>
                    </button>
                  </div>
                </div>

              </div>
            </div>

            <!-- Card Footer Actions (Desktop Only) -->
            <div class="hidden sm:flex mt-auto px-4 py-2 border-t border-outline-variant/25 items-center justify-between gap-2 bg-surface/40">
              <span class="font-mono text-[10px] text-outline uppercase">${formatEditorialDateTime(art.fetched_at || art.created_at)}</span>
              <div class="flex items-center gap-1" onclick="event.stopPropagation()">
                <button type="button" 
                        class="editorial-card-icon-btn bookmark-btn ${isBookmarked ? 'active' : ''}"
                        data-url="${esc(art.url)}"
                        onclick="window.__toggleArticleBookmark(event, '${artJsonEncoded}')"
                        title="${isBookmarked ? 'ลบบุ๊กมาร์ก' : 'บันทึกบทความ'}">
                  <span class="material-symbols-outlined text-[15px]" style="${isBookmarked ? "font-variation-settings: 'FILL' 1;" : ""}">
                    ${isBookmarked ? 'bookmark' : 'bookmark_border'}
                  </span>
                </button>
                <button type="button" 
                        class="editorial-card-icon-btn"
                        onclick="window.__showLessLikeThis(event, '${artJsonEncoded}')"
                        title="แสดงเนื้อหาแบบนี้ให้น้อยลง">
                  <span class="material-symbols-outlined text-[15px]">visibility_off</span>
                </button>
                <button type="button" class="editorial-card-action-btn" onclick="window.__openPreview('${esc(art.url)}')">อ่านย่อ</button>
                <button type="button" class="editorial-card-ai-btn" onclick="window.__openPreviewAndSummarize('${esc(art.url)}')">AI</button>
              </div>
            </div>
          </article>
        `;
      }).join("")}
    </div>
  ` : `
    <div class="text-center py-16 text-slate-500 dark:text-zinc-400 space-y-2">
      <span class="material-symbols-outlined text-3xl">sports_soccer</span>
      <p class="text-sm font-medium">ไม่พบข่าวกีฬาในเงื่อนไขการกรองนี้</p>
      <button type="button" class="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-zinc-800 text-xs font-bold cursor-pointer" onclick="window.__filterSportDiscipline(''); window.__filterSportContentType(''); window.__filterStorylinePublisher('');">ล้างตัวกรองทั้งหมด</button>
    </div>
  `;

  // Hashtags
  const sportsHashtags = Array.from(new Set([
    "กีฬา", "ผลบอล", "UCL", "ไทยลีก", "วอลเลย์บอล",
    ...(Array.isArray(storyData.hashtags) ? storyData.hashtags : []),
    ...(sortedArticles.flatMap(a => Array.isArray(a.hashtags) ? a.hashtags : [])),
  ])).filter(Boolean).slice(0, 10);

  const sportsHashtagsHtml = sportsHashtags.length > 0 ? `
    <div class="pt-4 border-t border-slate-100 dark:border-zinc-800 flex items-center gap-2 flex-wrap">
      <span class="font-mono text-[11px] text-slate-400 uppercase">TAGS:</span>
      ${sportsHashtags.map(tag => {
        const clean = tag.startsWith("#") ? tag.slice(1) : tag;
        return `
          <button type="button"
                  class="px-2.5 py-1 text-xs rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-zinc-800 text-slate-600 dark:text-zinc-300 transition-colors cursor-pointer"
                  onclick="window.__filterByHashtag('${esc(clean)}')">
            #${esc(clean)}
          </button>
        `;
      }).join("")}
    </div>
  ` : "";

  // Extract unique valid article images for the Hero Multi-Image Montage
  const sportsImages = [];
  const seenImageUrls = new Set();
  for (const art of sortedArticles) {
    const img = art.image_url;
    if (img && typeof img === "string" && img.startsWith("http") && !seenImageUrls.has(img)) {
      seenImageUrls.add(img);
      sportsImages.push({
        url: img,
        title: art.title || "",
        articleUrl: art.url || "",
        source: art.source || "ข่าว",
        meta: art._sportsMeta || classifySportsArticle(art),
      });
    }
  }

  // Build Dedicated Sports Hero Multi-Image Montage
  let sportsCollageHtml = "";
  if (sportsImages.length >= 3) {
    const mainImg = sportsImages[0];
    const subImgs = sportsImages.slice(1, 3);
    sportsCollageHtml = `
      <div class="sports-hero-collage-container shadow-md border border-slate-200 dark:border-zinc-800 rounded-2xl overflow-hidden bg-slate-950">
        <div class="grid grid-cols-1 md:grid-cols-12 gap-1.5 p-1.5">
          <!-- Featured Main Photo (7 cols) -->
          <div class="md:col-span-7 relative group rounded-xl overflow-hidden h-64 sm:h-80 cursor-pointer bg-slate-900"
               onclick="window.__openPreview('${esc(mainImg.articleUrl)}')">
            <img src="${esc(mainImg.url)}" 
                 alt="${esc(mainImg.title)}" 
                 class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                 loading="eager"
                 onerror="this.style.display='none';">
            <div class="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent flex flex-col justify-end p-4 sm:p-5 text-white pointer-events-none">
              <div class="flex items-center gap-1.5 mb-2 flex-wrap">
                <span class="sports-tag-badge ${mainImg.meta.leagueBadgeClass}">${mainImg.meta.leagueBadge}</span>
                ${mainImg.meta.scoreHighlight ? `<span class="sports-tag-badge sports-result-badge">🏆 ${esc(mainImg.meta.scoreHighlight)}</span>` : ''}
                <span class="text-[10px] font-mono text-slate-300 font-bold bg-white/20 backdrop-blur-xs px-2 py-0.5 rounded">${esc(mainImg.source)}</span>
              </div>
              <h3 class="text-base sm:text-lg font-bold text-white line-clamp-2 drop-shadow-md group-hover:text-emerald-300 transition-colors leading-snug">
                ${esc(mainImg.title)}
              </h3>
              <span class="text-[11px] text-emerald-400 font-mono mt-1.5 flex items-center gap-1 font-semibold">
                คลิกอ่านข่าวย่อ ➔
              </span>
            </div>
          </div>

          <!-- Secondary Stacked Photos (5 cols on desktop, 2 cols side-by-side on mobile) -->
          <div class="md:col-span-5 grid grid-cols-2 md:grid-cols-1 md:grid-rows-2 gap-1.5 h-28 sm:h-80">
            ${subImgs.map((item) => `
              <div class="relative group rounded-xl overflow-hidden h-full cursor-pointer bg-slate-900"
                   onclick="window.__openPreview('${esc(item.articleUrl)}')">
                <img src="${esc(item.url)}" 
                     alt="${esc(item.title)}" 
                     class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                     loading="lazy"
                     onerror="this.style.display='none';">
                <div class="absolute inset-0 bg-gradient-to-t from-black/90 via-black/30 to-transparent flex flex-col justify-end p-3 text-white pointer-events-none">
                  <div class="flex items-center gap-1.5 mb-1 flex-wrap">
                    <span class="sports-tag-badge text-[9px] py-0.5 px-1.5 ${item.meta.leagueBadgeClass}">${item.meta.leagueBadge}</span>
                    ${item.meta.scoreHighlight ? `<span class="sports-tag-badge sports-result-badge text-[9px] py-0.5 px-1.5">🏆 ${esc(item.meta.scoreHighlight)}</span>` : ''}
                    <span class="text-[9px] font-mono text-slate-300 bg-black/40 px-1.5 py-0.5 rounded">${esc(item.source)}</span>
                  </div>
                  <h4 class="text-xs sm:text-sm font-semibold text-white line-clamp-1 drop-shadow-md group-hover:text-emerald-300 transition-colors">
                    ${esc(item.title)}
                  </h4>
                </div>
              </div>
            `).join("")}
          </div>
        </div>

        <!-- Footer Strip -->
        <div class="px-4 py-2.5 bg-slate-950 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400 flex-wrap gap-2">
          <div class="flex items-center gap-2">
            <span class="text-emerald-400">📸</span>
            <span class="font-mono text-[11px] font-bold text-slate-200">ประมวลภาพและไฮไลต์ ${sportsImages.length} ภาพจากสนามแข่ง</span>
          </div>
          <span class="text-[10px] font-mono text-slate-400">คลิกที่ภาพเพื่อดูรายละเอียดข่าว</span>
        </div>
      </div>
    `;
  } else if (sportsImages.length === 2) {
    sportsCollageHtml = `
      <div class="sports-hero-collage-container shadow-md border border-slate-200 dark:border-zinc-800 rounded-2xl overflow-hidden bg-slate-950">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5 p-1.5 h-64 sm:h-72">
          ${sportsImages.map(item => `
            <div class="relative group rounded-xl overflow-hidden h-full cursor-pointer bg-slate-900"
                 onclick="window.__openPreview('${esc(item.articleUrl)}')">
              <img src="${esc(item.url)}" alt="${esc(item.title)}" class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105">
              <div class="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent flex flex-col justify-end p-4 text-white pointer-events-none">
                <div class="flex items-center gap-2 mb-1.5 flex-wrap">
                  <span class="sports-tag-badge ${item.meta.leagueBadgeClass}">${item.meta.leagueBadge}</span>
                  ${item.meta.scoreHighlight ? `<span class="sports-tag-badge sports-result-badge">🏆 ${esc(item.meta.scoreHighlight)}</span>` : ''}
                  <span class="text-[10px] font-mono text-slate-300 font-bold bg-white/20 px-2 py-0.5 rounded">${esc(item.source)}</span>
                </div>
                <h3 class="text-sm sm:text-base font-bold text-white line-clamp-2 group-hover:text-emerald-300 transition-colors leading-snug">
                  ${esc(item.title)}
                </h3>
              </div>
            </div>
          `).join("")}
        </div>
        <div class="px-4 py-2.5 bg-slate-950 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
          <span class="font-mono text-[11px] text-slate-200">📸 รวมภาพข่าวกีฬา 2 รายงาน</span>
          <span class="text-[10px] font-mono text-slate-400">คลิกที่ภาพเพื่อดูรายละเอียด</span>
        </div>
      </div>
    `;
  } else if (sportsImages.length === 1) {
    const singleImg = sportsImages[0];
    sportsCollageHtml = `
      <div class="sports-hero-collage-container shadow-md border border-slate-200 dark:border-zinc-800 rounded-2xl overflow-hidden bg-slate-950">
        <div class="p-1.5">
          <div class="relative group rounded-xl overflow-hidden h-64 sm:h-80 cursor-pointer bg-slate-900"
               onclick="window.__openPreview('${esc(singleImg.articleUrl)}')">
            <img src="${esc(singleImg.url)}" alt="${esc(singleImg.title)}" class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105">
            <div class="absolute inset-0 bg-gradient-to-t from-black/90 via-black/30 to-transparent flex flex-col justify-end p-5 text-white pointer-events-none">
              <div class="flex items-center gap-2 mb-2 flex-wrap">
                <span class="sports-tag-badge ${singleImg.meta.leagueBadgeClass}">${singleImg.meta.leagueBadge}</span>
                <span class="text-[10px] font-mono text-slate-300 font-bold bg-white/20 px-2 py-0.5 rounded">${esc(singleImg.source)}</span>
              </div>
              <h3 class="text-base sm:text-lg font-bold text-white line-clamp-2 group-hover:text-emerald-300 transition-colors">${esc(singleImg.title)}</h3>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  container.innerHTML = `
    <div class="storyline-container">
      <div class="storyline-top-bar" id="storyline-top-bar">
        <button type="button" class="storyline-back-btn" onclick="window.__backFromStoryline()">
          <span class="material-symbols-outlined text-[16px]">arrow_back</span>
          <span>กลับสู่ฟีดรวมข่าว</span>
        </button>
        <span class="font-mono text-[11px] font-bold uppercase tracking-widest text-secondary flex items-center gap-1.5">
          <span>⚽</span>
          <span>SPORTS ROUNDUP • ${outlets.length} PUBLISHERS</span>
        </span>
      </div>

      <div class="sports-hub-hero bg-white dark:bg-zinc-900 border border-slate-200 dark:border-zinc-800 rounded-2xl p-6 sm:p-8 shadow-sm space-y-6 text-slate-800 dark:text-zinc-100">
        
        <!-- Header -->
        <div class="space-y-4 border-b border-slate-100 dark:border-zinc-800 pb-5">
          <div class="flex items-center justify-between flex-wrap gap-2">
            <div class="flex items-center gap-2.5">
              <span class="inline-flex items-center gap-1.5 font-mono text-[11px] font-bold uppercase px-2.5 py-1 rounded-md bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-300 border border-emerald-200/80 dark:border-emerald-700/40">
                <span class="material-symbols-outlined text-[14px]">sports_soccer</span>
                ศูนย์รวมข่าวกีฬา • SPORTS ROUNDUP
              </span>
              <span class="text-xs text-slate-400 dark:text-zinc-500 font-medium">${formatEditorialDateOnly(storyData.updated_at)}</span>
            </div>

            <div class="px-3 py-1 rounded-full bg-slate-50 dark:bg-zinc-800 text-slate-600 dark:text-zinc-300 text-xs font-mono font-medium border border-slate-200 dark:border-zinc-700 flex items-center gap-1.5">
              <span class="inline-block w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
              <span>รวม ${sortedArticles.length} รายงาน • ${outlets.length} สำนักข่าว</span>
            </div>
          </div>

          <div class="space-y-1.5">
            <h1 class="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white leading-tight tracking-tight flex items-center gap-2.5 flex-wrap">
              <span>รวมข่าวกีฬาล่าสุด</span>
              <span class="text-xs sm:text-sm font-mono font-bold px-2.5 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 border border-emerald-300/60 dark:border-emerald-700/60">
                สดรอบวัน
              </span>
            </h1>
            <p class="text-xs sm:text-sm text-slate-600 dark:text-zinc-300 leading-relaxed max-w-3xl">
              สรุปผลการแข่งขัน ไฮไลต์ฟุตบอลไทย บอลยุโรป วอลเลย์บอล และความเคลื่อนไหววงการกีฬา รวบรวมทั้งหมด ${sortedArticles.length} รายงาน จาก ${outlets.length} สำนักข่าว
            </p>
          </div>

          <!-- Quick Sports Summary Badges / Stat Chips -->
          <div class="flex items-center gap-2 flex-wrap pt-1">
            ${discTabs.map(tab => `
              <button type="button"
                      class="sports-hero-stat-chip ${activeSportDisciplineFilter === tab.id ? 'active' : ''}"
                      onclick="window.__filterSportDiscipline('${tab.id}')">
                <span>${tab.icon} ${tab.label}</span>
                <span class="font-mono font-bold ${activeSportDisciplineFilter === tab.id ? 'text-white' : 'text-emerald-600 dark:text-emerald-400'}">(${tab.count})</span>
              </button>
            `).join("")}
            ${contentTypeCounts.result > 0 ? `
              <button type="button"
                      class="sports-hero-stat-chip ${activeSportContentTypeFilter === 'result' ? 'active' : ''}"
                      onclick="window.__filterSportContentType('result')">
                <span>🏆 ผลการแข่งขัน</span>
                <span class="font-mono font-bold ${activeSportContentTypeFilter === 'result' ? 'text-white' : 'text-amber-600 dark:text-amber-400'}">(${contentTypeCounts.result})</span>
              </button>
            ` : ""}
          </div>
        </div>

        <!-- Multi-Image Montage Showcase (เอาหลายภาพมารวม) -->
        ${sportsCollageHtml}

        <!-- AI Digest Board Section -->
        <div id="storyline-ai-section" class="space-y-4">
          <div class="pl-4 sm:pl-5 py-1 border-l-2 border-amber-600/80 dark:border-amber-400/80 text-slate-700 dark:text-zinc-200 text-sm sm:text-base leading-relaxed">
            ${esc(storyData.summary || "รวบรวมรายงานผลการแข่งขัน ฟุตบอลยุโรป ฟุตบอลไทย วอลเลย์บอล และความเคลื่อนไหวในวงการกีฬาจากทุกสำนักข่าว")}
          </div>
          <div class="pt-3 border-t border-slate-100 dark:border-zinc-800 flex items-center justify-between flex-wrap gap-3">
            <span class="text-xs text-slate-500 dark:text-zinc-400">ต้องการสรุปผลการแข่งขันและไฮไลต์สำคัญด้วย AI หรือไม่?</span>
            <button type="button" id="storyline-ai-btn" class="px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs flex items-center gap-1.5 transition-colors cursor-pointer shadow-sm"
                    onclick="window.__runStorylineAiSummary('${esc(storyId)}')">
              <span class="material-symbols-outlined text-[16px]">auto_awesome</span>
              <span>สรุปไฮไลต์และผลการแข่งขันด้วย AI</span>
            </button>
          </div>
        </div>

        <!-- Hashtags -->
        ${sportsHashtagsHtml}
      </div>

      <!-- Sports Discipline Filter Bar -->
      <div class="storyline-filter-bar space-y-3">
        <!-- Row 1: Sport Disciplines (Primary) -->
        <div class="flex items-center justify-between gap-2 flex-wrap">
          <span class="font-mono text-xs uppercase tracking-wider text-slate-500 dark:text-zinc-400">หมวดหมู่กีฬา / DISCIPLINE:</span>
          <span class="font-mono text-[11px] text-outline">แสดง ${filteredArticles.length} จาก ${sortedArticles.length} รายการ</span>
        </div>
        <div class="storyline-pills-row custom-scrollbar">
          ${disciplinePillsHtml}
        </div>

        <!-- Row 2: Content Type & Publisher Sub-filters -->
        <div class="pt-2 border-t border-slate-100 dark:border-zinc-800 flex flex-col md:flex-row md:items-center justify-between gap-3">
          <!-- Content Type Filters -->
          <div class="flex items-center gap-1.5 flex-wrap">
            <span class="font-mono text-[10px] text-outline uppercase mr-1">ประเภท:</span>
            ${contentTypePillsHtml}
          </div>
          <!-- Publisher Perspective Filters -->
          <div class="flex items-center gap-1.5 flex-wrap">
            <span class="font-mono text-[10px] text-outline uppercase mr-1">สำนักข่าว:</span>
            ${publisherPillsHtml}
          </div>
        </div>
      </div>

      <!-- Articles Grid -->
      <div class="mt-6">
        ${articlesGridHtml}
      </div>
    </div>
  `;

  // If synthesis is already present, render it into #storyline-ai-section immediately
  if (storyData.synthesis) {
    renderSportsAiDigest(storyData.synthesis, sortedArticles);
  }
}

export function renderStorylineView(
  storyData,
  activeSourceFilter = "",
  bookmarkedMap = {},
  activeSportDisciplineFilter = "",
  activeSportContentTypeFilter = ""
) {
  const container = document.getElementById("storyline-view");
  if (!container || !storyData) return;

  currentStorylineDataCache = storyData;

  const rawArticles = Array.isArray(storyData.articles) ? storyData.articles : [];

  const sortedArticles = [...rawArticles].sort((a, b) => {
    const timeA = new Date(a.fetched_at || a.created_at || 0).getTime();
    const timeB = new Date(b.fetched_at || b.created_at || 0).getTime();
    return timeA - timeB;
  });

  // Check if this cluster is predominantly sports news -> dispatch to dedicated sports roundup view
  if (checkIsSportsCluster(storyData, sortedArticles)) {
    return renderSportsStorylineView(
      storyData,
      activeSourceFilter,
      activeSportDisciplineFilter,
      activeSportContentTypeFilter,
      bookmarkedMap
    );
  }

  const storyId = storyData.macro_event_id || storyData.story_id || storyData.cluster_id || "";
  const heroTitle = storyData.topic_title || storyData.title || storyData.headline || "แฟ้มเจาะลึกประเด็นข่าว";

  const synthesis = storyData.synthesis;
  const metrics = synthesis?.metrics;
  const irrelevantList = Array.isArray(synthesis?.irrelevant_articles) ? synthesis.irrelevant_articles : [];
  const contextList = Array.isArray(synthesis?.political_contexts) ? synthesis.political_contexts : [];
  const excludedCount = metrics?.excluded_count ?? (irrelevantList.length + contextList.length);

  // Pre-index context and outlier articles from synthesis to cross-reference evidence IDs
  const titleToEvidenceId = new Map();
  const urlToEvidenceId = new Map();

  contextList.forEach(c => {
    if (c.title && c.article_id) titleToEvidenceId.set(c.title.trim().toLowerCase(), c.article_id);
  });
  irrelevantList.forEach(irr => {
    if (irr.title && irr.article_id) titleToEvidenceId.set(irr.title.trim().toLowerCase(), irr.article_id);
  });

  // Assign permanent, stable chronological evidence IDs to all articles in the storyline
  sortedArticles.forEach((art, idx) => {
    const artTitle = (art.title || "").trim().toLowerCase();
    const artUrl = (art.url || "").trim().toLowerCase();
    if (!art.article_id) {
      if (titleToEvidenceId.has(artTitle)) {
        art.article_id = titleToEvidenceId.get(artTitle);
      } else if (urlToEvidenceId.has(artUrl)) {
        art.article_id = urlToEvidenceId.get(artUrl);
      } else {
        art.article_id = `art_${String(idx + 1).padStart(2, '0')}`;
      }
    }
    art._chronology_num = idx + 1;
  });

  const outletCounts = {};
  sortedArticles.forEach(a => {
    const src = a.source || "สำนักข่าว";
    outletCounts[src] = (outletCounts[src] || 0) + 1;
  });
  const outlets = Object.keys(outletCounts);

  // Extract evidence publishers set for prioritization
  const evidencePublishers = Array.isArray(metrics?.synthesized_publishers) && metrics.synthesized_publishers.length > 0
    ? metrics.synthesized_publishers
    : [];
  const evidencePublishersSet = new Set(evidencePublishers.map(p => p.toLowerCase()));

  // Prioritize evidence publishers first, then other outlets by volume
  const sortedOutlets = [...outlets].sort((a, b) => {
    const isAEvidence = evidencePublishersSet.has(a.toLowerCase());
    const isBEvidence = evidencePublishersSet.has(b.toLowerCase());
    if (isAEvidence && !isBEvidence) return -1;
    if (!isAEvidence && isBEvidence) return 1;
    return (outletCounts[b] || 0) - (outletCounts[a] || 0);
  });

  // Filter articles based on activeSourceFilter
  let filteredArticles = sortedArticles;
  if (activeSourceFilter === "__context_excluded__") {
    filteredArticles = sortedArticles.filter(art => {
      const evId = (art.article_id || "").toLowerCase();
      const isOut = irrelevantList.some(irr =>
        (irr.article_id && irr.article_id.toLowerCase() === evId) ||
        (irr.title && art.title && irr.title.trim().toLowerCase() === art.title.trim().toLowerCase())
      );
      const isCtx = contextList.some(c =>
        (c.article_id && c.article_id.toLowerCase() === evId) ||
        (c.title && art.title && c.title.trim().toLowerCase() === art.title.trim().toLowerCase())
      );
      return isOut || isCtx;
    });
  } else if (activeSourceFilter) {
    filteredArticles = sortedArticles.filter(a => (a.source || "").toLowerCase() === activeSourceFilter.toLowerCase());
  }

  const allIsActive = !activeSourceFilter;
  let publisherPillsHtml = `
    <button type="button" 
            class="storyline-publisher-pill ${allIsActive ? 'active' : ''}"
            onclick="window.__filterStorylinePublisher('')">
      <span>ทุกสำนักข่าว</span>
      <span class="pill-count">${sortedArticles.length}</span>
    </button>
  `;

  publisherPillsHtml += sortedOutlets.map(outlet => {
    const isActive = outlet.toLowerCase() === activeSourceFilter.toLowerCase();
    const isCorroborated = evidencePublishersSet.has(outlet.toLowerCase());
    const count = outletCounts[outlet] || 0;
    const color = SOURCE_COLORS[outlet] ?? "#1d3557";
    return `
      <button type="button" 
              class="storyline-publisher-pill ${isActive ? 'active' : ''}"
              onclick="window.__filterStorylinePublisher('${esc(outlet)}')">
        <span style="display:inline-block; width:7px; height:7px; border-radius:9999px; background:${isActive ? '#ffffff' : color};"></span>
        <span>${esc(outlet)}</span>
        ${isCorroborated ? `<span class="text-[10px] text-emerald-400 font-bold" title="สำนักข่าวที่ให้หลักฐานตรงกัน">✓</span>` : ""}
        <span class="pill-count">${count}</span>
      </button>
    `;
  }).join("");

  if (excludedCount > 0) {
    const isContextActive = activeSourceFilter === "__context_excluded__";
    publisherPillsHtml += `
      <button type="button" 
              class="storyline-publisher-pill ${isContextActive ? 'active' : ''} border border-amber-500/40 text-amber-300"
              onclick="window.__filterStorylinePublisher('__context_excluded__')">
        <span class="material-symbols-outlined text-[13px] text-amber-400">filter_alt</span>
        <span>ข่าวบริบท/คัดออก</span>
        <span class="pill-count">${excludedCount}</span>
      </button>
    `;
  }

  const storylineHashtags = Array.from(new Set([
    ...(Array.isArray(storyData.hashtags) ? storyData.hashtags : []),
    ...(Array.isArray(storyData.entities) ? storyData.entities : []),
    ...(sortedArticles.flatMap(a => Array.isArray(a.hashtags) ? a.hashtags : [])),
  ])).filter(Boolean).slice(0, 10);

  const storylineHashtagsHtml = storylineHashtags.length > 0 ? `
    <div class="pt-4 border-t border-slate-100 dark:border-zinc-800 flex items-center gap-2 flex-wrap">
      <span class="font-mono text-[11px] text-slate-400 uppercase">TAGS:</span>
      ${storylineHashtags.map(tag => {
        const clean = tag.startsWith("#") ? tag.slice(1) : tag;
        return `
          <button type="button"
                  class="px-2.5 py-1 text-xs rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-zinc-800 text-slate-600 dark:text-zinc-300 transition-colors cursor-pointer"
                  onclick="window.__filterByHashtag('${esc(clean)}')">
            #${esc(clean)}
          </button>
        `;
      }).join("")}
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
        const evidenceId = art.article_id || `art_${String(art._chronology_num || idx + 1).padStart(2, '0')}`;
        const chronologyNum = art._chronology_num || (idx + 1);

        // Check if flagged as outlier / irrelevant
        const matchedOutlier = irrelevantList.find(irr => 
          (irr.article_id && irr.article_id.toLowerCase() === evidenceId.toLowerCase()) ||
          (irr.title && art.title && irr.title.trim().toLowerCase() === art.title.trim().toLowerCase())
        );
        const isOutlier = Boolean(matchedOutlier);
        const outlierReason = matchedOutlier?.reason || "";

        // Check if flagged as political / situational context
        const matchedContext = contextList.find(c => 
          (c.article_id && c.article_id.toLowerCase() === evidenceId.toLowerCase()) ||
          (c.title && art.title && c.title.trim().toLowerCase() === art.title.trim().toLowerCase())
        );
        const isContext = Boolean(matchedContext);
        const contextRelation = matchedContext?.relation_to_event || matchedContext?.context_summary || "";

        return `
          <article class="editorial-card transition-all duration-300 ${isOutlier ? 'border border-amber-500/35 bg-amber-950/10' : (isContext ? 'border border-blue-500/35 bg-blue-950/10' : '')}" 
                   id="article-evidence-${evidenceId.toLowerCase()}" 
                   data-evidence-id="${evidenceId.toLowerCase()}" 
                   data-url="${esc(art.url)}">
            <div class="flex flex-row sm:flex-col flex-1 p-2.5 sm:p-0 cursor-pointer" data-url="${esc(art.url)}" onclick="window.__openPreview(this.dataset.url)">
              <!-- Thumbnail: Left on mobile (108px x 76px), Top on Desktop (compact 144px) -->
              <div class="w-[108px] h-[76px] sm:w-full sm:h-36 relative overflow-hidden shrink-0 rounded-lg sm:rounded-none bg-surface-container-low sm:border-b sm:border-outline-variant/25">
                <img src="${esc(imgSrc)}" alt="${esc(art.title)}" class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" onerror="this.onerror=null; this.src='${placeholder}';" loading="lazy">
                
                <!-- Desktop Only: Chronology Badges -->
                <div class="hidden sm:flex absolute top-2 left-2.5 items-center gap-1.5 flex-wrap">
                  <span class="bg-black/75 text-white font-mono text-[10px] font-bold px-2 py-0.5 rounded">
                    CHRONOLOGY #${String(chronologyNum).padStart(2, '0')}
                  </span>
                  <span class="citation-chip" title="รหัสหลักฐานสำหรับตรวจสอบย้อนกลับ">
                    ${evidenceId.toUpperCase()}
                  </span>
                </div>
                ${isOutlier ? `
                  <div class="hidden sm:flex absolute top-2 right-2.5 bg-amber-500/90 text-black font-mono font-bold text-[9px] px-2 py-0.5 rounded shadow items-center gap-1">
                    <span class="material-symbols-outlined text-[11px]">filter_alt</span>
                    <span>คัดแยก</span>
                  </div>
                ` : (isContext ? `
                  <div class="hidden sm:flex absolute top-2 right-2.5 bg-blue-600/90 text-white font-mono font-bold text-[9px] px-2 py-0.5 rounded shadow items-center gap-1">
                    <span class="material-symbols-outlined text-[11px]">info</span>
                    <span>บริบท</span>
                  </div>
                ` : "")}
              </div>

              <!-- Content: Right on mobile, Below on Desktop -->
              <div class="editorial-card-body flex flex-col justify-between sm:justify-start flex-1 min-w-0">
                ${isContext ? `
                  <div class="hidden sm:flex mb-2 px-2.5 py-1.5 rounded bg-blue-500/10 border border-blue-500/25 text-blue-900 dark:text-blue-200 text-xs items-start gap-1.5">
                    <span class="material-symbols-outlined text-[14px] text-blue-600 dark:text-blue-400 shrink-0 mt-0.5">info</span>
                    <div class="min-w-0 flex-1 leading-normal text-[11px]">
                      <span class="font-bold text-blue-700 dark:text-blue-300">บริบทการเมือง (อยู่นอกสารบบหลักฐาน):</span>
                      <span class="text-on-surface-variant ml-1">${esc(contextRelation || "ข้อมูลบริบทเบื้องหลัง")}</span>
                    </div>
                  </div>
                ` : (isOutlier ? `
                  <div class="hidden sm:flex mb-2 px-2.5 py-1.5 rounded bg-amber-500/10 border border-amber-500/25 text-amber-900 dark:text-amber-200 text-xs items-start gap-1.5">
                    <span class="material-symbols-outlined text-[14px] text-amber-600 dark:text-amber-400 shrink-0 mt-0.5">filter_alt</span>
                    <div class="min-w-0 flex-1 leading-normal text-[11px]">
                      <span class="font-bold text-amber-700 dark:text-amber-300">ข่าวนอกประเด็นหลัก:</span>
                      <span class="text-on-surface-variant ml-1">${esc(outlierReason || "คัดแยกออกจากเหตุการณ์")}</span>
                    </div>
                  </div>
                ` : "")}

                <!-- Dateline: Desktop top row -->
                <div class="hidden sm:flex items-center justify-between gap-2 mb-1.5">
                  <div class="flex items-center gap-1.5">
                    <span class="w-2 h-2 rounded-full" style="background:${color}"></span>
                    <span class="font-mono text-[11px] font-bold uppercase text-on-surface">${esc(art.source || "ข่าว")}</span>
                  </div>
                  <span class="font-mono text-[10px] text-secondary font-semibold">${esc(perspective)}</span>
                </div>

                <!-- Headline -->
                <h3 class="text-[14px] sm:text-[15.5px] font-headline font-bold text-on-surface leading-snug transition-colors group-hover:text-primary line-clamp-2 mb-1 sm:mb-1.5">
                  ${esc(art.title)}
                </h3>

                <!-- Summary (Desktop only) -->
                <div class="hidden sm:block">
                  <p class="text-xs text-on-surface-variant line-clamp-2 leading-relaxed">
                    ${esc(art.summary || "")}
                  </p>
                </div>

                <!-- Mobile Dateline & Source: directly below headline -->
                <div class="flex sm:hidden items-center justify-between gap-1 mt-auto pt-1 text-xs">
                  <div class="flex items-center gap-1.5 min-w-0 text-outline">
                    <span class="w-1.5 h-1.5 rounded-full shrink-0" style="background:${color}"></span>
                    <span class="text-[11px] font-medium text-on-surface-variant/90 truncate">${esc(art.source || "ข่าว")}</span>
                    <span class="text-[10px] font-mono text-amber-600 dark:text-amber-400 font-bold shrink-0">[${evidenceId.toUpperCase()}]</span>
                  </div>
                  <div class="flex items-center gap-1 shrink-0" onclick="event.stopPropagation()">
                    <button type="button" 
                            class="p-1 rounded text-outline hover:text-on-surface bookmark-btn ${isBookmarked ? 'active text-amber-500' : ''}"
                            data-url="${esc(art.url)}"
                            onclick="window.__toggleArticleBookmark(event, '${artJsonEncoded}')"
                            title="${isBookmarked ? 'ลบบุ๊กมาร์ก' : 'บันทึกบทความ'}">
                      <span class="material-symbols-outlined text-[15px]" style="${isBookmarked ? "font-variation-settings: 'FILL' 1; color: #f59e0b;" : ""}">
                        ${isBookmarked ? 'bookmark' : 'bookmark_border'}
                      </span>
                    </button>
                    <button type="button" 
                            class="px-2 py-0.5 rounded bg-black/5 dark:bg-white/10 hover:bg-amber-500 hover:text-black text-[10px] font-bold text-on-surface flex items-center gap-0.5 transition-colors cursor-pointer"
                            onclick="window.__openPreviewAndSummarize('${esc(art.url)}')">
                      <span class="material-symbols-outlined text-[11px] text-amber-500" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
                      <span>AI</span>
                    </button>
                  </div>
                </div>

              </div>
            </div>

            <!-- Card Footer Actions (Desktop Only) -->
            <div class="hidden sm:flex mt-auto px-4 py-2 border-t border-outline-variant/25 items-center justify-between gap-2 bg-surface/40">
              <span class="font-mono text-[10px] text-outline uppercase">${esc(art.fetched_at || "")}</span>
              <div class="flex items-center gap-1" onclick="event.stopPropagation()">
                <button type="button" 
                        class="editorial-card-icon-btn bookmark-btn ${isBookmarked ? 'active' : ''}"
                        data-url="${esc(art.url)}"
                        onclick="window.__toggleArticleBookmark(event, '${artJsonEncoded}')"
                        title="${isBookmarked ? 'ลบบุ๊กมาร์ก' : 'บันทึกบทความ'}">
                  <span class="material-symbols-outlined text-[15px]" style="${isBookmarked ? "font-variation-settings: 'FILL' 1;" : ""}">
                    ${isBookmarked ? 'bookmark' : 'bookmark_border'}
                  </span>
                </button>
                <button type="button" 
                        class="editorial-card-icon-btn"
                        onclick="window.__showLessLikeThis(event, '${artJsonEncoded}')"
                        title="แสดงเนื้อหาแบบนี้ให้น้อยลง">
                  <span class="material-symbols-outlined text-[15px]">visibility_off</span>
                </button>
                <button type="button" class="editorial-card-action-btn" onclick="window.__openPreview('${esc(art.url)}')">อ่านย่อ</button>
                <button type="button" class="editorial-card-ai-btn" onclick="window.__openPreviewAndSummarize('${esc(art.url)}')">AI</button>
              </div>
            </div>
          </article>
        `;
      }).join("")}
    </div>
  ` : "";

  const totalCandidates = metrics?.candidate_count ?? sortedArticles.length;
  let evidenceCount = metrics?.synthesized_evidence_count;
  if (typeof evidenceCount !== "number") {
    evidenceCount = Math.max(1, totalCandidates - excludedCount);
  }

  const isHalted = synthesis?.synthesis_status === "halted_mismatch";
  const isSingleSource = synthesis?.synthesis_status === "single_source" || synthesis?.is_single_source || evidenceCount === 1;

  let auditBadgeIcon = "verified_user";
  let auditBadgeColor = "text-emerald-600 dark:text-emerald-400";
  let auditBadgeText = `สังเคราะห์จาก <strong class="text-emerald-700 dark:text-emerald-400 font-semibold">${evidenceCount}</strong>/${totalCandidates} ข่าว ${excludedCount > 0 ? `(คัดออก ${excludedCount})` : ""}`;

  if (isHalted) {
    auditBadgeIcon = "warning";
    auditBadgeColor = "text-amber-600 dark:text-amber-400";
    auditBadgeText = `<span class="text-amber-600 dark:text-amber-400 font-semibold">ระงับการสังเคราะห์ (Candidate Mismatch)</span> • คัดออก ${excludedCount} รายการ`;
  } else if (isSingleSource) {
    auditBadgeIcon = "feed";
    auditBadgeColor = "text-sky-600 dark:text-sky-400";
    auditBadgeText = `สรุปจากแหล่งข่าวเดียว (<strong class="text-sky-600 dark:text-sky-400 font-semibold">1</strong>/${totalCandidates} ข่าว) ${excludedCount > 0 ? `(คัดออก ${excludedCount})` : ""}`;
  }

  container.innerHTML = `
    <div class="storyline-container">
      <div class="storyline-top-bar" id="storyline-top-bar">
        <button type="button" class="storyline-back-btn" onclick="window.__backFromStoryline()">
          <span class="material-symbols-outlined text-[16px]">arrow_back</span>
          <span>กลับสู่ฟีดรวมข่าว</span>
        </button>
        <span class="font-mono text-[11px] font-bold uppercase tracking-widest text-secondary">
          SPECIAL DOSSIER • ${outlets.length} PUBLISHERS
        </span>
      </div>

      <div class="storyline-hero-banner bg-white dark:bg-zinc-900 border border-slate-200 dark:border-zinc-800 rounded-2xl p-4 sm:p-8 shadow-sm space-y-6 text-slate-800 dark:text-zinc-100">
        
        <!-- 1. Header & Tags: สะอาดตา ตรงประเด็น -->
        <div class="space-y-3 border-b border-slate-100 dark:border-zinc-800 pb-5">
          <div class="flex items-center justify-between flex-wrap gap-2">
            <div class="flex items-center gap-2.5">
              <span class="inline-flex items-center gap-1.5 font-mono text-[11px] font-bold uppercase px-2.5 py-1 rounded-md bg-amber-50 dark:bg-amber-500/10 text-amber-800 dark:text-amber-300 border border-amber-200/80 dark:border-amber-500/30">
                <span class="material-symbols-outlined text-[14px]">auto_awesome</span>
                AI Storyline Summary
              </span>
              <span class="text-xs text-slate-400 dark:text-zinc-500 font-medium">${formatEditorialDateOnly(storyData.updated_at)}</span>
            </div>

            <!-- ยุบรวมปุ่ม Audit มาไว้ตรงนี้จุดเดียว ไม่ให้รกเนื้อหาหลัก -->
            <button type="button" 
                    id="storyline-audit-toggle-btn"
                    onclick="window.__toggleQualityAuditPanel()" 
                    class="px-3 py-1.5 rounded-full bg-slate-50 hover:bg-slate-100 dark:bg-zinc-800 dark:hover:bg-zinc-700 text-slate-600 dark:text-zinc-300 text-xs font-medium flex items-center gap-2 transition-colors border border-slate-200 dark:border-zinc-700 cursor-pointer"
                    title="คลิกเพื่อคลี่ดูรายงานการตรวจสอบคุณภาพหลักฐาน">
              <span class="material-symbols-outlined ${auditBadgeColor} text-[16px]">${auditBadgeIcon}</span>
              <span id="storyline-audit-toggle-text">${auditBadgeText}</span>
            </button>
          </div>

          <h1 class="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white leading-snug tracking-tight">
            ${esc(heroTitle)}
          </h1>
        </div>

        <!-- 2. Toggle List: รายงานการคัดกรองข่าวของ AI (Default ปิดไว้ ให้คลิกเปิดดูได้ทันที) -->
        ${excludedCount > 0 ? `
          <details id="dossier-audit-panel" class="group rounded-xl bg-slate-50 dark:bg-zinc-800/60 border border-slate-200 dark:border-zinc-700 overflow-hidden transition-all text-xs text-slate-800 dark:text-zinc-200 shadow-sm">
            <summary class="p-3.5 sm:p-4 flex items-center justify-between cursor-pointer select-none hover:bg-slate-100/70 dark:hover:bg-zinc-700/40 transition-colors list-none">
              <div class="flex items-center gap-2 font-bold text-amber-800 dark:text-amber-400">
                <span class="material-symbols-outlined text-[18px]">fact_check</span>
                <span>รายงานการคัดกรองข่าวของ AI (คัดออก ${excludedCount} รายการที่นอกประเด็น)</span>
              </div>
              <div class="flex items-center gap-1.5 text-slate-400 dark:text-zinc-500 group-hover:text-slate-600 dark:group-hover:text-zinc-300 font-mono text-[11px]">
                <span class="group-open:hidden">คลิกเพื่อดู</span>
                <span class="hidden group-open:inline">ซ่อน</span>
                <span class="material-symbols-outlined text-[18px] transition-transform duration-200 group-open:rotate-180">expand_more</span>
              </div>
            </summary>

            <!-- แสดงหมวดหมู่ที่คัดออกเป็น Grid หรือ List สั้นๆ ที่อ่านง่าย -->
            <div class="p-4 pt-1 border-t border-slate-200 dark:border-zinc-700 space-y-4 animate-fade-in">
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                <!-- ข่าวบริบทแวดล้อม -->
                <div class="p-3.5 rounded-lg bg-blue-50/70 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-500/20 space-y-2">
                  <div class="text-blue-800 dark:text-blue-300 font-bold flex items-center gap-1.5">
                    <span class="material-symbols-outlined text-[14px]">lightbulb</span>
                    <span>ข่าวบริบทแวดล้อม (${contextList.length})</span>
                  </div>
                  <p class="text-[11px] text-slate-600 dark:text-zinc-400">ข่าวที่มีเนื้อหาเกี่ยวโยงแต่ไม่ใช่ใจความหลัก</p>
                  ${contextList.length > 0 ? `
                    <div class="space-y-2 max-h-72 sm:max-h-80 overflow-y-auto custom-scrollbar pt-1 pr-1">
                      ${contextList.map(pc => `
                        <div class="p-2 rounded-lg bg-white dark:bg-zinc-900 border border-blue-100 dark:border-blue-500/20 flex items-start justify-between gap-2 shadow-2xs">
                          <div class="min-w-0 flex-1 text-[11px] leading-snug text-slate-800 dark:text-zinc-200 break-words">
                            <span class="text-blue-700 dark:text-blue-400 font-bold mr-1">[${esc(pc.source || "ข่าว")}]</span>
                            <span>${esc(pc.title)}</span>
                          </div>
                          <button type="button" class="px-1.5 py-0.5 text-[10px] font-mono rounded bg-slate-100 hover:bg-slate-200 dark:bg-zinc-800 text-slate-600 dark:text-zinc-300 border border-slate-200 dark:border-zinc-700 cursor-pointer shrink-0" onclick="window.__inspectCitation('${esc(pc.article_id)}')">${esc(pc.article_id)}</button>
                        </div>
                      `).join("")}
                    </div>
                  ` : `<p class="text-[10px] text-slate-400 dark:text-zinc-500 italic">ไม่พบข่าวบริบทแยกต่างหาก</p>`}
                </div>

                <!-- ข่าวคนละเรื่อง/คลัสเตอร์อื่น -->
                <div class="p-3.5 rounded-lg bg-amber-50/70 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-500/20 space-y-2">
                  <div class="text-amber-800 dark:text-amber-300 font-bold flex items-center gap-1.5">
                    <span class="material-symbols-outlined text-[14px]">shuffle</span>
                    <span>ข่าวคนละเรื่อง (${irrelevantList.length})</span>
                  </div>
                  <p class="text-[11px] text-slate-600 dark:text-zinc-400">เนื้อหาไม่ตรงกับประเด็นหลักนี้</p>
                  ${irrelevantList.length > 0 ? `
                    <div class="space-y-2 max-h-72 sm:max-h-80 overflow-y-auto custom-scrollbar pt-1 pr-1">
                      ${irrelevantList.map(irr => `
                        <div class="p-2 rounded-lg bg-white dark:bg-zinc-900 border border-amber-100 dark:border-amber-500/20 flex items-start justify-between gap-2 shadow-2xs">
                          <div class="min-w-0 flex-1 text-[11px] leading-snug text-slate-800 dark:text-zinc-200 break-words">
                            <span class="text-amber-700 dark:text-amber-400 font-bold mr-1">[${esc(irr.source || "ข่าว")}]</span>
                            <span>${esc(irr.title)}</span>
                          </div>
                          <button type="button" class="px-1.5 py-0.5 text-[10px] font-mono rounded bg-slate-100 hover:bg-slate-200 dark:bg-zinc-800 text-slate-600 dark:text-zinc-300 border border-slate-200 dark:border-zinc-700 cursor-pointer shrink-0" onclick="window.__inspectCitation('${esc(irr.article_id)}')">${esc(irr.article_id)}</button>
                        </div>
                      `).join("")}
                    </div>
                  ` : `<p class="text-[10px] text-slate-400 dark:text-zinc-500 italic">ไม่พบข่าวหลุดประเด็น</p>`}
                </div>
              </div>
            </div>
          </details>
        ` : `
          <div id="dossier-audit-panel" class="hidden"></div>
        `}

        <!-- 3. AI Main Summary Section (จุดสำคัญที่สุด วางเด่นๆ ให้คนอ่านทันที) -->
        <div id="storyline-ai-section" class="space-y-4">
          <div class="pl-4 sm:pl-5 py-1 border-l-2 border-amber-600/80 dark:border-amber-400/80 text-slate-700 dark:text-zinc-200 text-sm sm:text-base leading-relaxed">
            ${esc(storyData.summary || "รวบรวมลำดับเหตุการณ์และมุมมองการรายงานจากหลายสำนักข่าวเพื่อให้เห็นภาพรวมอย่างรอบด้าน")}
          </div>
          <div class="pt-3 border-t border-slate-100 dark:border-zinc-800 flex items-center justify-between flex-wrap gap-3">
            <span class="text-xs text-slate-500 dark:text-zinc-400">ต้องการสังเคราะห์พัฒนาการเหตุการณ์เชิงลึกหรือไม่?</span>
            <button type="button" id="storyline-ai-btn" class="px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs flex items-center gap-1.5 transition-colors cursor-pointer shadow-sm"
                    onclick="window.__runStorylineAiSummary('${esc(storyId)}')">
              <span class="material-symbols-outlined text-[16px]">auto_awesome</span>
              <span>สังเคราะห์ความคืบหน้าด้วย AI</span>
            </button>
          </div>
        </div>

        <!-- 4. Tags ประเด็นข่าว -->
        ${storylineHashtagsHtml}

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

  // If synthesis data is already attached, render it into #storyline-ai-section immediately
  if (synthesis) {
    renderStorylineAiSynthesis(synthesis);
  }
}

// ── Project Evaluation Landing Page & Feedback Prompt ─────────────

export function showFeedbackPromptModal() {
  if (localStorage.getItem(FEEDBACK_COMPLETED_KEY) === "true") return;
  const modal = document.getElementById("feedback-prompt-modal");
  if (!modal) return;
  modal.classList.remove("hidden");
  modal.classList.add("flex");
}

export function hideFeedbackPromptModal() {
  const modal = document.getElementById("feedback-prompt-modal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.classList.remove("flex");
}

export function renderEvaluationView() {
  const container = document.getElementById("evaluation-view");
  if (!container) return;

  const isCompleted = localStorage.getItem(FEEDBACK_COMPLETED_KEY) === "true";

  container.innerHTML = `
    <!-- Top Return Bar -->
    <div class="mb-6 flex items-center justify-between gap-4">
      <button type="button" 
              onclick="window.location.hash = '#/'" 
              class="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-surface-container hover:bg-surface-container-high text-on-surface font-semibold text-xs border border-outline-variant/30 transition-all cursor-pointer">
        <span class="material-symbols-outlined text-[18px]">arrow_back</span>
        <span>กลับสู่ฟีดรวมข่าว</span>
      </button>
      <span class="text-[11px] font-mono text-outline uppercase tracking-widest hidden sm:inline">PROJECT EVALUATION</span>
    </div>

    <!-- Main Editorial Landing Hero -->
    <div class="bg-surface border border-outline-variant/40 rounded-2xl p-6 sm:p-10 shadow-sm space-y-6 mb-8">
      <div class="space-y-3">
        <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-400 font-mono text-[11px] font-bold uppercase tracking-wider">
          <span class="material-symbols-outlined text-[16px]">school</span>
          <span>แบบประเมินโครงงาน (Academic Project Evaluation)</span>
        </div>
        <h1 class="text-2xl sm:text-3xl font-headline font-extrabold tracking-tight text-on-surface">
          แบบประเมินความพึงพอใจและประสิทธิภาพการใช้งานระบบ
        </h1>
        <p class="font-headline italic text-base sm:text-lg text-primary font-bold">
          NEWSROOM — Real-Time Thai News Aggregator & Intelligent Summarizer
        </p>
        <p class="text-xs sm:text-sm text-on-surface-variant leading-relaxed">
          แบบสอบถามนี้จัดทำขึ้นเพื่อรวบรวมข้อมูลเชิงประจักษ์และความคิดเห็นจากผู้ใช้งานจริง เพื่อนำไปประเมินผลสัมฤทธิ์ สรุปผลการวิจัย และพัฒนาโครงงานระบบรวบรวม จัดหมวดหมู่อัจฉริยะ และสรุปเนื้อหาข่าวสารภาษาไทย
        </p>
      </div>

      <!-- Action Card / Call to Action -->
      <div class="p-6 rounded-2xl bg-gradient-to-br from-amber-500/10 via-amber-500/5 to-transparent border border-amber-500/30 space-y-4">
        <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div class="space-y-1">
            <h2 class="text-base sm:text-lg font-bold text-on-surface flex items-center gap-2">
              <span class="material-symbols-outlined text-amber-600 dark:text-amber-400">rate_review</span>
              <span>กรอกแบบประเมินผ่าน Google Forms</span>
            </h2>
            <p class="text-xs text-on-surface-variant leading-relaxed">
              ใช้เวลาตอบคำถามเพียง 2-3 นาที คำตอบของท่านจะช่วยให้การวิเคราะห์ผลโครงงานมีความสมบูรณ์ยิ่งขึ้น
            </p>
          </div>

          <a href="${FEEDBACK_FORM_URL}" 
             target="_blank" 
             rel="noopener noreferrer" 
             onclick="window.__handleFeedbackFormClick(event)"
             class="shrink-0 inline-flex items-center justify-center gap-2 px-6 py-3.5 bg-[#141413] dark:bg-white text-white dark:text-[#141413] font-bold text-xs sm:text-sm rounded-xl shadow-lg hover:opacity-90 active:scale-95 transition-all text-center">
            <span class="material-symbols-outlined text-[18px]">assignment</span>
            <span>เปิดทำแบบประเมินบน Google Forms</span>
            <span class="material-symbols-outlined text-[15px]">open_in_new</span>
          </a>
        </div>

        <div id="eval-status-banner" class="${isCompleted ? "flex" : "hidden"} items-center gap-2 pt-2 border-t border-amber-500/20 text-xs font-medium text-emerald-700 dark:text-emerald-400">
          <span class="material-symbols-outlined text-[16px]">check_circle</span>
          <span>คุณได้กดเปิดทำแบบประเมินเรียบร้อยแล้ว ขอขอบพระคุณสำหรับความคิดเห็นและการสนับสนุนโครงงาน</span>
        </div>
      </div>

      <!-- 5 Core Features Evaluated in this Project -->
      <div class="space-y-4 pt-4 border-t border-outline-variant/30">
        <h3 class="font-mono text-xs font-bold text-outline uppercase tracking-wider">
          ขอบเขตระบบและฟังก์ชันที่ประเมิน (Core System Capabilities)
        </h3>
        
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div class="p-4 rounded-xl border border-outline-variant/30 bg-surface-container-low/50 space-y-1.5">
            <div class="flex items-center gap-2 font-bold text-xs text-on-surface">
              <span class="material-symbols-outlined text-primary text-[18px]">rss_feed</span>
              <span>1. รวบรวม 14 สำนักข่าวไทย</span>
            </div>
            <p class="text-[11px] text-on-surface-variant leading-relaxed">
              ดึงข่าวอัตโนมัติแบบเรียลไทม์ พร้อมตรวจจับข่าวซ้ำและสตรีมมิ่งผ่าน WebSocket
            </p>
          </div>

          <div class="p-4 rounded-xl border border-outline-variant/30 bg-surface-container-low/50 space-y-1.5">
            <div class="flex items-center gap-2 font-bold text-xs text-on-surface">
              <span class="material-symbols-outlined text-primary text-[18px]">category</span>
              <span>2. จัดหมวดหมู่อัจฉริยะ (3-Tier)</span>
            </div>
            <p class="text-[11px] text-on-surface-variant leading-relaxed">
              Fast-Path URL Priority, กฎคำสำคัญทางภาษาศาสตร์ (NLP) และโมเดล Machine Learning (TF-IDF + SVM)
            </p>
          </div>

          <div class="p-4 rounded-xl border border-outline-variant/30 bg-surface-container-low/50 space-y-1.5">
            <div class="flex items-center gap-2 font-bold text-xs text-on-surface">
              <span class="material-symbols-outlined text-primary text-[18px]">timeline</span>
              <span>3. ร้อยเรียงเหตุการณ์ต่อเนื่อง (Storyline)</span>
            </div>
            <p class="text-[11px] text-on-surface-variant leading-relaxed">
              จัดกลุ่มเหตุการณ์เดียวกันข้ามวันและข้ามหมวดหมู่ด้วย Dense Vector Embeddings และ Entity Confirmation
            </p>
          </div>

          <div class="p-4 rounded-xl border border-outline-variant/30 bg-surface-container-low/50 space-y-1.5">
            <div class="flex items-center gap-2 font-bold text-xs text-on-surface">
              <span class="material-symbols-outlined text-primary text-[18px]">auto_awesome</span>
              <span>4. สรุปใจความสำคัญด้วย AI</span>
            </div>
            <p class="text-[11px] text-on-surface-variant leading-relaxed">
              สังเคราะห์ประเด็นสำคัญ (Key Takeaways), โทนข่าว (Sentiment) และไทม์ไลน์สถานการณ์อย่างแม่นยำ
            </p>
          </div>

          <div class="sm:col-span-2 p-4 rounded-xl border border-outline-variant/30 bg-surface-container-low/50 space-y-1.5">
            <div class="flex items-center gap-2 font-bold text-xs text-on-surface">
              <span class="material-symbols-outlined text-primary text-[18px]">devices</span>
              <span>5. สถาปัตยกรรม PWA ปลอดภัยลิขสิทธิ์</span>
            </div>
            <p class="text-[11px] text-on-surface-variant leading-relaxed">
              รองรับการอ่านบทคัดย่อในแอป (Snippet Preview), แคชอ่านออฟไลน์, ติดตั้งลงหน้าจอมือถือ และเปิดเว็บต้นฉบับอย่างปลอดภัยโดยล้างเครื่องมือติดตาม
            </p>
          </div>
        </div>
      </div>

      <!-- Ethics & Privacy Statement -->
      <div class="p-4 rounded-xl bg-surface-container text-outline space-y-1 text-xs leading-relaxed border border-outline-variant/20">
        <span class="font-bold text-on-surface flex items-center gap-1.5">
          <span class="material-symbols-outlined text-[16px]">privacy_tip</span>
          <span>การคุ้มครองข้อมูลส่วนบุคคล (PDPA Statement)</span>
        </span>
        <p>
          การประเมินนี้ไม่มีการบันทึกชื่อ อีเมล หรือข้อมูลระบุตัวตนของผู้ตอบแบบสอบถาม ข้อมูลทั้งหมดจะถูกประมวลผลเป็นภาพรวมเชิงสถิติเพื่อรายงานผลสัมฤทธิ์ของโครงงานเท่านั้น
        </p>
      </div>
    </div>
  `;
}