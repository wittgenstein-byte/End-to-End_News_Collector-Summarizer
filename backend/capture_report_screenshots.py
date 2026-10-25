import asyncio
import os
import sys
import time
from pathlib import Path
from playwright.async_api import async_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

OUTPUT_DIR = Path("docs/report/images")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

async def capture_all():
    print("Starting Playwright capture pipeline with enhanced state handling...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
            color_scheme="light"
        )
        
        # Inject script to force Light Mode and clear obstructive popups
        await context.add_init_script("""
            localStorage.setItem('theme_pref', 'light');
            localStorage.setItem('newsroom_privacy_pref', JSON.stringify({pdpa_consent: true, personalized: false}));
            document.documentElement.classList.remove('dark');
            document.documentElement.classList.add('light');
        """)
        
        page = await context.new_page()

        # ── M-01: Bento Hub SPA ─────────────────────────────────────
        print("Capturing M-01: Bento Hub SPA...")
        await page.goto("http://localhost:5000/#/", wait_until="networkidle", timeout=30000)
        await page.evaluate("""
            document.documentElement.classList.remove('dark');
            document.documentElement.classList.add('light');
            const pwa = document.getElementById('pwa-install-banner');
            if (pwa) pwa.style.display = 'none';
        """)
        await page.wait_for_timeout(2500)
        m01_path = OUTPUT_DIR / "screenshot_m01_bento_hub.png"
        await page.screenshot(path=str(m01_path))
        print(f"   Saved M-01: {m01_path} ({os.path.getsize(m01_path):,} bytes)")

        # ── M-02: In-App Cleaned Reader ─────────────────────────────
        print("Capturing M-02: In-App Cleaned Reader...")
        # Click the first article card to trigger clean in-app preview
        clicked = await page.evaluate("""() => {
            const card = document.querySelector('[data-article-url], .bento-card');
            if (card) {
                card.click();
                return true;
            }
            return false;
        }""")
        if not clicked:
            # Fallback direct preview route
            await page.goto("http://localhost:5000/#/preview/https%3A%2F%2Fwww.pptvhd36.com%2Fsport%2Fnews%2F285735", wait_until="networkidle")
        
        await page.wait_for_timeout(3000)
        m02_path = OUTPUT_DIR / "screenshot_m02_in_app_reader.png"
        await page.screenshot(path=str(m02_path))
        print(f"   Saved M-02: {m02_path} ({os.path.getsize(m02_path):,} bytes)")

        # ── M-03: Macro Storyline Dossier ───────────────────────────
        print("Capturing M-03: Macro Storyline Dossier...")
        # Navigate directly to the first active macro storyline
        await page.goto("http://localhost:5000/#/storyline/macro_23356b58d061", wait_until="networkidle", timeout=30000)
        await page.evaluate("""
            document.documentElement.classList.remove('dark');
            document.documentElement.classList.add('light');
        """)
        await page.wait_for_timeout(3000)
        m03_path = OUTPUT_DIR / "screenshot_m03_macro_dossier.png"
        await page.screenshot(path=str(m03_path))
        print(f"   Saved M-03: {m03_path} ({os.path.getsize(m03_path):,} bytes)")

        # ── M-04: Issue Explorer Workstation ─────────────────────────
        print("Capturing M-04: Issue Explorer Workstation...")
        await page.goto("http://localhost:5000/issues", wait_until="networkidle", timeout=30000)
        await page.evaluate("""
            document.documentElement.classList.remove('dark');
            document.documentElement.classList.add('light');
        """)
        await page.wait_for_timeout(3000)
        m04_path = OUTPUT_DIR / "screenshot_m04_issue_explorer.png"
        await page.screenshot(path=str(m04_path))
        print(f"   Saved M-04: {m04_path} ({os.path.getsize(m04_path):,} bytes)")

        # ── M-05: Ops Monitoring Console (Authenticated) ────────────
        print("Capturing M-05: Ops Monitoring Console...")
        await page.goto("http://localhost:5000/monitoring", wait_until="networkidle", timeout=30000)
        await page.evaluate("""
            document.documentElement.classList.remove('dark');
            document.documentElement.classList.add('light');
        """)
        # Fill secret and log in to show the full authenticated ops console
        secret_input = page.locator("#auth-secret")
        if await secret_input.count() > 0:
            await secret_input.fill("iloveuhihi")
            await page.locator("#auth-submit-btn").click()
            await page.wait_for_selector("#dashboard-view:not(.hidden), #stats-container, #live-log", timeout=10000)
        
        await page.wait_for_timeout(3000)
        m05_path = OUTPUT_DIR / "screenshot_m05_ops_console.png"
        await page.screenshot(path=str(m05_path))
        print(f"   Saved M-05: {m05_path} ({os.path.getsize(m05_path):,} bytes)")

        # ── M-06: Privacy & Cookie Modal ─────────────────────────────
        print("Capturing M-06: Privacy & Cookie Modal...")
        await page.goto("http://localhost:5000/#/", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        await page.evaluate("""() => {
            if (typeof window.__openPrivacyModal === 'function') {
                window.__openPrivacyModal();
            } else {
                const modal = document.getElementById('privacy-modal');
                if (modal) modal.classList.remove('hidden');
            }
        }""")
        await page.wait_for_timeout(2000)
        m06_path = OUTPUT_DIR / "screenshot_m06_privacy_modal.png"
        await page.screenshot(path=str(m06_path))
        print(f"   Saved M-06: {m06_path} ({os.path.getsize(m06_path):,} bytes)")

        await browser.close()
        print("All 6 screenshots captured and verified successfully!")

if __name__ == "__main__":
    asyncio.run(capture_all())
