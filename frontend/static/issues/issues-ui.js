/**
 * frontend/static/issues/issues-ui.js
 * ─────────────────────────────────────────────────────────────────
 * DOM Rendering and UI component generation for Issue Explorer.
 * Aesthetic: Editorial Intelligence / Swiss Grid Typography
 * Security: Uses textContent and programmatic DOM node creation for 
 * untrusted news headlines and summaries (zero raw innerHTML injection).
 * ─────────────────────────────────────────────────────────────────
 */

/**
 * Create a DOM element with highlighted keyword matches using safe text nodes and <mark> elements.
 * @param {string} tag - HTML tag name (e.g. 'div', 'p', 'span')
 * @param {string} text - Untrusted input text
 * @param {string[]} terms - Search terms to highlight
 * @param {string} [className] - Optional CSS classes
 * @returns {HTMLElement} Safe DOM element
 */
export function createHighlightedElement(tag, text, terms = [], className = "") {
  const el = document.createElement(tag);
  if (className) el.className = className;

  if (!text) return el;
  const validTerms = terms.filter(t => t && t.trim().length > 0);
  if (validTerms.length === 0) {
    el.textContent = text;
    return el;
  }

  // Escape terms for regex
  const escaped = validTerms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  const regex = new RegExp(`(${escaped})`, "gi");

  const parts = text.split(regex);
  for (const part of parts) {
    if (!part) continue;
    if (regex.test(part)) {
      const mark = document.createElement("mark");
      // Tasteful editorial highlight instead of harsh neon yellow
      mark.className = "bg-primary/12 text-primary font-semibold px-1 py-0.2 rounded-xs border-b border-primary/30";
      mark.textContent = part;
      el.appendChild(mark);
    } else {
      el.appendChild(document.createTextNode(part));
    }
  }

  return el;
}

/**
 * Render stats bar metrics with Swiss-grid hairline dividers.
 */
export function renderStats(container, stats, query) {
  container.innerHTML = "";
  if (!stats) return;

  const wrapper = document.createElement("div");
  wrapper.className = "grid grid-cols-2 sm:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-outline-variant/40 bg-surface-container-lowest rounded-xl border border-outline-variant/50 overflow-hidden shadow-2xs";

  const items = [
    { 
      code: "VOL", 
      label: "ปริมาณข่าวที่พบ", 
      value: `${stats.total_matches.toLocaleString()}`, 
      unit: "บทความ",
      sub: `วิเคราะห์เชิงลึก ${stats.analyzed} รายการ` 
    },
    { 
      code: "SRC", 
      label: "ความครอบคลุมสื่อ", 
      value: `${stats.sources_count}`, 
      unit: "สำนักข่าว",
      sub: `กระจายใน ${stats.categories_count} หมวดหมู่` 
    },
    { 
      code: "SPAN", 
      label: "ห้วงเวลาของเหตุการณ์", 
      value: stats.first_seen ? `${stats.first_seen}` : "—", 
      unit: stats.last_seen && stats.last_seen !== stats.first_seen ? `→ ${stats.last_seen}` : "",
      sub: "ช่วงเวลาที่ปรากฏในฐานข้อมูล" 
    },
    { 
      code: "LATENCY", 
      label: "เวลาประมวลผล", 
      value: `${stats.elapsed_ms}`, 
      unit: "ms",
      sub: "SQLite + In-Memory Clustering" 
    }
  ];

  for (const item of items) {
    const col = document.createElement("div");
    col.className = "p-4 flex flex-col justify-between bg-surface-container-lowest hover:bg-surface-container-low/40 transition-colors";

    const topRow = document.createElement("div");
    topRow.className = "flex items-center justify-between gap-2 mb-1";

    const lbl = document.createElement("span");
    lbl.className = "text-on-surface-variant text-[11px] font-medium";
    lbl.textContent = item.label;

    const code = document.createElement("span");
    code.className = "font-mono text-[9px] tracking-widest uppercase text-outline px-1.5 py-0.5 rounded bg-surface-container";
    code.textContent = item.code;

    topRow.appendChild(lbl);
    topRow.appendChild(code);

    const valRow = document.createElement("div");
    valRow.className = "flex items-baseline gap-1.5 my-0.5";

    const val = document.createElement("span");
    val.className = "text-lg sm:text-xl font-bold font-mono text-on-surface tracking-tight";
    val.textContent = item.value;
    valRow.appendChild(val);

    if (item.unit) {
      const unit = document.createElement("span");
      unit.className = "text-[11px] font-mono text-on-surface-variant font-medium";
      unit.textContent = item.unit;
      valRow.appendChild(unit);
    }

    const sub = document.createElement("span");
    sub.className = "text-[10px] text-outline mt-1 truncate font-mono";
    sub.textContent = item.sub;

    col.appendChild(topRow);
    col.appendChild(valRow);
    col.appendChild(sub);
    wrapper.appendChild(col);
  }

  container.appendChild(wrapper);
}

