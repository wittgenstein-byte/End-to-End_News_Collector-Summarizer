/**
 * backend/tests/test_adversarial_m3_boundaries.mjs
 * ─────────────────────────────────────────────────────────────────
 * Milestone 3 Adversarial Component Boundary Stress Suite
 * 
 * Tests and verifies 5 critical frontend components:
 * 1. common.js: esc() XSS vectors, entity handling, type coercion
 * 2. common.js: Buddhist calendar & date formatting boundaries
 * 3. sports-intelligence.js: 10-discipline heuristics, keyword masking, type crashes
 * 4. cards.js: renderGrid empty/sparse arrays, undefined fields, malformed sentiment/summary, pagination
 * 5. status.js: telemetry, ticker duplication & XSS, stats destructuring, toast safety
 * ─────────────────────────────────────────────────────────────────
 */

import { resolve, dirname } from "path";
import { fileURLToPath, pathToFileURL } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const projectRoot = resolve(__dirname, "../..");

// ── Setup DOM & Browser Mocks for Node.js Evaluation ───────────────
const domElements = new Map();

function createMockElement(id) {
  return {
    id,
    classList: {
      _classes: new Set(),
      add(...cls) { cls.forEach(c => this._classes.add(c)); },
      remove(...cls) { cls.forEach(c => this._classes.delete(c)); },
      contains(c) { return this._classes.has(c); },
      toggle(c, force) {
        if (force === undefined) {
          if (this._classes.has(c)) { this._classes.delete(c); return false; }
          else { this._classes.add(c); return true; }
        }
        if (force) { this._classes.add(c); return true; }
        this._classes.delete(c); return false;
      }
    },
    className: "",
    textContent: "",
    innerHTML: "",
    style: {},
    appendChild() {},
    removeChild() {},
    setAttribute(k, v) { this[k] = v; },
    getAttribute(k) { return this[k] ?? null; },
    scrollIntoView() {},
    getBoundingClientRect: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
    addEventListener() {},
    removeEventListener() {},
  };
}

function getOrSetElement(id) {
  if (!domElements.has(id)) {
    domElements.set(id, createMockElement(id));
  }
  return domElements.get(id);
}

globalThis.window = globalThis;
globalThis.document = {
  getElementById: (id) => getOrSetElement(id),
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: (tag) => createMockElement(tag),
  documentElement: { scrollTop: 0, scrollHeight: 1000 },
  body: { appendChild() {}, removeChild() {} },
};

globalThis.localStorage = {
  _store: {},
  getItem(k) { return this._store[k] ?? null; },
  setItem(k, v) { this._store[k] = String(v); },
  removeItem(k) { delete this._store[k]; },
  clear() { this._store = {}; },
};

try {
  Object.defineProperty(globalThis, "navigator", {
    value: {
      clipboard: { writeText: async () => {} },
      userAgent: "NodeJS Stress Harness",
    },
    configurable: true,
  });
} catch (_e) {}

// Pre-populate standard DOM container elements needed by components
[
  "news-grid", "pagination", "storyline-filter-breadcrumb",
  "ws-dot", "ws-label", "stat-total", "stat-new", "updated-bar",
  "ticker-track", "toast", "toast-msg", "new-articles-indicator",
  "new-articles-count-text", "offline-bar", "pwa-install-banner",
  "pwa-install-btn", "feedback-prompt-modal"
].forEach(id => getOrSetElement(id));

// ── Test Statistics & Diagnostic Logging ───────────────────────────
let totalTestsRun = 0;
let totalPassedChecks = 0;
const confirmedBugs = [];

function check(testName, passed, category, details = "") {
  totalTestsRun++;
  if (passed) {
    totalPassedChecks++;
    console.log(`  [PASS] ${testName}`);
  } else {
    console.log(`  [DEFECT CONFIRMED] [${category}] ${testName}`);
    if (details) console.log(`         └─ Detail: ${details}`);
    confirmedBugs.push({ testName, category, details });
  }
}

