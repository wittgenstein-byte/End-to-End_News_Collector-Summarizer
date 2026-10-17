/**
 * backend/tests/test_client_communication.mjs
 * ─────────────────────────────────────────────────────────────────
 * Comprehensive Automated Verification Suite for Milestone 2:
 * - socket.js Exports & Connection Contract
 * - socket.js Reconnection Engine (Exponential Backoff, Jitter, Telemetry)
 * - socket.js Dual-Mapping (new_articles / news_batch, init / stats_update)
 * - socket.js Memory Leak Prevention & Error Isolation
 * - socket.js Browser Remote Action Emitters & Listeners
 * - api.js Standardized ApiError Model & Classification
 * - api.js Dynamic Base URL & Image Proxy Normalization
 * - api.js Offline Detection & AbortController Timeout Handling
 * - api.js Backward-Compatible Bridge Re-exports
 * - Zero DOM Invariant & Strict Line Count Guardrails (<800 LOC)
 * ─────────────────────────────────────────────────────────────────
 */

import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  ConnectionState,
  initSocket,
  connectSocket,
  disconnectSocket,
  getSocket,
  isConnected,
  getConnectionState,
  getTelemetry,
  resetTelemetry,
  onConnectionChange,
  onNewsBatch,
  onStatsUpdate,
  onTrendingUpdate,
  onMonitoringLog,
  onBrowserLoading,
  onBrowserSnapshot,
  onBrowserTabOpened,
  emitBrowserOpenTab,
  emitBrowserCloseTab,
  emitBrowserNavigate,
  emitBrowserOpenAndNavigate,
  emitBrowserGoBack,
  emitBrowserGoForward,
  emitBrowserRefresh,
  emitSocketEvent,
  on,
  createSocket as socketCreateSocket,
} from "../../frontend/static/socket.js";

import {
  ApiError,
  DEFAULT_TIMEOUT_MS,
  request,
  normalizeArticle,
  normalizeStory,
  fetchNews,
  fetchArticleContent,
  fetchCategories,
  fetchSources,
  fetchTrendingNews,
  fetchTrendingStories,
  fetchStoryDetail,
  fetchMacroEventDetail,
  fetchStorylineSynthesis,
  triggerStorylineSynthesis,
  recordEngagement,
  summarizeArticle,
  fetchApiHealth,
  fetchStories,
  fetchTrendingMacroEvents,
  createSocket as apiCreateSocket,
  getSocket as apiGetSocket,
} from "../../frontend/static/api.js";

import { resolveApiBase, resolveImageUrl } from "../../frontend/static/config.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../..");

console.log("🚀 Starting Milestone 2 Client Communication Automated Verification Suite...\n");

let passed = 0;
let failed = 0;

async function test(name, fn) {
  try {
    await fn();
    console.log(`  ✅ PASS: ${name}`);
    passed++;
  } catch (err) {
    console.error(`  ❌ FAIL: ${name}`);
    console.error(`     Error: ${err.message}\n${err.stack}`);
    failed++;
  }
}

// ── Mock Helpers for Socket.IO Testing ─────────────────────────────
class MockSocketIO {
  constructor(url, options) {
    this.url = url;
    this.options = options;
    this.connected = false;
    this.id = "mock-socket-" + Math.random().toString(36).slice(2, 8);
    this.eventHandlers = new Map();
    this.emittedEvents = [];

    // Mock Socket.IO Manager (socket.io)
    this.io = {
      eventHandlers: new Map(),
      on: (event, handler) => {
        if (!this.io.eventHandlers.has(event)) {
          this.io.eventHandlers.set(event, []);
        }
        this.io.eventHandlers.get(event).push(handler);
      },
      emit: (event, ...args) => {
        const handlers = this.io.eventHandlers.get(event) || [];
        for (const h of handlers) h(...args);
      },
    };
  }

  on(event, handler) {
    if (!this.eventHandlers.has(event)) {
      this.eventHandlers.set(event, []);
    }
    this.eventHandlers.get(event).push(handler);
  }

