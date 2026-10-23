/**
 * socket.js — Dedicated Client WebSocket & Telemetry Layer
 *
 * Architecture:
 * - Decouples WebSocket communication from DOM rendering and HTTP API.
 * - Single Responsibility: Manages Socket.IO lifecycle, backoff, and event dispatch.
 * - ZERO DOM references (all UI updates are handled by subscribers).
 * - Implements 4-tier URL resolution via resolveSocketUrl() from config.js.
 * - Exponential backoff with jitter and telemetry metrics.
 * - Clean Pub/Sub registry with unsubscribe handlers for memory leak prevention.
 *
 * Client DAG Level: Level 2 (Depends only on Level 0 config.js).
 */

import { resolveSocketUrl } from "./config.js";

/**
 * Enumeration of discrete connection lifecycle states.
 */
export const ConnectionState = Object.freeze({
  DISCONNECTED: "DISCONNECTED",
  CONNECTING: "CONNECTING",
  CONNECTED: "CONNECTED",
  RECONNECTING: "RECONNECTING",
  ERROR: "ERROR",
});

// ── Internal Module State ──────────────────────────────────────────
let socketInstance = null;
let currentState = ConnectionState.DISCONNECTED;

// Internal Telemetry Store
const telemetry = {
  state: ConnectionState.DISCONNECTED,
  reconnectAttempts: 0,
  maxReconnectAttemptsReached: false,
  connectedAt: null,
  disconnectedAt: null,
  disconnectReason: null,
  lastError: null,
  totalEventsReceived: 0,
  eventsReceivedByType: {},
};

// Internal Pub/Sub Registries
const connectionChangeListeners = new Set();
const newsBatchListeners = new Set();
const statsUpdateListeners = new Set();
const trendingUpdateListeners = new Set();
const monitoringLogListeners = new Set();
const browserLoadingListeners = new Set();
const browserSnapshotListeners = new Set();
const browserTabOpenedListeners = new Set();
const genericEventListeners = new Map(); // eventName -> Set<handler>

// ── Private Helpers ────────────────────────────────────────────────

function notifyConnectionChange(details = {}) {
  const payload = {
    state: currentState,
    isConnected: currentState === ConnectionState.CONNECTED,
    attempt: telemetry.reconnectAttempts,
    error: telemetry.lastError,
    reason: telemetry.disconnectReason,
    ...details,
  };

  for (const listener of connectionChangeListeners) {
    try {
      listener(payload);
    } catch (err) {
      console.error("[SOCKET] Error in onConnectionChange listener:", err);
    }
  }
}

function recordEventTelemetry(eventName) {
  telemetry.totalEventsReceived++;
  telemetry.eventsReceivedByType[eventName] =
    (telemetry.eventsReceivedByType[eventName] || 0) + 1;
}

function dispatchToSet(listenerSet, payload, eventName) {
  recordEventTelemetry(eventName);
  for (const listener of listenerSet) {
    try {
      listener(payload);
    } catch (err) {
      console.error(`[SOCKET] Error in listener for "${eventName}":`, err);
    }
  }
}

// ── Core Exported API ──────────────────────────────────────────────

/**
 * Initializes and connects the Socket.IO client singleton.
 *
 * @param {object} [options]
 * @param {string} [options.url] - Explicit Socket URL override (defaults to resolveSocketUrl())
 * @param {string} [options.apiBase] - API Base for URL resolution
 * @param {Window} [options.win] - Injectable window object for testing
 * @param {Function} [options.io] - Injectable Socket.IO client factory (for Node/tests)
 * @param {boolean} [options.autoConnect=true] - Connect immediately
 * @param {number} [options.reconnectionDelay=1000] - Base delay in ms
 * @param {number} [options.reconnectionDelayMax=30000] - Max delay in ms
 * @param {number} [options.randomizationFactor=0.5] - Jitter factor [0.5, 1.5]
 * @param {number} [options.timeout=20000] - Connection timeout in ms
 * @param {object} [options.handlers] - Legacy backward-compatible handler map
 * @returns {object|null} Socket instance or null if io factory unavailable
 */