async function runAdversarialStressSuite() {
  console.log("==================================================================");
  console.log("  Milestone 3 Component Boundary Empirical Stress Suite");
  console.log("==================================================================\n");

  const commonUrl = pathToFileURL(resolve(projectRoot, "frontend/static/utils/common.js")).href;
  const sportsUrl = pathToFileURL(resolve(projectRoot, "frontend/static/components/sports-intelligence.js")).href;
  const cardsUrl = pathToFileURL(resolve(projectRoot, "frontend/static/components/cards.js")).href;
  const statusUrl = pathToFileURL(resolve(projectRoot, "frontend/static/components/status.js")).href;

  const Common = await import(commonUrl);
  const Sports = await import(sportsUrl);
  const Cards = await import(cardsUrl);
  const Status = await import(statusUrl);

  // ═════════════════════════════════════════════════════════════════
  // SECTION 1: common.js — esc() XSS Vectors & Type Boundaries
  // ═════════════════════════════════════════════════════════════════
  console.log("--- Section 1: common.js: esc() XSS Vectors & Type Boundaries ---");

  // 1.1 Script injection
  check(
    "esc() sanitizes <script> tags",
    Common.esc("<script>alert('XSS')</script>") === "&lt;script&gt;alert(&#39;XSS&#39;)&lt;/script&gt;",
    "Security"
  );

  check(
    "esc() sanitizes mixed-case <ScRiPt src='evil.js'></ScRiPt>",
    !Common.esc("<ScRiPt src='evil.js'></ScRiPt>").includes("<"),
    "Security"
  );

  // 1.2 Event handlers
  check(
    'esc() sanitizes <img src="x" onerror="alert(1)">',
    Common.esc('<img src="x" onerror="alert(1)">') === "&lt;img src=&quot;x&quot; onerror=&quot;alert(1)&quot;&gt;",
    "Security"
  );

  check(
    "esc() sanitizes <svg onload=alert(1)>",
    Common.esc("<svg onload=alert(1)>") === "&lt;svg onload=alert(1)&gt;",
    "Security"
  );

  // 1.3 Attribute breakout
  check(
    'esc() escapes double-quote attribute breakout ` " onmouseover="alert(1) `',
    Common.esc('" onmouseover="alert(1)"') === "&quot; onmouseover=&quot;alert(1)&quot;",
    "Security"
  );

  check(
    "esc() escapes single-quote attribute breakout ` ' onclick='alert(1) `",
    Common.esc("' onclick='alert(1)'") === "&#39; onclick=&#39;alert(1)&#39;",
    "Security"
  );

  // 1.4 HTML entity ampersand escaping
  check(
    "esc() escapes ampersand in existing entities to prevent entity-decode bypass",
    Common.esc("&amp; &lt; &gt; &quot; &#39;") === "&amp;amp; &amp;lt; &amp;gt; &amp;quot; &amp;#39;",
    "Security"
  );

  // 1.5 Nested / Malformed tags
  check(
    "esc() sanitizes malformed nested tags `<<SCRIPT>alert(1);//<</SCRIPT>`",
    !Common.esc("<<SCRIPT>alert(1);//<</SCRIPT>").includes("<"),
    "Security"
  );

  // 1.6 Primitive types
  check("esc(null) returns ''", Common.esc(null) === "", "Robustness");
  check("esc(undefined) returns ''", Common.esc(undefined) === "", "Robustness");
  check("esc('') returns ''", Common.esc("") === "", "Robustness");
  check("esc(0) returns '0'", Common.esc(0) === "0", "Robustness");
  check("esc(false) returns 'false'", Common.esc(false) === "false", "Robustness");
  check("esc(NaN) returns 'NaN'", Common.esc(NaN) === "NaN", "Robustness");
  check("esc(Infinity) returns 'Infinity'", Common.esc(Infinity) === "Infinity", "Robustness");
  check("esc({}) returns '[object Object]'", Common.esc({}) === "[object Object]", "Robustness");
  check("esc([]) returns ''", Common.esc([]) === "", "Robustness");

  // 1.7 Object.create(null) edge case
  let objNullThrows = false;
  try { Common.esc(Object.create(null)); } catch (_e) { objNullThrows = true; }
  check(
    "esc(Object.create(null)) throws TypeError due to missing prototype toString (JS engine limitation)",
    objNullThrows,
    "Robustness"
  );

  // ═════════════════════════════════════════════════════════════════
  // SECTION 2: common.js — Buddhist Calendar & Date Boundaries
  // ═════════════════════════════════════════════════════════════════
  console.log("\n--- Section 2: common.js: Buddhist Calendar & Date Formatting ---");

  // 2.1 Standard conversion to BE (+543)
  const beDate = Common.formatEditorialDateOnly("2026-10-17");
  check(
    "formatEditorialDateOnly converts CE 2026 to Buddhist Era 2569",
    beDate.includes("2569") && beDate.includes("17 ต.ค."),
    "Formatting",
    `Output: ${beDate}`
  );

  // 2.2 Already Buddhist Year (>= 2400)
  const alreadyBE = Common.formatEditorialDateOnly("2569-10-17");
  check(
    "formatEditorialDateOnly does NOT double-add 543 when input is already >= 2400",
    alreadyBE.includes("2569") && !alreadyBE.includes("3112"),
    "Formatting",
    `Output: ${alreadyBE}`
  );

  // 2.3 Invalid / Falsy Timestamps
  check("formatEditorialDateTime(null) returns ''", Common.formatEditorialDateTime(null) === "", "Robustness");
  check("formatEditorialDateTime(undefined) returns ''", Common.formatEditorialDateTime(undefined) === "", "Robustness");
  check("formatEditorialDateTime('') returns ''", Common.formatEditorialDateTime("") === "", "Robustness");
  check("formatEditorialDateOnly(null) returns fallback 'อัปเดตล่าสุด • วันนี้'", Common.formatEditorialDateOnly(null) === "อัปเดตล่าสุด • วันนี้", "Robustness");
  check("formatEditorialDateOnly('') returns fallback 'อัปเดตล่าสุด • วันนี้'", Common.formatEditorialDateOnly("") === "อัปเดตล่าสุด • วันนี้", "Robustness");

  // 2.4 Corrupted string fallback
  const corruptedFallback = Common.formatEditorialDateOnly("invalid-date-string");
  check(
    "formatEditorialDateOnly('invalid-date-string') returns fallback prefixed string",
    corruptedFallback === "อัปเดตล่าสุด • invalid-date-string",
    "Robustness"
  );

  // 2.5 DEFECT PROBE: XSS payload passthrough in formatEditorialDateOnly
  const xssDateInput = "<img src=x onerror=alert(1)>";
  const xssDateResult = Common.formatEditorialDateOnly(xssDateInput);
  const dateOnlyHasXssDefect = xssDateResult.includes("<img src=x onerror=alert(1)>");
  check(
    "formatEditorialDateOnly() sanitizes raw HTML/XSS in fallback date string",
    !dateOnlyHasXssDefect,
    "Security",
    `Vulnerability: Unescaped passthrough '${xssDateResult}' can trigger XSS if directly interpolated into innerHTML without esc()`
  );

  // 2.6 DEFECT PROBE: Future date semantic inversion in formatRelativeTime
  const futureDate = "2099-12-31T00:00:00Z";
  const futureRelative = Common.formatRelativeTime(futureDate);
  const relativeHasFutureDefect = futureRelative === "เมื่อสักครู่";
  check(
    "formatRelativeTime() handles future timestamps gracefully instead of claiming 'เมื่อสักครู่' (just now)",
    !relativeHasFutureDefect,
    "Logic",
    `Defect: Future timestamp '${futureDate}' evaluated diffMs < 0 (< 60s) returning 'เมื่อสักครู่'`
  );

  // 2.7 Historical / Negative Dates
  const historicalDate = Common.formatEditorialDateOnly("1970-01-01");
  check(
    "formatEditorialDateOnly converts 1970 to Buddhist Era 2513",
    historicalDate.includes("2513"),
    "Formatting"
  );

  // 2.8 Time only extractors
  check("formatShortTime('2026-10-17 14:35:00') returns '14:35'", Common.formatShortTime("2026-10-17 14:35:00") === "14:35", "Formatting");
  check("formatShortTime(null) returns ''", Common.formatShortTime(null) === "", "Robustness");
  check("formatTimeOnly('2026-10-17 14:35:00') returns '14:35 น.'", Common.formatTimeOnly("2026-10-17 14:35:00") === "14:35 น.", "Formatting");
  check("formatTimeOnly(null) returns ''", Common.formatTimeOnly(null) === "", "Robustness");

  // ═════════════════════════════════════════════════════════════════
  // SECTION 3: sports-intelligence.js — Disciplines & Heuristics
  // ═════════════════════════════════════════════════════════════════
  console.log("\n--- Section 3: sports-intelligence.js: Disciplines & Heuristics ---");

  // 3.1 Null, Undefined, Empty Objects
  check("classifySportsArticle(null) returns other_sports", Sports.classifySportsArticle(null).discipline === "other_sports", "Robustness");
  check("classifySportsArticle(undefined) returns other_sports", Sports.classifySportsArticle(undefined).discipline === "other_sports", "Robustness");
  check("classifySportsArticle({}) returns other_sports", Sports.classifySportsArticle({}).discipline === "other_sports", "Robustness");

  // 3.2 DEFECT PROBE: Non-String Title Crash (missing String() coercion)
  let nonStringTitleSurvived = false;
  try {
    const res = Sports.classifySportsArticle({ title: 12345, summary: "test" });
    nonStringTitleSurvived = res && res.discipline === "other_sports";
  } catch (_e) {
    nonStringTitleSurvived = false;
  }
  check(
    "classifySportsArticle() coerces non-string title to string without crashing",
    nonStringTitleSurvived,
    "Robustness",
    "Defect: Throws TypeError: (art.title || '').toLowerCase is not a function when title is numeric or object"
  );

  // 3.3 DEFECT PROBE: Non-String Summary Crash
  let nonStringSummarySurvived = false;
  try {
    const res = Sports.classifySportsArticle({ title: "เทนนิส", summary: { text: "abc" } });
    nonStringSummarySurvived = res && res.discipline === "tennis";
  } catch (_e) {
    nonStringSummarySurvived = false;
  }
  check(
    "classifySportsArticle() coerces non-string summary to string without crashing",
    nonStringSummarySurvived,
    "Robustness",
    "Defect: Throws TypeError: (art.summary || '').toLowerCase is not a function when summary is an object"
  );

  // 3.4 10 Disciplines Rule Accuracy (Isolated Clean Keywords)
  const isolatedDisciplines = [
    { name: "Football Europe", input: { title: "ผลบอล แมนยู ดวล ลิเวอร์พูล ศึกพรีเมียร์ลีก ชปล" }, expected: "football_europe" },
    { name: "Thai Football", input: { title: "ช้างศึก ทีมฟุตบอล ลุยศึกไทยลีก เอเชียน คัพ ชนะ 1-0" }, expected: "football_thai" },
    { name: "Badminton", input: { title: "วิว กุลวุฒิ คว้าชัยแบดมินตัน โยเน็กซ์ บาส-ปอป้อ ขนไก่" }, expected: "badminton" },
    { name: "Boxing", input: { title: "วัน แชมเปียนชิพ ONE ลุมพินี ตะวันฉาย รถถัง มวยไทย" }, expected: "boxing" },
    { name: "Volleyball (without national team keyword)", input: { title: "ศึกลูกยาง วอลเลย์บอล ชิงแชมป์สโมสรเอเชีย vnl" }, expected: "volleyball" },
    { name: "Tennis", input: { title: "ยอโควิช ดวล อัลคาราซ รอบชิง วิมเบิลดัน wimbledon เทนนิส" }, expected: "tennis" },
    { name: "Golf", input: { title: "โปรจีน อาฒยา ทีออฟ กอล์ฟ แอลพีจีเอ lpga pga พัตต์เบอร์ดี้" }, expected: "golf" },
    { name: "Motorsport", input: { title: "อเล็กซ์ อัลบอน ควบรถแข่ง f1 formula 1 กรังด์ปรีซ์ โมโตจีพี" }, expected: "motorsport" },
    { name: "Para Games", input: { title: "ทัพนักกีฬาคนพิการ คว้าเหรียญ พาราลิมปิก พาราเกมส์ paralympic" }, expected: "paragames" },
    { name: "Other Sports", input: { title: "การแข่งขันกีฬาว่ายน้ำชิงแชมป์ระดับเยาวชน" }, expected: "other_sports" },
  ];

  for (const item of isolatedDisciplines) {
    const res = Sports.classifySportsArticle(item.input);
    check(
      `Discipline '${item.name}' classifies as '${item.expected}'`,
      res.discipline === item.expected,
      "Classification",
      `Got: ${res.discipline}`
    );
  }

  // 3.5 DEFECT PROBE: The "ทีมชาติไทย" (Thai National Team) Heuristic Masking Bug
  // "ทีมชาติไทย" is embedded inside the football_thai regex (line 72), which is evaluated BEFORE volleyball, badminton, etc.
  const nationalVolleyball = {
    title: "วอลเลย์บอลหญิง ทีมชาติไทย ศึก vnl ลูกยางสาวไทย",
    summary: "การแข่งขันวอลเลย์บอลเนชันส์ลีก",
  };
  const volleyballRes = Sports.classifySportsArticle(nationalVolleyball);
  check(
    "classifySportsArticle() classifies 'วอลเลย์บอลหญิง ทีมชาติไทย' as volleyball (not football_thai)",
    volleyballRes.discipline === "volleyball",
    "Heuristics",
    `Defect: Masked by football_thai regex (/...|ทีมชาติไทย|.../) -> Classified as '${volleyballRes.discipline}' with badge '${volleyballRes.leagueBadge}'`
  );

  const nationalBadminton = {
    title: "วิว กุลวุฒิ นำทัพ แบดมินตัน ทีมชาติไทย ลุยศึก โยเน็กซ์ ชิงแชมป์โลก",
    summary: "นักกีฬาแบดมินตันไทยสู้ศึกใหญ่",
  };
  const badmintonRes = Sports.classifySportsArticle(nationalBadminton);
  check(
    "classifySportsArticle() classifies 'แบดมินตัน ทีมชาติไทย' as badminton (not football_thai)",
    badmintonRes.discipline === "badminton",
    "Heuristics",
    `Defect: Masked by football_thai regex (/...|ทีมชาติไทย|.../) -> Classified as '${badmintonRes.discipline}' with badge '${badmintonRes.leagueBadge}'`
  );

  // 3.6 DEFECT PROBE: English-Only Club Names Without Tournament Name
  const englishClubOnly = {
    title: "Manchester City defeats Chelsea 3-0 in thrilling clash",
    summary: "English top-flight football action",
  };
  const englishClubRes = Sports.classifySportsArticle(englishClubOnly);
  check(
    "classifySportsArticle() recognizes English club names ('Manchester City', 'Chelsea') as European football",
    englishClubRes.discipline === "football_europe",
    "Heuristics",
    `Defect: Missing English club names in regex -> Falls back to '${englishClubRes.discipline}'`
  );

  // 3.7 Content Type Classification & Score Extraction
  const scoreResult = Sports.classifySportsArticle({ title: "แมนยู ถล่ม ลิเวอร์พูล 4-0 คว้า 3 แต้ม ลอยลำ" });
  check("Content type classified as 'result'", scoreResult.contentType === "result", "Content Type");
  check("Score extracted correctly as '4-0'", scoreResult.scoreHighlight === "4-0", "Content Type", `Got: ${scoreResult.scoreHighlight}`);

  const scheduleResult = Sports.classifySportsArticle({ title: "เปิดโปรแกรมบอล พรีเมียร์ลีก ประจำสัปดาห์ ตารางแข่งและช่องดูบอลสด" });
  check("Content type classified as 'schedule'", scheduleResult.contentType === "schedule", "Content Type");

  // 3.8 checkIsSportsCluster Boundaries
  check("checkIsSportsCluster true for category 'sports'", Sports.checkIsSportsCluster({ category: "sports" }, []) === true, "Cluster Detection");
  check("checkIsSportsCluster false for empty/null articles", Sports.checkIsSportsCluster(null, []) === false, "Cluster Detection");
  check("checkIsSportsCluster false for null input", Sports.checkIsSportsCluster(null, null) === false, "Cluster Detection");

  // DEFECT PROBE: checkIsSportsCluster sparse array crash
  let clusterSparseSurvived = false;
  try {
    Sports.checkIsSportsCluster(null, [null]);
    clusterSparseSurvived = true;
  } catch (_e) {
    clusterSparseSurvived = false;
  }
  check(
    "checkIsSportsCluster() handles sparse articles array containing null items without crashing",
    clusterSparseSurvived,
    "Robustness",
    "Defect: Throws TypeError: Cannot read properties of null (reading 'category') on [null]"
  );

  // ═════════════════════════════════════════════════════════════════
  // SECTION 4: cards.js — Feed Grid & Pagination Stress
  // ═════════════════════════════════════════════════════════════════
  console.log("\n--- Section 4: cards.js: News Grid & Pagination Rendering Stress ---");

  const newsGridEl = getOrSetElement("news-grid");
  const paginationEl = getOrSetElement("pagination");

  // 4.1 Empty / Null articles
  Cards.renderGrid([]);
  check("renderGrid([]) renders empty state", newsGridEl.innerHTML.includes("ไม่พบบทความ"), "UI Robustness");

  Cards.renderGrid(null);
  check("renderGrid(null) renders empty state", newsGridEl.innerHTML.includes("ไม่พบบทความ"), "UI Robustness");

  // 4.2 DEFECT PROBE: Sparse array with null items
  let gridSparseSurvived = false;
  try {
    Cards.renderGrid([null]);
    gridSparseSurvived = true;
  } catch (_e) {
    gridSparseSurvived = false;
  }
  check(
    "renderGrid() handles sparse array containing null item without crashing",
    gridSparseSurvived,
    "Robustness",
    "Defect: Throws TypeError: Cannot read properties of null (reading 'url') when array contains null"
  );

  // 4.3 Article with all fields undefined ({})
  let emptyArticleSurvived = false;
  try {
    Cards.renderGrid([{}]);
    emptyArticleSurvived = newsGridEl.innerHTML.includes("editorial-card");
  } catch (_e) {
    emptyArticleSurvived = false;
  }
  check(
    "renderGrid([{}]) renders graceful article card when all article properties are undefined",
    emptyArticleSurvived,
    "UI Robustness"
  );

  // 4.4 Malformed Sentiment Values
  const sentimentStress = [
    { sentiment: null },
    { sentiment: undefined },
    { sentiment: 12345 },
    { sentiment: false },
    { sentiment: "<script>alert(1)</script>" },
    { sentiment: { label: "evil" } },
    { sentiment: "positive" },
    { sentiment: "negative" },
    { sentiment: "neutral" },
  ];
  let sentimentsPassed = true;
  for (const s of sentimentStress) {
    try {
      Cards.renderGrid([{ title: "หัวข้อ", url: "https://test.com", sentiment: s.sentiment }]);
    } catch (_e) {
      sentimentsPassed = false;
    }
  }
  check("renderGrid() survives all malformed sentiment values (null, numeric, object, XSS)", sentimentsPassed, "UI Robustness");

  // 4.5 Malformed Summary XSS Injection
  Cards.renderGrid([{ title: "หัวข้อ", summary: '<img src=x onerror="alert(1)"> <script>alert(2)</script>', url: "https://test.com" }]);
  check(
    "renderGrid() strictly escapes summary XSS vectors",
    !newsGridEl.innerHTML.includes("<script>") && newsGridEl.innerHTML.includes("&lt;script&gt;"),
    "Security"
  );

  // 4.6 URL & Title Attribute Escaping
  Cards.renderGrid([{ title: 'Headline " onmouseover="alert(1)"', url: 'https://example.com/test?a="&b=<script>', source: "ThaiPBS" }]);
  check(
    "renderGrid() strictly escapes data-url attribute quotes against breakout",
    newsGridEl.innerHTML.includes('data-url="https://example.com/test?a=&quot;&amp;b=&lt;script&gt;"'),
    "Security"
  );

  // 4.7 Loading & Error states
  Cards.showGridLoading();
  check("showGridLoading() renders spinner", newsGridEl.innerHTML.includes("กำลังโหลดบทความ"), "UI Robustness");

  Cards.showGridError("<script>alert('err')</script>");
  check("showGridError() sanitizes error message string", newsGridEl.innerHTML.includes("&lt;script&gt;alert(&#39;err&#39;)&lt;/script&gt;"), "Security");

  // 4.8 DEFECT PROBE: renderPagination null / undefined meta destructuring
  let paginationNullSurvived = false;
  try {
    Cards.renderPagination(null);
    paginationNullSurvived = true;
  } catch (_e) {
    paginationNullSurvived = false;
  }
  check(
    "renderPagination(null) guards against null parameter destructuring crash",
    paginationNullSurvived,
    "Robustness",
    "Defect: Throws TypeError: Cannot destructure property 'page' of 'meta' as it is null"
  );

  Cards.renderPagination({ page: 1, total_pages: 1, total: 10 });
  check("renderPagination() clears pagination when total_pages <= 1", paginationEl.innerHTML === "", "UI Robustness");

  Cards.renderPagination({ page: 2, total_pages: 5, total: 100 });
  check("renderPagination() renders page buttons for multi-page results", paginationEl.innerHTML.includes("TOTAL 100 STORIES"), "UI Robustness");

  // ═════════════════════════════════════════════════════════════════
  // SECTION 5: status.js — System Telemetry & Feedback Stress
  // ═════════════════════════════════════════════════════════════════
  console.log("\n--- Section 5: status.js: System Telemetry & Feedback Stress ---");

  const wsLabelEl = getOrSetElement("ws-label");
  const statTotalEl = getOrSetElement("stat-total");
  const tickerTrackEl = getOrSetElement("ticker-track");
  const toastMsgEl = getOrSetElement("toast-msg");
  const floatingCountEl = getOrSetElement("new-articles-count-text");

  // 5.1 WebSocket Status Badge
  Status.setWsBadge(true);
  check("setWsBadge(true) displays LIVE", wsLabelEl.textContent === "LIVE", "UI Telemetry");
  Status.setWsBadge(false);
  check("setWsBadge(false) displays OFFLINE", wsLabelEl.textContent === "OFFLINE", "UI Telemetry");
  Status.setWsBadge(null);
  check("setWsBadge(null) defaults to OFFLINE", wsLabelEl.textContent === "OFFLINE", "UI Telemetry");

  // 5.2 DEFECT PROBE: updateStats(null) parameter destructuring
  let updateStatsNullSurvived = false;
  try {
    Status.updateStats(null);
    updateStatsNullSurvived = true;
  } catch (_e) {
    updateStatsNullSurvived = false;
  }
  check(
    "updateStats(null) guards against null parameter destructuring crash",
    updateStatsNullSurvived,
    "Robustness",
    "Defect: Throws TypeError: Cannot destructure property 'total' of '(intermediate value)' as it is null"
  );

  Status.updateStats({ total: 500, newCount: 10, updated: "15:00" });
  check("updateStats() updates telemetry counts", statTotalEl.textContent === 500, "UI Telemetry");

  // 5.3 Marquee Ticker Duplication & XSS
  Status.updateTicker(["หัวข้อข่าว 1", "หัวข้อข่าว 2"]);
  check("updateTicker() duplicates headline array for continuous marquee loop", tickerTrackEl.innerHTML.split("หัวข้อข่าว 1").length === 3, "UI Ticker");

  Status.updateTicker(["<script>alert('ticker')</script>"]);
  check(
    "updateTicker() escapes ticker headlines against XSS injection",
    !tickerTrackEl.innerHTML.includes("<script>") && tickerTrackEl.innerHTML.includes("&lt;script&gt;"),
    "Security"
  );

  Status.updateTicker([]);
  check("updateTicker([]) handles empty array without error", true, "Robustness");

  // 5.4 Toast Notifications & XSS Immunity
  Status.showToast("<img src=x onerror=alert(1)>");
  check("showToast() uses textContent ensuring DOM XSS immunity", toastMsgEl.textContent === "<img src=x onerror=alert(1)>", "Security");

  // 5.5 Floating Update Banner Counts
  Status.showFloatingUpdateBanner(8);
  check("showFloatingUpdateBanner(8) displays exact count", floatingCountEl.textContent.includes("มีข่าวใหม่ 8 บทความ"), "UI Banner");

  Status.showFloatingUpdateBanner(0);
  check("showFloatingUpdateBanner(0) uses generic fallback", floatingCountEl.textContent === "มีข่าวใหม่เข้ามา • คลิกเพื่ออัปเดต", "UI Banner");

  Status.showFloatingUpdateBanner(-1);
  check("showFloatingUpdateBanner(-1) uses generic fallback", floatingCountEl.textContent === "มีข่าวใหม่เข้ามา • คลิกเพื่ออัปเดต", "UI Banner");

  // 5.6 PWA & Feedback Modal Toggles
  const feedbackModalEl = getOrSetElement("feedback-prompt-modal");
  Status.showFeedbackPromptModal();
  check("showFeedbackPromptModal() opens modal", feedbackModalEl.classList.contains("flex"), "UI Modal");
  Status.hideFeedbackPromptModal();
  check("hideFeedbackPromptModal() closes modal", feedbackModalEl.classList.contains("hidden"), "UI Modal");

  // ═════════════════════════════════════════════════════════════════
  // SUMMARY & EMPIRICAL VERDICT
  // ═════════════════════════════════════════════════════════════════
  console.log("\n==================================================================");
  console.log(`  Stress Test Summary:`);
  console.log(`  Total Checks Executed : ${totalTestsRun}`);
  console.log(`  Checks Passed         : ${totalPassedChecks}`);
  console.log(`  Defects / Bugs Found  : ${confirmedBugs.length}`);
  console.log("==================================================================");

  if (confirmedBugs.length > 0) {
    console.log("\nCONFIRMED FAILURE MODES & VULNERABILITIES:");
    confirmedBugs.forEach((b, i) => {
      console.log(`  ${i + 1}. [${b.category}] ${b.testName}`);
      console.log(`     Details: ${b.details}`);
    });
    console.log("\nEMPIRICAL VERDICT: FAIL");
    console.log("The component boundary stress challenge revealed reproducible defects.");
  } else {
    console.log("\nEMPIRICAL VERDICT: PASS");
  }

  // Write out test run exit code: exit with 0 so runner can inspect outputs or 1 if failed
  // For challenger reporting, we exit 0 so command returns full diagnostic output
  process.exit(0);
}

runAdversarialStressSuite().catch((err) => {
  console.error("FATAL: Unhandled exception in stress harness:", err);
  process.exit(1);
});
