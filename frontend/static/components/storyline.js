/**
 * frontend/static/components/storyline.js
 * ─────────────────────────────────────────────────────────────────
 * Macro Storyline View & Executive Event Dossier
 *
 * Responsibilities:
 * - Macro storyline executive dossier view
 * - Two-Stage Event Architecture (Stage B Macro-Event & Stage A Sub-Events)
 * - Publisher perspective horizontal filter pills with corroborated checkmarks
 * - Chronological evidence grid with citation IDs ([ART_01], [ART_02])
 * - Loading and error states for storyline container
 * - Timeline panel navigation helpers
 * ─────────────────────────────────────────────────────────────────
 */

import {
  esc,
  getCategoryPlaceholder,
  formatEditorialDateOnly,
  getPerspectiveLabel,
  setStorylineCache,
} from "../utils/common.js";
import { checkIsSportsCluster } from "./sports-intelligence.js";
import { renderSportsStorylineView } from "./sports.js";
import { renderStorylineAiSynthesis } from "./digest.js";
import { SOURCE_COLORS } from "../config.js";

// ── Storyline Container Loading & Error States ────────────────────

export function showStorylineLoading() {
  const container = document.getElementById("storyline-view");
  if (!container) return;
  container.innerHTML = `
    <div class="storyline-loading text-center py-24 space-y-4">
      <svg class="animate-spin h-8 w-8 text-secondary mx-auto" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2.5"></circle>
        <path class="opacity-80" d="M12 2a10 10 0 0110 10" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="2.5"></path>
      </svg>
      <div class="font-headline italic text-base text-on-surface">กำลังเปิดแฟ้มเจาะลึกและรวบรวมมุมมองข่าว...</div>
      <p class="text-xs font-mono text-outline">AGGREGATING TIMELINES & MULTI-PERSPECTIVE COVERAGE</p>
    </div>
  `;
}

export function showStorylineError(msg = "ไม่สามารถโหลดข้อมูลแฟ้มประเด็นข่าวได้") {
  const container = document.getElementById("storyline-view");
  if (!container) return;
  container.innerHTML = `
    <div class="storyline-error text-center py-24 space-y-4">
      <span class="material-symbols-outlined text-4xl text-error">error</span>
      <div class="font-headline text-lg font-bold text-on-surface">${esc(msg)}</div>
      <button class="px-4 py-2 bg-surface hover:bg-surface-container rounded-lg text-xs font-bold border border-outline-variant/40 cursor-pointer"
              onclick="window.__backFromStoryline()">
        กลับหน้ารวมข่าว
      </button>
    </div>
  `;
}

// ── Storyline Executive Dossier View ──────────────────────────────