/**
 * Render expanded synonyms pill tags.
 */
export function renderSynonyms(container, expandedTerms, onToggleExpand, isExpandActive) {
  container.innerHTML = "";
  if (!expandedTerms || expandedTerms.length <= 1) return;

  const wrapper = document.createElement("div");
  wrapper.className = "flex flex-wrap items-center gap-1.5 pt-2.5 border-t border-outline-variant/20 text-xs";

  const label = document.createElement("span");
  label.className = "text-[10px] font-mono uppercase tracking-wider text-outline mr-1";
  label.textContent = "Synonyms:";
  wrapper.appendChild(label);

  for (const term of expandedTerms) {
    const chip = document.createElement("span");
    chip.className = "inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono bg-surface-container-low border border-outline-variant/50 text-on-surface-variant";
    chip.textContent = term;
    wrapper.appendChild(chip);
  }

  container.appendChild(wrapper);
}

/**
 * Render responsive SVG timeline chart with baseline and subtle gridlines.
 */
export function renderTimeline(container, timelinePoints) {
  container.innerHTML = "";
  if (!timelinePoints || timelinePoints.length === 0) return;

  const card = document.createElement("div");
  card.className = "bg-surface-container-lowest p-4 sm:p-5 rounded-xl border border-outline-variant/50 shadow-2xs";

  const header = document.createElement("div");
  header.className = "flex justify-between items-center mb-4 pb-2.5 border-b border-outline-variant/30";

  const titleWrap = document.createElement("div");
  titleWrap.className = "flex items-center gap-2";

  const indexNum = document.createElement("span");
  indexNum.className = "text-[11px] font-mono uppercase tracking-wider font-semibold text-outline";
  indexNum.textContent = "01 /";

  const title = document.createElement("h3");
  title.className = "text-sm font-bold text-on-surface tracking-tight";
  title.textContent = "ความถี่การเกิดข่าวตามลำดับเวลา (Timeline Distribution)";

  titleWrap.appendChild(indexNum);
  titleWrap.appendChild(title);

  const totalNews = timelinePoints.reduce((acc, p) => acc + p.count, 0);
  const badge = document.createElement("span");
  badge.className = "text-[11px] text-on-surface-variant font-mono bg-surface-container px-2 py-0.5 rounded border border-outline-variant/30";
  badge.textContent = `Σ = ${totalNews}`;

  header.appendChild(titleWrap);
  header.appendChild(badge);
  card.appendChild(header);

  // SVG Chart dimensions
  const maxCount = Math.max(...timelinePoints.map(p => p.count), 1);
  const chartHeight = 96;
  const barWidth = Math.max(14, Math.min(36, Math.floor(640 / timelinePoints.length)));
  const gap = 8;
  const chartWidth = Math.max(300, timelinePoints.length * (barWidth + gap));

  const scrollWrapper = document.createElement("div");
  scrollWrapper.className = "overflow-x-auto pb-1 pt-2";

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${chartWidth} ${chartHeight + 28}`);
  svg.setAttribute("class", "min-w-full h-32");
  svg.style.overflow = "visible";

  // Subtle horizontal reference lines
  [0.25, 0.5, 0.75, 1].forEach(ratio => {
    const lineY = Math.round(chartHeight * (1 - ratio));
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", "0");
    line.setAttribute("y1", String(lineY));
    line.setAttribute("x2", String(chartWidth));
    line.setAttribute("y2", String(lineY));
    line.setAttribute("stroke", "currentColor");
    line.setAttribute("stroke-dasharray", "2,3");
    line.setAttribute("class", "text-outline-variant/40");
    svg.appendChild(line);
  });

  // Baseline
  const baseLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
  baseLine.setAttribute("x1", "0");
  baseLine.setAttribute("y1", String(chartHeight));
  baseLine.setAttribute("x2", String(chartWidth));
  baseLine.setAttribute("y2", String(chartHeight));
  baseLine.setAttribute("stroke", "currentColor");
  baseLine.setAttribute("class", "text-outline-variant/80");
  svg.appendChild(baseLine);

  timelinePoints.forEach((p, idx) => {
    const x = idx * (barWidth + gap);
    const barHeight = Math.max(4, Math.round((p.count / maxCount) * (chartHeight - 14)));
    const y = chartHeight - barHeight;

    const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
    group.setAttribute("class", "group cursor-pointer");

    // Bar rect
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", String(x));
    rect.setAttribute("y", String(y));
    rect.setAttribute("width", String(barWidth));
    rect.setAttribute("height", String(barHeight));
    rect.setAttribute("rx", "2");
    // Highlight peak bars subtly
    const isPeak = p.count === maxCount && maxCount > 1;
    rect.setAttribute("class", isPeak 
      ? "fill-primary transition-all duration-150 group-hover:opacity-85" 
      : "fill-on-surface/75 group-hover:fill-primary transition-all duration-150");

    // Title tooltip on hover
    const tooltip = document.createElementNS("http://www.w3.org/2000/svg", "title");
    tooltip.textContent = `${p.date} — ${p.count} บทความ`;
    rect.appendChild(tooltip);
    group.appendChild(rect);

    // Value label above bar
    if (barWidth >= 16) {
      const countText = document.createElementNS("http://www.w3.org/2000/svg", "text");
      countText.setAttribute("x", String(x + barWidth / 2));
      countText.setAttribute("y", String(y - 5));
      countText.setAttribute("text-anchor", "middle");
      countText.setAttribute("class", "text-[9px] fill-on-surface-variant group-hover:fill-primary group-hover:font-bold font-mono transition-colors");
      countText.textContent = String(p.count);
      group.appendChild(countText);
    }

    // Date label
    const dateText = document.createElementNS("http://www.w3.org/2000/svg", "text");
    dateText.setAttribute("x", String(x + barWidth / 2));
    dateText.setAttribute("y", String(chartHeight + 15));
    dateText.setAttribute("text-anchor", "middle");
    dateText.setAttribute("class", "text-[9px] fill-outline group-hover:fill-on-surface font-mono transition-colors");
    dateText.textContent = p.date.length >= 5 ? p.date.slice(5) : p.date;
    group.appendChild(dateText);

    svg.appendChild(group);
  });

  scrollWrapper.appendChild(svg);
  card.appendChild(scrollWrapper);
  container.appendChild(card);
}

/**
 * Render clustered sub-topics with density distribution bar.
 */
export function renderClusters(container, clusters, onFilterCluster, currentSort = "size", onSortChange = null) {
  container.innerHTML = "";
  if (!clusters || clusters.length === 0) return;

  const totalArticlesInClusters = clusters.reduce((acc, c) => acc + (c.size || 0), 0) || 1;

  const wrapper = document.createElement("div");
  wrapper.className = "space-y-3";

  const titleRow = document.createElement("div");
  titleRow.className = "flex justify-between items-center border-b border-outline-variant/40 pb-2.5";

  const titleLeft = document.createElement("div");
  titleLeft.className = "flex items-center gap-2";

  const indexSpan = document.createElement("span");
  indexSpan.className = "text-[11px] font-mono uppercase tracking-wider font-semibold text-outline";
  indexSpan.textContent = "03 /";

  const title = document.createElement("h3");
  title.className = "text-sm font-bold text-on-surface tracking-tight";
  title.textContent = "คลัสเตอร์ประเด็นย่อย";

  titleLeft.appendChild(indexSpan);
  titleLeft.appendChild(title);

  const rightControls = document.createElement("div");
  rightControls.className = "flex items-center gap-2";

  // Sort toggle buttons (Size vs Timeline)
  if (typeof onSortChange === "function") {
    const sortToggle = document.createElement("div");
    sortToggle.className = "inline-flex items-center bg-surface-container rounded p-0.5 border border-outline-variant/30 text-[10px] font-mono";

    const sizeBtn = document.createElement("button");
    sizeBtn.type = "button";
    sizeBtn.className = `px-1.5 py-0.5 rounded cursor-pointer transition-colors ${currentSort === "size" ? "bg-surface-container-lowest text-on-surface font-bold shadow-2xs" : "text-outline hover:text-on-surface"}`;
    sizeBtn.textContent = "ขนาด";
    sizeBtn.title = "เรียงตามจำนวนข่าว";
    sizeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      onSortChange("size");
    });

    const timeBtn = document.createElement("button");
    timeBtn.type = "button";
    timeBtn.className = `px-1.5 py-0.5 rounded cursor-pointer transition-colors ${currentSort === "time" ? "bg-surface-container-lowest text-on-surface font-bold shadow-2xs" : "text-outline hover:text-on-surface"}`;
    timeBtn.textContent = "เวลา";
    timeBtn.title = "เรียงตามไทม์ไลน์เหตุการณ์";
    timeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      onSortChange("time");
    });

    sortToggle.appendChild(sizeBtn);
    sortToggle.appendChild(timeBtn);
    rightControls.appendChild(sortToggle);
  }

  const countBadge = document.createElement("span");
  countBadge.className = "text-[11px] font-mono text-outline";
  countBadge.textContent = `${clusters.length} กลุ่ม`;
  rightControls.appendChild(countBadge);

  titleRow.appendChild(titleLeft);
  titleRow.appendChild(rightControls);
  wrapper.appendChild(titleRow);

  const listWrap = document.createElement("div");
  listWrap.className = "space-y-2.5";

  clusters.forEach((cl, idx) => {
    const sharePct = Math.min(100, Math.max(4, Math.round(((cl.size || 0) / totalArticlesInClusters) * 100)));

    const card = document.createElement("div");
    card.className = "group bg-surface-container-lowest p-3.5 rounded-xl border border-outline-variant/50 hover:border-on-surface/50 transition-all cursor-pointer shadow-2xs";
    card.setAttribute("data-cluster-id", cl.id);

    const topRow = document.createElement("div");
    topRow.className = "flex items-start justify-between gap-2.5";

    const labelWrap = document.createElement("div");
    labelWrap.className = "flex-1 min-w-0";

    const clusterBadge = document.createElement("span");
    clusterBadge.className = "inline-block font-mono text-[10px] font-semibold text-outline group-hover:text-primary transition-colors mr-1.5";
    clusterBadge.textContent = `#${String(idx + 1).padStart(2, "0")}`;

    const clusterLabel = document.createElement("span");
    clusterLabel.className = "text-xs sm:text-sm font-bold text-on-surface group-hover:text-primary transition-colors leading-snug";
    clusterLabel.textContent = cl.label;

    labelWrap.appendChild(clusterBadge);
    labelWrap.appendChild(clusterLabel);

    const sizeBadge = document.createElement("span");
    sizeBadge.className = "text-[11px] font-mono font-semibold text-on-surface bg-surface-container px-2 py-0.5 rounded border border-outline-variant/40 shrink-0";
    sizeBadge.textContent = `${cl.size} ข่าว`;

    topRow.appendChild(labelWrap);
    topRow.appendChild(sizeBadge);
    card.appendChild(topRow);

    // Subtle proportional progress bar
    const barTrack = document.createElement("div");
    barTrack.className = "w-full h-1 bg-surface-container rounded-full overflow-hidden mt-2.5";
    const barFill = document.createElement("div");
    barFill.className = "h-full bg-on-surface/60 group-hover:bg-primary transition-all rounded-full";
    barFill.style.width = `${sharePct}%`;
    barTrack.appendChild(barFill);
    card.appendChild(barTrack);

    // Keyword pills and metadata
    const metaRow = document.createElement("div");
    metaRow.className = "flex flex-wrap items-center gap-1 mt-2.5 pt-2 border-t border-outline-variant/20 text-xs";

    if (cl.top_terms && cl.top_terms.length > 0) {
      for (const kw of cl.top_terms) {
        const pill = document.createElement("span");
        pill.className = "text-[10px] font-mono bg-surface-container-low border border-outline-variant/40 px-1.5 py-0.5 rounded text-on-surface-variant";
        pill.textContent = kw;
        metaRow.appendChild(pill);
      }
    }

    if (cl.first_seen) {
      const dateSpan = document.createElement("span");
      dateSpan.className = "text-[10px] text-outline ml-auto font-mono pl-1";
      dateSpan.textContent = cl.first_seen === cl.last_seen ? cl.first_seen : `${cl.first_seen} → ${cl.last_seen || ''}`;
      metaRow.appendChild(dateSpan);
    }

    card.appendChild(metaRow);

    card.addEventListener("click", () => {
      if (typeof onFilterCluster === "function") {
        onFilterCluster(cl.id);
      }
    });

    listWrap.appendChild(card);
  });

  wrapper.appendChild(listWrap);
  container.appendChild(wrapper);
}

