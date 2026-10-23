/**
 * frontend/static/components/evaluation.js
 * ─────────────────────────────────────────────────────────────────
 * Academic Thesis Project Evaluation & Feedback Landing View
 *
 * Responsibilities:
 * - Editorial project evaluation landing page view
 * - Google Forms feedback questionnaire link & state tracker
 * - Core architectural capability highlights (5 Pillars)
 * - PDPA compliance and research ethics disclosure
 * ─────────────────────────────────────────────────────────────────
 */

import { FEEDBACK_FORM_URL, FEEDBACK_COMPLETED_KEY } from "../config.js";

/**
 * Renders the comprehensive Project Evaluation and Academic Feedback landing view.
 * Displays project objectives, 5 core architectural capabilities, PDPA statement,
 * and direct call-to-action button linking to the Google Forms evaluation questionnaire.
 */
export function renderEvaluationView() {
  const container = document.getElementById("evaluation-view");
  if (!container) return;

  const isCompleted = typeof localStorage !== "undefined" && localStorage.getItem(FEEDBACK_COMPLETED_KEY) === "true";

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
