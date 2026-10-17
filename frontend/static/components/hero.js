/**
 * frontend/static/components/hero.js
 * ─────────────────────────────────────────────────────────────────
 * Hero Highlight Carousel, Trending Lead Stories & Multi-Image Montage
 *
 * Responsibilities:
 * - Editorial trending carousel slide rendering
 * - Dedicated Sports Multi-Image Montage (asymmetric 7-col/5-col layout)
 * - Autoplay timer lifecycle (pause on hover/view switch, resume on feed)
 * - Touch swipe gesture detection for mobile devices
 * - Slide navigation controls and progress segment indicators
 * ─────────────────────────────────────────────────────────────────
 */

import { esc, getCategoryPlaceholder } from "../utils/common.js";
import { checkIsSportsCluster, classifySportsArticle } from "./sports-intelligence.js";
import { SOURCE_COLORS, HERO_CLUSTER_LIMIT } from "../config.js";

// ── Hero / Trending Carousel State ───────────────────────────────
let heroTrendingArticles = [];
let heroBookmarkedMap = {};
let heroCurrentIndex = 0;
let heroAutoPlayTimer = null;
let heroTouchStartX = 0;
let heroTouchStartY = 0;

export function startHeroAutoPlay() {
  stopHeroAutoPlay();
  if (heroTrendingArticles.length > 1) {
    heroAutoPlayTimer = setInterval(() => {
      heroCurrentIndex = (heroCurrentIndex + 1) % heroTrendingArticles.length;
      updateHeroTrendingSlide();
    }, 5500);
  }
}

