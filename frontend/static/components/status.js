/**
 * frontend/static/components/status.js
 * ─────────────────────────────────────────────────────────────────
 * System Status, Telemetry & User Feedback Notifications
 *
 * Responsibilities:
 * - Real-time WebSocket connection badge indicator
 * - Scraper ingestion telemetry and timestamp counters
 * - Breaking news marquee ticker track
 * - Toast notification popups
 * - Floating live-update pill banner
 * - Offline network status bar
 * - Progressive Web App (PWA) installation prompts
 * - Project evaluation feedback prompt modal toggles
 * ─────────────────────────────────────────────────────────────────
 */

import { esc } from "../utils/common.js";
import { FEEDBACK_COMPLETED_KEY } from "../config.js";

// ── WebSocket Connection Badge ─────────────────────────────────────

export function setWsBadge(connected) {
  const dot = document.getElementById("ws-dot");
  const label = document.getElementById("ws-label");
  if (!dot || !label) return;
  if (connected) {
    dot.className = "w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse";
    label.className = "text-[10px] font-mono font-bold tracking-widest text-green-400 uppercase";
    label.textContent = "LIVE";
  } else {
    dot.className = "w-1.5 h-1.5 rounded-full bg-error";
    label.className = "text-[10px] font-mono font-bold tracking-widest text-error uppercase";
    label.textContent = "OFFLINE";
  }
}

export function updateStatus(connected) {
  return setWsBadge(connected);
}

// ── Stats Telemetry Bar ───────────────────────────────────────────

export function updateStats(stats = {}) {
  if (!stats || typeof stats !== "object") return;
  const { total, newCount, updated } = stats;
  const totalEl = document.getElementById("stat-total");
  const newEl = document.getElementById("stat-new");
  const updatedEl = document.getElementById("updated-bar");
  if (total !== undefined && totalEl) totalEl.textContent = total;
  if (newCount !== undefined && newEl) newEl.textContent = newCount;
  if (updated !== undefined && updatedEl) updatedEl.textContent = `อัปเดต: ${updated}`;
}

// ── Breaking News Ticker ──────────────────────────────────────────

export function updateTicker(titles) {
  if (!titles || !titles.length) return;
  const doubled = [...titles, ...titles];
  const track = document.getElementById("ticker-track");
  if (!track) return;
  track.innerHTML = doubled.map(t => `
    <div class="flex gap-6 items-center px-3 shrink-0">
      <span class="text-[11px] font-normal tracking-wide text-white/90">${esc(t)}</span>
      <span class="text-white/30 text-[10px]">•</span>
    </div>
  `).join("");
}

// ── Toast Notifications ───────────────────────────────────────────

export function showToast(msg) {
  const toast = document.getElementById("toast");
  const msgEl = document.getElementById("toast-msg");
  if (!toast || !msgEl) return;
  msgEl.textContent = msg;
  toast.classList.remove("translate-y-full", "opacity-0");
  toast.classList.add("translate-y-0", "opacity-100");
  setTimeout(() => hideToast(), 3000);
}

export function hideToast() {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.classList.remove("translate-y-0", "opacity-100");
  toast.classList.add("translate-y-full", "opacity-0");
}

// ── Floating Live Update Indicator ────────────────────────────────

export function showFloatingUpdateBanner(count) {
  const indicator = document.getElementById("new-articles-indicator");
  const countText = document.getElementById("new-articles-count-text");
  if (!indicator) return;

  if (countText) {
    countText.textContent = count && count > 0
      ? `มีข่าวใหม่ ${count} บทความ • คลิกเพื่ออัปเดต`
      : `มีข่าวใหม่เข้ามา • คลิกเพื่ออัปเดต`;
  }

  indicator.classList.remove("-translate-y-16", "opacity-0", "pointer-events-none");
  indicator.classList.add("translate-y-0", "opacity-100", "pointer-events-auto");
}

export function hideFloatingUpdateBanner() {
  const indicator = document.getElementById("new-articles-indicator");
  if (!indicator) return;

  indicator.classList.remove("translate-y-0", "opacity-100", "pointer-events-auto");
  indicator.classList.add("-translate-y-16", "opacity-0", "pointer-events-none");
}

// ── Offline & PWA Banner Helpers ──────────────────────────────────

export function showOfflineStatus(isOffline) {
  const bar = document.getElementById("offline-bar");
  if (!bar) return;
  if (isOffline) {
    bar.classList.remove("-translate-y-full");
    bar.classList.add("translate-y-0");
  } else {
    bar.classList.remove("translate-y-0");
    bar.classList.add("-translate-y-full");
  }
}

export function showPwaInstallBanner(onInstall) {
  const banner = document.getElementById("pwa-install-banner");
  const installBtn = document.getElementById("pwa-install-btn");
  if (!banner) return;
  if (installBtn && onInstall) installBtn.onclick = onInstall;
  banner.classList.remove("translate-y-32", "opacity-0", "pointer-events-none");
  banner.classList.add("translate-y-0", "opacity-100", "pointer-events-auto");
}

export function hidePwaInstallBanner() {
  const banner = document.getElementById("pwa-install-banner");
  if (!banner) return;
  banner.classList.remove("translate-y-0", "opacity-100", "pointer-events-auto");
  banner.classList.add("translate-y-32", "opacity-0", "pointer-events-none");
}

// ── Feedback Prompt Modal ─────────────────────────────────────────

export function showFeedbackPromptModal() {
  if (typeof localStorage !== "undefined" && localStorage.getItem(FEEDBACK_COMPLETED_KEY) === "true") return;
  const modal = document.getElementById("feedback-prompt-modal");
  if (!modal) return;
  modal.classList.remove("hidden");
  modal.classList.add("flex");
}

export function hideFeedbackPromptModal() {
  const modal = document.getElementById("feedback-prompt-modal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.classList.remove("flex");
}