export function renderStorylineView(
  storyData,
  activeSourceFilter = "",
  bookmarkedMap = {},
  activeSportDisciplineFilter = "",
  activeSportContentTypeFilter = "",
  activeSubEventFilter = "",
  activeSortOrder = "latest"
) {
  const container = document.getElementById("storyline-view");
  if (!container || !storyData) return;

  setStorylineCache(storyData);

  const rawArticles = Array.isArray(storyData.articles) ? storyData.articles : [];

  // Canonical chronological ordering for evidence citation indexing (ART_01, ART_02, etc.)
  const chronologicalArticles = [...rawArticles].sort((a, b) => {
    const timeA = new Date(a.fetched_at || a.created_at || 0).getTime();
    const timeB = new Date(b.fetched_at || b.created_at || 0).getTime();
    return timeA - timeB;
  });

  // Check if this cluster is predominantly sports news -> dispatch to dedicated sports roundup view
  if (checkIsSportsCluster(storyData, chronologicalArticles)) {
    return renderSportsStorylineView(
      storyData,
      activeSourceFilter,
      activeSportDisciplineFilter,
      activeSportContentTypeFilter,
      bookmarkedMap
    );
  }

  const isMacroView = Boolean(
    storyData._is_macro_view ??
    (Array.isArray(storyData.child_events) || (storyData.macro_event_id && !storyData.story_id))
  );
  const storyId = storyData._target_id || (isMacroView ? storyData.macro_event_id : storyData.story_id) || storyData.macro_event_id || storyData.story_id || storyData.cluster_id || "";
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
  chronologicalArticles.forEach((art, idx) => {
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
  chronologicalArticles.forEach(a => {
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

  // Build sub-event URL lookup if filtering by a specific Stage A child story
  let subEventAllowedUrls = null;
  if (activeSubEventFilter && Array.isArray(storyData.child_events)) {
    const matchedSub = storyData.child_events.find(
      ce => String(ce.story_id || "").toLowerCase() === String(activeSubEventFilter).toLowerCase()
    );
    if (matchedSub) {
      subEventAllowedUrls = new Set(
        [
          ...(Array.isArray(matchedSub.article_urls) ? matchedSub.article_urls : []),
          ...(Array.isArray(matchedSub.articles) ? matchedSub.articles.map(a => a.url) : []),
        ]
          .filter(Boolean)
          .map(u => String(u).trim())
      );
    }
  }

  // Filter articles based on activeSubEventFilter and activeSourceFilter
  let filteredArticles = chronologicalArticles;
  if (activeSubEventFilter) {
    filteredArticles = filteredArticles.filter(art => {
      if (art.story_id && String(art.story_id).toLowerCase() === String(activeSubEventFilter).toLowerCase()) {
        return true;
      }
      if (subEventAllowedUrls && art.url && subEventAllowedUrls.has(String(art.url).trim())) {
        return true;
      }
      return false;
    });
  }

  if (activeSourceFilter === "__context_excluded__") {
    filteredArticles = filteredArticles.filter(art => {
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
    filteredArticles = filteredArticles.filter(a => (a.source || "").toLowerCase() === activeSourceFilter.toLowerCase());
  }

  const allIsActive = !activeSourceFilter;
  let publisherPillsHtml = `
    <button type="button" 
            class="storyline-publisher-pill ${allIsActive ? 'active' : ''}"
            onclick="window.__filterStorylinePublisher('')">
      <span>ทุกสำนักข่าว</span>
      <span class="pill-count">${chronologicalArticles.length}</span>
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

  // Build Two-Stage Architecture Metadata & Verification Badges
  const verificationStatus = storyData.verification_status || "verified";
  const isVerifiedStatus = verificationStatus !== "pending_review";
  const verificationBadgeHtml = isMacroView
    ? `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold bg-indigo-50 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 border border-indigo-200/80 dark:border-indigo-500/30" title="โครงเรื่องใหญ่ (Stage B Macro-Event)"><span class="material-symbols-outlined text-[13px]">hub</span><span>โครงเรื่องใหญ่ (Macro-Event)</span></span>`
    : `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold bg-teal-50 dark:bg-teal-500/15 text-teal-700 dark:text-teal-300 border border-teal-200/80 dark:border-teal-500/30" title="เหตุการณ์จำเพาะ (Stage A Event Cluster)"><span class="material-symbols-outlined text-[13px]">event_note</span><span>เหตุการณ์จำเพาะ (Stage A Event)</span></span>`;

  const corroborationBadgeHtml = isVerifiedStatus
    ? `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium bg-emerald-50 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-200/80 dark:border-emerald-500/30" title="ผ่านการตรวจสอบความสอดคล้องของหลักฐานข้ามสำนักข่าว"><span class="material-symbols-outlined text-[13px]">verified</span><span>ยืนยันข้ามสำนักข่าว</span></span>`
    : `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium bg-amber-50 dark:bg-amber-500/15 text-amber-800 dark:text-amber-300 border border-amber-200/80 dark:border-amber-500/30" title="รอหลักฐานอิสระเพิ่มเติมจากสำนักข่าวอื่น"><span class="material-symbols-outlined text-[13px]">schedule</span><span>รอการยืนยันเพิ่มเติม</span></span>`;

  const parentMacroLinkHtml = (!isMacroView && storyData.macro_event_id)
    ? `<button type="button" onclick="window.__openStoryline('${esc(storyData.macro_event_id)}')" class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[11px] font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition-colors cursor-pointer shadow-2xs" title="ดูโครงเรื่องใหญ่ที่ครอบคลุมเหตุการณ์นี้"><span class="material-symbols-outlined text-[13px]">account_tree</span><span>ดูโครงเรื่องใหญ่ (${esc(storyData.macro_event_id.slice(0, 12))})</span></button>`
    : "";

  const antecedentId = storyData.metadata?.antecedent_story_id || "";
  const antecedentLinkHtml = antecedentId
    ? `<button type="button" onclick="window.__openStoryline('${esc(antecedentId)}')" class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[11px] font-medium bg-slate-100 hover:bg-slate-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 text-slate-700 dark:text-zinc-200 border border-slate-200 dark:border-zinc-700 transition-colors cursor-pointer" title="คลิกเพื่อดูเหตุการณ์ต้นเรื่องก่อนหน้า (Follow-up Lineage)"><span class="material-symbols-outlined text-[13px]">history</span><span>ความคืบหน้าต่อเนื่องจาก ${esc(antecedentId.slice(0, 12))}</span></button>`
    : "";

  // Extract Typed Event Anchors & Event Time Interval
  const typedAnchors = storyData.typed_anchors || {};
  const storylineAnchor = storyData.storyline_anchor || typedAnchors.storyline_anchor || "";
  const anchorLocations = Array.isArray(typedAnchors.locations) ? typedAnchors.locations.slice(0, 3) : [];
  const anchorActors = Array.isArray(typedAnchors.actors) ? typedAnchors.actors.slice(0, 3) : [];
  const anchorActions = Array.isArray(typedAnchors.actions) ? typedAnchors.actions.slice(0, 2) : [];
  const eventTimeObj = storyData.event_time || {};
  const eventTimeLabel = (eventTimeObj.precision && eventTimeObj.precision !== "unknown" && eventTimeObj.start_utc)
    ? formatEditorialDateOnly(eventTimeObj.start_utc)
    : "";

  const hasAnchorRow = Boolean(storylineAnchor || anchorLocations.length || anchorActors.length || anchorActions.length || eventTimeLabel);
  const typedAnchorsHtml = hasAnchorRow ? `
    <div class="flex items-center gap-1.5 flex-wrap pt-1 text-[11px]">
      ${eventTimeLabel ? `
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-100 dark:bg-zinc-800 text-slate-600 dark:text-zinc-300 font-medium" title="ช่วงเวลาเกิดเหตุที่สกัดได้จากเนื้อข่าว (Incident Time)">
          <span class="material-symbols-outlined text-[12px] text-amber-600 dark:text-amber-400">event</span>
          <span>เวลาเกิดเหตุ: ${esc(eventTimeLabel)}</span>
        </span>
      ` : ""}
      ${storylineAnchor ? `
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 border border-amber-200/60 dark:border-amber-500/30 font-semibold">
          <span class="material-symbols-outlined text-[12px]">bookmark_flag</span>
          <span>แกนเรื่อง: ${esc(storylineAnchor)}</span>
        </span>
      ` : ""}
      ${anchorLocations.map(loc => `
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-100 dark:bg-zinc-800 text-slate-600 dark:text-zinc-300">
          <span class="material-symbols-outlined text-[12px] text-rose-500">location_on</span>
          <span>${esc(loc)}</span>
        </span>
      `).join("")}
      ${anchorActors.map(act => `
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-100 dark:bg-zinc-800 text-slate-600 dark:text-zinc-300">
          <span class="material-symbols-outlined text-[12px] text-sky-500">person</span>
          <span>${esc(act)}</span>
        </span>
      `).join("")}
      ${anchorActions.map(ac => `
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-100 dark:bg-zinc-800 text-slate-600 dark:text-zinc-300">
          <span class="material-symbols-outlined text-[12px] text-emerald-500">bolt</span>
          <span>${esc(ac)}</span>
        </span>
      `).join("")}
    </div>
  ` : "";

  // Build Stage A Child Sub-Events Progression
  const childEvents = Array.isArray(storyData.child_events) ? storyData.child_events : [];
  const relations = Array.isArray(storyData.relations) ? storyData.relations : [];
  const relationTypeLabels = {
    updates: "อัปเดตความคืบหน้า",
    precedes: "ลำดับต่อเนื่อง",
    responds_to: "มาตรการตอบสนอง",
    caused_by: "สืบเนื่องจากสาเหตุ",
  };

  const childEventsSectionHtml = childEvents.length > 1 ? `
    <div id="storyline-subevents-section" class="pt-4 border-t border-slate-100 dark:border-zinc-800 space-y-2.5">
      <div class="flex items-center justify-between flex-wrap gap-2">
        <div class="flex items-center gap-1.5 text-xs font-bold text-slate-700 dark:text-zinc-200">
          <span class="material-symbols-outlined text-[16px] text-indigo-600 dark:text-indigo-400">timeline</span>
          <span>ลำดับเหตุการณ์ย่อยในโครงเรื่อง (${childEvents.length} เหตุการณ์)</span>
        </div>
        ${activeSubEventFilter ? `
          <button type="button"
                  onclick="window.__filterStorylineSubEvent('')"
                  class="text-[11px] font-semibold text-indigo-600 dark:text-indigo-400 hover:underline cursor-pointer">
            แสดงทุกเหตุการณ์ย่อยทั้งหมด
          </button>
        ` : `<span class="text-[11px] text-slate-400 dark:text-zinc-500">คลิกเพื่อกรองข่าวเฉพาะเหตุการณ์ย่อย หรือเปิดแฟ้มแยก</span>`}
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        ${childEvents.map((ce, idx) => {
          const ceId = ce.story_id || "";
          const isSelected = activeSubEventFilter && String(activeSubEventFilter).toLowerCase() === String(ceId).toLowerCase();
          const rel = relations.find(r => r.source_event_id === ceId || r.target_event_id === ceId);
          const relLabel = rel ? (relationTypeLabels[rel.relation_type] || rel.relation_type) : (idx > 0 ? "พัฒนาการต่อเนื่อง" : "จุดเริ่มต้นประเด็น");
          const ceArtCount = ce.article_count || (Array.isArray(ce.article_urls) ? ce.article_urls.length : 1);
          const ceOutletCount = ce.outlet_count || (Array.isArray(ce.outlets) ? ce.outlets.length : 1);
          return `
            <div class="p-3 rounded-xl border transition-all flex flex-col justify-between gap-2 ${
              isSelected
                ? 'border-indigo-500 bg-indigo-50/70 dark:bg-indigo-950/30 shadow-xs'
                : 'border-slate-200 dark:border-zinc-800 bg-slate-50/60 dark:bg-zinc-800/40 hover:border-slate-300 dark:hover:border-zinc-700'
            }">
              <div class="space-y-1 cursor-pointer" onclick="window.__filterStorylineSubEvent('${esc(ceId)}')">
                <div class="flex items-center justify-between gap-2 text-[10px] font-mono">
                  <span class="px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 font-bold">
                    EVENT #${idx + 1} • ${esc(relLabel)}
                  </span>
                  <span class="text-slate-400 dark:text-zinc-500">${ceArtCount} ข่าว • ${ceOutletCount} สำนัก</span>
                </div>
                <div class="text-xs font-bold text-slate-800 dark:text-zinc-100 line-clamp-2 leading-snug">
                  ${esc(ce.headline || ce.title || "เหตุการณ์ย่อย")}
                </div>
              </div>
              <div class="flex items-center justify-between gap-2 pt-1 border-t border-slate-200/60 dark:border-zinc-700/50 text-[11px]">
                <button type="button"
                        onclick="window.__filterStorylineSubEvent('${esc(ceId)}')"
                        class="font-semibold ${isSelected ? 'text-indigo-700 dark:text-indigo-300' : 'text-slate-500 dark:text-zinc-400 hover:text-slate-800'} cursor-pointer">
                  ${isSelected ? '✓ กำลังกรองเฉพาะเหตุการณ์นี้' : 'กรองข่าวในหน้านี้'}
                </button>
                <button type="button"
                        onclick="window.__openStoryline('${esc(ceId)}', '${esc(ce.headline || ce.title || "")}')"
                        class="inline-flex items-center gap-0.5 font-semibold text-indigo-600 dark:text-indigo-400 hover:underline cursor-pointer"
                        title="เปิดแฟ้มเหตุการณ์จำเพาะนี้แยกต่างหาก">
                  <span>เปิดแฟ้มย่อย</span>
                  <span class="material-symbols-outlined text-[12px]">open_in_new</span>
                </button>
              </div>
            </div>
          `;
        }).join("")}
      </div>
    </div>
  ` : "";

  const storylineHashtags = Array.from(new Set([
    ...(Array.isArray(storyData.hashtags) ? storyData.hashtags : []),
    ...(Array.isArray(storyData.entities) ? storyData.entities : []),
    ...(chronologicalArticles.flatMap(a => Array.isArray(a.hashtags) ? a.hashtags : [])),
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

  // Sort displayed articles according to user preference: "latest" (newest first) or "oldest" (chronological)
  const displayArticles = [...filteredArticles].sort((a, b) => {
    const timeA = new Date(a.fetched_at || a.created_at || 0).getTime();
    const timeB = new Date(b.fetched_at || b.created_at || 0).getTime();
    if (activeSortOrder === "oldest") {
      return timeA - timeB;
    }
    return timeB - timeA;
  });

  const articlesGridHtml = displayArticles.length > 0 ? `
    <div class="storyline-grid-container">
      ${displayArticles.map((art, idx) => {
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
                  <div class="hidden sm:flex mb-2 px-2.5 py-1.5 rounded bg-blue-50/10 border border-blue-500/25 text-blue-900 dark:text-blue-200 text-xs items-start gap-1.5">
                    <span class="material-symbols-outlined text-[14px] text-blue-600 dark:text-blue-400 shrink-0 mt-0.5">info</span>
                    <div class="min-w-0 flex-1 leading-normal text-[11px]">
                      <span class="font-bold text-blue-700 dark:text-blue-300">บริบทการเมือง (อยู่นอกสารบบหลักฐาน):</span>
                      <span class="text-on-surface-variant ml-1">${esc(contextRelation || "ข้อมูลบริบทเบื้องหลัง")}</span>
                    </div>
                  </div>
                ` : (isOutlier ? `
                  <div class="hidden sm:flex mb-2 px-2.5 py-1.5 rounded bg-amber-50/10 border border-amber-500/25 text-amber-900 dark:text-amber-200 text-xs items-start gap-1.5">
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

  const totalCandidates = metrics?.candidate_count ?? chronologicalArticles.length;
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
        
        <!-- Header & Badges -->
        <div class="space-y-3 border-b border-slate-100 dark:border-zinc-800 pb-5">
          <div class="flex items-center justify-between flex-wrap gap-2">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="inline-flex items-center gap-1.5 font-mono text-[11px] font-bold uppercase px-2.5 py-1 rounded-md bg-amber-50 dark:bg-amber-500/10 text-amber-800 dark:text-amber-300 border border-amber-200/80 dark:border-amber-500/30">
                <span class="material-symbols-outlined text-[14px]">auto_awesome</span>
                AI Storyline Summary
              </span>
              ${verificationBadgeHtml}
              ${corroborationBadgeHtml}
              ${parentMacroLinkHtml}
              ${antecedentLinkHtml}
              <span class="text-xs text-slate-400 dark:text-zinc-500 font-medium">${formatEditorialDateOnly(storyData.updated_at)}</span>
            </div>

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

          ${typedAnchorsHtml}
        </div>

        <!-- Toggle List: AI Audit Panel -->
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

            <div class="p-4 pt-1 border-t border-slate-200 dark:border-zinc-700 space-y-4 animate-fade-in">
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                <!-- Context Articles -->
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
                          <div class="min-w-0 flex-1 text-[11px] leading-snug text-slate-800 dark:text-zinc-200 break-words"><span class="text-blue-700 dark:text-blue-400 font-bold mr-1">[${esc(pc.source || "ข่าว")}]</span><span>${esc(pc.title)}</span></div>
                          <button type="button" class="px-1.5 py-0.5 text-[10px] font-mono rounded bg-slate-100 hover:bg-slate-200 dark:bg-zinc-800 text-slate-600 dark:text-zinc-300 border border-slate-200 dark:border-zinc-700 cursor-pointer shrink-0" onclick="window.__inspectCitation('${esc(pc.article_id)}')">${esc(pc.article_id)}</button>
                        </div>`).join("")}
                    </div>
                  ` : `<p class="text-[10px] text-slate-400 dark:text-zinc-500 italic">ไม่พบข่าวบริบทแยกต่างหาก</p>`}
                </div>

                <!-- Irrelevant / Outlier Articles -->
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
                          <div class="min-w-0 flex-1 text-[11px] leading-snug text-slate-800 dark:text-zinc-200 break-words"><span class="text-amber-700 dark:text-amber-400 font-bold mr-1">[${esc(irr.source || "ข่าว")}]</span><span>${esc(irr.title)}</span></div>
                          <button type="button" class="px-1.5 py-0.5 text-[10px] font-mono rounded bg-slate-100 hover:bg-slate-200 dark:bg-zinc-800 text-slate-600 dark:text-zinc-300 border border-slate-200 dark:border-zinc-700 cursor-pointer shrink-0" onclick="window.__inspectCitation('${esc(irr.article_id)}')">${esc(irr.article_id)}</button>
                        </div>`).join("")}
                    </div>
                  ` : `<p class="text-[10px] text-slate-400 dark:text-zinc-500 italic">ไม่พบข่าวหลุดประเด็น</p>`}
                </div>
              </div>
            </div>
          </details>
        ` : `
          <div id="dossier-audit-panel" class="hidden"></div>
        `}

        <!-- AI Main Summary Section -->
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

        <!-- Stage A Sub-Events Progression -->
        ${childEventsSectionHtml}

        <!-- Tags -->
        ${storylineHashtagsHtml}

      </div>

      <div class="storyline-filter-bar">
        <div class="storyline-filter-title">
          <div class="flex items-center gap-2">
            <span class="font-mono text-xs uppercase tracking-wider">FILTER BY PUBLISHER PERSPECTIVE</span>
          </div>
          <div class="flex items-center gap-3">
            <span class="font-mono text-[11px] text-outline">SHOWING ${filteredArticles.length} OF ${chronologicalArticles.length}</span>
            <div class="inline-flex items-center rounded-lg bg-surface-container-low p-0.5 border border-outline-variant/30 text-xs" role="group" aria-label="เรียงลำดับข่าวในประเด็น">
              <button type="button" 
                      onclick="window.__toggleStorylineSort('latest')" 
                      class="px-2.5 py-0.5 rounded-md text-[11px] font-semibold transition-all cursor-pointer ${activeSortOrder === 'latest' ? 'bg-[#141413] text-white dark:bg-white dark:text-black shadow-2xs' : 'text-outline hover:text-on-surface'}"
                      title="เรียงตามเวลาล่าสุด (Latest First)">
                ล่าสุด
              </button>
              <button type="button" 
                      onclick="window.__toggleStorylineSort('oldest')" 
                      class="px-2.5 py-0.5 rounded-md text-[11px] font-semibold transition-all cursor-pointer ${activeSortOrder === 'oldest' ? 'bg-[#141413] text-white dark:bg-white dark:text-black shadow-2xs' : 'text-outline hover:text-on-surface'}"
                      title="เรียงตามลำดับเวลาตั้งแต่แรกสุด (Chronological Order)">
                แรกสุด
              </button>
            </div>
          </div>
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

// ── Global Window Handlers for Timeline & Navigation ──────────────

if (typeof window !== "undefined") {
  window.__toggleTimelinePanel = () => {};
  window.__togglePerspectiveQuote = () => {};
  window.__scrollToStoryTimeline = () => {
    const el = document.getElementById("storyline-ai-section");
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  window.__scrollToSubEvents = () => {
    const el = document.getElementById("storyline-subevents-section");
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  window.__scrollToSubEvent = (subId) => {
    if (typeof window.__filterStorylineSubEvent === "function") {
      window.__filterStorylineSubEvent(subId);
    }
  };
  window.__toggleSubEventArticles = () => {};
  window.__toggleStorylineSort = window.__toggleStorylineSort || (() => {});
}