export function stopHeroAutoPlay() {
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

export function updateHeroTrendingSlide() {
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

  // 1. Editorial Index Strip
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
  ])).filter(Boolean).slice(0, 3);

  const storylineHashtagsHtml = storylineHashtags.length > 0 ? `
    <div class="hidden sm:flex items-center gap-1.5 flex-wrap">
      ${storylineHashtags.map(tag => {
        const clean = tag.startsWith("#") ? tag.slice(1) : tag;
        return `
          <button type="button"
                  class="text-[10px] sm:text-[11px] font-mono text-white/75 hover:text-white bg-white/5 hover:bg-white/10 border border-white/15 px-2 py-0.5 rounded transition-colors cursor-pointer"
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

  // Dedicated Sports Multi-Image Hero Montage on Main Page
  if (isSportsStory) {
    allSlideArticles.forEach(art => {
      if (!art._sportsMeta) art._sportsMeta = classifySportsArticle(art);
    });

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
      { id: "badminton", label: "แบดมินตัน", icon: "🏸", count: disciplineCounts.badminton },
      { id: "boxing", label: "มวย & ต่อสู้", icon: "🥊", count: disciplineCounts.boxing },
      { id: "volleyball", label: "วอลเลย์บอล", icon: "🏐", count: disciplineCounts.volleyball },
      { id: "tennis", label: "เทนนิส", icon: "🎾", count: disciplineCounts.tennis },
      { id: "golf", label: "กอล์ฟ", icon: "⛳", count: disciplineCounts.golf },
      { id: "motorsport", label: "มอเตอร์สปอร์ต", icon: "🏎️", count: disciplineCounts.motorsport },
      { id: "paragames", label: "พาราเกมส์", icon: "♿", count: disciplineCounts.paragames },
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
        
        <!-- Sports Multi-Image Split Montage -->
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
                  ${esc(n.title)} • รวบรวมไฮไลต์ ผลบอลไทย บอลยุโรป แบดมินตัน มวย วอลเลย์บอล จาก ${outletMap.size} สำนักข่าว (${allSlideArticles.length} ข่าว)
                </p>
              </div>

              <!-- Quick Sports Discipline Pills -->
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

            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 sm:gap-3 pt-1.5 sm:pt-2 border-t border-white/15 w-full">
              <div class="flex items-center justify-between sm:justify-start gap-2 text-white/70 font-mono text-[10px] sm:text-[11px] uppercase tracking-wider">
                <span class="flex items-center gap-1.5">
                  <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                  <span>STORY ${String(rankNum).padStart(2, "0")}/${String(total).padStart(2, "0")}</span>
                </span>
                ${n.fetched_at ? `<span class="opacity-60 text-[9px] sm:text-[11px]">${esc(n.fetched_at)}</span>` : ""}
              </div>
              <div class="flex items-center gap-1.5 sm:gap-2 w-full sm:w-auto flex-nowrap" onclick="event.stopPropagation()">
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
                        class="hero-read-abstract-btn flex-1 sm:flex-initial flex items-center justify-center gap-1 sm:gap-1.5 px-2 sm:px-3.5 py-1.5 sm:py-2 rounded-lg font-bold text-[11px] sm:text-xs transition-all cursor-pointer shadow-sm whitespace-nowrap min-w-0" 
                        onclick="window.__openPreview('${esc(n.url)}')">
                  <span class="material-symbols-outlined text-[14px] sm:text-[15px] shrink-0">article</span>
                  <span class="truncate">อ่านบทคัดย่อ</span>
                </button>
                <button type="button" 
                        class="hero-storyline-action-btn flex-1 sm:flex-initial flex items-center justify-center gap-1 sm:gap-2 px-2.5 sm:px-4 py-1.5 sm:py-2 rounded-lg font-extrabold text-[11px] sm:text-xs transition-all cursor-pointer shadow-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 whitespace-nowrap min-w-0" 
                        onclick="window.__openCurrentHeroStoryline()"
                        title="เจาะลึกและดูรายงานทุกสำนักข่าวในประเด็นนี้">
                  <span class="material-symbols-outlined text-[14px] sm:text-[16px] text-slate-950 font-bold shrink-0">sports_and_outdoors</span>
                  <span class="truncate"><span class="hidden sm:inline">ดูข่าวกีฬาทั้งหมดใน</span><span class="sm:hidden">ดูกีฬา</span>ประเด็นนี้</span>
                  <span class="bg-black/25 text-slate-950 px-1.5 py-0.5 rounded-full text-[9px] sm:text-[10px] font-mono font-extrabold tracking-wider shrink-0">${outletMap.size} สื่อ</span>
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
        <div class="space-y-1.5 sm:space-y-3 pointer-events-auto pb-1.5 sm:pb-3 max-w-4xl">
          <div class="space-y-1 sm:space-y-2">
            <h1 class="text-base sm:text-2xl md:text-3xl font-headline font-bold hero-headline leading-snug cursor-pointer hover:underline decoration-white/40 underline-offset-4 line-clamp-2"
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

          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 sm:gap-3 pt-1.5 sm:pt-2 border-t border-white/15 w-full">
            <div class="flex items-center justify-between sm:justify-start gap-2 text-white/70 font-mono text-[10px] sm:text-[11px] uppercase tracking-wider">
              <span class="flex items-center gap-1.5">
                <span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
                <span>STORY ${String(rankNum).padStart(2, "0")}/${String(total).padStart(2, "0")}</span>
              </span>
              ${n.fetched_at ? `<span class="opacity-60 text-[9px] sm:text-[11px]">${esc(n.fetched_at)}</span>` : ""}
            </div>
            <div class="flex items-center gap-1.5 sm:gap-2 w-full sm:w-auto flex-nowrap" onclick="event.stopPropagation()">
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
                      class="hero-read-abstract-btn flex-1 sm:flex-initial flex items-center justify-center gap-1 sm:gap-1.5 px-2 sm:px-3.5 py-1.5 sm:py-2 rounded-lg font-bold text-[11px] sm:text-xs transition-all cursor-pointer shadow-sm whitespace-nowrap min-w-0" 
                      onclick="window.__openPreview('${esc(n.url)}')">
                <span class="material-symbols-outlined text-[14px] sm:text-[15px] shrink-0">article</span>
                <span class="truncate">อ่านบทคัดย่อ</span>
              </button>
              <button type="button" 
                      class="hero-storyline-action-btn flex-1 sm:flex-initial flex items-center justify-center gap-1 sm:gap-2 px-2.5 sm:px-4 py-1.5 sm:py-2 rounded-lg font-extrabold text-[11px] sm:text-xs transition-all cursor-pointer shadow-lg whitespace-nowrap min-w-0" 
                      onclick="window.__openCurrentHeroStoryline()"
                      title="เจาะลึกและดูรายงานทุกสำนักข่าวในประเด็นนี้">
                <span class="material-symbols-outlined text-[14px] sm:text-[16px] text-slate-950 font-bold shrink-0">account_tree</span>
                <span class="truncate"><span class="hidden sm:inline">ดูข่าวทั้งหมดใน</span><span class="sm:hidden">ดู</span>ประเด็นนี้</span>
                <span class="bg-black/25 text-slate-950 px-1.5 py-0.5 rounded-full text-[9px] sm:text-[10px] font-mono font-extrabold tracking-wider shrink-0">${outletMap.size} สื่อ</span>
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

// ── Touch Swipe Handling ──────────────────────────────────────────

export function handleHeroSwipe(dx, dy) {
  if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) {
    if (dx < 0) {
      if (typeof window.__nextTrendingSlide === "function") window.__nextTrendingSlide();
    } else {
      if (typeof window.__prevTrendingSlide === "function") window.__prevTrendingSlide();
    }
  }
}

