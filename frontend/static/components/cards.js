/**
 * frontend/static/components/cards.js
 * ─────────────────────────────────────────────────────────────────
 * News Cards, Editorial Feed Grid & Pagination Controls
 *
 * Responsibilities:
 * - Editorial news card feed grid with responsive layout
 * - Mobile & desktop optimized thumbnail, dateline and badges
 * - Skeleton loading spinner for articles feed
 * - Graceful server error fallback states
 * - Pagination bar with fast-jump page buttons
 * ─────────────────────────────────────────────────────────────────
 */

import { esc, getCategoryPlaceholder, formatShortTime, renderArticleBadges } from "../utils/common.js";
import { SOURCE_COLORS, getCategoryById } from "../config.js";

// ── News Grid (Editorial Responsive Cards) ────────────────────────

export function renderGrid(articles, newUrlSet = new Set(), bookmarkedMap = {}) {
  const grid = document.getElementById("news-grid");
  if (!grid) return;

  if (!articles || !articles.length) {
    grid.innerHTML = `<div class="col-span-full text-center py-20 text-outline font-headline italic text-lg">ไม่พบบทความในหมวดหมู่ หรือคำค้นหานี้</div>`;
    return;
  }

  const validArticles = articles.filter(Boolean);
  if (!validArticles.length) {
    grid.innerHTML = `<div class="col-span-full text-center py-20 text-outline font-headline italic text-lg">ไม่พบบทความในหมวดหมู่ หรือคำค้นหานี้</div>`;
    return;
  }

  grid.innerHTML = validArticles.map((n, i) => {
    n = n || {};
    const isNew = newUrlSet && (newUrlSet instanceof Set ? newUrlSet.has(n.url) : (Array.isArray(newUrlSet) && newUrlSet.includes(n.url)));
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
                ${n.fetched_at ? `<span class="text-[10px] font-mono text-outline opacity-60 shrink-0">• ${esc(formatShortTime(n.fetched_at))}</span>` : ""}
              </div>
              <div class="flex items-center gap-1 shrink-0 flex-wrap justify-end">
                ${renderArticleBadges(n, isNew)}
              </div>
            </div>

            <!-- Headline: Directly at top on mobile -->
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

            <!-- Mobile Dateline & Source: directly below headline -->
            <div class="flex sm:hidden items-center justify-between gap-1 mt-auto pt-1 text-xs overflow-hidden">
              <div class="flex items-center gap-1.5 min-w-0 flex-1 overflow-hidden mr-1 text-outline">
                <span class="w-1.5 h-1.5 rounded-full shrink-0" style="background:${color}"></span>
                <span class="text-[11px] font-medium text-on-surface-variant/90 truncate">${esc(n.source)}</span>
                ${n.fetched_at ? `<span class="text-[10px] font-mono opacity-60 shrink-0 whitespace-nowrap">• ${esc(formatShortTime(n.fetched_at))}</span>` : ""}
              </div>
              <div class="flex items-center gap-1 shrink-0 ml-auto z-10" onclick="event.stopPropagation()">
                ${(n.story_id || n.macro_event_id) ? `
                <button type="button"
                        class="px-1.5 py-0.5 rounded bg-surface-container hover:bg-primary hover:text-white text-[10px] font-semibold text-on-surface-variant flex items-center gap-0.5 transition-colors cursor-pointer shrink-0"
                        onclick="window.__openStoryline('${esc(n.story_id || n.macro_event_id)}', '${esc(n.title)}')"
                        title="เปิดแฟ้มเกาะติดเหตุการณ์นี้">
                  <span class="material-symbols-outlined text-[11px]">account_tree</span>
                  <span>แฟ้มข่าว</span>
                </button>` : ""}
                ${n.url ? `
                <button type="button"
                        class="p-1 rounded text-outline hover:text-on-surface bookmark-btn shrink-0 ${isBookmarked ? 'active text-amber-500' : ''}"
                        data-url="${esc(n.url)}"
                        onclick="window.__toggleArticleBookmark(event, '${articleJsonEncoded}')"
                        title="${isBookmarked ? 'ลบบุ๊กมาร์ก' : 'บันทึกบทความ'}">
                  <span class="material-symbols-outlined text-[15px]" style="${isBookmarked ? "font-variation-settings: 'FILL' 1; color: #f59e0b;" : ""}">
                    ${isBookmarked ? 'bookmark' : 'bookmark_border'}
                  </span>
                </button>` : ""}
                <button type="button"
                        class="px-2 py-0.5 rounded bg-black/5 dark:bg-white/10 hover:bg-amber-500 hover:text-black text-[10px] font-bold text-on-surface flex items-center gap-0.5 transition-colors cursor-pointer shrink-0"
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
        <div class="hidden sm:flex px-4 py-2 mt-auto border-t border-outline-variant/25 items-center justify-end gap-1 bg-surface/40" onclick="event.stopPropagation()">
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

            ${(n.story_id || n.macro_event_id) ? `
            <button type="button"
                    class="editorial-card-action-btn flex items-center gap-1"
                    onclick="window.__openStoryline('${esc(n.story_id || n.macro_event_id)}', '${esc(n.title)}')"
                    title="เปิดแฟ้มเหตุการณ์และลำดับความคืบหน้า">
              <span class="material-symbols-outlined text-[13px]">account_tree</span>
              <span>แฟ้มประเด็น</span>
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
  if (!meta || typeof meta !== "object") {
    pg.innerHTML = "";
    return;
  }
  const { page = 1, total_pages: totalPages = 1, total = 0 } = meta;

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
