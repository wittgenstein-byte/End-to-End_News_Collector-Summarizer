/**
 * frontend/static/components/digest.js
 * ─────────────────────────────────────────────────────────────────
 * Storyline AI Progression Synthesis & Citation Dossier
 *
 * Responsibilities:
 * - AI event progression timeline with evidence links
 * - Confirmed multi-source facts and cross-outlet conflict cards
 * - Interactive citation chips with auto-scroll and pulse highlighting
 * - Quality audit panel telemetry and excluded outlier articles details
 * - Global window handlers for dossier tab and citation inspection
 * ─────────────────────────────────────────────────────────────────
 */

import { esc, formatEditorialDateTime, getStorylineCache } from "../utils/common.js";
import { checkIsSportsCluster } from "./sports-intelligence.js";
import { renderSportsAiDigest } from "./sports.js";

// ── Citations Chips ───────────────────────────────────────────────

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

// ── Storyline AI Loading ──────────────────────────────────────────

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

// ── Storyline AI Synthesis Dossier ────────────────────────────────

export function renderStorylineAiSynthesis(synthesisData) {
  const section = document.getElementById("storyline-ai-section");
  if (!section || !synthesisData) return;

  const currentStorylineDataCache = getStorylineCache();
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

  // Mode 1: Halted Mismatch Alert
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

  let timelineTitle = 'ลำดับเหตุการณ์สำคัญ (ยืนยันตรงกันทุกสื่อ)';
  if (isSingleSource) {
    timelineTitle = 'ลำดับเหตุการณ์เบื้องต้น (จากรายงานแหล่งข่าวเดียว)';
  } else if (s.is_fallback) {
    timelineTitle = 'ลำดับรายงานตามเวลา (โหมดรวบรวมอัตโนมัติ)';
  }

  const timelineHtml = `
      <div class="space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-zinc-400 flex items-center gap-1.5">
            <span class="material-symbols-outlined text-[16px] ${isSingleSource ? 'text-sky-600 dark:text-sky-400' : 'text-amber-600 dark:text-amber-400'}">${isSingleSource ? 'feed' : 'timeline'}</span>
            ${timelineTitle}
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
    `;

  const rightColHtml = conflicts.length > 0 ? `
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
    ` : "");

  const hasRightContent = Boolean(rightColHtml && rightColHtml.trim());

  section.innerHTML = `
      <!-- Executive Summary -->
      <div class="pl-4 sm:pl-5 py-1 border-l-2 ${isSingleSource ? 'border-sky-500/80 dark:border-sky-400/80' : 'border-amber-600/80 dark:border-amber-400/80'} text-slate-700 dark:text-zinc-200 text-sm sm:text-base leading-relaxed">
        ${esc(summaryText || "รวบรวมและสังเคราะห์ประเด็นสำคัญจากสำนักข่าวทั้งหมด")}
      </div>

      <!-- Content -->
      <div class="${hasRightContent ? 'grid grid-cols-1 lg:grid-cols-12 gap-6' : 'max-w-4xl'} pt-2">
        <div class="${hasRightContent ? 'lg:col-span-7' : 'w-full'}">
          ${timelineHtml}
        </div>
        ${hasRightContent ? `
          <div class="lg:col-span-5 space-y-5">
            ${rightColHtml}
          </div>
        ` : ""}
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

// ── Global Handlers for Event Progression Dossier & Citation Inspection ──

if (typeof window !== "undefined") {
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
    const findEvidenceEl = () => {
      let found = document.getElementById(`article-evidence-${cleanId}`);
      if (!found) {
        try {
          const safeSelector = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(cleanId) : cleanId.replace(/["\\]/g, '\\$&');
          found = document.querySelector(`[data-evidence-id="${safeSelector}"]`);
        } catch {
          found = null;
        }
      }
      return found;
    };
    let el = findEvidenceEl();
    if (!el && typeof window.__filterStorylinePublisher === "function") {
      window.__filterStorylinePublisher("");
      el = findEvidenceEl();
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
}