  emit(event, payload) {
    this.emittedEvents.push({ event, payload });
  }

  // Test helpers to trigger server events
  simulateServerEvent(event, data) {
    const handlers = this.eventHandlers.get(event) || [];
    for (const h of handlers) h(data);
  }

  simulateConnect() {
    this.connected = true;
    this.simulateServerEvent("connect");
  }

  simulateDisconnect(reason = "transport close") {
    this.connected = false;
    this.simulateServerEvent("disconnect", reason);
  }

  simulateConnectError(err = new Error("Connection failed")) {
    this.simulateServerEvent("connect_error", err);
  }

  connect() {
    this.simulateConnect();
  }

  disconnect() {
    this.connected = false;
    this.simulateDisconnect("io client disconnect");
  }
}

// ── Test Group 1: Module Exports & Contracts ───────────────────────
console.log("--- Group 1: Module Exports & Contract Integrity ---");

await test("socket.js exports all required constants, functions, and listeners", () => {
  assert.ok(ConnectionState);
  assert.strictEqual(ConnectionState.DISCONNECTED, "DISCONNECTED");
  assert.strictEqual(ConnectionState.CONNECTING, "CONNECTING");
  assert.strictEqual(ConnectionState.CONNECTED, "CONNECTED");
  assert.strictEqual(ConnectionState.RECONNECTING, "RECONNECTING");
  assert.strictEqual(ConnectionState.ERROR, "ERROR");

  assert.strictEqual(typeof initSocket, "function");
  assert.strictEqual(typeof connectSocket, "function");
  assert.strictEqual(typeof disconnectSocket, "function");
  assert.strictEqual(typeof getSocket, "function");
  assert.strictEqual(typeof isConnected, "function");
  assert.strictEqual(typeof getConnectionState, "function");
  assert.strictEqual(typeof getTelemetry, "function");
  assert.strictEqual(typeof resetTelemetry, "function");

  assert.strictEqual(typeof onConnectionChange, "function");
  assert.strictEqual(typeof onNewsBatch, "function");
  assert.strictEqual(typeof onStatsUpdate, "function");
  assert.strictEqual(typeof onTrendingUpdate, "function");
  assert.strictEqual(typeof onMonitoringLog, "function");
  assert.strictEqual(typeof onBrowserLoading, "function");
  assert.strictEqual(typeof onBrowserSnapshot, "function");
  assert.strictEqual(typeof onBrowserTabOpened, "function");

  assert.strictEqual(typeof emitBrowserOpenTab, "function");
  assert.strictEqual(typeof emitBrowserCloseTab, "function");
  assert.strictEqual(typeof emitBrowserNavigate, "function");
  assert.strictEqual(typeof emitBrowserOpenAndNavigate, "function");
  assert.strictEqual(typeof emitBrowserGoBack, "function");
  assert.strictEqual(typeof emitBrowserGoForward, "function");
  assert.strictEqual(typeof emitBrowserRefresh, "function");
  assert.strictEqual(typeof emitSocketEvent, "function");

  assert.strictEqual(typeof on, "function");
  assert.strictEqual(typeof socketCreateSocket, "function");
});

await test("api.js exports all required REST methods, normalizers, and ApiError", () => {
  assert.ok(ApiError);
  assert.strictEqual(typeof DEFAULT_TIMEOUT_MS, "number");
  assert.strictEqual(typeof request, "function");
  assert.strictEqual(typeof normalizeArticle, "function");
  assert.strictEqual(typeof normalizeStory, "function");

  assert.strictEqual(typeof fetchNews, "function");
  assert.strictEqual(typeof fetchArticleContent, "function");
  assert.strictEqual(typeof fetchCategories, "function");
  assert.strictEqual(typeof fetchSources, "function");
  assert.strictEqual(typeof fetchTrendingNews, "function");
  assert.strictEqual(typeof fetchTrendingStories, "function");
  assert.strictEqual(typeof fetchStoryDetail, "function");
  assert.strictEqual(typeof fetchMacroEventDetail, "function");
  assert.strictEqual(typeof fetchStorylineSynthesis, "function");
  assert.strictEqual(typeof triggerStorylineSynthesis, "function");
  assert.strictEqual(typeof recordEngagement, "function");
  assert.strictEqual(typeof summarizeArticle, "function");
  assert.strictEqual(typeof fetchApiHealth, "function");

  // Deprecated backward-compatible exports
  assert.strictEqual(typeof fetchStories, "function");
  assert.strictEqual(typeof fetchTrendingMacroEvents, "function");
  assert.strictEqual(typeof apiCreateSocket, "function");
  assert.strictEqual(typeof apiGetSocket, "function");
});

