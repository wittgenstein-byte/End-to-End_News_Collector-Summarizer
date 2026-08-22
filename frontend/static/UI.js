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
    const count   = cat.id === "all" ? (counts.all ?? "") : (counts[cat.id] ?? 0);
    const isActive = cat.id === activeId;
    
    return `
      <button class="cat-pill flex items-center gap-2 px-5 py-2 rounded-full border text-sm font-medium transition-colors flex-shrink-0 ${isActive ? activeClasses : inactiveClasses}"
              data-id="${cat.id}"
              onclick="__categoryClick('${cat.id}')">
        <span class="material-symbols-outlined text-lg">${cat.icon}</span>
        <span>${cat.label}</span>
        ${count !== "" ? `<span class="cat-count text-[10px] ${isActive ? 'opacity-80' : 'opacity-50'} ml-1 font-bold">${count}</span>` : ""}
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
      ${bookmarkCount > 0 ? `<span class="cat-count text-[10px] ${isBookmarkActive ? 'opacity-80' : 'opacity-50'} ml-1 font-bold">${bookmarkCount}</span>` : ""}
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
        } else {
          btn.insertAdjacentHTML("beforeend", `<span class="cat-count text-[10px] opacity-50 ml-1 font-bold">${bookmarkCount}</span>`);
        }
      } else if (badge) {
        badge.remove();
      }
      return;
    }
    if (!badge) return;
    const count = id === "all" ? (counts.all ?? "") : (counts[id] ?? 0);
    badge.textContent = count;
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
  let bgClass = "bg-surface-container text-outline border-outline-variant/30";

  if (m.startsWith("URL Priority") || m.startsWith("URL")) {
    icon = "bolt";
    const match = m.match(/\((.*?)\)/);
    const cue = match ? match[1] : "URL";
    label = `URL: ${cue}`;
    bgClass = "bg-blue-50 text-blue-700 border-blue-200";
  } else if (m.startsWith("Hybrid:") || m.includes("WangchanBERTa")) {
    icon = "smart_toy";
    const confMatch = m.match(/conf=([\d.]+)/);
    const pct = confMatch ? ` ${Math.round(parseFloat(confMatch[1]) * 100)}%` : "";
    const isHybrid = m.startsWith("Hybrid");
    label = isHybrid ? `Hybrid WangchanBERTa${pct}` : `WangchanBERTa${pct}`;
    bgClass = "bg-amber-50 text-amber-800 border-amber-300";
  } else if (m.startsWith("ML")) {
    icon = "memory";
    const confMatch = m.match(/conf=([\d.]+)/);
    const pct = confMatch ? ` ${Math.round(parseFloat(confMatch[1]) * 100)}%` : "";
    label = `LinearSVC${pct}`;
    bgClass = "bg-purple-50 text-purple-700 border-purple-200";
  } else if (m.startsWith("Rule (") || m.startsWith("High-Specificity Rule")) {
    icon = "verified";
    const match = m.match(/\((.*?)\)/);
    const cue = match ? match[1] : "Rule";
    label = `Rule: ${cue}`;
    bgClass = "bg-emerald-50 text-emerald-700 border-emerald-200";
  } else if (m.startsWith("Rule-based") || m.startsWith("Rule")) {
    icon = "rule";
    label = "Rules";
    bgClass = "bg-slate-100 text-slate-700 border-slate-300";
  } else {
    icon = "tune";
    label = "Default";
    bgClass = "bg-gray-50 text-gray-600 border-gray-200";
  }

  return `
    <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border shadow-xs ${bgClass}" title="Classification Engine: ${esc(m)}">
      <span class="material-symbols-outlined text-[12px] shrink-0">${icon}</span>
      <span>${esc(label)}</span>
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