/**
 * Render related keywords chips (allows clicking to drill deeper).
 */
export function renderRelatedTerms(container, terms, onSelectTerm) {
  container.innerHTML = "";
  if (!terms || terms.length === 0) return;

  const card = document.createElement("div");
  card.className = "bg-surface-container-lowest p-4 rounded-xl border border-outline-variant/50 shadow-2xs space-y-3";

  const header = document.createElement("div");
  header.className = "flex items-center justify-between border-b border-outline-variant/30 pb-2";

  const title = document.createElement("h3");
  title.className = "text-xs font-mono uppercase tracking-wider font-semibold text-on-surface flex items-center gap-1.5";
  title.textContent = "04 / คำสำคัญที่พบร่วม (Co-occurring Terms)";
  header.appendChild(title);
  card.appendChild(header);

  const chipsWrap = document.createElement("div");
  chipsWrap.className = "flex flex-wrap gap-1.5";

  for (const item of terms) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "group inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-md bg-surface-container-low hover:bg-on-surface hover:text-surface transition-all border border-outline-variant/50 font-medium text-on-surface cursor-pointer";

    const termText = document.createElement("span");
    termText.textContent = item.term;

    const count = document.createElement("span");
    count.className = "text-[10px] text-outline group-hover:text-surface/70 font-mono";
    count.textContent = item.df;

    chip.appendChild(termText);
    chip.appendChild(count);

    chip.addEventListener("click", () => {
      if (typeof onSelectTerm === "function") {
        onSelectTerm(item.term);
      }
    });

    chipsWrap.appendChild(chip);
  }

  card.appendChild(chipsWrap);
  container.appendChild(card);
}

