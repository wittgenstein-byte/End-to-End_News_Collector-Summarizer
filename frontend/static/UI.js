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
 * @param {string}         activeId   — id ที่กำลัง active
 * @param {object}         counts     — {politics: 12, economy: 8, ...}
 */
export function renderCategoryNav(activeId, counts = {}) {
  const nav = document.getElementById("category-nav");
  nav.innerHTML = CATEGORIES.map(cat => {
    const count   = cat.id === "all" ? (counts.all ?? "") : (counts[cat.id] ?? 0);
    const isActive = cat.id === activeId;
    
    // Tailwind specific styling
    const activeClasses = "bg-primary text-white border-primary shadow-sm";
    const inactiveClasses = "bg-white border-outline-variant/30 text-on-surface-variant hover:bg-surface-container";
    
    return `
      <button class="cat-pill flex items-center gap-2 px-5 py-2 rounded-full border text-sm font-medium transition-colors flex-shrink-0 ${isActive ? activeClasses : inactiveClasses}"
              data-id="${cat.id}"
              onclick="__categoryClick('${cat.id}')">
        <span class="material-symbols-outlined text-lg">${cat.icon}</span>
        <span>${cat.label}</span>
        ${count !== "" ? `<span class="cat-count text-[10px] ${isActive ? 'opacity-80' : 'opacity-50'} ml-1 font-bold">${count}</span>` : ""}
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

export function updateSourceFilters(activeSource) {
    document.querySelectorAll(".filter-btn").forEach(btn => {
        const source = btn.dataset.source;
        if (source === activeSource) {
            btn.className = "filter-btn px-5 py-1.5 rounded-lg text-xs font-bold bg-primary text-white hover:bg-primary-container transition-colors";
        } else {
            btn.className = "filter-btn px-5 py-1.5 rounded-lg bg-white border border-outline-variant/30 text-xs font-medium text-on-surface-variant hover:bg-surface-container transition-colors";
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

// ── News grid ─────────────────────────────────────────────────────

/**
 * @param {object[]} articles
 * @param {Set<string>} newUrlSet  — URLs ของข่าวใหม่ใน session นี้
 */
export function renderGrid(articles, newUrlSet = new Set()) {
  const grid = document.getElementById("news-grid");

  if (!articles.length) {
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
    const isNew = newUrlSet.has(n.url);
    const color = SOURCE_COLORS[n.source] ?? "#1a3a6b";
    const imgSrc = resolveImageUrl(n.image_url, n.source);

    // Build Image Markup
    const imgMarkup = imgSrc
      ? `
      <div class="aspect-[16/10] overflow-hidden relative shrink-0">
        <img alt="thumbnail" class="object-cover w-full h-full transition-transform duration-500 group-hover:scale-105" src="${esc(imgSrc)}" onerror="this.parentElement.style.display='none'" loading="lazy" />
      </div>`
      : '';

    return `
      <article class="bg-white rounded-xl overflow-hidden flex flex-col border border-outline-variant/20 transition-shadow duration-300 group hover:shadow-lg hover:-translate-y-1" style="animation: fadeUp 0.5s ease-out ${i * 0.05}s both;">
        <a class="flex flex-col flex-1" href="${esc(n.url) || "#"}" target="_blank" rel="noopener">
          ${imgMarkup}
          <div class="p-8 pb-4 flex flex-col flex-1 ${!imgSrc ? 'border-t-4 border-primary' : ''}">
            
            <div class="flex items-center justify-between mb-6 gap-2">
              <div class="flex items-center gap-2 truncate">
                <span class="w-2 h-2 rounded-full shrink-0" style="background:${color}"></span>
                <span class="text-[10px] font-bold tracking-widest uppercase text-on-surface-variant truncate">${esc(n.source)}</span>
              </div>
              <div class="flex gap-2 shrink-0">
                ${isNew ? `<span class="px-2 py-0.5 rounded-full bg-surface-container text-[10px] font-bold text-primary uppercase">NEW</span>` : ""}
                ${n.classification_method ? `<span class="px-2 py-0.5 rounded-full bg-surface-container text-[10px] font-medium text-outline uppercase truncate max-w-[100px]" title="${esc(n.classification_method)}">${esc(n.classification_method)}</span>` : ""}
              </div>
            </div>

            <h2 class="text-xl lg:text-2xl font-headline font-bold leading-tight mb-4 transition-colors group-hover:text-primary line-clamp-3">${esc(n.title)}</h2>
            
            <p class="text-sm text-outline leading-relaxed mb-4 flex-grow line-clamp-3">${esc(n.summary ?? "")}</p>
            
          </div>
        </a>
        <div class="px-8 pb-8 mt-auto">
          <div class="pt-4 border-t border-outline-variant/10 flex items-center justify-between gap-3">
                <span class="text-[10px] font-bold tracking-widest text-outline-variant uppercase">${esc(n.fetched_at ?? "")}</span>
                <button type="button" class="flex items-center justify-center gap-2 bg-primary/10 text-primary px-4 py-2 rounded-lg font-bold text-xs hover:bg-primary hover:text-white active:scale-95 transition-all w-fit disabled:opacity-50 disabled:cursor-not-allowed"
                        data-url="${esc(n.url)}"
                        ${n.url ? 'onclick="window.__summarize(event, this.dataset.url)"' : 'disabled title="ไม่มี URL"'}>
                  <span class="material-symbols-outlined text-[16px]" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
                  สรุป
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

export function showModalResult(summary) {
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
            <div class="flex items-center space-x-2">
                ${s.category ? `<span class="px-3 py-1 bg-primary/10 text-primary text-[10px] font-bold uppercase tracking-widest rounded-full border border-primary/20">${esc(s.category)}</span>` : ""}
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

    <footer class="mt-12 pt-8 border-t border-outline-variant/20 flex justify-between items-center text-xs font-bold text-outline uppercase tracking-widest">
        <span>Generated: ${new Date().toLocaleTimeString()}</span>
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