export function renderHeroTrending(articles = [], bookmarkedMap = {}) {
  const container = document.getElementById("hero-trending");
  if (!container) return;

  if (!articles || !articles.length) {
    container.innerHTML = "";
    container.classList.add("hidden");
    return;
  }

  container.classList.remove("hidden");

  const resolveImageUrl = (url, source) => {
    if (!url) return "";
    try {
      const u = new URL(url);
      if (source === "The Standard" || u.hostname.endsWith("thestandard.co")) {
        return `/api/image?url=${encodeURIComponent(url)}`;
      }
    } catch (e) {
      return url;
    }
    return url;
  };

  const primaryArticle = articles[0];
  const secondaryArticles = articles.slice(1, 3);

  const primImg = resolveImageUrl(primaryArticle.image_url, primaryArticle.source);
  const primColor = SOURCE_COLORS[primaryArticle.source] ?? "#1a3a6b";
  const primBookmarked = Boolean(bookmarkedMap && bookmarkedMap[primaryArticle.url]);
  const primJsonEncoded = encodeURIComponent(JSON.stringify(primaryArticle));

  let multiSourcePill = "";
  if (primaryArticle.cluster_sources && Array.isArray(primaryArticle.cluster_sources) && primaryArticle.cluster_sources.length > 1) {
    multiSourcePill = `
      <div class="flex items-center gap-1.5 text-xs text-primary font-bold bg-primary/5 px-3 py-1 rounded-full border border-primary/20 w-fit">
        <span class="material-symbols-outlined text-[14px]">hub</span>
        <span>รายงานจาก ${primaryArticle.cluster_sources.length} สำนักข่าว: ${esc(primaryArticle.cluster_sources.join(", "))}</span>
      </div>
    `;
  } else if (primaryArticle.cluster_size && primaryArticle.cluster_size > 1) {
    multiSourcePill = `
      <div class="flex items-center gap-1.5 text-xs text-primary font-bold bg-primary/5 px-3 py-1 rounded-full border border-primary/20 w-fit">
        <span class="material-symbols-outlined text-[14px]">hub</span>
        <span>มีประเด็นตรงกัน ${primaryArticle.cluster_size} สำนักข่าว</span>
      </div>
    `;
  }

  const secondaryCardsHtml = secondaryArticles.map((n, idx) => {
    const rankNum = idx + 2;
    const isBookmarked = Boolean(bookmarkedMap && bookmarkedMap[n.url]);
    const secImg = resolveImageUrl(n.image_url, n.source);
    const color = SOURCE_COLORS[n.source] ?? "#1a3a6b";
    const secJsonEncoded = encodeURIComponent(JSON.stringify(n));

    return `
      <div class="bg-white rounded-xl border border-outline-variant/30 p-4 flex gap-4 hover:shadow-md hover:border-primary/40 transition-all group flex-1">
        ${secImg ? `
        <div class="w-28 sm:w-36 aspect-[4/3] rounded-lg overflow-hidden relative shrink-0 cursor-pointer" onclick="window.__openBrowserWithUrl('${esc(n.url)}')">
          <img src="${esc(secImg)}" alt="thumbnail" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" onerror="this.parentElement.style.display='none'" loading="lazy">
          <span class="absolute top-1.5 left-1.5 px-2 py-0.5 rounded-md bg-black/75 text-white font-bold text-[10px] backdrop-blur-xs">#${rankNum}</span>
        </div>` : `
        <div class="w-12 h-12 rounded-lg bg-surface-container flex items-center justify-center font-bold text-lg text-primary shrink-0">
          #${rankNum}
        </div>`}
        <div class="flex flex-col justify-between flex-1 min-w-0">
          <div>
            <div class="flex items-center justify-between gap-2 mb-1.5 flex-wrap">
              <div class="flex items-center gap-1.5 truncate">
                <span class="w-2 h-2 rounded-full shrink-0" style="background:${color}"></span>
                <span class="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant truncate">${esc(n.source)}</span>
              </div>
              <div class="flex items-center gap-1">
                ${(typeof n.trending_score === "number" && !isNaN(n.trending_score)) ? `<span class="text-[10px] font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">🔥 Trending • ${n.trending_score.toFixed(1)}</span>` : ''}
              </div>
            </div>
            <h3 class="font-headline font-bold text-sm sm:text-base text-on-surface leading-snug line-clamp-2 cursor-pointer group-hover:text-primary transition-colors" onclick="window.__openBrowserWithUrl('${esc(n.url)}')">
              ${esc(n.title)}
            </h3>
          </div>
          <div class="flex items-center justify-between gap-2 pt-2 mt-2 border-t border-outline-variant/10">
            <span class="text-[9px] font-bold text-outline uppercase">${esc(n.fetched_at ?? "")}</span>
            <div class="flex items-center gap-1.5">
              <button type="button" class="p-1 rounded hover:bg-surface-container text-on-surface-variant hover:text-primary transition-colors" onclick="window.__toggleArticleBookmark(event, '${secJsonEncoded}')" title="${isBookmarked ? 'ลบบุ๊กมาร์ก' : 'บันทึกบทความ'}">
                <span class="material-symbols-outlined text-[16px]" style="${isBookmarked ? "font-variation-settings: 'FILL' 1; color: #2e4d83;" : ""}">
                  ${isBookmarked ? 'bookmark' : 'bookmark_border'}
                </span>
              </button>
              <button type="button" class="px-2 py-1 bg-primary/10 text-primary hover:bg-primary hover:text-white rounded text-[11px] font-bold transition-colors flex items-center gap-1" onclick="window.__summarize(event, '${esc(n.url)}')">
                <span class="material-symbols-outlined text-[12px]" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
                สรุป
              </button>
            </div>
          </div>
        </div>
      </div>
    `;
  }).join("");

  container.innerHTML = `
    <div class="mb-4 flex items-center justify-between gap-4">
      <div class="flex items-center gap-2.5">
        <div class="w-8 h-8 rounded-lg bg-gradient-to-tr from-rose-500 to-amber-500 flex items-center justify-center text-white shadow-sm">
          <span class="material-symbols-outlined text-[18px]" style="font-variation-settings: 'FILL' 1;">local_fire_department</span>
        </div>
        <div>
          <h2 class="font-headline font-extrabold text-xl lg:text-2xl text-on-surface tracking-tight">เกาะติดประเด็นร้อน (Trending Highlights)</h2>
          <p class="text-xs text-outline font-medium">วิเคราะห์กระแสข่าวและความเชื่อมโยงหลายสำนักด้วย AI แบบเรียลไทม์</p>
        </div>
      </div>
      <span class="text-[10px] font-bold uppercase tracking-widest text-primary bg-primary/10 px-3 py-1 rounded-full border border-primary/20 hidden sm:inline-flex items-center gap-1">
        <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping"></span>
        AI TRENDING ENGINE
      </span>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 items-stretch">
      <!-- Primary Hero Card (Rank #1) -->
      <div class="lg:col-span-2 bg-white rounded-2xl overflow-hidden border border-outline-variant/30 shadow-md hover:shadow-xl transition-all duration-300 flex flex-col group">
        <div class="relative cursor-pointer overflow-hidden aspect-[16/9] max-h-[380px] bg-slate-900" onclick="window.__openBrowserWithUrl('${esc(primaryArticle.url)}')">
          ${primImg ? `
            <img src="${esc(primImg)}" alt="Hero Highlight" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700 opacity-90" onerror="this.parentElement.style.display='none'" />
          ` : ''}
          <div class="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent flex flex-col justify-between p-6 md:p-8">
            <div class="flex items-center justify-between gap-2 flex-wrap">
              <div class="flex items-center gap-2">
                <span class="px-3 py-1 rounded-full bg-rose-600 text-white font-extrabold text-xs tracking-wider uppercase shadow-md flex items-center gap-1 animate-pulse">
                  <span class="material-symbols-outlined text-[14px]">whatshot</span>
                  <span>#1 HOT STORY</span>
                </span>
                <span class="px-2.5 py-1 rounded-full bg-black/60 text-white backdrop-blur-md text-xs font-bold border border-white/20">
                  🔥 Trending • ${(typeof primaryArticle.trending_score === "number" && !isNaN(primaryArticle.trending_score)) ? primaryArticle.trending_score.toFixed(1) : '9.8'}
                </span>
              </div>
            </div>

            <div>
              <div class="flex items-center gap-2 mb-2">
                <span class="w-2.5 h-2.5 rounded-full" style="background:${primColor}"></span>
                <span class="text-xs font-bold text-white uppercase tracking-wider">${esc(primaryArticle.source)}</span>
              </div>
              <h1 class="text-xl md:text-3xl font-headline font-bold text-white leading-tight drop-shadow-md group-hover:text-amber-200 transition-colors line-clamp-3">
                ${esc(primaryArticle.title)}
              </h1>
            </div>
          </div>
        </div>

        <div class="p-6 md:p-8 flex-1 flex flex-col justify-between space-y-4">
          <div class="space-y-3">
            <div class="flex items-center gap-2 flex-wrap">
              ${renderArticleBadges(primaryArticle, false)}
            </div>
            ${multiSourcePill}
            <p class="text-sm md:text-base text-outline leading-relaxed line-clamp-3">
              ${esc(primaryArticle.summary || "ไม่มีเนื้อหาบทคัดย่อ")}
            </p>
          </div>

          <div class="pt-4 border-t border-outline-variant/20 flex items-center justify-between gap-4 flex-wrap">
            <span class="text-xs font-bold text-outline uppercase tracking-wider">${esc(primaryArticle.fetched_at || "")}</span>
            <div class="flex items-center gap-2">
              <button type="button" class="p-2.5 rounded-xl border border-outline-variant/30 ${primBookmarked ? 'bg-primary/10 text-primary border-primary/30' : 'text-on-surface-variant hover:text-primary hover:bg-surface-container'} active:scale-95 transition-all" onclick="window.__toggleArticleBookmark(event, '${primJsonEncoded}')" title="${primBookmarked ? 'ลบบุ๊กมาร์ก' : 'บันทึกบทความ'}">
                <span class="material-symbols-outlined text-[20px]" style="${primBookmarked ? "font-variation-settings: 'FILL' 1; color: #2e4d83;" : ""}">
                  ${primBookmarked ? 'bookmark' : 'bookmark_border'}
                </span>
              </button>
              <a href="${esc(primaryArticle.url)}" target="_blank" rel="noopener noreferrer" class="flex items-center gap-1.5 border border-outline-variant/30 text-on-surface px-4 py-2.5 rounded-xl font-bold text-xs hover:bg-surface-container hover:text-primary active:scale-95 transition-all" onclick="event.stopPropagation()">
                <span class="material-symbols-outlined text-[16px]">open_in_new</span>
                <span>อ่านต้นฉบับ</span>
              </a>
              <button type="button" class="flex items-center gap-2 bg-primary text-white hover:bg-primary-container px-5 py-2.5 rounded-xl font-bold text-xs shadow-md active:scale-95 transition-all" onclick="window.__summarize(event, '${esc(primaryArticle.url)}')">
                <span class="material-symbols-outlined text-[18px]" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
                <span>สรุปประเด็นด้วย AI</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Secondary Trending Cards (Rank #2, #3) -->
      <div class="flex flex-col gap-4 justify-between">
        ${secondaryCardsHtml}
      </div>
    </div>
  `;
}

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

  const resolveImageUrl = (url, source) => {
    if (!url) return "";
    try {
      const u = new URL(url);
      if (source === "The Standard" || u.hostname.endsWith("thestandard.co")) {
        return `/api/image?url=${encodeURIComponent(url)}`;
      }
    } catch (e) {
      return url;
    }
    return url;
  };

  grid.innerHTML = articles.map((n, i) => {
    const isNew = newUrlSet && newUrlSet.has(n.url);
    const isBookmarked = Boolean(bookmarkedMap && bookmarkedMap[n.url]);
    const color = SOURCE_COLORS[n.source] ?? "#1a3a6b";
    const imgSrc = resolveImageUrl(n.image_url, n.source);
    const articleJsonEncoded = encodeURIComponent(JSON.stringify(n));

    // Build Image Markup
    const imgMarkup = imgSrc
      ? `
      <div class="aspect-[16/10] overflow-hidden relative shrink-0">
        <img alt="thumbnail" class="object-cover w-full h-full transition-transform duration-500 group-hover:scale-105" src="${esc(imgSrc)}" onerror="this.parentElement.style.display='none'" loading="lazy" />
      </div>`
      : '';

    return `
      <article class="bg-white rounded-xl overflow-hidden flex flex-col border border-outline-variant/20 transition-shadow duration-300 group hover:shadow-lg hover:-translate-y-1" style="animation: fadeUp 0.5s ease-out ${i * 0.05}s both;">
        <div class="flex flex-col flex-1 cursor-pointer" data-url="${esc(n.url)}" onclick="window.__openBrowserWithUrl(this.dataset.url)">
          ${imgMarkup}
          <div class="p-8 pb-4 flex flex-col flex-1 ${!imgSrc ? 'border-t-4 border-primary' : ''}">
            
            <div class="flex items-center justify-between mb-4 gap-2 flex-wrap">
              <div class="flex items-center gap-2 truncate">
                <span class="w-2 h-2 rounded-full shrink-0" style="background:${color}"></span>
                <span class="text-[10px] font-bold tracking-widest uppercase text-on-surface-variant truncate">${esc(n.source)}</span>
              </div>
              <div class="flex items-center gap-1.5 shrink-0 flex-wrap">
                ${renderArticleBadges(n, isNew)}
              </div>
            </div>

            <h2 class="text-xl lg:text-2xl font-headline font-bold leading-tight mb-4 transition-colors group-hover:text-primary line-clamp-3">${esc(n.title)}</h2>
            
            <p class="text-sm text-outline leading-relaxed mb-4 flex-grow line-clamp-3">${esc(n.summary ?? "")}</p>
            
          </div>
        </div>
        <div class="px-8 pb-8 mt-auto">
          <div class="pt-4 border-t border-outline-variant/10 flex items-center justify-between gap-3">
                <span class="text-[10px] font-bold tracking-widest text-outline-variant uppercase">${esc(n.fetched_at ?? "")}</span>
                <div class="flex items-center gap-2">
                  ${n.url ? `
                  <button type="button"
                          class="flex items-center justify-center p-2 rounded-lg border border-outline-variant/30 ${isBookmarked ? 'bg-primary/10 text-primary border-primary/30' : 'text-on-surface-variant hover:text-primary hover:bg-surface-container'} active:scale-95 transition-all"
                          onclick="window.__toggleArticleBookmark(event, '${articleJsonEncoded}')"
                          title="${isBookmarked ? 'ลบบุ๊กมาร์ก' : 'บันทึกบทความ'}">
                    <span class="material-symbols-outlined text-[18px]" style="${isBookmarked ? "font-variation-settings: 'FILL' 1; color: #2e4d83;" : ""}">
                      ${isBookmarked ? 'bookmark' : 'bookmark_border'}
                    </span>
                  </button>
                  <a href="${esc(n.url)}" target="_blank" rel="noopener noreferrer"
                     class="flex items-center justify-center gap-1 border border-outline-variant/30 text-on-surface-variant px-3 py-2 rounded-lg font-bold text-xs hover:bg-surface-container hover:text-primary active:scale-95 transition-all"
                     title="เปิดอ่านที่เว็บข่าวต้นทาง"
                     onclick="event.stopPropagation()">
                    <span class="material-symbols-outlined text-[16px]">open_in_new</span>
                    <span class="hidden sm:inline">ต้นทาง</span>
                  </a>` : ""}
                  <button type="button" class="flex items-center justify-center gap-2 bg-primary/10 text-primary px-4 py-2 rounded-lg font-bold text-xs hover:bg-primary hover:text-white active:scale-95 transition-all w-fit disabled:opacity-50 disabled:cursor-not-allowed"
                          data-url="${esc(n.url)}"
                          ${n.url ? 'onclick="window.__summarize(event, this.dataset.url)"' : 'disabled title="ไม่มี URL"'}>
                    <span class="material-symbols-outlined text-[16px]" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
                    สรุป
                  </button>
                </div>
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