/**
 * Render list of articles safely with editorial feed styling and snippet highlights.
 */
export function renderArticles(container, articles, queryTerms) {
  container.innerHTML = "";
  if (!articles || articles.length === 0) {
    const emptyBox = document.createElement("div");
    emptyBox.className = "text-center py-12 bg-surface-container-lowest rounded-xl border border-outline-variant/40 text-outline text-xs font-mono";
    emptyBox.textContent = "— ไม่พบบทความข่าวที่ตรงกับเงื่อนไขการกรอง —";
    container.appendChild(emptyBox);
    return;
  }

  const wrapper = document.createElement("div");
  wrapper.className = "divide-y divide-outline-variant/40 bg-surface-container-lowest rounded-xl border border-outline-variant/50 overflow-hidden shadow-2xs";

  articles.forEach(art => {
    const item = document.createElement("article");
    item.className = "p-4 sm:p-5 hover:bg-surface-container-low/40 transition-colors group";

    // Meta bar
    const meta = document.createElement("div");
    meta.className = "flex flex-wrap items-center gap-2 text-[11px] mb-2";

    const src = document.createElement("span");
    src.className = "font-bold text-on-surface uppercase tracking-wide";
    src.textContent = art.source || "NEWS";
    meta.appendChild(src);

    const dot = document.createElement("span");
    dot.className = "text-outline-variant";
    dot.textContent = "•";
    meta.appendChild(dot);

    const time = document.createElement("span");
    time.className = "text-outline font-mono";
    time.textContent = art.fetched_at || "";
    meta.appendChild(time);

    if (art.category) {
      const cat = document.createElement("span");
      cat.className = "bg-surface-container border border-outline-variant/40 px-1.5 py-0.2 rounded text-[10px] text-on-surface-variant font-medium";
      cat.textContent = art.category;
      meta.appendChild(cat);
    }

    const targetStoryId = art.story_id || art.macro_event_id || art.cluster_id;
    if (targetStoryId) {
      const clLink = document.createElement("a");
      clLink.href = `/#/storyline/${encodeURIComponent(targetStoryId)}`;
      clLink.className = "ml-auto inline-flex items-center gap-1 bg-surface-container-high hover:bg-primary hover:text-white text-on-surface px-2 py-0.5 rounded text-[10px] font-mono font-semibold transition-colors";
      clLink.title = "คลิกเพื่อเปิดแฟ้มเหตุการณ์ต่อเนื่อง (Story Dossier)";
      clLink.textContent = `แฟ้มข่าว: ${String(targetStoryId).slice(0, 12).toUpperCase()}`;
      meta.appendChild(clLink);
    }

    item.appendChild(meta);

    // Title link
    const link = document.createElement("a");
    link.href = art.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.className = "text-base font-bold text-on-surface group-hover:text-primary transition-colors block leading-snug";
    
    // Highlight matched query terms inside title safely
    const titleEl = createHighlightedElement("h4", art.title, queryTerms);
    link.appendChild(titleEl);
    item.appendChild(link);

    // Summary snippet
    if (art.summary) {
      const summaryEl = createHighlightedElement(
        "p", 
        art.summary, 
        queryTerms, 
        "text-xs sm:text-[13px] text-on-surface-variant mt-2 line-clamp-2 leading-relaxed"
      );
      item.appendChild(summaryEl);
    }

    wrapper.appendChild(item);
  });

  container.appendChild(wrapper);
}