// ── Test Group 2: ApiError Class Specification ─────────────────────
console.log("\n--- Group 2: ApiError Class Specification ---");

await test("ApiError inherits from Error and encapsulates all diagnostic fields", () => {
  const err = new ApiError({
    message: "Resource not found",
    status: 404,
    statusText: "Not Found",
    url: "http://localhost:5000/api/stories/st_999",
    responseBody: { detail: "Story not found" },
    isOffline: false,
    isTimeout: false,
  });

  assert.ok(err instanceof Error);
  assert.strictEqual(err.name, "ApiError");
  assert.strictEqual(err.message, "Resource not found");
  assert.strictEqual(err.status, 404);
  assert.strictEqual(err.statusText, "Not Found");
  assert.strictEqual(err.url, "http://localhost:5000/api/stories/st_999");
  assert.deepStrictEqual(err.responseBody, { detail: "Story not found" });
  assert.strictEqual(err.isClientError, true);
  assert.strictEqual(err.isServerError, false);
  assert.strictEqual(err.isOffline, false);
  assert.strictEqual(err.isTimeout, false);
  assert.ok(typeof err.timestamp === "string");
});

await test("ApiError correctly classifies 5xx server errors", () => {
  const err = new ApiError({
    status: 502,
    statusText: "Bad Gateway",
    url: "http://localhost:5000/api/news",
  });

  assert.strictEqual(err.isClientError, false);
  assert.strictEqual(err.isServerError, true);
});

await test("ApiError provides meaningful default messages for offline and timeout", () => {
  const offlineErr = new ApiError({ isOffline: true });
  assert.ok(offlineErr.message.includes("Offline") || offlineErr.message.includes("อินเทอร์เน็ต"));

  const timeoutErr = new ApiError({ isTimeout: true, url: "http://example.com/api" });
  assert.ok(timeoutErr.message.includes("Timeout") || timeoutErr.message.includes("หมดเวลา"));
});

await test("ApiError.toJSON() returns complete structured telemetry payload", () => {
  const err = new ApiError({
    message: "Server exploded",
    status: 500,
    statusText: "Internal Server Error",
    url: "http://localhost:5000/api/fail",
    responseBody: { error: "DB deadlock" },
    isOffline: false,
    isTimeout: false,
  });

  const json = err.toJSON();
  assert.strictEqual(json.name, "ApiError");
  assert.strictEqual(json.status, 500);
  assert.strictEqual(json.statusText, "Internal Server Error");
  assert.strictEqual(json.url, "http://localhost:5000/api/fail");
  assert.deepStrictEqual(json.responseBody, { error: "DB deadlock" });
});

// ── Test Group 3: Data Normalization Layer in api.js ────────────────
console.log("\n--- Group 3: Data Normalization Layer ---");

await test("normalizeArticle resolves relative /api/image proxy paths using dynamic API base", () => {
  const raw = {
    url: "https://thestandard.co/economy/123",
    title: "  เศรษฐกิจไทยปี 2026  ",
    source: "The Standard",
    image_url: "/api/image?url=https%3A%2F%2Fthestandard.co%2Fimg.jpg",
    category: "economy",
  };

  const norm = normalizeArticle(raw);
  assert.strictEqual(norm.url, "https://thestandard.co/economy/123");
  assert.strictEqual(norm.title, "เศรษฐกิจไทยปี 2026");
  assert.ok(norm.image_url.startsWith("http://localhost:5000/api/image?url="));
});

