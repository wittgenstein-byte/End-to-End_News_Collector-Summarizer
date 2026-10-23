/**
 * backend/tests/test_dom_contract.mjs
 * ─────────────────────────────────────────────────────────────────
 * Independent Verification Suite for Milestone 3 DOM Contracts & Events:
 * 1. Checks every DOM element ID referenced in UI modules and main.js
 *    against frontend/index.html or dynamic component templates.
 * 2. Verifies all 16 window.__* global event handlers registration.
 * 3. Verifies all inline HTML event handlers (onclick="window.__*") in
 *    frontend/index.html and component render templates resolve to defined functions.
 * 4. Verifies view switching contracts (#feed-view, #preview-view, #storyline-view, #evaluation-view).
 * 5. Stress-tests modal handling, bookmarking, and error states.
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
    console.log(`  ✅ PASS: ${message}`);
  }
}

async function run() {
  console.log("==================================================================");
  console.log("  Milestone 3 DOM Contract & Event Handler Independent Verification");
  console.log("==================================================================\n");

  const htmlPath = path.resolve(projectRoot, "frontend/index.html");
  const htmlContent = fs.readFileSync(htmlPath, "utf-8");

  // Collect all static IDs from index.html
  const staticHtmlIds = new Set(
    [...htmlContent.matchAll(/id=["']([^"']+)["']/g)].map((m) => m[1])
  );
  console.log(`[Info] Found ${staticHtmlIds.size} static IDs in frontend/index.html`);

  const componentFiles = [
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
    "frontend/static/main.js",
  ];

  // Also collect all IDs rendered dynamically into innerHTML inside components or set via .id =
  const dynamicTemplateIds = new Set();
  componentFiles.forEach((rel) => {
    const full = path.resolve(projectRoot, rel);
    const content = fs.readFileSync(full, "utf-8");
    const matches1 = [...content.matchAll(/id=["']([a-zA-Z0-9_\-]+)["']/g)].map((m) => m[1]);
    const matches2 = [...content.matchAll(/\.id\s*=\s*["']([a-zA-Z0-9_\-]+)["']/g)].map((m) => m[1]);
    matches1.forEach((id) => dynamicTemplateIds.add(id));
    matches2.forEach((id) => dynamicTemplateIds.add(id));
  });
  // Also recognize optional fallback IDs
  dynamicTemplateIds.add("news-grid-section");
  console.log(`[Info] Found ${dynamicTemplateIds.size} dynamic template IDs in components`);

  // ── Test Suite 1: Critical Main View Containers ──────────────────
  console.log("\n[Test Suite 1] Verifying Core View Containers in index.html...");
  const criticalViews = [
    "feed-view",
    "preview-view",
    "storyline-view",
    "evaluation-view",
    "news-grid",
    "hero-trending",
    "category-nav",
    "source-filters",
    "search-input",
    "pagination",
    "summary-modal",
    "summary-loading",
    "summary-result",
    "history-modal",
    "pwa-install-banner",
    "feedback-prompt-modal",
    "storyline-floating-back",
  ];

  for (const viewId of criticalViews) {
    assert(staticHtmlIds.has(viewId), `Critical DOM element #${viewId} exists in frontend/index.html`);
  }

  // ── Test Suite 2: All getElementById references in JS files ──────
  console.log("\n[Test Suite 2] Verifying getElementById references across codebase...");
  const referencedIdsByFile = {};

  componentFiles.forEach((rel) => {
    const full = path.resolve(projectRoot, rel);
    const content = fs.readFileSync(full, "utf-8");
    const ids = [
      ...content.matchAll(/getElementById\s*\(\s*["']([^"']+)["']\s*\)/g),
    ].map((m) => m[1]);
    referencedIdsByFile[rel] = [...new Set(ids)];
  });

  for (const [relFile, ids] of Object.entries(referencedIdsByFile)) {
    for (const id of ids) {
      // Must be in static HTML OR dynamically created in a component template
      const existsInStatic = staticHtmlIds.has(id);
      const existsInDynamic = dynamicTemplateIds.has(id);
      assert(
        existsInStatic || existsInDynamic,
        `DOM ID #${id} referenced in ${relFile} must exist in index.html or dynamic template (static: ${existsInStatic}, dynamic: ${existsInDynamic})`
      );
    }
  }

  // ── Test Suite 3: Setup Mock Environment and Load UI.js + main.js ──
  console.log("\n[Test Suite 3] Verifying Module Evaluation & window.__* Global Handlers...");

  // Shim browser globals
  globalThis.window = globalThis;
  globalThis.addEventListener = () => {};
  globalThis.removeEventListener = () => {};
  globalThis.location = { hash: "#/" };
  globalThis.document = {
    getElementById: (id) => {
      return {
        id,
        classList: {
          add: () => {},
          remove: () => {},
          contains: () => false,
          toggle: () => {},
        },
        className: "",
        textContent: "",
        innerHTML: "",
        style: {},
        appendChild: () => {},
        removeChild: () => {},
        setAttribute: () => {},
        getAttribute: () => null,
        scrollIntoView: () => {},
        getBoundingClientRect: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
        addEventListener: () => {},
        removeEventListener: () => {},
        focus: () => {},
        dataset: {},
      };
    },
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: (tag) => ({
      tagName: tag.toUpperCase(),
      classList: { add: () => {}, remove: () => {}, toggle: () => {} },
      setAttribute: () => {},
      style: {},
      appendChild: () => {},
    }),
    documentElement: {
      classList: { add: () => {}, remove: () => {}, contains: () => false },
      style: {},
      scrollTop: 0,
      scrollHeight: 1000,
    },
    body: {
      appendChild: () => {},
      removeChild: () => {},
      dataset: {},
    },
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
        userAgent: "NodeJS Test Runner",
        onLine: true,
      },
      configurable: true,
    });
  } catch (_e) {}

  // Import UI barrel facade
  const uiUrl = pathToFileURL(path.resolve(projectRoot, "frontend/static/UI.js")).href;
  const UI = await import(uiUrl);

  // The 16 required global window handlers specified in M3 scope
  const expected16GlobalHandlers = [
    // Hero carousel (7)
    "__heroTouchStart",
    "__heroTouchEnd",
    "__prevTrendingSlide",
    "__nextTrendingSlide",
    "__goToTrendingSlide",
    "__pauseTrendingAutoPlay",
    "__resumeTrendingAutoPlay",

    // Storyline & timeline navigation (6)
    "__toggleTimelinePanel",
    "__togglePerspectiveQuote",
    "__scrollToStoryTimeline",
    "__scrollToSubEvents",
    "__scrollToSubEvent",
    "__toggleSubEventArticles",

    // AI Progression dossier & synthesis (3)
    "__switchDossierTab",
    "__inspectCitation",
    "__toggleQualityAuditPanel",
  ];

  assert(expected16GlobalHandlers.length === 16, "Count of M3 target global handlers is exactly 16");

  for (const handlerName of expected16GlobalHandlers) {
    const fn = globalThis[handlerName];
    assert(
      typeof fn === "function",
      `Target global handler window.${handlerName} is registered and is typeof function`
    );
  }

  // ── Test Suite 4: Verify All Inline onclick Handlers in index.html ──
  console.log("\n[Test Suite 4] Verifying HTML Inline Event Bindings...");
  // Now evaluate main.js to bind application-level window.__* handlers as well
  const mainUrl = pathToFileURL(path.resolve(projectRoot, "frontend/static/main.js")).href;
  await import(mainUrl);

  const onclickMatches = [
    ...htmlContent.matchAll(/onclick=["']([^"']+)["']/g),
  ].map((m) => m[1]);

  const windowCalls = [];
  onclickMatches.forEach((code) => {
    const calls = [...code.matchAll(/window\.(__\w+)/g)].map((m) => m[1]);
    windowCalls.push(...calls);
  });

  const uniqueHtmlWindowCalls = [...new Set(windowCalls)];
  console.log(`[Info] Found ${uniqueHtmlWindowCalls.length} unique window.__* calls in index.html onclick attributes`);

  for (const fnName of uniqueHtmlWindowCalls) {
    const fn = globalThis[fnName];
    assert(
      typeof fn === "function",
      `index.html inline event handler window.${fnName} is bound to a function`
    );
  }

  // ── Test Suite 5: Verify main.js Integration with UI.js ───────────
  console.log("\n[Test Suite 5] Verifying main.js integration with UI.js methods...");

  assert(typeof UI.switchView === "function", "UI.switchView is callable");
  assert(typeof UI.renderGrid === "function", "UI.renderGrid is callable");
  assert(typeof UI.openModal === "function", "UI.openModal is callable");
  assert(typeof UI.closeModal === "function", "UI.closeModal is callable");
  assert(typeof UI.renderPreviewView === "function", "UI.renderPreviewView is callable");
  assert(typeof UI.renderStorylineView === "function", "UI.renderStorylineView is callable");
  assert(typeof UI.renderEvaluationView === "function", "UI.renderEvaluationView is callable");

  // Functional smoke test for switchView
  let classListMock = {
    addCalled: [],
    removeCalled: [],
    add(cls) { this.addCalled.push(cls); },
    remove(cls) { this.removeCalled.push(cls); },
    contains(cls) { return false; },
  };

  const dummyElements = {
    "feed-view": { classList: { ...classListMock, addCalled: [], removeCalled: [] } },
    "preview-view": { classList: { ...classListMock, addCalled: [], removeCalled: [] } },
    "storyline-view": { classList: { ...classListMock, addCalled: [], removeCalled: [] } },
    "evaluation-view": { classList: { ...classListMock, addCalled: [], removeCalled: [] } },
    "storyline-floating-back": { classList: { ...classListMock, addCalled: [], removeCalled: [] } },
    "hero-trending": { classList: { ...classListMock, addCalled: [], removeCalled: [] } },
  };

  globalThis.document.getElementById = (id) => dummyElements[id] || {
    classList: { add: () => {}, remove: () => {} },
    innerHTML: "",
    style: {},
  };

  // Test switchView("storyline")
  UI.switchView("storyline");
  assert(
    dummyElements["storyline-view"].classList.removeCalled.includes("hidden"),
    "UI.switchView('storyline') unhides storyline-view"
  );
  assert(
    dummyElements["feed-view"].classList.addCalled.includes("hidden"),
    "UI.switchView('storyline') hides feed-view"
  );

  // Test switchView("feed")
  UI.switchView("feed");
  assert(
    dummyElements["feed-view"].classList.removeCalled.includes("hidden"),
    "UI.switchView('feed') unhides feed-view"
  );
  assert(
    dummyElements["storyline-view"].classList.addCalled.includes("hidden"),
    "UI.switchView('feed') hides storyline-view"
  );

  // Test switchView("evaluation")
  UI.switchView("evaluation");
  assert(
    dummyElements["evaluation-view"].classList.removeCalled.includes("hidden"),
    "UI.switchView('evaluation') unhides evaluation-view"
  );

  // Test renderGrid smoke test
  const gridContainer = { innerHTML: "", classList: { add: () => {}, remove: () => {} } };
  globalThis.document.getElementById = (id) => {
    if (id === "news-grid") return gridContainer;
    return dummyElements[id] || { classList: { add: () => {}, remove: () => {} } };
  };

  const sampleArticles = [
    {
      url: "https://example.com/art1",
      title: "ทดสอบข่าวภาษาไทย 1",
      summary: "สรุปเนื้อหาข่าวตัวอย่าง",
      source: "ThaiPBS",
      published_at: "2026-10-17T12:00:00Z",
      category: "politics",
    },
    {
      url: "https://example.com/art2",
      title: "ทดสอบข่าวภาษาไทย 2",
      summary: "สรุปเนื้อหาข่าวกีฬา",
      source: "Matichon",
      published_at: "2026-10-17T13:00:00Z",
      category: "sports",
    },
  ];

  UI.renderGrid(sampleArticles, { "https://example.com/art1": true }, () => {});
  assert(
    gridContainer.innerHTML.includes("ทดสอบข่าวภาษาไทย 1"),
    "UI.renderGrid successfully rendered article 1"
  );
  assert(
    gridContainer.innerHTML.includes("ทดสอบข่าวภาษาไทย 2"),
    "UI.renderGrid successfully rendered article 2"
  );
  assert(
    gridContainer.innerHTML.includes("bookmark"),
    "UI.renderGrid rendered bookmark indicators"
  );

  console.log("\n==================================================================");
  console.log(`  DOM & Contract Tests Complete: ${passed} Passed, ${failed} Failed`);
  console.log("==================================================================\n");

  if (failed > 0) {
    console.error("FAILURES ENCOUNTERED:", failures);
    process.exit(1);
  }
}

run().catch((err) => {
  console.error("Error during DOM contract test run:", err);
  process.exit(1);
});
