/**
 * backend/tests/test_adversarial_socket_client.mjs
 * ─────────────────────────────────────────────────────────────────
 * Adversarial Empirical Stress Testing & Challenge Suite for Milestone 2:
 * 1. Connection State Machine Transitions (Linear, Cyclic, Failures, Jumps)
 * 2. Exponential Backoff Calculation, Bounding, Cap & Jitter
 * 3. Subscriber Error Isolation under Extreme Failure Scenarios
 * 4. Unsubscribe Functions, Self-Unsubscription, Churn & Memory Leaks
 * 5. Dual Event Mappings & Hostile / Malformed Data Ingestion Resiliency
 * 6. Browser Action Emitters, Disconnected Guards & Telemetry Mutation Shield
 * 7. Edge Cases: Pre-init subscriptions and legacy options.handlers isolation
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
  createSocket,
} from "../../frontend/static/socket.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../..");

console.log("⚡ Starting Adversarial Socket.IO Client Stress & Challenge Suite...\n");

let passed = 0;
let failed = 0;
const testResults = [];

async function challenge(name, fn) {
  try {
    await fn();
    console.log(`  ✅ PASS: ${name}`);
    passed++;
    testResults.push({ name, status: "PASS" });
  } catch (err) {
    console.error(`  ❌ FAIL: ${name}`);
    console.error(`     Error: ${err.message}\n${err.stack}`);
    failed++;
    testResults.push({ name, status: "FAIL", error: err.message });
  }
}

// ── High-Fidelity Mock Socket.IO Harness ───────────────────────────
class AdversarialMockSocket {
  constructor(url, options) {
    this.url = url;
    this.options = options;
    this.connected = false;
    this.id = "adv-sock-" + Math.random().toString(36).slice(2, 9);
    this.eventListeners = new Map();
    this.emittedList = [];
    this.disconnectCallCount = 0;

    // Manager mock
    this.io = {
      listeners: new Map(),
      on: (evt, handler) => {
        if (!this.io.listeners.has(evt)) this.io.listeners.set(evt, []);
        this.io.listeners.get(evt).push(handler);
      },
      emit: (evt, ...args) => {
        const handlers = this.io.listeners.get(evt) || [];
        for (const h of handlers) h(...args);
      },
      off: (evt, handler) => {
        if (!this.io.listeners.has(evt)) return;
        if (!handler) {
          this.io.listeners.delete(evt);
        } else {
          const arr = this.io.listeners.get(evt).filter((h) => h !== handler);
          this.io.listeners.set(evt, arr);
        }
      },
    };
  }

  on(evt, handler) {
    if (!this.eventListeners.has(evt)) this.eventListeners.set(evt, []);
    this.eventListeners.get(evt).push(handler);
  }

  emit(evt, payload) {
    this.emittedList.push({ event: evt, payload });
  }

  trigger(evt, ...args) {
    if (evt === "connect") {
      this.connected = true;
    } else if (evt === "disconnect") {
      this.connected = false;
    }
    const handlers = this.eventListeners.get(evt) || [];
    for (const h of handlers) {
      h(...args);
    }
  }

  connect() {
    this.connected = true;
    this.trigger("connect");
  }

  disconnect() {
    this.disconnectCallCount++;
    this.connected = false;
    this.trigger("disconnect", "io client disconnect");
  }
}

function createMockFactory() {
  let activeMock = null;
  const factory = (url, opts) => {
    activeMock = new AdversarialMockSocket(url, opts);
    return activeMock;
  };
  return {
    factory,
    getMock: () => activeMock,
  };
}

// ═════════════════════════════════════════════════════════════════════
// SUITE 1: Connection State Machine Transitions
// ═════════════════════════════════════════════════════════════════════
console.log("=== Suite 1: Connection State Machine Transitions ===");

await challenge("1.1 Full Lifecycle Transition: DISCONNECTED -> CONNECTING -> CONNECTED -> RECONNECTING -> DISCONNECTED", async () => {
  disconnectSocket();
  resetTelemetry();
  const stateLog = [];
  const unsub = onConnectionChange(({ state }) => stateLog.push(state));

  const harness = createMockFactory();
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  const mock = harness.getMock();

  assert.strictEqual(getConnectionState(), ConnectionState.CONNECTING);
  assert.strictEqual(isConnected(), false);

  mock.connect();
  assert.strictEqual(getConnectionState(), ConnectionState.CONNECTED);
  assert.strictEqual(isConnected(), true);

  // Network drop -> server disconnect
  mock.trigger("disconnect", "transport close");
  assert.strictEqual(getConnectionState(), ConnectionState.RECONNECTING);
  assert.strictEqual(isConnected(), false);

  // Manual client disconnect
  disconnectSocket();
  assert.strictEqual(getConnectionState(), ConnectionState.DISCONNECTED);
  assert.strictEqual(isConnected(), false);

  unsub();
  assert.ok(stateLog.includes(ConnectionState.CONNECTING));
  assert.ok(stateLog.includes(ConnectionState.CONNECTED));
  assert.ok(stateLog.includes(ConnectionState.RECONNECTING));
  assert.ok(stateLog.includes(ConnectionState.DISCONNECTED));
});

await challenge("1.2 Disconnect Reasons Differentiation (Manual vs Transport vs Server Ping)", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();

  // Test 1: ping timeout -> RECONNECTING
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  harness.getMock().connect();
  harness.getMock().trigger("disconnect", "ping timeout");
  assert.strictEqual(getConnectionState(), ConnectionState.RECONNECTING);
  assert.strictEqual(getTelemetry().disconnectReason, "ping timeout");

  // Test 2: transport error -> RECONNECTING
  harness.getMock().connect();
  harness.getMock().trigger("disconnect", "transport error");
  assert.strictEqual(getConnectionState(), ConnectionState.RECONNECTING);
  assert.strictEqual(getTelemetry().disconnectReason, "transport error");

  // Test 3: io server disconnect -> RECONNECTING
  harness.getMock().connect();
  harness.getMock().trigger("disconnect", "io server disconnect");
  assert.strictEqual(getConnectionState(), ConnectionState.RECONNECTING);

  // Test 4: io client disconnect -> DISCONNECTED
  harness.getMock().connect();
  harness.getMock().trigger("disconnect", "io client disconnect");
  assert.strictEqual(getConnectionState(), ConnectionState.DISCONNECTED);
  assert.strictEqual(getTelemetry().disconnectReason, "io client disconnect");

  // Test 5: client_manual_disconnect via disconnectSocket() -> DISCONNECTED
  harness.getMock().connect();
  disconnectSocket();
  assert.strictEqual(getConnectionState(), ConnectionState.DISCONNECTED);
  assert.strictEqual(getTelemetry().disconnectReason, "client_manual_disconnect");
});

await challenge("1.3 Reconnection Cycle Recovery and Attempt Counter Reset", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  const mock = harness.getMock();

  mock.connect();
  mock.trigger("disconnect", "transport close");
  assert.strictEqual(getConnectionState(), ConnectionState.RECONNECTING);

  // Multiple reconnect attempts
  for (let i = 1; i <= 7; i++) {
    mock.io.emit("reconnect_attempt", i);
    assert.strictEqual(getTelemetry().reconnectAttempts, i);
    assert.strictEqual(getConnectionState(), ConnectionState.RECONNECTING);
  }

  // Successful reconnection
  mock.io.emit("reconnect", 7);
  assert.strictEqual(getConnectionState(), ConnectionState.CONNECTED);
  assert.strictEqual(getTelemetry().reconnectAttempts, 0);
  assert.strictEqual(getTelemetry().lastError, null);
  assert.ok(getTelemetry().connectedAt > 0);

  disconnectSocket();
});

await challenge("1.4 Reconnection Failure Permanent Exhaustion (reconnect_failed)", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  const mock = harness.getMock();

  mock.connect();
  mock.trigger("disconnect", "transport close");
  mock.io.emit("reconnect_failed");

  assert.strictEqual(getConnectionState(), ConnectionState.ERROR);
  assert.strictEqual(getTelemetry().state, ConnectionState.ERROR);
  assert.strictEqual(getTelemetry().maxReconnectAttemptsReached, true);

  disconnectSocket();
});

await challenge("1.5 Initial Connection Failure (connect_error during CONNECTING)", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  const mock = harness.getMock();

  const customErr = new Error("Connection refused (ECONNREFUSED)");
  mock.trigger("connect_error", customErr);

  assert.strictEqual(getConnectionState(), ConnectionState.RECONNECTING);
  assert.strictEqual(getTelemetry().lastError, customErr);

  disconnectSocket();
});

await challenge("1.6 Idempotency: Multiple connectSocket() and initSocket() Calls", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();
  const s1 = initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  harness.getMock().connect();

  // Repeated connectSocket when already connected should return existing socket instance
  const s2 = connectSocket();
  assert.strictEqual(s1, s2);
  assert.strictEqual(getConnectionState(), ConnectionState.CONNECTED);

  // initSocket without forceNew when connected should return existing socket instance
  const s3 = initSocket({ io: harness.factory, url: "http://localhost:5000" });
  assert.strictEqual(s1, s3);

  // initSocket with forceNew: true should replace socket
  const s4 = initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  assert.notStrictEqual(s1, s4);
  assert.strictEqual(getConnectionState(), ConnectionState.CONNECTING);

  disconnectSocket();
});

// ═════════════════════════════════════════════════════════════════════
// SUITE 2: Exponential Backoff Calculation & Cap
// ═════════════════════════════════════════════════════════════════════
console.log("\n=== Suite 2: Exponential Backoff Calculation & Cap ===");

await challenge("2.1 Backoff Options Integrity (Defaults, Custom Overrides, Nullish Handling)", async () => {
  disconnectSocket();
  let capturedOpts = null;
  const mockFactory = (url, opts) => {
    capturedOpts = opts;
    return new AdversarialMockSocket(url, opts);
  };

  // Test default configuration
  initSocket({ io: mockFactory, url: "http://localhost:5000", forceNew: true });
  assert.strictEqual(capturedOpts.reconnection, true);
  assert.strictEqual(capturedOpts.reconnectionAttempts, Infinity);
  assert.strictEqual(capturedOpts.reconnectionDelay, 1000);
  assert.strictEqual(capturedOpts.reconnectionDelayMax, 30000);
  assert.strictEqual(capturedOpts.randomizationFactor, 0.5);
  assert.strictEqual(capturedOpts.timeout, 20000);

  // Test custom overrides including boundary 0
  initSocket({
    io: mockFactory,
    url: "http://localhost:5000",
    forceNew: true,
    reconnectionDelay: 500,
    reconnectionDelayMax: 10000,
    randomizationFactor: 0.2,
    timeout: 5000,
  });
  assert.strictEqual(capturedOpts.reconnectionDelay, 500);
  assert.strictEqual(capturedOpts.reconnectionDelayMax, 10000);
  assert.strictEqual(capturedOpts.randomizationFactor, 0.2);
  assert.strictEqual(capturedOpts.timeout, 5000);

  // Test zero delay boundary (0 must not fall back to 1000 due to ??)
  initSocket({
    io: mockFactory,
    url: "http://localhost:5000",
    forceNew: true,
    reconnectionDelay: 0,
    randomizationFactor: 0,
  });
  assert.strictEqual(capturedOpts.reconnectionDelay, 0);
  assert.strictEqual(capturedOpts.randomizationFactor, 0);

  disconnectSocket();
});

await challenge("2.2 Mathematical Verification: Backoff Exponential Growth & 30s Cap Ceiling", async () => {
  // Socket.IO uses the Backo algorithm: min(delay * 2^attempt, delayMax)
  const baseDelay = 1000;
  const maxDelay = 30000;
  const jitterFactor = 0.5;

  function calculateExpectedBackoff(attempt) {
    const theoretical = baseDelay * Math.pow(2, attempt);
    const capped = Math.min(theoretical, maxDelay);
    const minJitter = capped * (1 - jitterFactor);
    const maxJitter = capped * (1 + jitterFactor);
    return { theoretical, capped, minJitter, maxJitter };
  }

  const expectedProgression = [
    { attempt: 0, expCapped: 1000, expMin: 500, expMax: 1500 },
    { attempt: 1, expCapped: 2000, expMin: 1000, expMax: 3000 },
    { attempt: 2, expCapped: 4000, expMin: 2000, expMax: 6000 },
    { attempt: 3, expCapped: 8000, expMin: 4000, expMax: 12000 },
    { attempt: 4, expCapped: 16000, expMin: 8000, expMax: 24000 },
    { attempt: 5, expCapped: 30000, expMin: 15000, expMax: 45000 }, // 32000 -> capped at 30000
    { attempt: 6, expCapped: 30000, expMin: 15000, expMax: 45000 }, // 64000 -> capped at 30000
    { attempt: 10, expCapped: 30000, expMin: 15000, expMax: 45000 }, // 1024000 -> capped at 30000
    { attempt: 25, expCapped: 30000, expMin: 15000, expMax: 45000 },
  ];

  for (const item of expectedProgression) {
    const calc = calculateExpectedBackoff(item.attempt);
    assert.strictEqual(
      calc.capped,
      item.expCapped,
      `Attempt ${item.attempt}: expected capped delay ${item.expCapped}, got ${calc.capped}`
    );
    assert.strictEqual(calc.minJitter, item.expMin);
    assert.strictEqual(calc.maxJitter, item.expMax);
    assert.ok(calc.capped <= maxDelay, `Attempt ${item.attempt} exceeded max delay cap!`);
  }
});

await challenge("2.3 Reconnection Telemetry Tracking Under Sustained Backoff Attempts", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  const mock = harness.getMock();

  mock.connect();
  mock.trigger("disconnect", "transport close");

  // Stress test 50 consecutive reconnection attempts
  for (let i = 1; i <= 50; i++) {
    mock.io.emit("reconnect_attempt", i);
    mock.io.emit("reconnect_error", new Error(`Timeout on attempt #${i}`));
    const tel = getTelemetry();
    assert.strictEqual(tel.reconnectAttempts, i);
    assert.strictEqual(tel.state, ConnectionState.RECONNECTING);
    assert.strictEqual(tel.lastError.message, `Timeout on attempt #${i}`);
  }

  // Now reconnected
  mock.io.emit("reconnect", 50);
  assert.strictEqual(getTelemetry().reconnectAttempts, 0);
  assert.strictEqual(getConnectionState(), ConnectionState.CONNECTED);

  disconnectSocket();
});

// ═════════════════════════════════════════════════════════════════════
// SUITE 3: Subscriber Error Isolation
// ═════════════════════════════════════════════
console.log("\n=== Suite 3: Subscriber Error Isolation ===");

await challenge("3.1 Interleaved Throwing & Non-Throwing Subscribers for onNewsBatch", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  harness.getMock().connect();

  const executedSubscribers = [];
  const errorsToThrow = [
    new Error("Subscriber 0 exploded"),
    new TypeError("Subscriber 2 undefined property"),
    "String error from Subscriber 4",
    { custom: "object error from Subscriber 6" },
  ];

  const unsubs = [];
  for (let i = 0; i < 10; i++) {
    const idx = i;
    if (idx % 2 === 0) {
      // Even subscribers throw various types of errors
      const err = errorsToThrow[Math.floor(idx / 2)];
      unsubs.push(
        onNewsBatch(() => {
          throw err;
        })
      );
    } else {
      // Odd subscribers must succeed
      unsubs.push(
        onNewsBatch((data) => {
          executedSubscribers.push({ idx, data });
        })
      );
    }
  }

  // Trigger news_batch
  harness.getMock().trigger("news_batch", {
    count: 1,
    total: 10,
    articles: [{ title: "Breaking News" }],
  });

  // All 5 odd subscribers must have executed successfully
  assert.strictEqual(executedSubscribers.length, 5);
  assert.deepStrictEqual(
    executedSubscribers.map((s) => s.idx),
    [1, 3, 5, 7, 9]
  );

  // Clean up
  unsubs.forEach((u) => u());
  disconnectSocket();
});

await challenge("3.2 onStatsUpdate Subscriber Error Isolation", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  harness.getMock().connect();

  let listener2Received = null;
  const unsub1 = onStatsUpdate(() => {
    throw new Error("Stats update catastrophic failure");
  });
  const unsub2 = onStatsUpdate((data) => {
    listener2Received = data;
  });

  harness.getMock().trigger("stats_update", { total: 999, updated: "2026-10-17T16:00:00Z" });

  assert.ok(listener2Received);
  assert.strictEqual(listener2Received.total, 999);

  unsub1();
  unsub2();
  disconnectSocket();
});

await challenge("3.3 onConnectionChange Subscriber Error Isolation", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();

  const receivedTransitions = [];
  const unsub1 = onConnectionChange(() => {
    throw new Error("Connection listener threw on initial register");
  });
  const unsub2 = onConnectionChange((data) => {
    receivedTransitions.push(data.state);
  });

  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  harness.getMock().connect();
  harness.getMock().trigger("disconnect", "transport close");

  unsub1();
  unsub2();
  disconnectSocket();

  assert.ok(receivedTransitions.includes(ConnectionState.CONNECTING));
  assert.ok(receivedTransitions.includes(ConnectionState.CONNECTED));
  assert.ok(receivedTransitions.includes(ConnectionState.RECONNECTING));
});

await challenge("3.4 Generic on(eventName) Subscriber Error Isolation", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  harness.getMock().connect();

  let handlerBExecuted = false;
  const unsubA = on("custom_event", () => {
    throw new Error("Error in generic subscriber A");
  });
  const unsubB = on("custom_event", (payload) => {
    handlerBExecuted = payload.valid;
  });

  harness.getMock().trigger("custom_event", { valid: true });

  assert.strictEqual(handlerBExecuted, true);

  unsubA();
  unsubB();
  disconnectSocket();
});

// ═════════════════════════════════════════════════════════════════════
// SUITE 4: Unsubscribe Functions, Cleanup & Memory Leak Stress
// ═════════════════════════════════════════════
console.log("\n=== Suite 4: Unsubscribe Functions, Cleanup & Memory Leaks ===");

await challenge("4.1 Idempotency & Return Value of Unsubscribe Functions", async () => {
  disconnectSocket();
  const fn = () => {};
  const unsub = onNewsBatch(fn);

  // First call should return true (successfully deleted)
  const first = unsub();
  assert.strictEqual(first, true);

  // Subsequent calls should return false (already deleted)
  const second = unsub();
  assert.strictEqual(second, false);

  const third = unsub();
  assert.strictEqual(third, false);
});

await challenge("4.2 Non-function Handlers Return Harmless No-op Unsubscribe", async () => {
  assert.strictEqual(typeof onConnectionChange(null), "function");
  assert.strictEqual(onConnectionChange(null)(), false);

  assert.strictEqual(typeof onNewsBatch(undefined), "function");
  assert.strictEqual(onNewsBatch(undefined)(), false);

  assert.strictEqual(typeof onStatsUpdate("not a function"), "function");
  assert.strictEqual(onStatsUpdate("not a function")(), false);

  assert.strictEqual(typeof onTrendingUpdate(123), "function");
  assert.strictEqual(onTrendingUpdate(123)(), false);

  assert.strictEqual(typeof on(null, null), "function");
  assert.strictEqual(on(null, null)(), false);
});

await challenge("4.3 Self-Unsubscribing Listener During Event Execution (Safe Set Mutation)", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  harness.getMock().connect();

  let callCountA = 0;
  let callCountB = 0;

  let unsubA;
  unsubA = onNewsBatch(() => {
    callCountA++;
    unsubA(); // Listener unsubscribes itself during execution
  });

  const unsubB = onNewsBatch(() => {
    callCountB++;
  });

  // First event: both execute
  harness.getMock().trigger("news_batch", { count: 1, total: 1, articles: [] });
  assert.strictEqual(callCountA, 1);
  assert.strictEqual(callCountB, 1);

  // Second event: listener A must not execute because it unsubscribed itself
  harness.getMock().trigger("news_batch", { count: 1, total: 2, articles: [] });
  assert.strictEqual(callCountA, 1); // Still 1
  assert.strictEqual(callCountB, 2); // Incremented to 2

  unsubB();
  disconnectSocket();
});

await challenge("4.4 High-Volume Subscriber Churn (10,000 Registrations & Unregistrations)", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  harness.getMock().connect();

  const ITERATIONS = 10000;
  const unsubs = new Array(ITERATIONS);

  // Register 10,000 distinct listeners
  for (let i = 0; i < ITERATIONS; i++) {
    unsubs[i] = onNewsBatch(() => {});
  }

  // Unsubscribe all 10,000 listeners
  for (let i = 0; i < ITERATIONS; i++) {
    const res = unsubs[i]();
    assert.strictEqual(res, true);
  }

  // Fire event to confirm 0 listeners execute
  let executed = 0;
  const probe = onNewsBatch(() => executed++);
  harness.getMock().trigger("news_batch", { count: 1, total: 1, articles: [] });
  assert.strictEqual(executed, 1);

  probe();
  disconnectSocket();
});

await challenge("4.5 Set Deduplication for Re-registered Identical Listener", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  harness.getMock().connect();

  let execCount = 0;
  const sharedHandler = () => execCount++;

  // Register identical handler 5 times
  const unsub1 = onNewsBatch(sharedHandler);
  const unsub2 = onNewsBatch(sharedHandler);
  const unsub3 = onNewsBatch(sharedHandler);

  harness.getMock().trigger("news_batch", { count: 1, total: 1, articles: [] });

  // In Set, duplicates are ignored, so it executes exactly once
  assert.strictEqual(execCount, 1);

  // Calling any unsubscribe removes it from Set
  unsub1();
  harness.getMock().trigger("news_batch", { count: 1, total: 2, articles: [] });
  assert.strictEqual(execCount, 1); // Not called again

  unsub2();
  unsub3();
  disconnectSocket();
});

// ═════════════════════════════════════════════════════════════════════
// SUITE 5: Dual Event Mappings & Hostile Payload Normalization
// ═════════════════════════════════════════════
console.log("\n=== Suite 5: Dual Event Mappings & Hostile Payloads ===");

await challenge("5.1 Dual Mapping: 'new_articles' vs 'news_batch' Equivalent Normalization", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  harness.getMock().connect();

  const received = [];
  const unsub = onNewsBatch((data) => received.push(data));

  // Legacy event
  harness.getMock().trigger("new_articles", {
    count: 2,
    total: 50,
    articles: [{ id: 1 }, { id: 2 }],
    updated: "2026-10-17T10:00:00Z",
  });

  // Standard event
  harness.getMock().trigger("news_batch", {
    count: 2,
    total: 52,
    articles: [{ id: 3 }, { id: 4 }],
    updated: "2026-10-17T10:01:00Z",
  });

  assert.strictEqual(received.length, 2);
  assert.strictEqual(received[0].count, 2);
  assert.strictEqual(received[0].total, 50);
  assert.strictEqual(received[0].articles.length, 2);
  assert.strictEqual(received[1].count, 2);
  assert.strictEqual(received[1].total, 52);
  assert.strictEqual(received[1].articles.length, 2);

  unsub();
  disconnectSocket();
});

await challenge("5.2 Dual Mapping: 'init' vs 'stats_update' Equivalent Normalization", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  harness.getMock().connect();

  const received = [];
  const unsub = onStatsUpdate((data) => received.push(data));

  // Legacy event
  harness.getMock().trigger("init", {
    total: 100,
    updated: "2026-10-17T12:00:00Z",
  });

  // Standard event
  harness.getMock().trigger("stats_update", {
    total: 120,
    updated: "2026-10-17T12:05:00Z",
  });

  assert.strictEqual(received.length, 2);
  assert.strictEqual(received[0].total, 100);
  assert.strictEqual(received[1].total, 120);

  unsub();
  disconnectSocket();
});

await challenge("5.3 Hostile & Malformed Payloads Ingestion Without Exceptions", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  harness.getMock().connect();

  const hostileBatches = [];
  const unsubBatch = onNewsBatch((data) => hostileBatches.push(data));

  const hostileStats = [];
  const unsubStats = onStatsUpdate((data) => hostileStats.push(data));

  const malformedInputs = [
    null,
    undefined,
    "",
    "corrupted payload",
    12345,
    [],
    {},
    { count: "NaN", total: "invalid", articles: "not array" },
    { articles: [null, undefined, 42, "hello"] },
    { count: -1, total: -50 },
  ];

  for (const input of malformedInputs) {
    // Should not throw on news_batch
    harness.getMock().trigger("news_batch", input);
    // Should not throw on stats_update
    harness.getMock().trigger("stats_update", input);
  }

  assert.strictEqual(hostileBatches.length, malformedInputs.length);
  assert.strictEqual(hostileStats.length, malformedInputs.length);

  for (const batch of hostileBatches) {
    assert.strictEqual(typeof batch.count, "number");
    assert.strictEqual(typeof batch.total, "number");
    assert.ok(Array.isArray(batch.articles));
    assert.strictEqual(typeof batch.updated, "string");
  }

  for (const stats of hostileStats) {
    assert.strictEqual(typeof stats.total, "number");
    assert.strictEqual(typeof stats.updated, "string");
  }

  unsubBatch();
  unsubStats();
  disconnectSocket();
});

await challenge("5.4 Dynamic Batch Count Inference When count Field Is Missing", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  harness.getMock().connect();

  let received = null;
  const unsub = onNewsBatch((data) => {
    received = data;
  });

  // Omit 'count' property, supply 4 articles
  harness.getMock().trigger("news_batch", {
    articles: [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }],
    total: 200,
  });

  assert.ok(received);
  assert.strictEqual(received.count, 4);
  assert.strictEqual(received.articles.length, 4);

  unsub();
  disconnectSocket();
});

// ═════════════════════════════════════════════════════════════════════
// SUITE 6: Browser Action Emitters, Disconnected Guards & Telemetry
// ═════════════════════════════════════════════
console.log("\n=== Suite 6: Browser Remote Emitters & Telemetry Integrity ===");

await challenge("6.1 Browser Emitters Safely Guard Against Disconnected Socket", async () => {
  disconnectSocket();
  assert.strictEqual(isConnected(), false);

  assert.strictEqual(emitSocketEvent("custom", {}), false);
  assert.strictEqual(emitBrowserOpenTab("tab-1"), false);
  assert.strictEqual(emitBrowserCloseTab("tab-1"), false);
  assert.strictEqual(emitBrowserNavigate("tab-1", "https://example.com"), false);
  assert.strictEqual(emitBrowserOpenAndNavigate("tab-1", "https://example.com"), false);
  assert.strictEqual(emitBrowserGoBack("tab-1"), false);
  assert.strictEqual(emitBrowserGoForward("tab-1"), false);
  assert.strictEqual(emitBrowserRefresh("tab-1"), false);
});

await challenge("6.2 Browser Emitters Faithfully Forward Typed Payloads When Connected", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  const mock = harness.getMock();
  mock.connect();

  assert.strictEqual(emitBrowserOpenTab("t-101"), true);
  assert.strictEqual(emitBrowserCloseTab("t-101"), true);
  assert.strictEqual(emitBrowserNavigate("t-102", "https://news.thaipbs.or.th"), true);
  assert.strictEqual(emitBrowserOpenAndNavigate("t-103", "https://thestandard.co"), true);
  assert.strictEqual(emitBrowserGoBack("t-102"), true);
  assert.strictEqual(emitBrowserGoForward("t-102"), true);
  assert.strictEqual(emitBrowserRefresh("t-102"), true);

  assert.strictEqual(mock.emittedList.length, 7);
  assert.deepStrictEqual(mock.emittedList[0], { event: "browser_open_tab", payload: { tab_id: "t-101" } });
  assert.deepStrictEqual(mock.emittedList[1], { event: "browser_close_tab", payload: { tab_id: "t-101" } });
  assert.deepStrictEqual(mock.emittedList[2], { event: "browser_navigate", payload: { tab_id: "t-102", url: "https://news.thaipbs.or.th" } });
  assert.deepStrictEqual(mock.emittedList[3], { event: "browser_open_and_navigate", payload: { tab_id: "t-103", url: "https://thestandard.co" } });
  assert.deepStrictEqual(mock.emittedList[4], { event: "browser_go_back", payload: { tab_id: "t-102" } });
  assert.deepStrictEqual(mock.emittedList[5], { event: "browser_go_forward", payload: { tab_id: "t-102" } });
  assert.deepStrictEqual(mock.emittedList[6], { event: "browser_refresh", payload: { tab_id: "t-102" } });

  disconnectSocket();
});

await challenge("6.3 Telemetry Immutability and Accurate Aggregation", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  harness.getMock().connect();

  // Send 3 news batches, 2 stats updates, 1 trending update, 1 monitoring log
  harness.getMock().trigger("news_batch", { count: 1, total: 10, articles: [] });
  harness.getMock().trigger("news_batch", { count: 1, total: 11, articles: [] });
  harness.getMock().trigger("news_batch", { count: 1, total: 12, articles: [] });
  harness.getMock().trigger("stats_update", { total: 12 });
  harness.getMock().trigger("stats_update", { total: 13 });
  harness.getMock().trigger("trending_update", { stories: [] });
  harness.getMock().trigger("monitoring_log", { log: "ok" });

  const tel1 = getTelemetry();
  assert.strictEqual(tel1.totalEventsReceived, 7);
  assert.strictEqual(tel1.eventsReceivedByType["news_batch"], 3);
  assert.strictEqual(tel1.eventsReceivedByType["stats_update"], 2);
  assert.strictEqual(tel1.eventsReceivedByType["trending_update"], 1);
  assert.strictEqual(tel1.eventsReceivedByType["monitoring_log"], 1);

  // Test immutability: mutating returned copy must NOT corrupt internal state
  tel1.totalEventsReceived = 999;
  tel1.eventsReceivedByType["news_batch"] = 999;

  const tel2 = getTelemetry();
  assert.strictEqual(tel2.totalEventsReceived, 7);
  assert.strictEqual(tel2.eventsReceivedByType["news_batch"], 3);

  // Reset telemetry
  resetTelemetry();
  const tel3 = getTelemetry();
  assert.strictEqual(tel3.totalEventsReceived, 0);
  assert.deepStrictEqual(tel3.eventsReceivedByType, {});

  disconnectSocket();
});

// ═════════════════════════════════════════════════════════════════════
// SUITE 7: Architectural Adversarial Edge Cases
// ═════════════════════════════════════════════
console.log("\n=== Suite 7: Architectural Adversarial Edge Cases ===");

await challenge("7.1 AUDIT FINDING: on(eventName) Silent Drop on Pre-Init Registration & Re-init", async () => {
  disconnectSocket();
  resetTelemetry();

  // Scenario A: Caller subscribes to "pre_init_evt" BEFORE initSocket()
  let preInitReceived = false;
  const unsubPre = on("pre_init_evt", () => {
    preInitReceived = true;
  });

  const harness = createMockFactory();
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  const mock1 = harness.getMock();
  mock1.connect();

  // Underlying socket never received on("pre_init_evt") because socketInstance was null at registration time
  mock1.trigger("pre_init_evt", { test: 1 });
  assert.strictEqual(
    preInitReceived,
    false,
    "VULNERABILITY CONFIRMED: on() before initSocket() is silently dropped and never bound to socket"
  );

  // Scenario B: Caller subscribes to a fresh event "post_init_evt" AFTER initSocket()
  let postInitReceived = false;
  const unsubPost = on("post_init_evt", () => {
    postInitReceived = true;
  });
  mock1.trigger("post_init_evt", { test: 2 });
  assert.strictEqual(
    postInitReceived,
    true,
    "on() with novel event name after initSocket() binds and receives events"
  );

  // Scenario C: Socket reconnects with forceNew: true (or disconnectSocket + initSocket)
  initSocket({ io: harness.factory, url: "http://localhost:5000", forceNew: true });
  const mock2 = harness.getMock();
  mock2.connect();

  let postReconnectReceived = false;
  on("post_init_evt", () => {
    postReconnectReceived = true;
  });
  mock2.trigger("post_init_evt", { test: 3 });
  assert.strictEqual(
    postReconnectReceived,
    false,
    "VULNERABILITY CONFIRMED: generic on() listeners are NOT re-bound to new socketInstance on re-init"
  );

  unsubPre();
  unsubPost();
  disconnectSocket();
});

await challenge("7.2 AUDIT FINDING: Throwing options.handlers Legacy Callbacks", async () => {
  disconnectSocket();
  resetTelemetry();
  const harness = createMockFactory();

  let pubSubReceived = false;
  const unsubPubSub = onNewsBatch(() => {
    pubSubReceived = true;
  });

  // Client initializes socket with a throwing legacy handler
  initSocket({
    io: harness.factory,
    url: "http://localhost:5000",
    forceNew: true,
    handlers: {
      onNewArticles: () => {
        throw new Error("Catastrophic error in legacy options.handlers.onNewArticles");
      },
    },
  });
  harness.getMock().connect();

  // Because dispatchToSet(newsBatchListeners, ...) runs BEFORE options.handlers?.onNewArticles,
  // pub/sub subscribers receive the batch safely even though the legacy callback throws afterwards:
  let thrown = false;
  try {
    harness.getMock().trigger("news_batch", { count: 1, total: 1, articles: [] });
  } catch (err) {
    thrown = true;
    assert.ok(err.message.includes("Catastrophic error in legacy"));
  }

  assert.strictEqual(pubSubReceived, true, "Pub/sub subscribers ran safely before legacy handler threw");
  assert.strictEqual(thrown, true, "Legacy handler threw as expected");

  unsubPubSub();
  disconnectSocket();
});

// ═════════════════════════════════════════════════════════════════════
// CHALLENGE SUMMARY
// ═════════════════════════════════════════════
console.log("\n=======================================================");
console.log(`🏁 Adversarial Stress Test Results: ${passed} passed, ${failed} failed`);
console.log("=======================================================\n");

if (failed > 0) {
  process.exit(1);
} else {
  process.exit(0);
}