await test("normalizeArticle preserves external HTTPS image URLs without proxy prefix", () => {
  const raw = {
    url: "https://thaipbs.or.th/news/456",
    title: "ข่าวด่วน",
    source: "ThaiPBS",
    image_url: "https://images.thaipbs.or.th/2026/img.jpg",
    category: "politics",
  };

  const norm = normalizeArticle(raw);
  assert.strictEqual(norm.image_url, "https://images.thaipbs.or.th/2026/img.jpg");
});

await test("normalizeArticle applies robust default fallbacks for missing/invalid fields", () => {
  assert.strictEqual(normalizeArticle(null), null);
  assert.strictEqual(normalizeArticle(undefined), null);
  assert.strictEqual(normalizeArticle("string"), null);

  const sparse = normalizeArticle({});
  assert.strictEqual(sparse.url, "");
  assert.strictEqual(sparse.title, "");
  assert.strictEqual(sparse.source, "สำนักข่าว");
  assert.strictEqual(sparse.category, "all");
  assert.strictEqual(sparse.image_url, "");
});

await test("normalizeStory normalizes lead image and recursively normalizes member articles and children", () => {
  const rawCluster = {
    story_id: "st_100",
    title: "มหกรรมกีฬาซีเกมส์",
    image_url: "/api/image?url=https%3A%2F%2Fthestandard.co%2Fsea-games.jpg",
    articles: [
      {
        url: "https://thestandard.co/sea-games-1",
        title: "พิธีเปิดซีเกมส์",
        source: "The Standard",
        image_url: "/api/image?url=https%3A%2F%2Fthestandard.co%2Fopening.jpg",
      },
      {
        url: "https://thaipbs.or.th/sea-games-2",
        title: "ไฮไลต์การแข่งขัน",
        source: "ThaiPBS",
        image_url: "https://images.thaipbs.or.th/sport.jpg",
      },
    ],
    child_events: [
      {
        story_id: "st_101",
        title: "การแข่งขันว่ายน้ำ",
        image_url: "/api/image?url=https%3A%2F%2Fthestandard.co%2Fswim.jpg",
        articles: [
          {
            url: "https://thestandard.co/swim-1",
            title: "ว่ายน้ำคว้าทอง",
            source: "The Standard",
            image_url: "/api/image?url=https%3A%2F%2Fthestandard.co%2Fgold.jpg",
          },
        ],
      },
    ],
  };

  const norm = normalizeStory(rawCluster);
  assert.ok(norm.image_url.startsWith("http://localhost:5000/api/image?url="));
  assert.strictEqual(norm.articles.length, 2);
  assert.ok(norm.articles[0].image_url.startsWith("http://localhost:5000/api/image?url="));
  assert.strictEqual(norm.articles[1].image_url, "https://images.thaipbs.or.th/sport.jpg");

  assert.strictEqual(norm.child_events.length, 1);
  assert.ok(norm.child_events[0].image_url.startsWith("http://localhost:5000/api/image?url="));
  assert.ok(norm.child_events[0].articles[0].image_url.startsWith("http://localhost:5000/api/image?url="));
});

// ── Test Group 4: Offline Detection & Timeout in api.js ─────────────
console.log("\n--- Group 4: Offline Detection & Timeout Handling ---");

await test("request() fast-fails with isOffline=true when navigator.onLine is false", async () => {
  let restoreOnline;
  if (typeof navigator !== "undefined") {
    const original = navigator.onLine;
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
    restoreOnline = () => {
      if (original !== undefined) {
        Object.defineProperty(navigator, "onLine", { value: original, configurable: true });
      } else {
        delete navigator.onLine;
      }
    };
  } else {
    globalThis.navigator = { onLine: false };
    restoreOnline = () => { delete globalThis.navigator; };
  }

  try {
    await assert.rejects(
      async () => {
        await request("/api/news");
      },
      (err) => {
        assert.ok(err instanceof ApiError);
        assert.strictEqual(err.isOffline, true);
        assert.strictEqual(err.status, 0);
        assert.strictEqual(err.statusText, "Offline");
        return true;
      }
    );
  } finally {
    restoreOnline();
  }
});

