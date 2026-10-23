/**
 * backend/tests/test_config_resolution_adversarial.mjs
 * ─────────────────────────────────────────────────────────────────
 * Adversarial Empirical Test Harness for Client Config Resolution:
 * Tests edge cases, hierarchy precedence, security restrictions,
 * and port mapping across 30+ adversarial scenarios.
 * ─────────────────────────────────────────────────────────────────
 */

import assert from "node:assert";
import { resolveApiBase, resolveSocketUrl, resolveImageUrl, getSentimentConfig, getCategoryById } from "../../frontend/static/config.js";

console.log("🚀 Starting Node.js Adversarial Client Config Test Suite...\n");

let passed = 0;
let failed = 0;

function runTest(name, fn) {
  try {
    fn();
    console.log(`  ✅ PASS: ${name}`);
    passed++;
  } catch (err) {
    console.error(`  ❌ FAIL: ${name}`);
    console.error(`     Error: ${err.message}`);
    failed++;
  }
}

// ── Test Group 1: Default / Non-Browser Environment ───────────────
console.log("--- Group 1: Environment Fallbacks ---");

runTest("Default in Node without options returns localhost:5000", () => {
  const result = resolveApiBase();
  assert.strictEqual(result, "http://localhost:5000");
});

runTest("Empty options object returns localhost:5000", () => {
  const result = resolveApiBase({});
  assert.strictEqual(result, "http://localhost:5000");
});

runTest("Options with win=null returns localhost:5000", () => {
  const result = resolveApiBase({ win: null });
  assert.strictEqual(result, "http://localhost:5000");
});

// ── Test Group 2: Tier 1 Runtime Injection ────────────────────────
console.log("\n--- Group 2: Tier 1 Runtime Injection ---");

runTest("Tier 1: clean API_BASE URL", () => {
  const win = { __NEWSROOM_CONFIG__: { API_BASE: "https://api.prod.example.com" } };
  assert.strictEqual(resolveApiBase({ win }), "https://api.prod.example.com");
});

runTest("Tier 1: strips multiple trailing slashes", () => {
  const win = { __NEWSROOM_CONFIG__: { API_BASE: "https://api.prod.example.com///" } };
  assert.strictEqual(resolveApiBase({ win }), "https://api.prod.example.com");
});

runTest("Tier 1: trims whitespace around URL and trailing slashes", () => {
  const win = { __NEWSROOM_CONFIG__: { API_BASE: "  https://api.prod.example.com/api//  " } };
  assert.strictEqual(resolveApiBase({ win }), "https://api.prod.example.com/api");
});

runTest("Tier 1: empty string falls through to lower tiers", () => {
  const win = {
    __NEWSROOM_CONFIG__: { API_BASE: "   " },
    location: { hostname: "localhost", port: "5173", protocol: "http:" }
  };
  assert.strictEqual(resolveApiBase({ win }), "http://localhost:5000");
});

runTest("Tier 1: non-string value falls through to lower tiers", () => {
  const win = {
    __NEWSROOM_CONFIG__: { API_BASE: 12345 },
    location: { hostname: "localhost", port: "3000", protocol: "http:" }
  };
  assert.strictEqual(resolveApiBase({ win }), "http://localhost:5000");
});

// ── Test Group 3: Tier 2 Build-Time Environment ───────────────────
console.log("\n--- Group 3: Tier 2 Build-Time Environment ---");

runTest("Tier 2: win.__ENV__.VITE_API_URL clean", () => {
  const win = {
    __ENV__: { VITE_API_URL: "https://vite-api.example.com" },
    location: { hostname: "localhost", port: "5173", protocol: "http:" }
  };
  assert.strictEqual(resolveApiBase({ win }), "https://vite-api.example.com");
});

runTest("Tier 2: win.__ENV__.VITE_API_URL strips trailing slashes", () => {
  const win = {
    __ENV__: { VITE_API_URL: "https://vite-api.example.com///" },
    location: { hostname: "localhost", port: "5173", protocol: "http:" }
  };
  assert.strictEqual(resolveApiBase({ win }), "https://vite-api.example.com");
});

runTest("Tier 2: empty VITE_API_URL falls through", () => {
  const win = {
    __ENV__: { VITE_API_URL: "  " },
    location: { hostname: "localhost", port: "8080", protocol: "http:" }
  };
  assert.strictEqual(resolveApiBase({ win }), "http://localhost:5000");
});