export function initSocket(options = {}) {
  if (socketInstance && socketInstance.connected && !options.forceNew) {
    return socketInstance;
  }
  if (socketInstance && (options.forceNew || !socketInstance.connected)) {
    try {
      socketInstance.disconnect();
    } catch (_) {}
    socketInstance = null;
  }

  const win = options.win || (typeof window !== "undefined" ? window : null);
  const ioFactory = options.io || (typeof io !== "undefined" ? io : win?.io);

  if (typeof ioFactory !== "function") {
    console.warn("[SOCKET] Socket.IO client library (io) is not available.");
    currentState = ConnectionState.ERROR;
    telemetry.state = ConnectionState.ERROR;
    telemetry.lastError = new Error("Socket.IO client library not found");
    notifyConnectionChange();
    return null;
  }

  const targetUrl = options.url || resolveSocketUrl(options.apiBase, { win });

  const socketOptions = {
    transports: ["websocket", "polling"],
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: options.reconnectionDelay ?? 1000,
    reconnectionDelayMax: options.reconnectionDelayMax ?? 30000,
    randomizationFactor: options.randomizationFactor ?? 0.5,
    timeout: options.timeout ?? 20000,
    autoConnect: options.autoConnect !== false,
  };

  console.log("[SOCKET] Connecting to:", targetUrl, "with backoff options:", {
    delay: socketOptions.reconnectionDelay,
    maxDelay: socketOptions.reconnectionDelayMax,
    jitter: socketOptions.randomizationFactor,
  });

  currentState = ConnectionState.CONNECTING;
  telemetry.state = ConnectionState.CONNECTING;
  notifyConnectionChange();

  const socket = ioFactory(targetUrl, socketOptions);
  socketInstance = socket;

  // ── Lifecycle Event Handlers ──
  socket.on("connect", () => {
    currentState = ConnectionState.CONNECTED;
    telemetry.state = ConnectionState.CONNECTED;
    telemetry.connectedAt = Date.now();
    telemetry.reconnectAttempts = 0;
    telemetry.lastError = null;
    telemetry.disconnectReason = null;
    console.log("[SOCKET] Connected successfully. Socket ID:", socket.id);
    notifyConnectionChange({ socketId: socket.id });
    options.handlers?.onConnect?.();
  });

  socket.on("disconnect", (reason) => {
    const isManual = reason === "io client disconnect" || reason === "client_manual_disconnect";
    currentState = isManual ? ConnectionState.DISCONNECTED : ConnectionState.RECONNECTING;
    telemetry.state = currentState;
    telemetry.disconnectedAt = Date.now();
    telemetry.disconnectReason = reason;
    console.warn("[SOCKET] Disconnected. Reason:", reason, "Next state:", currentState);
    notifyConnectionChange({ reason });
    options.handlers?.onDisconnect?.();
  });

  socket.on("connect_error", (err) => {
    telemetry.lastError = err;
    currentState = ConnectionState.RECONNECTING;
    telemetry.state = currentState;
    console.warn("[SOCKET] Connection error:", err.message);
    notifyConnectionChange({ error: err });
  });

  // Socket.IO Manager reconnection telemetry
  if (socket.io) {
    socket.io.on("reconnect_attempt", (attemptNumber) => {
      telemetry.reconnectAttempts = attemptNumber;
      currentState = ConnectionState.RECONNECTING;
      telemetry.state = currentState;
      console.log(`[SOCKET] Reconnection attempt #${attemptNumber} (exponential backoff with jitter)`);
      notifyConnectionChange({ attempt: attemptNumber });
    });

    socket.io.on("reconnect", (attemptNumber) => {
      currentState = ConnectionState.CONNECTED;
      telemetry.state = currentState;
      telemetry.connectedAt = Date.now();
      telemetry.reconnectAttempts = 0;
      telemetry.lastError = null;
      console.log(`[SOCKET] Reconnected successfully after ${attemptNumber} attempts`);
      notifyConnectionChange();
    });

    socket.io.on("reconnect_error", (err) => {
      telemetry.lastError = err;
      console.warn("[SOCKET] Reconnection error:", err.message);
    });

    socket.io.on("reconnect_failed", () => {
      currentState = ConnectionState.ERROR;
      telemetry.state = currentState;
      telemetry.maxReconnectAttemptsReached = true;
      console.error("[SOCKET] Reconnection failed: maximum attempts reached.");
      notifyConnectionChange();
    });
  }

  // ── Data Ingestion & Dual-Mapping ──
  const handleIncomingNews = (data) => {
    const normalized = {
      count: (typeof data?.count === "number")
        ? data.count
        : (Array.isArray(data?.articles) ? data.articles.length : 0),
      total: (typeof data?.total === "number") ? data.total : 0,
      articles: Array.isArray(data?.articles) ? data.articles : [],
      updated: data?.updated || new Date().toISOString(),
      raw: data,
    };
    dispatchToSet(newsBatchListeners, normalized, "news_batch");
    options.handlers?.onNewArticles?.(normalized);
  };

  socket.on("new_articles", handleIncomingNews);
  socket.on("news_batch", handleIncomingNews);

  const handleStatsUpdate = (data) => {
    const normalized = {
      total: (typeof data?.total === "number") ? data.total : 0,
      updated: data?.updated || new Date().toISOString(),
      raw: data,
    };
    dispatchToSet(statsUpdateListeners, normalized, "stats_update");
    options.handlers?.onInit?.(normalized);
  };

  socket.on("init", handleStatsUpdate);
  socket.on("stats_update", handleStatsUpdate);

  socket.on("trending_update", (data) => {
    dispatchToSet(trendingUpdateListeners, data, "trending_update");
  });

  socket.on("monitoring_log", (data) => {
    dispatchToSet(monitoringLogListeners, data, "monitoring_log");
  });

  // ── Browser Remote Event Listeners ──
  socket.on("browser_loading", (data) => {
    dispatchToSet(browserLoadingListeners, data, "browser_loading");
  });

  socket.on("browser_snapshot", (data) => {
    dispatchToSet(browserSnapshotListeners, data, "browser_snapshot");
  });

  socket.on("browser_tab_opened", (data) => {
    dispatchToSet(browserTabOpenedListeners, data, "browser_tab_opened");
  });

  return socket;
}