await test("request() aborts and throws ApiError with isTimeout=true on connection timeout", async () => {
  // 10.255.255.1 is a non-routable IP that will hang until timeout
  await assert.rejects(
    async () => {
      await request("http://10.255.255.1:9999/timeout", { timeoutMs: 50 });
    },
    (err) => {
      assert.ok(err instanceof ApiError);
      assert.strictEqual(err.isTimeout, true);
      assert.strictEqual(err.status, 0);
      return true;
    }
  );
});

// ── Test Group 5: Socket.IO Factory & Reconnection Engine ──────────
console.log("\n--- Group 5: Socket.IO Lifecycle, Backoff & State Machine ---");

await test("initSocket without io factory gracefully transitions to ERROR state without throwing", () => {
  resetTelemetry();
  const socket = initSocket({ io: null, win: null });
  assert.strictEqual(socket, null);
  assert.strictEqual(getConnectionState(), ConnectionState.ERROR);
  const tel = getTelemetry();
  assert.strictEqual(tel.state, ConnectionState.ERROR);
  assert.ok(tel.lastError);
});

await test("initSocket configures exponential backoff, jitter, and transports on ioFactory", () => {
  resetTelemetry();
  let capturedUrl = "";
  let capturedOptions = null;

  const mockFactory = (url, options) => {
    capturedUrl = url;
    capturedOptions = options;
    return new MockSocketIO(url, options);
  };

  const socket = initSocket({
    io: mockFactory,
    url: "http://localhost:5000",
    reconnectionDelay: 1000,
    reconnectionDelayMax: 30000,
    randomizationFactor: 0.5,
    timeout: 20000,
  });

  assert.ok(socket);
  assert.strictEqual(capturedUrl, "http://localhost:5000");
  assert.deepStrictEqual(capturedOptions.transports, ["websocket", "polling"]);
  assert.strictEqual(capturedOptions.reconnection, true);
  assert.strictEqual(capturedOptions.reconnectionAttempts, Infinity);
  assert.strictEqual(capturedOptions.reconnectionDelay, 1000);
  assert.strictEqual(capturedOptions.reconnectionDelayMax, 30000);
  assert.strictEqual(capturedOptions.randomizationFactor, 0.5);
  assert.strictEqual(capturedOptions.timeout, 20000);
});

await test("Socket lifecycle transitions through CONNECTING -> CONNECTED -> RECONNECTING -> DISCONNECTED", () => {
  resetTelemetry();
  let mock;
  const mockFactory = (url, options) => {
    mock = new MockSocketIO(url, options);
    return mock;
  };

  const stateHistory = [];
  const unsubscribe = onConnectionChange(({ state }) => {
    stateHistory.push(state);
  });

  initSocket({ io: mockFactory, url: "http://localhost:5000" });
  assert.strictEqual(getConnectionState(), ConnectionState.CONNECTING);

  mock.simulateConnect();
  assert.strictEqual(getConnectionState(), ConnectionState.CONNECTED);
  assert.strictEqual(isConnected(), true);

  mock.simulateDisconnect("transport close");
  assert.strictEqual(getConnectionState(), ConnectionState.RECONNECTING);
  assert.strictEqual(isConnected(), false);

  mock.io.emit("reconnect_attempt", 1);
  assert.strictEqual(getTelemetry().reconnectAttempts, 1);

  mock.io.emit("reconnect_attempt", 2);
  assert.strictEqual(getTelemetry().reconnectAttempts, 2);

  mock.io.emit("reconnect", 2);
  assert.strictEqual(getConnectionState(), ConnectionState.CONNECTED);
  assert.strictEqual(getTelemetry().reconnectAttempts, 0);

  disconnectSocket();
  assert.strictEqual(getConnectionState(), ConnectionState.DISCONNECTED);
  assert.strictEqual(isConnected(), false);
  assert.strictEqual(getTelemetry().disconnectReason, "client_manual_disconnect");

  unsubscribe();
});

