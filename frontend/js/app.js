/* ==========================================================================
   app.js — bootstrap, routing, shared chrome (login, nav, case selector,
   global search, toast notifications).
   ========================================================================== */

const State = {
  cases: [],
  currentCaseId: null,
  route: "dashboard",
  routeParam: null,
};

function showToast(message, isError) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.style.borderColor = isError ? "var(--danger)" : "var(--observed)";
  el.classList.add("show");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), 3200);
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

function formatDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

function statusLabel(status) {
  return status === "observed" ? "Observed" : "Inferred / hypothesis";
}

/* ---------------------------------------------------------------------
   Login
   --------------------------------------------------------------------- */
document.getElementById("login-submit").addEventListener("click", async () => {
  document.getElementById("login-screen").style.display = "none";
  document.getElementById("app-shell").classList.add("active");
  await bootstrapApp();
});

/* ---------------------------------------------------------------------
   Bootstrap: check backend health, load cases, wire nav, land on dashboard
   --------------------------------------------------------------------- */
async function bootstrapApp() {
  try {
    await Api.health();
  } catch (e) {
    document.getElementById("main-view").innerHTML = `
      <div class="error-state">
        <p><strong>Cannot reach the Operation Nexus backend API.</strong></p>
        <p>Make sure the backend is running (see README) at ${escapeHtml(API_BASE)},
        then reload this page.</p>
      </div>`;
    return;
  }

  await refreshCaseList();
  await refreshBadges();
  wireNav();
  wireTopbar();
  navigateTo("dashboard");
}

async function refreshCaseList() {
  try {
    const { cases } = await Api.cases();
    State.cases = cases;
    if (!State.currentCaseId && cases.length) State.currentCaseId = cases[0].id;
    const sel = document.getElementById("case-select");
    sel.innerHTML = cases.map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join("");
    sel.value = State.currentCaseId;
  } catch (e) {
    showToast("Could not load case list: " + e.message, true);
  }
}

async function refreshBadges() {
  try {
    const [{ queue }, dash] = await Promise.all([
      Api.reviewQueue().catch(() => ({ queue: [] })),
      Api.dashboard().catch(() => null),
    ]);
    setBadge("badge-resolution", (queue || []).length);
    setBadge("badge-links", dash ? dash.potential_link_count : 0);
  } catch (e) { /* non-fatal */ }
}

function setBadge(id, count) {
  const el = document.getElementById(id);
  if (count > 0) { el.style.display = "flex"; el.textContent = count > 99 ? "99+" : count; }
  else { el.style.display = "none"; }
}

/* ---------------------------------------------------------------------
   Nav / routing
   --------------------------------------------------------------------- */
function wireNav() {
  document.querySelectorAll(".nav-item[data-route]").forEach(btn => {
    btn.addEventListener("click", () => navigateTo(btn.dataset.route));
  });
}

function wireTopbar() {
  document.getElementById("case-select").addEventListener("change", (e) => {
    State.currentCaseId = e.target.value;
    navigateTo(State.route); // re-render current page for new case
  });
  document.getElementById("load-demo-btn").addEventListener("click", async () => {
    const btn = document.getElementById("load-demo-btn");
    btn.disabled = true; btn.textContent = "Loading…";
    try {
      const res = await Api.loadDemo();
      showToast("Operation Nexus demo investigation (re)loaded.");
      await refreshCaseList();
      await refreshBadges();
      navigateTo("dashboard");
    } catch (e) {
      showToast("Failed to load demo: " + e.message, true);
    } finally {
      btn.disabled = false; btn.textContent = "Load Demo Investigation";
    }
  });

  let searchTimer;
  document.getElementById("global-search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    const q = e.target.value.trim();
    if (!q) return;
    searchTimer = setTimeout(() => navigateTo("search", { q }), 350);
  });
  document.getElementById("global-search").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { navigateTo("search", { q: e.target.value.trim() }); }
  });
}

let _renderGeneration = 0;

function navigateTo(route, param) {
  State.route = route;
  State.routeParam = param || null;
  const myGeneration = ++_renderGeneration;
  document.querySelectorAll(".nav-item[data-route]").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.route === route);
  });
  const view = document.getElementById("main-view");
  view.dataset.gen = String(myGeneration);
  view.innerHTML = `<div class="loading-state"><span class="spinner"></span><br/>Loading…</div>`;
  const renderer = Pages[route];
  if (!renderer) {
    view.innerHTML = `<div class="error-state">Unknown view.</div>`;
    return;
  }
  // isStale() lets each page renderer abort its final render if the user
  // has already navigated elsewhere before this page's data finished
  // loading (prevents a slow/stale response from clobbering a newer page).
  const isStale = () => view.dataset.gen !== String(myGeneration);
  renderer(view, param, isStale).catch(err => {
    console.error(err);
    if (isStale()) return;
    view.innerHTML = `<div class="error-state">Something went wrong loading this view: ${escapeHtml(err.message)}</div>`;
  });
}

// Expose for pages.js to call after actions that change counts
window.NexusApp = { navigateTo, refreshBadges, refreshCaseList, showToast, escapeHtml, formatDate, statusLabel, State };