// ── Test Group 4: Tier 3 Query Param & LocalStorage ───────────────
console.log("\n--- Group 4: Tier 3 Query Param & LocalStorage ---");

runTest("Tier 3: URL query param ?api= overrides dev port and saves to localStorage", () => {
  let savedKey = null;
  let savedVal = null;
  const mockStorage = {
    getItem: () => null,
    setItem: (k, v) => { savedKey = k; savedVal = v; }
  };
  const win = {
    location: { search: "?api=https://qa-backend.internal:8000///", hostname: "localhost", port: "5173", protocol: "http:" },
    localStorage: mockStorage
  };
  assert.strictEqual(resolveApiBase({ win }), "https://qa-backend.internal:8000");
  assert.strictEqual(savedKey, "newsroom_api_base");
  assert.strictEqual(savedVal, "https://qa-backend.internal:8000");
});

runTest("Tier 3: localStorage fallback when query param is absent", () => {
  const mockStorage = {
    getItem: (k) => k === "newsroom_api_base" ? "https://stored-backend:9000///" : null
  };
  const win = {
    location: { search: "", hostname: "localhost", port: "5173", protocol: "http:" },
    localStorage: mockStorage
  };
  assert.strictEqual(resolveApiBase({ win }), "https://stored-backend:9000");
});

runTest("Tier 3: localStorage throwing SecurityError (e.g. Safari Private) falls through gracefully", () => {
  const mockStorage = {
    getItem: () => { throw new Error("SecurityError: Access is denied"); },
    setItem: () => { throw new Error("SecurityError: Access is denied"); }
  };
  const win = {
    location: { search: "?api=https://safe-api.org/", hostname: "localhost", port: "5173", protocol: "http:" },
    localStorage: mockStorage
  };
  // Should still return query param without throwing!
  assert.strictEqual(resolveApiBase({ win }), "https://safe-api.org");
});

// ── Test Group 5: Tier 4 Dynamic Dev Port Auto-Mapping ────────────
console.log("\n--- Group 5: Tier 4 Dynamic Detection & Dev Port Auto-Mapping ---");

const devPortCases = [
  { host: "localhost", port: "5173", expected: "http://localhost:5000", desc: "Vite dev port 5173" },
  { host: "localhost", port: "3000", expected: "http://localhost:5000", desc: "React/Next dev port 3000" },
  { host: "127.0.0.1", port: "5500", expected: "http://127.0.0.1:5000", desc: "Live Server 127.0.0.1:5500" },
  { host: "localhost", port: "8080", expected: "http://localhost:5000", desc: "Vue/Webpack dev port 8080" },
  { host: "localhost", port: "4173", expected: "http://localhost:5000", desc: "Vite preview port 4173" },
  { host: "0.0.0.0", port: "8000", expected: "http://0.0.0.0:5000", desc: "Python local port 8000 on 0.0.0.0" },
  { host: "[::1]", port: "5001", expected: "http://[::1]:5000", desc: "IPv6 loopback dev port 5001" },
  { host: "localhost", port: "9999", expected: "http://localhost:5000", desc: "Arbitrary local dev port 9999" },
  { host: "localhost", port: "5000", origin: "http://localhost:5000", expected: "http://localhost:5000", desc: "Same-origin backend port 5000" },
  { host: "localhost", port: "", expected: "http://localhost:5000", desc: "Localhost reverse proxy with no port" }
];

for (const tc of devPortCases) {
  runTest(`Tier 4 dev port: ${tc.desc}`, () => {
    const win = {
      location: {
        hostname: tc.host,
        port: tc.port,
        protocol: "http:",
        origin: tc.origin || `http://${tc.host}:${tc.port}`
      }
    };
    assert.strictEqual(resolveApiBase({ win }), tc.expected);
  });
}

runTest("Tier 4 production domain: returns location.origin", () => {
  const win = {
    location: {
      hostname: "newsroom.live",
      port: "",
      protocol: "https:",
      origin: "https://newsroom.live"
    }
  };
  assert.strictEqual(resolveApiBase({ win }), "https://newsroom.live");
});

runTest("Tier 4 production domain with custom port: returns location.origin", () => {
  const win = {
    location: {
      hostname: "internal.company.net",
      port: "8443",
      protocol: "https:",
      origin: "https://internal.company.net:8443"
    }
  };
  assert.strictEqual(resolveApiBase({ win }), "https://internal.company.net:8443");
});

// ── Test Group 6: Socket URL Resolution ───────────────────────────
console.log("\n--- Group 6: Socket URL Resolution ---");