// ── Test Group 6: Socket Dual-Mapping & Pub/Sub ─────────────────────
console.log("\n--- Group 6: Socket Dual-Mapping & Memory Leak Prevention ---");

await test("onNewsBatch normalizes both 'new_articles' and 'news_batch' events", () => {
  resetTelemetry();
  let mock;
  const mockFactory = (url, options) => {
    mock = new MockSocketIO(url, options);
    return mock;
  };

  initSocket({ io: mockFactory, url: "http://localhost:5000", forceNew: true });
  mock.simulateConnect();

  const receivedBatches = [];
  const unsubNews = onNewsBatch((data) => {
    receivedBatches.push(data);
  });

  // 1. Simulate legacy "new_articles"
  mock.simulateServerEvent("new_articles", {
    count: 2,
    total: 100,
    articles: [{ title: "Art 1" }, { title: "Art 2" }],
  });

  // 2. Simulate standard "news_batch"
  mock.simulateServerEvent("news_batch", {
    total: 101,
    articles: [{ title: "Art 3" }],
  });

  assert.strictEqual(receivedBatches.length, 2);
  assert.strictEqual(receivedBatches[0].count, 2);
  assert.strictEqual(receivedBatches[0].total, 100);
  assert.strictEqual(receivedBatches[0].articles.length, 2);

  // Auto-calculated count when missing in payload
  assert.strictEqual(receivedBatches[1].count, 1);
  assert.strictEqual(receivedBatches[1].total, 101);
  assert.strictEqual(receivedBatches[1].articles.length, 1);

  // Test unsubscribe
  unsubNews();
  mock.simulateServerEvent("news_batch", { count: 1, total: 102, articles: [] });
  assert.strictEqual(receivedBatches.length, 2); // Unsubscribed, should not receive
  disconnectSocket();
});

await test("onStatsUpdate normalizes both 'init' and 'stats_update' events", () => {
  resetTelemetry();
  let mock;
  const mockFactory = (url, options) => {
    mock = new MockSocketIO(url, options);
    return mock;
  };

  initSocket({ io: mockFactory, url: "http://localhost:5000", forceNew: true });
  mock.simulateConnect();

  const receivedStats = [];
  const unsubStats = onStatsUpdate((data) => {
    receivedStats.push(data);
  });

  mock.simulateServerEvent("init", { total: 42, updated: "2026-10-17T15:00:00Z" });
  mock.simulateServerEvent("stats_update", { total: 45, updated: "2026-10-17T15:05:00Z" });

  assert.strictEqual(receivedStats.length, 2);
  assert.strictEqual(receivedStats[0].total, 42);
  assert.strictEqual(receivedStats[0].updated, "2026-10-17T15:00:00Z");
  assert.strictEqual(receivedStats[1].total, 45);
  assert.strictEqual(receivedStats[1].updated, "2026-10-17T15:05:00Z");

  unsubStats();
  disconnectSocket();
});

await test("Error in one listener does not crash or block remaining subscribers", () => {
  resetTelemetry();
  let mock;
  const mockFactory = (url, options) => {
    mock = new MockSocketIO(url, options);
    return mock;
  };

  initSocket({ io: mockFactory, url: "http://localhost:5000", forceNew: true });
  mock.simulateConnect();

  let listenerBExecuted = false;

  const unsubA = onNewsBatch(() => {
    throw new Error("Deliberate error in Listener A");
  });

  const unsubB = onNewsBatch(() => {
    listenerBExecuted = true;
  });

  // Should catch error gracefully and still execute listener B
  mock.simulateServerEvent("news_batch", { count: 1, total: 10, articles: [] });

  assert.strictEqual(listenerBExecuted, true);

  unsubA();
  unsubB();
  disconnectSocket();
});

// ── Test Group 7: Browser Remote Action Helpers ────────────────────
console.log("\n--- Group 7: Browser Action Emitters & Remote Inspection ---");