/**
 * Render possibly unrelated outlier drawer.
 */
export function renderPossiblyUnrelated(container, outliers) {
  container.innerHTML = "";
  if (!outliers || outliers.length === 0) return;

  const details = document.createElement("details");
  details.className = "group bg-surface-container-lowest rounded-xl border border-outline-variant/50 p-3.5 text-xs";

  const summary = document.createElement("summary");
  summary.className = "font-medium text-on-surface-variant cursor-pointer flex items-center justify-between select-none";

  const leftText = document.createElement("span");
  leftText.className = "font-mono text-[11px] flex items-center gap-2";
  leftText.textContent = `[OUTLIERS] ข่าวที่ถูกคัดแยกเนื่องจากบริบทห่างไกลหรือคำพ้องรูป (${outliers.length} รายการ)`;

  const rightHint = document.createElement("span");
  rightHint.className = "text-[11px] font-mono text-outline group-hover:text-on-surface transition-colors";
  rightHint.textContent = "แสดงรายการ ↓";

  summary.appendChild(leftText);
  summary.appendChild(rightHint);
  details.appendChild(summary);

  const list = document.createElement("div");
  list.className = "mt-3 divide-y divide-outline-variant/30 border-t border-outline-variant/30 pt-1";

  for (const out of outliers) {
    const row = document.createElement("div");
    row.className = "py-2.5 flex flex-col sm:flex-row sm:items-center justify-between gap-1";

    const link = document.createElement("a");
    link.href = out.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.className = "font-medium text-on-surface hover:text-primary transition-colors truncate flex-1";
    link.textContent = out.title;
    row.appendChild(link);

    const note = document.createElement("div");
    note.className = "text-[10px] font-mono text-outline shrink-0";
    note.textContent = `${out.source} • ${out.reason}`;
    row.appendChild(note);

    list.appendChild(row);
  }

  details.appendChild(list);
  container.appendChild(details);
}

/**
 * Export data to client download (zero backend load).
 */
export function exportData(data, format = "json") {
  if (!data) return;

  let blob;
  let filename = `newsroom-issue-${Date.now()}`;

  if (format === "json") {
    blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    filename += ".json";
  } else if (format === "csv") {
    const articles = data.articles || [];
    const headers = ["id", "source", "fetched_at", "category", "cluster_id", "title", "url"];
    const rows = articles.map(a => [
      a.id,
      `"${(a.source || "").replace(/"/g, '""')}"`,
      `"${a.fetched_at || ""}"`,
      `"${(a.category || "").replace(/"/g, '""')}"`,
      `"${(a.cluster_id || "").replace(/"/g, '""')}"`,
      `"${(a.title || "").replace(/"/g, '""')}"`,
      `"${(a.url || "").replace(/"/g, '""')}"`
    ]);
    const csvContent = "\uFEFF" + [headers.join(","), ...rows.map(r => r.join(","))].join("\n");
    blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    filename += ".csv";
  }

  if (blob) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }
}