/**
 * Connect or re-connect socket.
 */
export function connectSocket(options = {}) {
  if (!socketInstance) {
    return initSocket(options);
  }
  if (!socketInstance.connected) {
    socketInstance.connect();
  }
  return socketInstance;
}

/**
 * Gracefully disconnects the active Socket.IO connection.
 */
export function disconnectSocket() {
  if (socketInstance) {
    try {
      socketInstance.disconnect();
    } catch (_) {}
    currentState = ConnectionState.DISCONNECTED;
    telemetry.state = ConnectionState.DISCONNECTED;
    telemetry.disconnectedAt = Date.now();
    telemetry.disconnectReason = "client_manual_disconnect";
    notifyConnectionChange({ reason: "client_manual_disconnect" });
    socketInstance = null;
  }
}

/**
 * Returns the underlying raw Socket.IO instance or null.
 */
export function getSocket() {
  return socketInstance;
}

/**
 * Returns true if socket exists and is actively connected.
 */
export function isConnected() {
  return Boolean(socketInstance?.connected);
}

/**
 * Returns current connection state enum.
 */
export function getConnectionState() {
  return currentState;
}

/**
 * Returns telemetry metrics snapshot.
 */
export function getTelemetry() {
  return {
    ...telemetry,
    eventsReceivedByType: { ...telemetry.eventsReceivedByType },
  };
}

/**
 * Resets telemetry metrics.
 */
export function resetTelemetry() {
  telemetry.totalEventsReceived = 0;
  telemetry.eventsReceivedByType = {};
  telemetry.reconnectAttempts = 0;
  telemetry.lastError = null;
  telemetry.connectedAt = null;
  telemetry.disconnectedAt = null;
  telemetry.disconnectReason = null;
}

// ── Clean Pub/Sub Subscription APIs ────────────────────────────────

/**
 * Subscribes to connection state changes. Immediately invokes handler with current state.
 * @param {Function} handler ({ state, isConnected, attempt, error, reason }) => void
 * @returns {Function} Unsubscribe closure
 */
export function onConnectionChange(handler) {
  if (typeof handler !== "function") return () => false;
  connectionChangeListeners.add(handler);
  try {
    handler({
      state: currentState,
      isConnected: currentState === ConnectionState.CONNECTED,
      attempt: telemetry.reconnectAttempts,
      error: telemetry.lastError,
      reason: telemetry.disconnectReason,
    });
  } catch (err) {
    console.error("[SOCKET] Error in initial onConnectionChange invocation:", err);
  }
  return () => connectionChangeListeners.delete(handler);
}

