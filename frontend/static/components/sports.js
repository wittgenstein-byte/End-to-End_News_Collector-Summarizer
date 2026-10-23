/**
 * frontend/static/components/sports.js
 * ─────────────────────────────────────────────────────────────────
 * Dedicated Sports Multi-Sport Storyline Hub & AI Sports Digest
 *
 * Responsibilities:
 * - 10 Sport discipline tabs (UCL, Thai Football, Badminton, Boxing, etc.)
 * - Content-type sub-filters (match results, schedules, general news)
 * - Sports Multi-Image montage collage (asymmetric 7-col/5-col layout)
 * - Sports Daily AI Digest cards with outcome score pills
 * - Publisher perspective filters for sports coverage
 * ─────────────────────────────────────────────────────────────────
 */

import {
  esc,
  getCategoryPlaceholder,
  formatEditorialDateTime,
  formatEditorialDateOnly,
  getPerspectiveLabel,
  setStorylineCache,
} from "../utils/common.js";
import { classifySportsArticle } from "./sports-intelligence.js";
import { SOURCE_COLORS } from "../config.js";

// ── Sports AI Digest Cards ────────────────────────────────────────

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
  const badmintonArticles = enrichedArticles.filter(a => a._sportsMeta?.discipline === "badminton");
  const boxingArticles = enrichedArticles.filter(a => a._sportsMeta?.discipline === "boxing");
  const volleyArticles = enrichedArticles.filter(a => a._sportsMeta?.discipline === "volleyball");
  const tennisArticles = enrichedArticles.filter(a => a._sportsMeta?.discipline === "tennis");
  const golfArticles = enrichedArticles.filter(a => a._sportsMeta?.discipline === "golf");
  const motorsportArticles = enrichedArticles.filter(a => a._sportsMeta?.discipline === "motorsport");
  const paragamesArticles = enrichedArticles.filter(a => a._sportsMeta?.discipline === "paragames");
  const otherArticles = enrichedArticles.filter(a => a._sportsMeta?.discipline === "other_sports");

  const sportsSections = [
    {
      id: "football_europe",
      title: "ฟุตบอลยุโรป & UCL",
      icon: "⚽",
      articles: euArticles,
      textColor: "text-indigo-700 dark:text-indigo-400",
      badgeBg: "bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300",
    },
    {
      id: "football_thai",
      title: "ฟุตบอลไทย & สโมสรเอเชีย",
      icon: "🇹🇭",
      articles: thArticles,
      textColor: "text-rose-700 dark:text-rose-400",
      badgeBg: "bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300",
    },
    {
      id: "badminton",
      title: "แบดมินตัน & ขนไก่โลก",
      icon: "🏸",
      articles: badmintonArticles,
      textColor: "text-teal-700 dark:text-teal-400",
      badgeBg: "bg-teal-50 dark:bg-teal-950/40 text-teal-700 dark:text-teal-300",
    },
    {
      id: "boxing",
      title: "มวย & ONE Championship",
      icon: "🥊",
      articles: boxingArticles,
      textColor: "text-red-700 dark:text-red-400",
      badgeBg: "bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-300",
    },
    {
      id: "volleyball",
      title: "วอลเลย์บอล & กีฬาในร่ม",
      icon: "🏐",
      articles: volleyArticles,
      textColor: "text-amber-700 dark:text-amber-400",
      badgeBg: "bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300",
    },
    {
      id: "tennis",
      title: "เทนนิส & แกรนด์สแลม",
      icon: "🎾",
      articles: tennisArticles,
      textColor: "text-lime-700 dark:text-lime-400",
      badgeBg: "bg-lime-50 dark:bg-lime-950/40 text-lime-700 dark:text-lime-300",
    },
    {
      id: "golf",
      title: "กอล์ฟ & LPGA / PGA",
      icon: "⛳",
      articles: golfArticles,
      textColor: "text-emerald-700 dark:text-emerald-400",
      badgeBg: "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300",
    },
    {
      id: "motorsport",
      title: "มอเตอร์สปอร์ต & โมโตจีพี",
      icon: "🏎️",
      articles: motorsportArticles,
      textColor: "text-cyan-700 dark:text-cyan-400",
      badgeBg: "bg-cyan-50 dark:bg-cyan-950/40 text-cyan-700 dark:text-cyan-300",
    },
    {
      id: "paragames",
      title: "พาราเกมส์ & กีฬาคนพิการ",
      icon: "♿",
      articles: paragamesArticles,
      textColor: "text-emerald-700 dark:text-emerald-400",
      badgeBg: "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300",
    },
    {
      id: "other_sports",
      title: "กีฬาอื่นๆ",
      icon: "🏃",
      articles: otherArticles,
      textColor: "text-slate-700 dark:text-slate-300",
      badgeBg: "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300",
    },
  ].filter(sec => sec.articles.length > 0);

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
      ${sportsSections.map(sec => `
        <div class="sports-digest-section-card bg-white dark:bg-zinc-900 border border-slate-200 dark:border-zinc-800 rounded-xl p-4 space-y-3 shadow-2xs">
          <div class="flex items-center justify-between border-b border-slate-100 dark:border-zinc-800 pb-2">
            <span class="font-bold text-xs ${sec.textColor} flex items-center gap-1.5">
              <span>${sec.icon}</span> ${esc(sec.title)}
            </span>
            <span class="text-[10px] font-mono font-bold ${sec.badgeBg} px-2 py-0.5 rounded-full">${sec.articles.length} ข่าว</span>
          </div>
          <div class="space-y-2 text-xs">
            ${sec.articles.slice(0, 4).map(a => `
              <div class="p-2 rounded-lg bg-slate-50 dark:bg-zinc-800/60 hover:bg-slate-100 dark:hover:bg-zinc-800 transition-colors cursor-pointer" onclick="window.__openPreview('${esc(a.url)}')">
                <div class="font-semibold text-slate-800 dark:text-zinc-200 line-clamp-2">${esc(a.title)}</div>
                <div class="flex items-center gap-2 mt-1.5 text-[10px] font-mono text-slate-500 dark:text-zinc-400">
                  <span class="font-bold">${esc(a.source || "ข่าว")}</span>
                  ${a._sportsMeta?.scoreHighlight ? `<span class="sports-score-highlight text-[9px]">${esc(a._sportsMeta.scoreHighlight)}</span>` : ""}
                  ${a._sportsMeta?.leagueBadge ? `<span class="text-[9px] text-slate-400 font-mono">${esc(a._sportsMeta.leagueBadge)}</span>` : ""}
                </div>
              </div>
            `).join("")}
          </div>
        </div>
      `).join("")}
    </div>
  `;
}

// ── Multi-Sport Storyline View ────────────────────────────────────

export function renderSportsStorylineView(
  storyData,
  activeSourceFilter = "",
  activeSportDisciplineFilter = "",
  activeSportContentTypeFilter = "",
  bookmarkedMap = {}
) {
  const container = document.getElementById("storyline-view");
  if (!container || !storyData) return;

  setStorylineCache(storyData);

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
    badminton: 0,
    boxing: 0,
    volleyball: 0,
    tennis: 0,
    golf: 0,
    motorsport: 0,
    paragames: 0,
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
    { id: "badminton", label: "แบดมินตัน", icon: "🏸", count: disciplineCounts.badminton },
    { id: "boxing", label: "มวย & ต่อสู้", icon: "🥊", count: disciplineCounts.boxing },
    { id: "volleyball", label: "วอลเลย์บอล & ในร่ม", icon: "🏐", count: disciplineCounts.volleyball },
    { id: "tennis", label: "เทนนิส", icon: "🎾", count: disciplineCounts.tennis },
    { id: "golf", label: "กอล์ฟ", icon: "⛳", count: disciplineCounts.golf },
    { id: "motorsport", label: "มอเตอร์สปอร์ต", icon: "🏎️", count: disciplineCounts.motorsport },
    { id: "paragames", label: "พาราเกมส์", icon: "♿", count: disciplineCounts.paragames },
    { id: "other_sports", label: "กีฬาอื่นๆ", icon: "🏃", count: disciplineCounts.other_sports },
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

  // Sports News Articles Grid HTML
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
              <span>${esc(sportsHeroTitle)}</span>
              <span class="text-xs sm:text-sm font-mono font-bold px-2.5 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 border border-emerald-300/60 dark:border-emerald-700/60">
                สดรอบวัน
              </span>
            </h1>
            <p class="text-xs sm:text-sm text-slate-600 dark:text-zinc-300 leading-relaxed max-w-3xl">
              สรุปผลการแข่งขัน ไฮไลต์ฟุตบอลไทย บอลยุโรป แบดมินตัน มวย วอลเลย์บอล และความเคลื่อนไหววงการกีฬา รวบรวมทั้งหมด ${sortedArticles.length} รายงาน จาก ${outlets.length} สำนักข่าว
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

        <!-- Multi-Image Montage Showcase -->
        ${sportsCollageHtml}

        <!-- AI Digest Board Section -->
        <div id="storyline-ai-section" class="space-y-4">
          <div class="pl-4 sm:pl-5 py-1 border-l-2 border-amber-600/80 dark:border-amber-400/80 text-slate-700 dark:text-zinc-200 text-sm sm:text-base leading-relaxed">
            ${esc(storyData.summary || "รวบรวมรายงานผลการแข่งขัน ฟุตบอลยุโรป ฟุตบอลไทย แบดมินตัน มวย วอลเลย์บอล และความเคลื่อนไหวในวงการกีฬาจากทุกสำนักข่าว")}
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
