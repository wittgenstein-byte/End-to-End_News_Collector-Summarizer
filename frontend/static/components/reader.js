/**
 * frontend/static/components/reader.js
 * ─────────────────────────────────────────────────────────────────
 * Reader View, AI Summary Modals & Reading History Management
 *
 * Responsibilities:
 * - Executive Briefing AI summary popup modal
 * - Inline accordion summary inside article preview view
 * - Full-page article preview reader drawer
 * - Reading history & saved bookmarks modal list
 * - Primary application view switching (feed / preview / storyline / evaluation)
 * ─────────────────────────────────────────────────────────────────
 */

import { esc, getCategoryPlaceholder, formatClassificationBadge } from "../utils/common.js";
import { SOURCE_COLORS, FEEDBACK_FORM_URL, FEEDBACK_COMPLETED_KEY } from "../config.js";

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
  
  if (typeof document !== "undefined" && document.body) {
    document.body.style.overflow = "hidden";
  }
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
    if (typeof document !== "undefined" && document.body) {
      document.body.style.overflow = "";
    }
  }, 300);
}

export function showModalLoading() {
  const loading = document.getElementById("summary-loading");
  const result = document.getElementById("summary-result");
  if (loading) loading.style.display = "block";
  if (result) {
    result.style.display = "none";
    result.innerHTML = "";
  }
}

export function showModalResult(summary, originalUrl = "") {
  const s = summary || {};
  const loading = document.getElementById("summary-loading");
  const result = document.getElementById("summary-result");
  if (loading) loading.style.display = "none";
  if (!result) return;
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

  const isFeedbackCompleted = typeof localStorage !== "undefined" && localStorage.getItem(FEEDBACK_COMPLETED_KEY) === "true";

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

    ${!isFeedbackCompleted ? `
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
  const loading = document.getElementById("summary-loading");
  const result = document.getElementById("summary-result");
  if (loading) loading.style.display = "none";
  if (!result) return;
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
    if (typeof window !== "undefined" && typeof window.__pauseTrendingAutoPlay === "function") {
      window.__pauseTrendingAutoPlay();
    }
    if (feedView) feedView.classList.add("hidden");
    if (storylineView) storylineView.classList.add("hidden");
    if (evaluationView) evaluationView.classList.add("hidden");
    if (previewView) previewView.classList.remove("hidden");
    if (floatingBack) floatingBack.classList.add("hidden-fade");
    if (topBar) topBar.classList.remove("is-hidden");
    if (typeof window !== "undefined" && typeof window.scrollTo === "function") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  } else if (viewName === "storyline") {
    if (typeof window !== "undefined" && typeof window.__pauseTrendingAutoPlay === "function") {
      window.__pauseTrendingAutoPlay();
    }
    if (feedView) feedView.classList.add("hidden");
    if (previewView) previewView.classList.add("hidden");
    if (evaluationView) evaluationView.classList.add("hidden");
    if (storylineView) storylineView.classList.remove("hidden");
    if (floatingBack) floatingBack.classList.add("hidden-fade");
    if (topBar) topBar.classList.remove("is-hidden");
    if (typeof window !== "undefined" && typeof window.scrollTo === "function") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  } else if (viewName === "evaluation") {
    if (typeof window !== "undefined" && typeof window.__pauseTrendingAutoPlay === "function") {
      window.__pauseTrendingAutoPlay();
    }
    if (feedView) feedView.classList.add("hidden");
    if (previewView) previewView.classList.add("hidden");
    if (storylineView) storylineView.classList.add("hidden");
    if (evaluationView) evaluationView.classList.remove("hidden");
    if (floatingBack) floatingBack.classList.add("hidden-fade");
    if (topBar) topBar.classList.remove("is-hidden");
    if (typeof window !== "undefined" && typeof window.scrollTo === "function") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  } else {
    if (previewView) previewView.classList.add("hidden");
    if (storylineView) storylineView.classList.add("hidden");
    if (evaluationView) evaluationView.classList.add("hidden");
    if (feedView) feedView.classList.remove("hidden");
    if (floatingBack) floatingBack.classList.add("hidden-fade");
    if (topBar) topBar.classList.remove("is-hidden");
    if (typeof window !== "undefined" && typeof window.__resumeTrendingAutoPlay === "function") {
      window.__resumeTrendingAutoPlay();
    }
  }
}

// ── Preview Sub-View Rendering ────────────────────────────────────

export function renderInlineSummary(summary) {
  const s = summary || {};
  const bullets = (s.bullets ?? []).map((b, i) => `
    <li class="flex items-start gap-3 text-sm leading-relaxed text-slate-800 dark:text-slate-100 font-medium">
      <span class="preview-ai-bullet-num font-mono text-xs font-bold text-amber-600 dark:text-amber-400 mt-0.5 shrink-0">0${i+1}.</span>
      <span class="preview-ai-bullet-text">${esc(b)}</span>
    </li>
  `).join("");

  const keywords = (s.keywords ?? []).map(k => `
    <span class="preview-ai-tag px-2.5 py-1 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 font-mono text-[11px] font-semibold rounded-md">#${esc(k)}</span>
  `).join("");

  const isFeedbackCompleted = typeof localStorage !== "undefined" && localStorage.getItem(FEEDBACK_COMPLETED_KEY) === "true";

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

      ${!isFeedbackCompleted ? `
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
  if (!preview || !article) return;

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
        ${(article.story_id || article.macro_event_id) ? `
        <button class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-amber-500/40 bg-amber-50 hover:bg-amber-100 dark:bg-amber-500/10 dark:hover:bg-amber-500/20 text-amber-900 dark:text-amber-300 text-xs font-bold transition-colors cursor-pointer"
                onclick="window.__openStoryline('${esc(article.story_id || article.macro_event_id)}', '${esc(article.title)}')"
                title="ดูแฟ้มลำดับเหตุการณ์และข่าวจากสำนักอื่นในประเด็นเดียวกัน">
          <span class="material-symbols-outlined text-[16px]">account_tree</span>
          <span>ดูแฟ้มประเด็นข่าว</span>
        </button>` : ""}

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
