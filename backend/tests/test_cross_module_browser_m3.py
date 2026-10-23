"""
backend/tests/test_cross_module_browser_m3.py
─────────────────────────────────────────────────────────────────
Milestone 3 Real Browser (Playwright Chromium) Cross-Module Verification
Empirically executes the modular Vanilla JS components in real Chromium engine:
- Shared Storyline Cache Lifecycle & Cross-Module State
- Hero Carousel Autoplay Timer, Touch Swipe, and Slide Controls
- Reader Primary View Switching (feed / preview / storyline / evaluation)
- Digest Window Handlers (__switchDossierTab, __inspectCitation, __toggleQualityAuditPanel)
─────────────────────────────────────────────────────────────────
"""

import socket
import sys
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def run_browser_verification():
    port = find_free_port()
    server = HTTPServer(("127.0.0.1", port), lambda *args, **kwargs: QuietHandler(*args, directory=str(ROOT_DIR), **kwargs))
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"[*] Ephemeral HTTP Server running on http://127.0.0.1:{port}")

    time.sleep(0.5)

    passed = 0
    failed = 0
    results = []

    def log_assert(cond: bool, test_name: str, err_msg: str = ""):
        nonlocal passed, failed
        if cond:
            passed += 1
            results.append((test_name, "PASS", ""))
            print(f"  [PASS] {test_name}")
        else:
            failed += 1
            results.append((test_name, "FAIL", err_msg))
            print(f"  [FAIL] {test_name}: {err_msg}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        console_messages = []
        page.on("console", lambda msg: console_messages.append(f"[{msg.type}] {msg.text}"))

        page_url = f"http://127.0.0.1:{port}/frontend/index.html"
        print(f"[*] Navigating to {page_url} in Chromium...")
        page.goto(page_url, wait_until="domcontentloaded")

        print("\n--- [Browser Suite 1] Shared Storyline Cache Lifecycle ---")
        cache_test_res = page.evaluate("""async () => {
            const UI = await import('/frontend/static/UI.js');
            
            // 1. Initial clear
            UI.clearStorylineCache();
            const initNull = UI.getStorylineCache() === null;

            // 2. Set Storyline Cache
            const testStory = {
                story_id: "macro_test_01",
                title: "การประชุมสภาพิจารณาร่างกฎหมาย",
                category: "politics",
                articles: [{ id: "a1", title: "ข่าว 1", source: "ThaiPBS" }]
            };
            UI.setStorylineCache(testStory);
            const retrieved = UI.getStorylineCache();
            const setMatch = retrieved && retrieved.story_id === "macro_test_01";

            // 3. Mutate
            retrieved.title = "การประชุมสภา (แก้ไข)";
            const mutateMatch = UI.getStorylineCache().title === "การประชุมสภา (แก้ไข)";

            // 4. Overwrite with Sports Story
            const sportsStory = {
                story_id: "sports_test_02",
                title: "ไทยลีก: เมืองทอง พบ บุรีรัมย์",
                category: "sports",
                articles: [{ id: "s1", title: "ไฮไลท์บอลไทย", category: "sports" }]
            };
            UI.setStorylineCache(sportsStory);
            const overwriteMatch = UI.getStorylineCache().story_id === "sports_test_02";

            // 5. Clear again
            UI.clearStorylineCache();
            const clearedNull = UI.getStorylineCache() === null;

            return { initNull, setMatch, mutateMatch, overwriteMatch, clearedNull };
        }""")
        log_assert(cache_test_res["initNull"], "Browser 1.1: clearStorylineCache resets cache to null")
        log_assert(cache_test_res["setMatch"], "Browser 1.2: setStorylineCache / getStorylineCache retains storyData")
        log_assert(cache_test_res["mutateMatch"], "Browser 1.3: Cache mutation dynamically reflects across imports")
        log_assert(cache_test_res["overwriteMatch"], "Browser 1.4: Sequential story cache overwrites cleanly without pollution")
        log_assert(cache_test_res["clearedNull"], "Browser 1.5: Final clearStorylineCache returns cache to null")

        print("\n--- [Browser Suite 2] Hero Carousel & Swipe Detection ---")
        hero_test_res = page.evaluate("""async () => {
            const UI = await import('/frontend/static/UI.js');
            
            const sampleArticles = [
                { title: "พาดหัวข่าว 1", url: "https://news.th/1", headline: "หัวข้อ 1", source: "ThaiPBS", trending_score: 9.8 },
                { title: "พาดหัวข่าว 2", url: "https://news.th/2", headline: "หัวข้อ 2", source: "Bangkok Post", trending_score: 8.5 },
                { title: "พาดหัวข่าว 3", url: "https://news.th/3", headline: "หัวข้อ 3", source: "Matichon", trending_score: 7.2 }
            ];

            // Render Carousel
            UI.renderHeroTrending(sampleArticles);
            const c = document.getElementById("hero-trending");
            const initialVisible = !c.classList.contains("hidden");
            const initialFeatured1 = c.innerText.includes("FEATURED #01");

            // Next Slide
            window.__nextTrendingSlide();
            const featured2 = c.innerText.includes("FEATURED #02");

            // Next Slide again
            window.__nextTrendingSlide();
            const featured3 = c.innerText.includes("FEATURED #03");

            // Wrap forward
            window.__nextTrendingSlide();
            const wrapped1 = c.innerText.includes("FEATURED #01");

            // Wrap backward
            window.__prevTrendingSlide();
            const wrappedPrev3 = c.innerText.includes("FEATURED #03");

            // Direct jump
            window.__goToTrendingSlide(1);
            const jump2 = c.innerText.includes("FEATURED #02");

            // Swipe left simulation (dx = -60, dy = 5 -> next slide)
            UI.handleHeroSwipe(-60, 5);
            const swipeNext3 = c.innerText.includes("FEATURED #03");

            // Swipe right simulation (dx = 60, dy = 5 -> prev slide)
            UI.handleHeroSwipe(60, 5);
            const swipePrev2 = c.innerText.includes("FEATURED #02");

            // Sub-threshold swipe (dx = 25 -> no change)
            UI.handleHeroSwipe(25, 5);
            const subNoChange = c.innerText.includes("FEATURED #02");

            // Vertical dominant scroll (dx = -60, dy = 90 -> no change)
            UI.handleHeroSwipe(-60, 90);
            const vertNoChange = c.innerText.includes("FEATURED #02");

            // Stop autoplay
            UI.stopHeroAutoPlay();

            return {
                initialVisible,
                initialFeatured1,
                featured2,
                featured3,
                wrapped1,
                wrappedPrev3,
                jump2,
                swipeNext3,
                swipePrev2,
                subNoChange,
                vertNoChange
            };
        }""")
        for k, v in hero_test_res.items():
            log_assert(v, f"Browser 2.{k}", f"Assertion for {k} failed")

        print("\n--- [Browser Suite 3] Reader Primary View Switching ---")
        view_test_res = page.evaluate("""async () => {
            const UI = await import('/frontend/static/UI.js');

            const feedEl = document.getElementById("feed-view");
            const previewEl = document.getElementById("preview-view");
            const storyEl = document.getElementById("storyline-view");
            const evalEl = document.getElementById("evaluation-view");

            // 1. Switch to feed
            UI.switchView("feed");
            const feedOk = !feedEl.classList.contains("hidden") &&
                           previewEl.classList.contains("hidden") &&
                           storyEl.classList.contains("hidden") &&
                           evalEl.classList.contains("hidden");

            // 2. Switch to preview
            UI.switchView("preview");
            const previewOk = feedEl.classList.contains("hidden") &&
                              !previewEl.classList.contains("hidden") &&
                              storyEl.classList.contains("hidden") &&
                              evalEl.classList.contains("hidden");

            // 3. Switch to storyline
            UI.switchView("storyline");
            const storyOk = feedEl.classList.contains("hidden") &&
                            previewEl.classList.contains("hidden") &&
                            !storyEl.classList.contains("hidden") &&
                            evalEl.classList.contains("hidden");

            // 4. Switch to evaluation
            UI.switchView("evaluation");
            const evalOk = feedEl.classList.contains("hidden") &&
                           previewEl.classList.contains("hidden") &&
                           storyEl.classList.contains("hidden") &&
                           !evalEl.classList.contains("hidden");

            // 5. Back to feed
            UI.switchView("feed");
            const returnFeedOk = !feedEl.classList.contains("hidden");

            // 6. Unknown view fallback
            UI.switchView("invalid-view-name");
            const fallbackOk = !feedEl.classList.contains("hidden") && previewEl.classList.contains("hidden");

            return { feedOk, previewOk, storyOk, evalOk, returnFeedOk, fallbackOk };
        }""")
        for k, v in view_test_res.items():
            log_assert(v, f"Browser 3.{k}", f"Assertion for {k} failed")

        print("\n--- [Browser Suite 4] Digest Window Handlers ---")
        digest_test_res = page.evaluate("""async () => {
            const UI = await import('/frontend/static/UI.js');

            // Check handlers exist on window
            const hasSwitchTab = typeof window.__switchDossierTab === "function";
            const hasInspectCitation = typeof window.__inspectCitation === "function";
            const hasToggleAudit = typeof window.__toggleQualityAuditPanel === "function";

            // Safe execution of callbacks with falsy / non-existent IDs
            let switchTabSafe = true;
            try {
                window.__switchDossierTab("non-existent");
                window.__switchDossierTab(null);
            } catch (e) {
                switchTabSafe = false;
            }

            let inspectCitationSafe = true;
            try {
                window.__inspectCitation("non-existent-art");
                window.__inspectCitation(null);
                window.__inspectCitation("");
            } catch (e) {
                inspectCitationSafe = false;
            }

            let toggleAuditSafe = true;
            try {
                window.__toggleQualityAuditPanel();
            } catch (e) {
                toggleAuditSafe = false;
            }

            // Test real citation pulse in DOM
            const testDiv = document.createElement("div");
            testDiv.id = "article-evidence-art_browser_01";
            testDiv.setAttribute("data-evidence-id", "art_browser_01");
            document.body.appendChild(testDiv);

            window.__inspectCitation("ART_BROWSER_01");
            const pulseApplied = testDiv.classList.contains("citation-highlight-pulse");

            return {
                hasSwitchTab,
                hasInspectCitation,
                hasToggleAudit,
                switchTabSafe,
                inspectCitationSafe,
                toggleAuditSafe,
                pulseApplied
            };
        }""")
        for k, v in digest_test_res.items():
            log_assert(v, f"Browser 4.{k}", f"Assertion for {k} failed")

        print("\n--- [Browser Suite 5] Real Browser Adversarial Boundary Challenge ---")
        adv_test_res = page.evaluate("""async () => {
            const UI = await import('/frontend/static/UI.js');

            // 5.1 Check if __goToTrendingSlide(null) throws in real browser
            let nullSlideThrew = false;
            let nullSlideError = "";
            try {
                window.__goToTrendingSlide(null);
            } catch (e) {
                nullSlideThrew = true;
                nullSlideError = e.message;
            }

            // 5.2 Check if selector injection in __inspectCitation throws in real browser
            let selectorInjectionThrew = false;
            let selectorError = "";
            try {
                window.__inspectCitation('art"invalid][selector');
            } catch (e) {
                selectorInjectionThrew = true;
                selectorError = e.message;
            }

            return {
                nullSlideThrew,
                nullSlideError,
                selectorInjectionThrew,
                selectorError
            };
        }""")

        print(f"  [Adversarial Probe 5.1] __goToTrendingSlide(null) threw in Chromium: {adv_test_res['nullSlideThrew']} (Error: {adv_test_res['nullSlideError']})")
        print(f"  [Adversarial Probe 5.2] __inspectCitation('art\"invalid][selector') threw in Chromium: {adv_test_res['selectorInjectionThrew']} (Error: {adv_test_res['selectorError']})")

        browser.close()

    server.shutdown()
    print("\n==================================================================")
    print(f"  Real Chromium Browser Suite Complete: {passed} Passed, {failed} Failed")
    print("==================================================================")
    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    run_browser_verification()