await test("Browser action emitters properly emit expected event names and payloads", () => {
  resetTelemetry();
  let mock;
  const mockFactory = (url, options) => {
    mock = new MockSocketIO(url, options);
    return mock;
  };

  initSocket({ io: mockFactory, url: "http://localhost:5000", forceNew: true });
  mock.simulateConnect();

  emitBrowserOpenTab("tab-1");
  emitBrowserCloseTab("tab-1");
  emitBrowserNavigate("tab-2", "https://example.com");
  emitBrowserOpenAndNavigate("tab-3", "https://example.com/3");
  emitBrowserGoBack("tab-2");
  emitBrowserGoForward("tab-2");
  emitBrowserRefresh("tab-2");

  assert.strictEqual(mock.emittedEvents.length, 7);
  assert.deepStrictEqual(mock.emittedEvents[0], { event: "browser_open_tab", payload: { tab_id: "tab-1" } });
  assert.deepStrictEqual(mock.emittedEvents[1], { event: "browser_close_tab", payload: { tab_id: "tab-1" } });
  assert.deepStrictEqual(mock.emittedEvents[2], { event: "browser_navigate", payload: { tab_id: "tab-2", url: "https://example.com" } });
  assert.deepStrictEqual(mock.emittedEvents[3], { event: "browser_open_and_navigate", payload: { tab_id: "tab-3", url: "https://example.com/3" } });
  assert.deepStrictEqual(mock.emittedEvents[4], { event: "browser_go_back", payload: { tab_id: "tab-2" } });
  assert.deepStrictEqual(mock.emittedEvents[5], { event: "browser_go_forward", payload: { tab_id: "tab-2" } });
  assert.deepStrictEqual(mock.emittedEvents[6], { event: "browser_refresh", payload: { tab_id: "tab-2" } });
  disconnectSocket();
});

await test("Browser action emitters safely return false when socket is disconnected", () => {
  disconnectSocket();
  assert.strictEqual(emitBrowserOpenTab("tab-x"), false);
  assert.strictEqual(emitBrowserCloseTab("tab-x"), false);
  assert.strictEqual(emitBrowserNavigate("tab-x", "https://foo"), false);
});

// ── Test Group 8: Zero DOM Invariant & LOC Guardrail ────────────────
console.log("\n--- Group 8: Zero DOM Invariant & LOC Guardrails ---");

await test("frontend/static/socket.js has strictly ZERO DOM references and is < 800 LOC", () => {
  const socketPath = path.join(repoRoot, "frontend/static/socket.js");
  const content = fs.readFileSync(socketPath, "utf8");
  const lines = content.split("\n").length;

  console.log(`     socket.js line count: ${lines} lines`);
  assert.ok(lines < 800, `socket.js must be < 800 LOC (found: ${lines})`);

  const domRegex = /\b(document\.|getElementById|querySelector|querySelectorAll|innerHTML|outerHTML)\b/;
  const match = content.match(domRegex);
  assert.strictEqual(match, null, `socket.js contains forbidden DOM reference: ${match?.[0]}`);
});

await test("frontend/static/api.js has strictly ZERO DOM references and is < 800 LOC", () => {
  const apiPath = path.join(repoRoot, "frontend/static/api.js");
  const content = fs.readFileSync(apiPath, "utf8");
  const lines = content.split("\n").length;

  console.log(`     api.js line count: ${lines} lines`);
  assert.ok(lines < 800, `api.js must be < 800 LOC (found: ${lines})`);

  const domRegex = /\b(document\.|getElementById|querySelector|querySelectorAll|innerHTML|outerHTML)\b/;
  const match = content.match(domRegex);
  assert.strictEqual(match, null, `api.js contains forbidden DOM reference: ${match?.[0]}`);
});

// ── Summary ────────────────────────────────────────────────────────
console.log("\n=======================================================");
console.log(`🏁 Milestone 2 Verification Results: ${passed} passed, ${failed} failed`);
console.log("=======================================================\n");

if (failed > 0) {
  process.exit(1);
} else {
  process.exit(0);
}