// ── Global Window Bindings for Inline HTML Attributes ─────────────

if (typeof window !== "undefined") {
  window.__heroTouchStart = (event) => {
    if (!event.touches || event.touches.length === 0) return;
    heroTouchStartX = event.touches[0].clientX;
    heroTouchStartY = event.touches[0].clientY;
    window.__pauseTrendingAutoPlay?.();
  };

  window.__heroTouchEnd = (event) => {
    if (!event.changedTouches || event.changedTouches.length === 0) return;
    const dx = event.changedTouches[0].clientX - heroTouchStartX;
    const dy = event.changedTouches[0].clientY - heroTouchStartY;
    handleHeroSwipe(dx, dy);
    window.__resumeTrendingAutoPlay?.();
  };

  window.__prevTrendingSlide = (event) => {
    if (event && typeof event.stopPropagation === "function") event.stopPropagation();
    if (!heroTrendingArticles.length) return;
    heroCurrentIndex = (heroCurrentIndex - 1 + heroTrendingArticles.length) % heroTrendingArticles.length;
    updateHeroTrendingSlide();
    startHeroAutoPlay();
  };

  window.__nextTrendingSlide = (event) => {
    if (event && typeof event.stopPropagation === "function") event.stopPropagation();
    if (!heroTrendingArticles.length) return;
    heroCurrentIndex = (heroCurrentIndex + 1) % heroTrendingArticles.length;
    updateHeroTrendingSlide();
    startHeroAutoPlay();
  };

  window.__goToTrendingSlide = (index) => {
    if (typeof index !== "number" || !Number.isInteger(index) || index < 0) return;
    if (index >= 0 && index < heroTrendingArticles.length) {
      heroCurrentIndex = index;
      updateHeroTrendingSlide();
      startHeroAutoPlay();
    }
  };

  window.__setHeroSlide = window.__goToTrendingSlide;

  window.__pauseTrendingAutoPlay = () => stopHeroAutoPlay();
  window.__resumeTrendingAutoPlay = () => startHeroAutoPlay();
}

if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      stopHeroAutoPlay();
    } else {
      const feedView = document.getElementById("feed-view");
      if (feedView && !feedView.classList.contains("hidden")) {
        startHeroAutoPlay();
      }
    }
  });
}
