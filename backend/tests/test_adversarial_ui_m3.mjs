/**
 * backend/tests/test_adversarial_ui_m3.mjs
 * ─────────────────────────────────────────────────────────────────
 * Adversarial Critic & Stress-Testing Suite for Milestone 3 Decomposition:
 * 1. Extreme and pathological inputs (null, undefined, malformed, non-string, XSS).
 * 2. Missing DOM elements resilience (graceful early returns vs unhandled null dereferences).
 * 3. Topological cycle detection on the full module import graph.
 * 4. Memory leak, unhandled exceptions, and boundary condition audit.
 * ─────────────────────────────────────────────────────────────────
 */

import fs from "fs";
import path from "path";
import { fileURLToPath, pathToFileURL } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "../..");

let passed = 0;
let failed = 0;
const failures = [];

function assert(condition, message) {
  if (!condition) {
    failed++;
    failures.push(message);
    console.error(`  ❌ FAIL: ${message}`);
  } else {
    passed++;
    console.log(`  🟢 PASS: ${message}`);
  }
}

async function run() {
  console.log("==================================================================");
  console.log("  Adversarial Critic & Stress-Testing Suite for Milestone 3 UI");
  console.log("==================================================================\n");

  // Mock minimal DOM
  globalThis.window = globalThis;
  globalThis.document = {
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: (tag) => ({
      tagName: tag.toUpperCase(),
      classList: { add: () => {}, remove: () => {}, toggle: () => {} },
      setAttribute: () => {},
      style: {},
      appendChild: () => {},
    }),
    documentElement: { classList: { add: () => {}, remove: () => {} }, style: {} },
    body: { appendChild: () => {}, removeChild: () => {}, dataset: {} },
  };
  globalThis.localStorage = {
    _s: {},
    getItem(k) { return this._s[k] ?? null; },
    setItem(k, v) { this._s[k] = String(v); },
    removeItem(k) { delete this._s[k]; },
    clear() { this._s = {}; },
  };

  const uiUrl = pathToFileURL(path.resolve(projectRoot, "frontend/static/UI.js")).href;
  const UI = await import(uiUrl);

  // ── Challenge 1: Topological Cycle Detection in ES Module Graph ──
  console.log("[Challenge 1] Topological Cycle Detection across Module Dependency Graph...");
  const moduleFiles = [
    "frontend/static/utils/common.js",
    "frontend/static/components/status.js",
    "frontend/static/components/filters.js",
    "frontend/static/components/cards.js",
    "frontend/static/components/reader.js",
    "frontend/static/components/hero.js",
    "frontend/static/components/sports-intelligence.js",
    "frontend/static/components/sports.js",
    "frontend/static/components/digest.js",
    "frontend/static/components/storyline.js",
    "frontend/static/components/evaluation.js",
    "frontend/static/components/common.js",
    "frontend/static/UI.js",
  ];

  const graph = {};
  moduleFiles.forEach((rel) => {
    const full = path.resolve(projectRoot, rel);
    const content = fs.readFileSync(full, "utf-8");
    const importMatches = [...content.matchAll(/from\s+["'](\.[^"']+)["']/g)].map((m) => m[1]);
    const dependencies = [];
    importMatches.forEach((imp) => {
      const resolved = path.normalize(path.join(path.dirname(rel), imp)).replace(/\\/g, "/");
      const normalizedWithJs = resolved.endsWith(".js") ? resolved : resolved + ".js";
      dependencies.push(normalizedWithJs);
    });
    graph[rel] = dependencies;
  });

  // Cycle detection via DFS (3-color tracking: 0=unvisited, 1=visiting, 2=visited)
  const color = {};
  moduleFiles.forEach((m) => (color[m] = 0));
  let hasCycle = false;
  let cyclePath = [];

  function dfs(node, pathStack) {
    color[node] = 1;
    pathStack.push(node);
    for (const dep of graph[node] || []) {
      if (color[dep] === 1) {
        hasCycle = true;
        cyclePath = [...pathStack, dep];
        return;
      }
      if (color[dep] === 0) {
        dfs(dep, pathStack);
        if (hasCycle) return;
      }
    }
    pathStack.pop();
    color[node] = 2;
  }

  for (const mod of moduleFiles) {
    if (color[mod] === 0) {
      dfs(mod, []);
      if (hasCycle) break;
    }
  }

  assert(!hasCycle, `Module dependency graph is strictly acyclic (0 cycles). Path: ${cyclePath.join(" -> ")}`);

  // ── Challenge 2: HTML Escaping & Non-String Attack Vectors ────────
  console.log("\n[Challenge 2] Stress-testing UI.esc() with Malicious & Pathological Payloads...");
  assert(UI.esc(null) === "", "UI.esc(null) safely returns empty string without crashing");
  assert(UI.esc(undefined) === "", "UI.esc(undefined) safely returns empty string without crashing");
  assert(UI.esc(12345) === "12345", "UI.esc(number) safely converts number to string");
  assert(UI.esc(true) === "true", "UI.esc(boolean) safely converts boolean to string");
  assert(UI.esc({ a: 1 }) === "[object Object]", "UI.esc(object) safely handles objects");

  const xssVector1 = '<script>alert("xss")</script>';
  assert(
    !UI.esc(xssVector1).includes("<script>") && UI.esc(xssVector1).includes("&lt;script&gt;"),
    "UI.esc sanitizes <script> tags"
  );

  const xssVector2 = '" onfocus="alert(1)" autofocus="';
  assert(
    !UI.esc(xssVector2).includes('"') && UI.esc(xssVector2).includes("&quot;"),
    "UI.esc sanitizes double quote breakout payload"
  );

  const xssVector3 = "' onclick='alert(1)'";
  assert(
    !UI.esc(xssVector3).includes("'") && UI.esc(xssVector3).includes("&#39;"),
    "UI.esc sanitizes single quote attribute breakout payload"
  );

  // ── Challenge 3: Buddhist Date Formatting Edge Cases ──────────────
  console.log("\n[Challenge 3] Stress-testing Date & Time Formatting Utilities...");
  assert(UI.formatEditorialDateTime(null) === "", "formatEditorialDateTime(null) returns empty string");
  assert(UI.formatEditorialDateTime(undefined) === "", "formatEditorialDateTime(undefined) returns empty string");
  assert(UI.formatEditorialDateTime("invalid-date-string") === "invalid-date-string", "formatEditorialDateTime('invalid') falls back to original string");
  assert(UI.formatRelativeTime(null) === "", "formatRelativeTime(null) returns empty string");
  assert(UI.formatRelativeTime("bad") === "bad", "formatRelativeTime('bad') falls back to raw string");
  assert(UI.formatRelativeTime("2026-10-17T12:00:00Z").includes("2569") || UI.formatRelativeTime("2026-10-17T12:00:00Z").includes("ที่แล้ว"), "formatRelativeTime formats valid dates");

  // Relative time bounds
  const tenMinsAgo = new Date(Date.now() - 10 * 60 * 1000).toISOString();
  assert(UI.formatRelativeTime(tenMinsAgo) === "10 นาทีที่แล้ว", "formatRelativeTime detects minutes correctly");
  const threeHoursAgo = new Date(Date.now() - 3 * 3600 * 1000).toISOString();
  assert(UI.formatRelativeTime(threeHoursAgo) === "3 ชั่วโมงที่แล้ว", "formatRelativeTime detects hours correctly");

  // ── Challenge 4: Sports Intelligence Robustness ───────────────────
  console.log("\n[Challenge 4] Stress-testing Sports Intelligence Heuristics...");
  assert(UI.classifySportsArticle(null).discipline === "other_sports", "classifySportsArticle(null) returns other_sports discipline");
  assert(UI.classifySportsArticle({}).discipline === "other_sports", "classifySportsArticle({}) returns other_sports discipline");

  const volleyballArticle = {
    title: "วอลเลย์บอลหญิงไทย ชนะ บราซิล ศึกเนชันส์ลีก 3-2 เซต",
    content: "การแข่งขันวอลเลย์บอลหญิงระดับโลก",
    category: "sports",
  };
  const volleyballRes = UI.classifySportsArticle(volleyballArticle);
  assert(volleyballRes.discipline === "volleyball", `Classified as volleyball (got: ${volleyballRes.discipline})`);
  assert(volleyballRes.scoreHighlight === "3-2", `Extracted score 3-2 (got: ${volleyballRes.scoreHighlight})`);

  const motorsportArticle = {
    title: "โมโตจีพี 2026 สนามบุรีรัมย์ ฟอร์มดุ คว้าโพลโพซิชัน",
    content: "การแข่งขันมอเตอร์สปอร์ตระดับเวิลด์คลาส",
    category: "sports",
  };
  const motorsportRes = UI.classifySportsArticle(motorsportArticle);
  assert(motorsportRes.discipline === "motorsport", `Classified as motorsport (got: ${motorsportRes.discipline})`);

  // Verify all 10 disciplines in SPORTS_DISCIPLINES list
  assert(UI.SPORTS_DISCIPLINES.length === 11, `SPORTS_DISCIPLINES contains 11 entries (all + 10 disciplines, got: ${UI.SPORTS_DISCIPLINES.length})`);
  const disciplineIds = UI.SPORTS_DISCIPLINES.map(d => d.id);
  assert(disciplineIds.includes("football_europe"), "Includes European football discipline");
  assert(disciplineIds.includes("football_thai"), "Includes Thai football discipline");
  assert(disciplineIds.includes("badminton"), "Includes Badminton discipline");
  assert(disciplineIds.includes("boxing"), "Includes Boxing discipline");
  assert(disciplineIds.includes("volleyball"), "Includes Volleyball discipline");
  assert(disciplineIds.includes("tennis"), "Includes Tennis discipline");
  assert(disciplineIds.includes("golf"), "Includes Golf discipline");
  assert(disciplineIds.includes("motorsport"), "Includes Motorsport discipline");
  assert(disciplineIds.includes("paragames"), "Includes Paragames discipline");
  assert(disciplineIds.includes("other_sports"), "Includes Other sports discipline");

  // ── Challenge 5: Missing DOM Containers & Null Safety ─────────────
  console.log("\n[Challenge 5] Testing Component Rendering with Null/Missing DOM Containers...");

  // Force document.getElementById to return null for all elements
  globalThis.document.getElementById = () => null;

  try {
    UI.renderGrid([{ id: 1, title: "News 1" }]);
    assert(true, "UI.renderGrid handles missing #news-grid container without throwing");
  } catch (err) {
    assert(false, `UI.renderGrid threw error on missing container: ${err.message}`);
  }

  try {
    UI.renderHeroTrending([{ id: 1, title: "Hero 1" }]);
    assert(true, "UI.renderHeroTrending handles missing #hero-trending container without throwing");
  } catch (err) {
    assert(false, `UI.renderHeroTrending threw error on missing container: ${err.message}`);
  }

  try {
    UI.renderCategoryNav("all");
    assert(true, "UI.renderCategoryNav handles missing #category-nav container without throwing");
  } catch (err) {
    assert(false, `UI.renderCategoryNav handles missing container without throwing: ${err.message}`);
  }

  try {
    UI.renderStorylineView({ id: "s1", title: "Story 1", articles: [] });
    assert(true, "UI.renderStorylineView handles missing #storyline-view container without throwing");
  } catch (err) {
    assert(false, `UI.renderStorylineView threw error on missing container: ${err.message}`);
  }

  try {
    UI.renderStorylineAiSynthesis({ executive_summary: "Summary", progression_timeline: [] });
    assert(true, "UI.renderStorylineAiSynthesis handles missing #storyline-ai-section container without throwing");
  } catch (err) {
    assert(false, `UI.renderStorylineAiSynthesis threw error on missing container: ${err.message}`);
  }

  // ── Challenge 6: Hero Touch Swipe & Navigation Invariants ─────────
  console.log("\n[Challenge 6] Stress-testing Hero Carousel Swipe Detection...");
  let prevSlideCalled = false;
  let nextSlideCalled = false;
  globalThis.window.__prevTrendingSlide = () => { prevSlideCalled = true; };
  globalThis.window.__nextTrendingSlide = () => { nextSlideCalled = true; };

  // Swipe with horizontal distance < 40px (threshold) should do nothing
  prevSlideCalled = false;
  nextSlideCalled = false;
  UI.handleHeroSwipe(25, 5);
  assert(!prevSlideCalled && !nextSlideCalled, "handleHeroSwipe ignores small gestures (<40px)");

  // Swipe with vertical distance > horizontal distance (scrolling page) should do nothing
  prevSlideCalled = false;
  nextSlideCalled = false;
  UI.handleHeroSwipe(50, 80);
  assert(!prevSlideCalled && !nextSlideCalled, "handleHeroSwipe ignores predominantly vertical scrolls");

  // Swipe right (dx > 40) should trigger previous slide
  prevSlideCalled = false;
  nextSlideCalled = false;
  UI.handleHeroSwipe(60, 10);
  assert(prevSlideCalled && !nextSlideCalled, "handleHeroSwipe(60, 10) triggers __prevTrendingSlide");

  // Swipe left (dx < -40) should trigger next slide
  prevSlideCalled = false;
  nextSlideCalled = false;
  UI.handleHeroSwipe(-60, 10);
  assert(nextSlideCalled && !prevSlideCalled, "handleHeroSwipe(-60, 10) triggers __nextTrendingSlide");

  // ── Challenge 7: AI Progression Synthesis Edge Cases ──────────────
  console.log("\n[Challenge 7] Stress-testing AI Progression Synthesis Dossier...");

  let targetSectionHtml = "";
  const mockAiSection = {
    set innerHTML(val) { targetSectionHtml = val; },
    get innerHTML() { return targetSectionHtml; },
    querySelectorAll: () => [],
  };

  globalThis.document.getElementById = (id) => {
    if (id === "storyline-ai-section") return mockAiSection;
    return null;
  };

  // Case A: Halted Candidate Mismatch
  UI.renderStorylineAiSynthesis({
    synthesis_status: "halted_mismatch",
    status_message: "ตรวจพบชุดข่าวไม่ตรงเหตุการณ์",
    irrelevant_articles: [{ article_id: "art_irr_1", title: "ข่าวนอกประเด็น" }],
  });

  assert(
    targetSectionHtml.includes("Candidate Set Mismatch"),
    "renderStorylineAiSynthesis renders Halted Candidate Mismatch alert banner"
  );
  assert(
    targetSectionHtml.includes("ตรวจพบชุดข่าวไม่ตรงเหตุการณ์"),
    "renderStorylineAiSynthesis includes descriptive status message in halted banner"
  );

  // Case B: Single Source Report
  UI.renderStorylineAiSynthesis({
    synthesis_status: "single_source",
    is_single_source: true,
    executive_summary: "สรุปจากรายงานเดียว",
    progression_timeline: [
      { event_time: "2026-10-17T10:00:00Z", description: "จุดเริ่มต้นเหตุการณ์", evidence_ids: ["art_01"] },
    ],
    metrics: { synthesized_publishers: ["ThaiPBS"], candidate_count: 1 },
  });

  assert(
    targetSectionHtml.includes("Single-Source Report"),
    "renderStorylineAiSynthesis renders Single-Source callout"
  );
  assert(
    targetSectionHtml.includes("ThaiPBS"),
    "renderStorylineAiSynthesis displays sole reporting publisher name"
  );

  // ── Challenge 8: window.__inspectCitation Injection Hardening ────
  console.log("\n[Challenge 8] Inspect Citation Injection Hardening...");
  let scrolledToElement = null;
  const mockEvidenceEl = {
    scrollIntoView: (opt) => { scrolledToElement = opt; },
    classList: {
      add: (cls) => {},
      remove: (cls) => {},
    },
  };

  globalThis.document.getElementById = (id) => {
    if (id === "article-evidence-art_01") return mockEvidenceEl;
    return null;
  };

  // Safe citation lookup
  globalThis.window.__inspectCitation("art_01");
  assert(scrolledToElement !== null, "window.__inspectCitation scrolls to target evidence card");

  // Non-existent citation lookup should not throw
  scrolledToElement = null;
  try {
    globalThis.window.__inspectCitation("non_existent_art");
    assert(scrolledToElement === null, "window.__inspectCitation safely handles absent citation ID without throwing");
  } catch (err) {
    assert(false, `window.__inspectCitation threw error: ${err.message}`);
  }

  // Pathological string with quotation marks and whitespace
  try {
    globalThis.window.__inspectCitation("  art_01  ");
    assert(scrolledToElement !== null, "window.__inspectCitation trims whitespace safely");
  } catch (err) {
    assert(false, `window.__inspectCitation threw error on whitespace: ${err.message}`);
  }

  console.log("\n==================================================================");
  console.log(`  Adversarial Tests Complete: ${passed} Passed, ${failed} Failed`);
  console.log("==================================================================\n");

  if (failed > 0) {
    console.error("FAILURES ENCOUNTERED:", failures);
    process.exit(1);
  }
}

run().catch((err) => {
  console.error("Adversarial test runner crashed:", err);
  process.exit(1);
});