runTest("resolveSocketUrl: uses __NEWSROOM_CONFIG__.SOCKET_URL", () => {
  const win = {
    __NEWSROOM_CONFIG__: { SOCKET_URL: "https://ws.prod.com///" }
  };
  assert.strictEqual(resolveSocketUrl(null, { win }), "https://ws.prod.com");
});

runTest("resolveSocketUrl: uses __ENV__.VITE_SOCKET_URL", () => {
  const win = {
    __ENV__: { VITE_SOCKET_URL: "https://vite-ws.example.com///" }
  };
  assert.strictEqual(resolveSocketUrl(null, { win }), "https://vite-ws.example.com");
});

runTest("resolveSocketUrl: uses localStorage newsroom_socket_url", () => {
  const mockStorage = {
    getItem: (k) => k === "newsroom_socket_url" ? "https://stored-ws.org/" : null
  };
  const win = { localStorage: mockStorage };
  assert.strictEqual(resolveSocketUrl(null, { win }), "https://stored-ws.org");
});

runTest("resolveSocketUrl: falls back to explicit apiBase parameter", () => {
  const win = {};
  assert.strictEqual(resolveSocketUrl("https://api.explicit.com", { win }), "https://api.explicit.com");
});

runTest("resolveSocketUrl: falls back to resolveApiBase when no custom socket url", () => {
  const win = {
    location: { hostname: "localhost", port: "5173", protocol: "http:" }
  };
  assert.strictEqual(resolveSocketUrl(null, { win }), "http://localhost:5000");
});

// ── Test Group 7: resolveImageUrl Proxy Resolution ────────────────
console.log("\n--- Group 7: resolveImageUrl Resolution ---");

runTest("resolveImageUrl: prefixes /api/image relative path", () => {
  const url = "/api/image?url=https%3A%2F%2Fthestandard.co%2Fimg.jpg";
  const result = resolveImageUrl(url, "http://localhost:5000");
  assert.strictEqual(result, "http://localhost:5000/api/image?url=https%3A%2F%2Fthestandard.co%2Fimg.jpg");
});

runTest("resolveImageUrl: handles missing leading slash 'api/image'", () => {
  const url = "api/image?url=https%3A%2F%2Fthestandard.co%2Fimg.jpg";
  const result = resolveImageUrl(url, "http://localhost:5000");
  assert.strictEqual(result, "http://localhost:5000/api/image?url=https%3A%2F%2Fthestandard.co%2Fimg.jpg");
});

runTest("resolveImageUrl: preserves absolute external URLs untouched", () => {
  const external = "https://images.thaipbs.or.th/2026/08/news.jpg";
  assert.strictEqual(resolveImageUrl(external, "http://localhost:5000"), external);
});

runTest("resolveImageUrl: empty string or non-string returns empty string", () => {
  assert.strictEqual(resolveImageUrl(""), "");
  assert.strictEqual(resolveImageUrl("   "), "");
  assert.strictEqual(resolveImageUrl(null), "");
  assert.strictEqual(resolveImageUrl(undefined), "");
  assert.strictEqual(resolveImageUrl(12345), "");
  assert.strictEqual(resolveImageUrl({}), "");
});

// ── Test Group 8: Sentiment & Taxonomy Configurations ─────────────
console.log("\n--- Group 8: Sentiment and Categories Taxonomy ---");

runTest("getSentimentConfig matches positive, negative, neutral", () => {
  assert.strictEqual(getSentimentConfig("positive")?.emoji, "😊");
  assert.strictEqual(getSentimentConfig("เชิงบวก")?.emoji, "😊");
  assert.strictEqual(getSentimentConfig("negative")?.emoji, "⚠️");
  assert.strictEqual(getSentimentConfig("neutral")?.emoji, "😐");
  assert.strictEqual(getSentimentConfig("unknown"), null);
  assert.strictEqual(getSentimentConfig(null), null);
});

runTest("getCategoryById finds known categories and defaults to 'all'", () => {
  assert.strictEqual(getCategoryById("politics")?.id, "politics");
  assert.strictEqual(getCategoryById("sports")?.id, "sports");
  assert.strictEqual(getCategoryById("unknown_category")?.id, "all");
});

// ── Summary ───────────────────────────────────────────────────────
console.log(`\n====================================================`);
console.log(`Adversarial JS Test Results: ${passed} passed, ${failed} failed`);
console.log(`====================================================`);

if (failed > 0) {
  process.exit(1);
} else {
  process.exit(0);
}