/**
 * Subscribes to new article batches (handles both "new_articles" and "news_batch").
 * @param {Function} handler ({ count, total, articles, updated }) => void
 * @returns {Function} Unsubscribe closure
 */
export function onNewsBatch(handler) {
  if (typeof handler !== "function") return () => false;
  newsBatchListeners.add(handler);
  return () => newsBatchListeners.delete(handler);
}

/**
 * Subscribes to stats updates (handles both "init" and "stats_update").
 * @param {Function} handler ({ total, updated }) => void
 * @returns {Function} Unsubscribe closure
 */
export function onStatsUpdate(handler) {
  if (typeof handler !== "function") return () => false;
  statsUpdateListeners.add(handler);
  return () => statsUpdateListeners.delete(handler);
}

/**
 * Subscribes to trending stories recalculation updates.
 * @param {Function} handler (data) => void
 * @returns {Function} Unsubscribe closure
 */
export function onTrendingUpdate(handler) {
  if (typeof handler !== "function") return () => false;
  trendingUpdateListeners.add(handler);
  return () => trendingUpdateListeners.delete(handler);
}

/**
 * Subscribes to scraper monitoring logs.
 * @param {Function} handler (logEntry) => void
 * @returns {Function} Unsubscribe closure
 */
export function onMonitoringLog(handler) {
  if (typeof handler !== "function") return () => false;
  monitoringLogListeners.add(handler);
  return () => monitoringLogListeners.delete(handler);
}

// ── Browser Socket Subscriptions & Action Emitters ─────────────────

export function onBrowserLoading(handler) {
  if (typeof handler !== "function") return () => false;
  browserLoadingListeners.add(handler);
  return () => browserLoadingListeners.delete(handler);
}

export function onBrowserSnapshot(handler) {
  if (typeof handler !== "function") return () => false;
  browserSnapshotListeners.add(handler);
  return () => browserSnapshotListeners.delete(handler);
}

export function onBrowserTabOpened(handler) {
  if (typeof handler !== "function") return () => false;
  browserTabOpenedListeners.add(handler);
  return () => browserTabOpenedListeners.delete(handler);
}

export function emitSocketEvent(eventName, payload) {
  if (!socketInstance || !socketInstance.connected) {
    console.warn(`[SOCKET] Cannot emit "${eventName}": socket not connected.`);
    return false;
  }
  socketInstance.emit(eventName, payload);
  return true;
}

export function emitBrowserOpenTab(tabId) {
  return emitSocketEvent("browser_open_tab", { tab_id: tabId });
}

export function emitBrowserCloseTab(tabId) {
  return emitSocketEvent("browser_close_tab", { tab_id: tabId });
}

export function emitBrowserNavigate(tabId, url) {
  return emitSocketEvent("browser_navigate", { tab_id: tabId, url });
}

export function emitBrowserOpenAndNavigate(tabId, url) {
  return emitSocketEvent("browser_open_and_navigate", { tab_id: tabId, url });
}

export function emitBrowserGoBack(tabId) {
  return emitSocketEvent("browser_go_back", { tab_id: tabId });
}

export function emitBrowserGoForward(tabId) {
  return emitSocketEvent("browser_go_forward", { tab_id: tabId });
}

export function emitBrowserRefresh(tabId) {
  return emitSocketEvent("browser_refresh", { tab_id: tabId });
}

// ── Generic Subscription Utility ───────────────────────────────────

/**
 * Subscribes to an arbitrary custom Socket.IO event.
 * @param {string} eventName
 * @param {Function} handler
 * @returns {Function} Unsubscribe closure
 */
export function on(eventName, handler) {
  if (!eventName || typeof handler !== "function") return () => false;
  if (!genericEventListeners.has(eventName)) {
    genericEventListeners.set(eventName, new Set());
    if (socketInstance) {
      socketInstance.on(eventName, (data) => {
        const set = genericEventListeners.get(eventName);
        if (set) dispatchToSet(set, data, eventName);
      });
    }
  }
  const set = genericEventListeners.get(eventName);
  set.add(handler);
  return () => set.delete(handler);
}

/**
 * Backward compatibility facade matching legacy api.js createSocket(handlers).
 * @deprecated Use initSocket(options) and onNewsBatch/onStatsUpdate instead.
 */
export function createSocket(handlers = {}) {
  return initSocket({ handlers });
}
