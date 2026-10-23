/**
 * frontend/static/utils/common.js
 * ─────────────────────────────────────────────────────────────────
 * Common Utilities & Editorial Formatting Helpers
 *
 * Responsibilities:
 * - HTML entity escaping and sanitization
 * - Thai Buddhist calendar and editorial date/time formatters
 * - Copyright-safe local placeholder resolution
 * - Article classification & editorial badge generators
 * - Storyline navigation breadcrumbs
 * - Shared storyline cache state management
 * ─────────────────────────────────────────────────────────────────
 */

import { getSentimentConfig, SENTIMENT_CONFIG } from "../config.js";

// ── Shared Storyline Cache State ──────────────────────────────────
let currentStorylineDataCache = null;

export function setStorylineCache(data) {
  currentStorylineDataCache = data;
}

export function getStorylineCache() {
  return currentStorylineDataCache;
}

export function clearStorylineCache() {
  currentStorylineDataCache = null;
}

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

// ── Category Badges & Names ───────────────────────────────────────

export function categoryBadgeClass(category = "") {
  const cat = String(category || "").toLowerCase().trim();
  const map = {
    politics: "bg-red-900/80 text-red-100 border-red-700/50",
    economy: "bg-emerald-900/80 text-emerald-100 border-emerald-700/50",
    technology: "bg-blue-900/80 text-blue-100 border-blue-700/50",
    environment: "bg-teal-900/80 text-teal-100 border-teal-700/50",
    sports: "bg-amber-900/80 text-amber-100 border-amber-700/50",
    world: "bg-purple-900/80 text-purple-100 border-purple-700/50",
  };
  return map[cat] || "bg-slate-800 text-slate-100 border-slate-700/50";
}

export function categoryNameTh(category = "") {
  const cat = String(category || "").toLowerCase().trim();
  const map = {
    all: "ทั้งหมด",
    politics: "การเมือง",
    economy: "เศรษฐกิจ",
    technology: "เทคโนโลยี",
    environment: "สิ่งแวดล้อม",
    sports: "กีฬา",
    world: "ต่างประเทศ",
  };
  return map[cat] || category || "";
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

// ── Perspective Label ─────────────────────────────────────────────

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

// ── Storyline Breadcrumb ──────────────────────────────────────────

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

// ── Thai Date & Time Formatters ───────────────────────────────────

export const THAI_MONTHS_SHORT = [
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
  const escaped = esc(str);
  return escaped.startsWith("อัปเดตล่าสุด") ? escaped : `อัปเดตล่าสุด • ${escaped}`;
}

export function formatShortTime(dateStr) {
  if (!dateStr) return "";
  const str = String(dateStr).trim();
  const timeMatch = str.match(/(?:[T\s]|^)(\d{1,2}:\d{2})/);
  if (timeMatch) return timeMatch[1];
  const d = new Date(str);
  if (!isNaN(d.getTime())) {
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  }
  return "";
}

export function formatTimeOnly(dateStr) {
  if (!dateStr) return "";
  const short = formatShortTime(dateStr);
  return short ? `${short} น.` : "";
}

export function formatRelativeTime(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return esc(String(dateStr));
  const diffMs = Date.now() - d.getTime();
  if (diffMs < 0) {
    return formatEditorialDateTime(dateStr) || "เร็วๆ นี้";
  }
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return "เมื่อสักครู่";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin} นาทีที่แล้ว`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours} ชั่วโมงที่แล้ว`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays} วันที่แล้ว`;
  return formatEditorialDateOnly(dateStr);
}
