const API = "http://localhost:5000/api/news";
const COLLECT_API = "http://localhost:5000/api/collect-md";
let currentPage = 1;
let activeSource = "";
let searchQuery = "";
let totalNew = 0;
let newArticles = [];
let searchTimer = null;
let sourceConfig = [];

async function fetchSources() {
    try {
        const res = await fetch("http://localhost:5000/api/sources");
        const data = await res.json();
        sourceConfig = data.sources || [];
        renderFilterButtons();
    } catch(e) {
        console.error("Failed to load sources", e);
    }
}

function renderFilterButtons() {
    const toolbar = document.getElementById("toolbar-filters");
    if (!toolbar) return;
    
    let html = `<span class="filter-label">กรอง :</span>
                <button class="filter-btn ${activeSource === "" ? "active" : ""}" data-source="">ทั้งหมด</button>`;
    
    sourceConfig.forEach(s => {
        html += `<button class="filter-btn ${activeSource === s.name ? "active" : ""}" data-source="${escAttr(s.name)}">${esc(s.name)} <span style="font-size: 0.6rem; color: var(--muted); margin-left: 2px;">(${s.count})</span></button>`;
    });
    
    html += `<input class="search-box" id="search-input" type="text" placeholder="ค้นหาข่าว..." value="${searchQuery}">`;
    toolbar.innerHTML = html;
    
    toolbar.querySelectorAll(".filter-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            toolbar.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            activeSource = btn.dataset.source;
            fetchPage(1);
        });
    });
    
    const searchInput = document.getElementById("search-input");
    if (searchInput) {
        searchInput.addEventListener("input", e => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => {
                searchQuery = e.target.value.trim();
                fetchPage(1);
            }, 400);
        });
    }
}

function getSourceColor(name) {
    const s = sourceConfig.find(x => x.name === name);
    return s ? s.color : "var(--accent)";
}

// โ”€โ”€ WebSocket โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
const socket = io("http://localhost:5000");

socket.on("connect", () => {
    setWsBadge(true);
});
socket.on("disconnect", () => {
    setWsBadge(false);
});
socket.on("init", async (data) => {
    document.getElementById("stat-total").textContent = data.total ?? "—";
    document.getElementById("updated-bar").textContent = `อัปเดตล่าสุด : ${data.updated}`;
    await fetchSources();
    fetchPage(1);
});
socket.on("new_articles", (data) => {
    totalNew += data.count;
    document.getElementById("stat-new").textContent = totalNew;
    document.getElementById("stat-total").textContent = data.total;
    document.getElementById("updated-bar").textContent = `อัปเดตล่าสุด : ${data.updated}`;
    newArticles = [...data.articles, ...newArticles];
    updateTicker(data.articles.map(a => a.title));
    showToast(`✅ มีข่าวใหม่ ${data.count} บทความ — คลิกเพื่อดู`);
});

function setWsBadge(ok) {
    document.getElementById("ws-dot").className = "dot " + (ok ? "connected" : "error");
    document.getElementById("ws-label").textContent = ok ? "Live" : "ออฟไลน์";
}

// โ”€โ”€ Fetch page โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
async function fetchPage(page) {
    currentPage = page;
    document.getElementById("news-grid").innerHTML =
        `<div class="loading"><div class="spinner"></div>กำลังโหลด...</div>`;

    const params = new URLSearchParams({ page });
    if (activeSource) params.set("source", activeSource);
    if (searchQuery) params.set("q", searchQuery);

    try {
        const res = await fetch(`${API}?${params}`);
        const data = await res.json();
        renderGrid(data);
        renderPagination(data);
        document.getElementById("stat-total").textContent = data.total;
        document.getElementById("updated-bar").textContent = `อัปเดตล่าสุด : ${data.updated}`;
        updateTicker(data.news.slice(0, 15).map(n => n.title));
    } catch (e) {
        document.getElementById("news-grid").innerHTML =
            `<div class="loading">❌ เชื่อมต่อ API ไม่ได้</div>`;
    }
}

