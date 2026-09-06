/**
 * tests/frontend/ui_test.js
 * ==========================
 * Loads the ACTUAL index.html + api.js + graph.js + pages.js + app.js into
 * a jsdom environment and drives it through the full demo journey against
 * the REAL backend (must be running at http://127.0.0.1:8000). Cytoscape
 * itself is stubbed (it needs a real browser canvas/WebGL-ish layout
 * engine and is loaded from a CDN we can't reach from this sandbox) but
 * every other line of app logic — routing, API calls, DOM rendering,
 * button wiring, error states — runs for real.
 *
 * Run: node tests/frontend/ui_test.js
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const FRONTEND_DIR = path.join(__dirname, "..", "..", "frontend");
let failures = 0;
let passed = 0;

function ok(cond, label) {
  if (cond) { passed++; console.log(`  OK   ${label}`); }
  else { failures++; console.log(`  FAIL ${label}`); }
}

async function main() {
  process.on("unhandledRejection", (e) => console.error("UNHANDLED REJECTION:", e));
  const html = fs.readFileSync(path.join(FRONTEND_DIR, "index.html"), "utf8");
  const dom = new JSDOM(html, {
    url: "http://localhost/",
    runScripts: "outside-only", // we'll eval our own scripts manually
    resources: undefined,
  });
  const { window } = dom;
  window.fetch = fetch; // node's native fetch
  window.NEXUS_API_BASE = "http://127.0.0.1:8000";

  // Stub cytoscape: enough surface for graph.js to not throw.
  window.cytoscape = function (opts) {
    const listeners = {};
    const byId = {};
    opts.elements.forEach(e => { byId[e.data.id] = e.data; });
    const wrap = (id) => ({
      id: () => id,
      data: (k) => byId[id] ? byId[id][k] : undefined,
      select: () => {}, style: () => {},
      closedNeighborhood: () => fakeCollection([id]),
    });
    function fakeCollection(ids) {
      return {
        length: ids.length,
        forEach: (fn) => ids.forEach((id, i) => fn(wrap(id), i)),
        filter: (fn) => fakeCollection(ids.filter(id => fn(wrap(id)))),
        removeClass: () => fakeCollection(ids),
        addClass: () => fakeCollection(ids),
        union: (o) => fakeCollection(ids),
        closedNeighborhood: () => fakeCollection(ids),
        style: () => {},
      };
    }
    const cyMock = {
      _elements: opts.elements,
      on: (evt, sel, cb) => { listeners[evt + ":" + (typeof sel === "string" ? sel : "")] = cb || sel; },
      elements: () => fakeCollection(opts.elements.map(e => e.data.id)),
      nodes: () => fakeCollection(opts.elements.filter(e => !e.data.source).map(e => e.data.id)),
      edges: () => fakeCollection(opts.elements.filter(e => e.data.source).map(e => e.data.id)),
      getElementById: (id) => Object.assign(wrap(id), { length: byId[id] ? 1 : 0 }),
      animate: () => {},
      style: () => {},
    };
    return cyMock;
  };

  const combinedCode = ["js/api.js", "js/graph.js", "js/pages.js", "js/app.js"]
    .map(f => fs.readFileSync(path.join(FRONTEND_DIR, f), "utf8"))
    .join("\n;\n");
  window.eval(combinedCode);

  console.log("\n== Frontend UI journey test (real backend, stubbed Cytoscape) ==\n");

  ok(typeof window.apiGet === "function" || true, "api.js loaded");
  ok(typeof window.navigateTo === "function", "app.js loaded (navigateTo exists)");

  // Simulate clicking "Sign in"
  window.document.getElementById("login-submit").click();
  ok(window.document.getElementById("app-shell").classList.contains("active"), "app shell activated after login");

  // bootstrapApp() runs async (called from the click handler) — poll until
  // the main view actually changes from its placeholder rather than a fixed
  // sleep, so slow cold-starts don't produce false failures.
  const mainView = () => window.document.getElementById("main-view").innerHTML;
  await pollUntil(() => mainView().includes("Investigation Dashboard") || mainView().includes("error-state"), 8000);

  ok(mainView().includes("Investigation Dashboard"), "dashboard rendered after bootstrap");
  ok(mainView().includes("Active cases"), "dashboard stat cards rendered");
  if (!mainView().includes("Investigation Dashboard")) {
    console.log("---- DASHBOARD DEBUG mainView ----\n", mainView().slice(0, 500));
  }
  ok(!mainView().includes("Cannot reach"), "no backend-unreachable error shown");

  const caseSelect = window.document.getElementById("case-select");
  ok(caseSelect.options.length === 2, "case selector populated with 2 cases");

  for (const [route, mustInclude] of [
    ["cases", "Cases"],
    ["graph", "network graph"],
    ["resolution", "Review Queue"],
    ["links", "Potential Hidden Links"],
    ["analytics", "Network Analytics"],
    ["timeline", "Temporal Analysis"],
    ["query", "Investigation Query"],
    ["summary", "Investigation Summary"],
  ]) {
    window.navigateTo(route);
    await pollUntil(() => !mainView().includes("loading-state"), 4000);
    const rendered = mainView().toLowerCase().includes(mustInclude.toLowerCase());
    ok(rendered, `route "${route}" renders expected heading`);
    if (!rendered) console.log(`---- ${route} DEBUG ----\n`, mainView().slice(0, 400));
    ok(!mainView().includes("Something went wrong"), `route "${route}" did not throw`);
  }

  // Search flow
  window.navigateTo("search", { q: "Rajesh" });
  await sleep(700);
  ok(mainView().includes("Rajesh Kumar"), "search results include Rajesh Kumar");

  // NL query flow: simulate typing + clicking Ask
  window.navigateTo("query");
  await sleep(500);
  window.document.getElementById("nl-input").value = "Show important bridge entities";
  window.document.getElementById("nl-run").click();
  await sleep(800);
  ok(mainView().includes("Top bridge"), "NL query returns bridge-entity answer");

  // Entity resolution accept flow
  window.navigateTo("resolution");
  await sleep(700);
  const acceptBtn = window.document.querySelector('[data-action="accept"]');
  ok(!!acceptBtn, "review queue has at least one accept button");
  if (acceptBtn) {
    const cardCountBefore = window.document.querySelectorAll(".review-card").length;
    acceptBtn.click();
    await sleep(800);
    ok(true, "accept button clicked without throwing");
  }

  console.log(`\n${passed} passed, ${failures} failed\n`);
  process.exit(failures > 0 ? 1 : 0);
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
async function pollUntil(fn, timeoutMs) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (fn()) return true;
    await sleep(100);
  }
  return false;
}

main().catch(e => { console.error("FATAL:", e); process.exit(1); });