// โ”€โ”€ Render grid โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
function renderGrid(data) {
    const grid = document.getElementById("news-grid");
    if (!data.news.length) {
        grid.innerHTML = `<div class="loading">ไม่พบข่าว</div>`;
        return;
    }
    const newUrls = new Set(newArticles.map(a => a.url));
    grid.innerHTML = data.news.map((n, i) => {
        const hasUrl = !!n.url;
        const summaryAttrs = hasUrl
            ? `data-url="${escAttr(n.url)}" data-title="${escAttr(n.title || "")}"`
            : `data-url="" data-title="${escAttr(n.title || "")}" aria-disabled="true"`;
        const summaryClass = hasUrl ? "summary-btn" : "summary-btn is-disabled";

        return `
      <a class="card ${newUrls.has(n.url) ? "is-new" : ""}"
         href="${n.url || '#'}" target="_blank" rel="noopener"
         style="animation-delay:${i * 25}ms">
        <span class="${summaryClass}" role="button" tabindex="0" ${summaryAttrs}>สรุป</span>
        ${n.image_url
                ? `<div class="card-img-wrap">
               <img class="card-img" src="${esc(n.image_url)}" alt=""
                    loading="lazy" onerror="this.parentElement.style.display='none'">
             </div>`
                : ""}
        <div class="card-body">
          <div class="card-source">
            <span class="src-dot" style="background-color: ${getSourceColor(n.source)}"></span>
            <span class="source-name">${esc(n.source)}</span>
            ${newUrls.has(n.url) ? '<span class="badge-new">NEW</span>' : ""}
          </div>
          <div class="card-title">${esc(n.title)}</div>
          <div class="card-summary">${esc(n.summary || "")}</div>
          <div class="card-footer">
            <span class="card-time">${n.fetched_at || ""}</span>
            <span class="card-arrow">โ’</span>
          </div>
        </div>
      </a>
    `;
    }).join("");
}

// โ”€โ”€ Pagination โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
function renderPagination(data) {
    const pg = document.getElementById("pagination");
    if (data.total_pages <= 1) { pg.innerHTML = ""; return; }

    const { page, total_pages } = data;
    let html = "";
    html += `<button class="page-btn" onclick="fetchPage(${page - 1})" ${page <= 1 ? "disabled" : ""}>โ€น</button>`;

    const start = Math.max(1, page - 2);
    const end = Math.min(total_pages, start + 4);
    if (start > 1) html += `<button class="page-btn" onclick="fetchPage(1)">1</button><span class="page-info">โ€ฆ</span>`;
    for (let p = start; p <= end; p++) {
        html += `<button class="page-btn ${p === page ? "active" : ""}" onclick="fetchPage(${p})">${p}</button>`;
    }
    if (end < total_pages) html += `<span class="page-info">โ€ฆ</span><button class="page-btn" onclick="fetchPage(${total_pages})">${total_pages}</button>`;

    html += `<button class="page-btn" onclick="fetchPage(${page + 1})" ${page >= total_pages ? "disabled" : ""}>โ€บ</button>`;
    html += `<span class="page-info">${data.total} บทความ</span>`;
    pg.innerHTML = html;
}

// โ”€โ”€ Ticker โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
function updateTicker(titles) {
    if (!titles.length) return;
    const doubled = [...titles, ...titles];
    document.getElementById("ticker-track").innerHTML =
        doubled.map(t => `<span>${esc(t)}</span>`).join("");
}

// ── Search/Filter bindings are now handled in renderFilterButtons ──

// โ”€โ”€ Summary action โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
function isSummaryTarget(el) {
    return el && el.classList && el.classList.contains("summary-btn");
}

document.addEventListener("click", async (e) => {
    const btn = e.target.closest(".summary-btn");
    if (!isSummaryTarget(btn)) return;

    e.preventDefault();
    e.stopPropagation();

    if (btn.classList.contains("is-disabled")) {
        showToast("โ ไม่มีลิงก์สำหรับบทความนี้");
        return;
    }

    await runSummary(btn);
});

document.addEventListener("keydown", async (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const btn = e.target.closest(".summary-btn");
    if (!isSummaryTarget(btn)) return;

    e.preventDefault();
    e.stopPropagation();

    if (btn.classList.contains("is-disabled")) {
        showToast("โ ไม่มีลิงก์สำหรับบทความนี้");
        return;
    }

    await runSummary(btn);
});

async function runSummary(btn) {
    const url = btn.dataset.url || "";
    if (!url) {
        showToast("โ ไม่มีลิงก์สำหรับบทความนี้");
        return;
    }

    const original = btn.textContent;
    btn.textContent = "กำลังสรุป...";
    btn.classList.add("is-disabled");

    try {
        const res = await fetch(COLLECT_API, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url })
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
            throw new Error(data.error || "collect failed");
        }
        showToast(`โ… บันทึกไฟล์แล้ว: ${data.path}`);
    } catch (err) {
        showToast(`โ ${err.message || "เกิดข้อผิดพลาด"}`);
    } finally {
        btn.textContent = original;
        btn.classList.remove("is-disabled");
    }
}

// โ”€โ”€ Toast โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
function showToast(msg) {
    const t = document.getElementById("toast");
    t.textContent = msg;
    t.classList.add("show");
}
function dismissToast() {
    document.getElementById("toast").classList.remove("show");
    fetchPage(1);
}
window.dismissToast = dismissToast;

// ── Helpers ───────────────────────────────────────────────────────
function esc(s) {
    return String(s)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}
function escAttr(s) {
    return esc(s).replace(/'/g, "&#39;");
}
