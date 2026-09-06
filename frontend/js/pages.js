/* ==========================================================================
   pages.js — render function per route. Each function receives the
   <main> element and an optional route param, and returns a Promise.
   ========================================================================== */

const Pages = {};

/* ---------------------------------------------------------------------
   DASHBOARD
   --------------------------------------------------------------------- */
Pages.dashboard = async (view, param, isStale) => {
  const d = await Api.dashboard();
  if (isStale && isStale()) return;
  const alerts = (d.alerts || []).filter(Boolean);

  view.innerHTML = `
    <div class="page-header">
      <div><h1>Investigation Dashboard</h1><div class="sub">Overview across all active cases</div></div>
    </div>
    <div class="stat-grid">
      ${statCard("Active cases", d.case_count)}
      ${statCard("Entities tracked", d.entity_count)}
      ${statCard("Observed relationships", d.relationship_count)}
      ${statCard("Potential leads", d.potential_link_count, true)}
      ${statCard("Unresolved matches", d.unresolved_entity_count, d.unresolved_entity_count > 0)}
    </div>
    <div class="two-col">
      <div class="panel">
        <div class="panel-header">Recent investigative activity</div>
        <div class="panel-body" id="recent-activity"></div>
      </div>
      <div class="panel">
        <div class="panel-header">Entities by type</div>
        <div class="panel-body" id="entity-breakdown"></div>
      </div>
    </div>
    ${alerts.length ? `
    <div class="panel">
      <div class="panel-header">Alerts</div>
      <div class="panel-body">
        ${alerts.map(a => `<div class="activity-row"><span class="rel-dot ${a.level === 'high' ? 'inferred' : 'observed'}"></span> ${escapeHtml(a.message)}</div>`).join("")}
      </div>
    </div>` : ""}
  `;

  const activityEl = view.querySelector("#recent-activity");
  activityEl.innerHTML = (d.recent_activity || []).length
    ? d.recent_activity.map(r => `
        <div class="activity-row">
          <span class="rel-dot ${r.status}"></span>
          ${escapeHtml(r.source_name || r.source)} — ${prettyRelType(r.type)} — ${escapeHtml(r.target_name || r.target)}
          <span class="activity-meta">${formatDate(r.timestamp)}</span>
        </div>`).join("")
    : `<div class="empty-state">No recent activity recorded yet.</div>`;

  const breakdownEl = view.querySelector("#entity-breakdown");
  const byType = d.entities_by_type || {};
  const total = Object.values(byType).reduce((a, b) => a + b, 0) || 1;
  breakdownEl.innerHTML = `<ul class="metric-list">` + Object.entries(byType).map(([t, c]) => `
    <li>
      <span>${t}</span>
      <span class="metric-bar-track"><span class="metric-bar-fill" style="width:${(c/total*100).toFixed(0)}%; background:${TYPE_COLORS[t] || '#8a96a6'}"></span></span>
      <span>${c}</span>
    </li>`).join("") + `</ul>`;
};

function statCard(label, value, alertStyle) {
  return `<div class="stat-card ${alertStyle ? 'alert-card' : ''}"><div class="label">${escapeHtml(label)}</div><div class="value">${value ?? 0}</div></div>`;
}
function prettyRelType(t) {
  return (t || "").replace(/_/g, " ").toLowerCase().replace(/^./, c => c.toUpperCase());
}

/* ---------------------------------------------------------------------
   CASES
   --------------------------------------------------------------------- */
Pages.cases = async (view, param, isStale) => {
  const { cases } = await Api.cases();
  if (isStale && isStale()) return;
  view.innerHTML = `
    <div class="page-header"><div><h1>Cases</h1><div class="sub">${cases.length} case(s) in this workspace</div></div></div>
    <div class="case-list">
      ${cases.map(c => `
        <div class="panel case-card" data-case="${c.id}">
          <div class="case-title-row">
            <h3>${escapeHtml(c.name)}</h3>
            <span class="status-pill ${c.status === 'Active' ? 'active' : ''}">${escapeHtml(c.status)}</span>
          </div>
          <span class="case-id">${c.id} · ${escapeHtml(c.type)} · ${c.period_start} → ${c.period_end}</span>
          <p>${escapeHtml(c.description)}</p>
          <div class="case-stats">
            <span>${c.entity_count} entities involved</span>
          </div>
        </div>`).join("")}
    </div>
  `;
  view.querySelectorAll(".case-card").forEach(card => {
    card.addEventListener("click", () => {
      NexusApp.State.currentCaseId = card.dataset.case;
      document.getElementById("case-select").value = card.dataset.case;
      navigateTo("graph");
    });
  });
};

/* ---------------------------------------------------------------------
   NETWORK GRAPH
   --------------------------------------------------------------------- */
Pages.graph = async (view, param, isStale) => {
  const caseId = NexusApp.State.currentCaseId;
  if (!caseId) { view.innerHTML = emptyState("No case selected."); return; }

  const [caseInfo, graphData] = await Promise.all([Api.case(caseId), Api.caseGraph(caseId)]);
  if (isStale && isStale()) return;

  view.innerHTML = `
    <div class="page-header">
      <div><h1>${escapeHtml(caseInfo.name)}</h1><div class="sub">${caseId} — network graph</div></div>
    </div>
    <div class="panel">
      <div class="graph-toolbar">
        <input type="text" id="graph-search" placeholder="Highlight entity…" style="width:200px" />
        <select id="rel-type-filter">
          <option value="">All relationship types</option>
          ${["CONTACTED","MET","ASSOCIATED_WITH","USED_PHONE","USED_VEHICLE","LOCATED_AT","MEMBER_OF","INVOLVED_IN"]
            .map(t => `<option value="${t}">${prettyRelType(t)}</option>`).join("")}
        </select>
        <label style="font-size:12px;color:var(--text-muted)">Time filter:
          <input type="range" id="time-slider" min="0" max="100" value="100" />
        </label>
        <span id="time-slider-label" style="font-size:11.5px;color:var(--text-faint)"></span>
      </div>
      <div class="graph-layout">
        <div class="graph-canvas-wrap">
          <div id="cy"></div>
          <div class="graph-legend">
            ${Object.entries(TYPE_COLORS).map(([t,c]) => `<span class="legend-item"><span class="legend-swatch" style="background:${c}"></span>${t}</span>`).join("")}
            <span class="legend-item"><span class="legend-swatch" style="background:var(--observed)"></span>Observed link</span>
            <span class="legend-item"><span class="legend-swatch" style="background:var(--inferred)"></span>Inferred / hypothesis</span>
          </div>
        </div>
        <div class="inspector panel" id="inspector">
          <div class="inspector-empty">Select a node or relationship to inspect its details and supporting evidence.</div>
        </div>
      </div>
    </div>
  `;

  if (!graphData.nodes.length) {
    view.querySelector(".graph-layout").innerHTML = emptyState(graphData.message || "No graph data available for this case yet.");
    return;
  }

  const timestamps = graphData.edges.map(e => e.timestamp).filter(Boolean).sort();
  const minT = timestamps[0], maxT = timestamps[timestamps.length - 1];

  renderGraph(
    view.querySelector("#cy"),
    graphData.nodes, graphData.edges,
    (nodeId) => showNodeInspector(nodeId),
    (edgeId) => showEdgeInspector(edgeId, graphData.edges),
  );

  view.querySelector("#graph-search").addEventListener("input", (e) => searchHighlight(e.target.value));
  view.querySelector("#rel-type-filter").addEventListener("change", (e) => filterGraphByType(e.target.value));
  const slider = view.querySelector("#time-slider");
  const label = view.querySelector("#time-slider-label");
  const updateTimeLabel = () => {
    if (!minT || !maxT) { label.textContent = ""; return; }
    const pct = slider.value / 100;
    const cutoff = new Date(new Date(minT).getTime() + pct * (new Date(maxT).getTime() - new Date(minT).getTime()));
    label.textContent = pct >= 1 ? "showing all activity" : "up to " + cutoff.toLocaleDateString();
    filterGraphByTime(pct >= 1 ? null : cutoff.toISOString());
  };
  slider.addEventListener("input", updateTimeLabel);
  updateTimeLabel();
};

async function showNodeInspector(nodeId) {
  const panel = document.getElementById("inspector");
  panel.innerHTML = `<div class="loading-state"><span class="spinner"></span></div>`;
  try {
    const [entity, neighborsRes] = await Promise.all([Api.entity(nodeId), Api.neighbors(nodeId)]);
    const neighbors = neighborsRes.neighbors || [];
    panel.innerHTML = `
      <div class="panel-body">
        <h2>${escapeHtml(entity.name)}</h2>
        <div class="inspector-type">${entity.type}${(entity.attributes.aliases || []).length ? " · aka " + entity.attributes.aliases.map(escapeHtml).join(", ") : ""}</div>
        <div style="margin-top:12px">
          <div class="kv-row"><span class="k">Entity ID</span><span class="v" style="font-family:var(--font-mono)">${entity.id}</span></div>
          ${entity.attributes.reported_age !== undefined ? `<div class="kv-row"><span class="k">Reported age</span><span class="v">${entity.attributes.reported_age}</span></div>` : ""}
          ${entity.attributes.nationality ? `<div class="kv-row"><span class="k">Nationality</span><span class="v">${escapeHtml(entity.attributes.nationality)}</span></div>` : ""}
          ${entity.attributes.number ? `<div class="kv-row"><span class="k">Number</span><span class="v" style="font-family:var(--font-mono)">${escapeHtml(entity.attributes.number)}</span></div>` : ""}
          ${entity.attributes.plate ? `<div class="kv-row"><span class="k">Plate</span><span class="v" style="font-family:var(--font-mono)">${escapeHtml(entity.attributes.plate)}</span></div>` : ""}
          ${entity.attributes.org_type ? `<div class="kv-row"><span class="k">Organization type</span><span class="v">${escapeHtml(entity.attributes.org_type)}</span></div>` : ""}
          <div class="kv-row"><span class="k">Cases</span><span class="v">${(entity.cases || []).join(", ") || "—"}</span></div>
          <div class="kv-row"><span class="k">Connections</span><span class="v">${entity.connection_count}</span></div>
        </div>
        ${entity.possible_matches && entity.possible_matches.length ? `
          <div style="margin-top:12px">
            <div class="kv-row"><span class="k">Possible identity match</span></div>
            <span class="chip inferred">Needs review — see Entity Resolution</span>
          </div>` : ""}
        <div class="conn-list">
          <div class="kv-row"><span class="k">Direct connections (${neighbors.length})</span></div>
          ${neighbors.slice(0, 25).map(n => `
            <div class="conn-item" data-nid="${n.id}">
              <span>${escapeHtml(n.name)}</span>
              <span class="t">${n.type} · ${n.relationship_count}×</span>
            </div>`).join("")}
        </div>
      </div>
    `;
    panel.querySelectorAll(".conn-item").forEach(item => {
      item.addEventListener("click", () => {
        if (cy) { cy.getElementById(item.dataset.nid).select(); highlightNeighborhood(item.dataset.nid); }
        showNodeInspector(item.dataset.nid);
      });
    });
  } catch (e) {
    panel.innerHTML = `<div class="error-state">Could not load entity: ${escapeHtml(e.message)}</div>`;
  }
}

async function showEdgeInspector(edgeId) {
  const panel = document.getElementById("inspector");
  panel.innerHTML = `<div class="loading-state"><span class="spinner"></span></div>`;
  try {
    const rel = await Api.relationship(edgeId);
    const status = rel.status;
    panel.innerHTML = `
      <div class="panel-body">
        <h2>${prettyRelType(rel.type)}</h2>
        <div class="inspector-type">${escapeHtml(rel.source_name)} → ${escapeHtml(rel.target_name)}</div>
        <div style="margin-top:12px">
          <span class="chip ${status}">${statusLabel(status)}</span>
          <div class="kv-row" style="margin-top:8px"><span class="k">Confidence</span><span class="v">${Math.round((rel.confidence||0)*100)}%</span></div>
          <div class="confidence-bar ${status === 'inferred' ? 'inferred' : ''}"><div class="fill" style="width:${(rel.confidence||0)*100}%"></div></div>
          <div class="kv-row"><span class="k">Recorded</span><span class="v">${formatDate(rel.timestamp)}</span></div>
          ${rel.notes ? `<div class="kv-row"><span class="k">Explanation</span><span class="v">${escapeHtml(rel.notes)}</span></div>` : ""}
        </div>
        <div style="margin-top:14px">
          <div class="kv-row"><span class="k">Source evidence (${(rel.evidence||[]).length})</span></div>
          ${(rel.evidence || []).map(ev => `
            <div class="evidence-card">
              <div class="ev-id">${ev.id} · ${escapeHtml(ev.type)}</div>
              <div class="ev-desc">${escapeHtml(ev.description)}</div>
              <div class="ev-meta"><span>Source: ${escapeHtml(ev.source_record)}</span><span>${formatDate(ev.timestamp)}</span><span>Extraction confidence: ${Math.round((ev.extraction_confidence||0)*100)}%</span></div>
            </div>`).join("") || `<div class="empty-state" style="padding:16px 0">No linked evidence record.</div>`}
        </div>
      </div>
    `;
  } catch (e) {
    panel.innerHTML = `<div class="error-state">Could not load relationship: ${escapeHtml(e.message)}</div>`;
  }
}

function emptyState(msg) { return `<div class="empty-state">${escapeHtml(msg)}</div>`; }

/* ---------------------------------------------------------------------
   ENTITY RESOLUTION / REVIEW QUEUE
   --------------------------------------------------------------------- */
Pages.resolution = async (view, param, isStale) => {
  const { queue, message } = await Api.reviewQueue();
  if (isStale && isStale()) return;
  view.innerHTML = `
    <div class="page-header"><div><h1>Entity Resolution — Review Queue</h1><div class="sub">Possible duplicate identities flagged by automated similarity scanning. Every suggestion needs investigator confirmation before it is treated as fact.</div></div></div>
    <div id="queue-container"></div>
  `;
  const container = view.querySelector("#queue-container");
  if (!queue || !queue.length) { container.innerHTML = emptyState(message || "No entity matches currently awaiting review."); return; }

  container.innerHTML = queue.map(q => `
    <div class="panel review-card" data-rel="${q.relationship_id}">
      <div class="review-title-row">
        <div class="review-names">${escapeHtml(q.entity_a.name)}<span class="vs">≟</span>${escapeHtml(q.entity_b.name)}</div>
        <span class="confidence-tag">${Math.round(q.confidence*100)}% confidence</span>
      </div>
      <ul class="reason-list">${q.reasons.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ul>
      ${q.contradictions.length ? `<ul class="contradiction-list">${q.contradictions.map(c => `<li>${escapeHtml(c)}</li>`).join("")}</ul>` : ""}
      <div class="review-actions">
        <button class="btn primary" data-action="accept">Accept Match</button>
        <button class="btn danger" data-action="reject">Reject Match</button>
        <button class="btn ghost" data-action="evidence">Review Evidence</button>
      </div>
      <div class="evidence-slot" style="margin-top:10px"></div>
    </div>
  `).join("");

  container.querySelectorAll(".review-card").forEach(card => {
    const relId = card.dataset.rel;
    card.querySelector('[data-action="accept"]').addEventListener("click", () => resolveMatch(relId, "accept", card));
    card.querySelector('[data-action="reject"]').addEventListener("click", () => resolveMatch(relId, "reject", card));
    card.querySelector('[data-action="evidence"]').addEventListener("click", async () => {
      const slot = card.querySelector(".evidence-slot");
      if (slot.dataset.loaded) { slot.style.display = slot.style.display === "none" ? "block" : "none"; return; }
      try {
        const rel = await Api.relationship(relId);
        slot.innerHTML = (rel.evidence || []).map(ev => `
          <div class="evidence-card">
            <div class="ev-id">${ev.id} · ${escapeHtml(ev.type)}</div>
            <div class="ev-desc">${escapeHtml(ev.description)}</div>
            <div class="ev-meta"><span>Source: ${escapeHtml(ev.source_record)}</span><span>${formatDate(ev.timestamp)}</span></div>
          </div>`).join("") || emptyState("No linked evidence record.");
        slot.dataset.loaded = "1";
      } catch (e) { slot.innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`; }
    });
  });
};

async function resolveMatch(relId, action, card) {
  card.querySelectorAll(".btn").forEach(b => b.disabled = true);
  try {
    if (action === "accept") await Api.acceptMatch(relId); else await Api.rejectMatch(relId);
    showToast(`Match ${action === "accept" ? "accepted" : "rejected"}. Decision recorded.`);
    card.style.opacity = "0.4";
    setTimeout(() => card.remove(), 350);
    NexusApp.refreshBadges();
  } catch (e) {
    showToast("Action failed: " + e.message, true);
    card.querySelectorAll(".btn").forEach(b => b.disabled = false);
  }
}

/* ---------------------------------------------------------------------
   POTENTIAL HIDDEN LINKS
   --------------------------------------------------------------------- */
Pages.links = async (view, param, isStale) => {
  const caseId = NexusApp.State.currentCaseId;
  const { potential_links, message } = await Api.potentialLinks(caseId);
  if (isStale && isStale()) return;
  view.innerHTML = `
    <div class="page-header"><div><h1>Potential Hidden Links</h1><div class="sub">AI-generated investigative leads based on shared associates, locations, vehicles and organizations. These are hypotheses for investigation, not confirmed relationships.</div></div></div>
    <div id="links-container"></div>
  `;
  const container = view.querySelector("#links-container");
  if (!potential_links || !potential_links.length) { container.innerHTML = emptyState(message || "No potential hidden links detected for this case."); return; }

  container.innerHTML = potential_links.map(l => `
    <div class="panel review-card" data-link="${l.id}">
      <div class="review-title-row">
        <div class="review-names">${escapeHtml(l.name_a)}<span class="vs">&harr;</span>${escapeHtml(l.name_b)}</div>
        <span class="confidence-tag">${Math.round(l.confidence*100)}% confidence</span>
      </div>
      <ul class="reason-list">${l.reasons.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ul>
      <div class="evidence-chain">
        ${l.evidence_chain.map((n,i) => `<span class="chain-node">${escapeHtml(n)}</span>${i < l.evidence_chain.length-1 ? '<span class="chain-arrow">&rarr;</span>' : ''}`).join("")}
      </div>
      <span class="chip inferred">AI-generated investigative lead</span>
      <div class="review-actions" style="margin-top:12px">
        <button class="btn primary" data-action="investigate">Investigate</button>
        <button class="btn ghost" data-action="mark_for_review">Mark for Review</button>
        <button class="btn danger" data-action="dismiss">Dismiss</button>
      </div>
    </div>
  `).join("");

  container.querySelectorAll(".review-card").forEach(card => {
    const linkId = card.dataset.link;
    card.querySelectorAll(".review-actions .btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        card.querySelectorAll(".btn").forEach(b => b.disabled = true);
        try {
          await Api.reviewLink(linkId, btn.dataset.action);
          showToast(`Lead marked: ${btn.dataset.action.replace(/_/g," ")}.`);
          if (btn.dataset.action === "dismiss") { card.style.opacity = "0.4"; setTimeout(() => card.remove(), 350); }
          else { btn.style.background = "var(--accept-bg)"; btn.style.borderColor = "var(--accept)"; btn.style.color = "var(--accept)"; }
          NexusApp.refreshBadges();
        } catch (e) { showToast("Action failed: " + e.message, true); card.querySelectorAll(".btn").forEach(b => b.disabled = false); }
      });
    });
  });
};

/* ---------------------------------------------------------------------
   ANALYTICS
   --------------------------------------------------------------------- */
Pages.analytics = async (view, param, isStale) => {
  const caseId = NexusApp.State.currentCaseId;
  if (!caseId) { view.innerHTML = emptyState("No case selected."); return; }
  const a = await Api.analytics(caseId);
  if (isStale && isStale()) return;
  view.innerHTML = `
    <div class="page-header"><div><h1>Network Analytics</h1><div class="sub">${a.node_count} entities · ${a.edge_count} observed relationships · ${a.community_count} community cluster(s)</div></div></div>
    <div class="two-col">
      <div class="panel">
        <div class="panel-header">Network connectivity — most connected entities</div>
        <div class="panel-body">${metricList(a.top_connectivity)}</div>
      </div>
      <div class="panel">
        <div class="panel-header">Bridge score — entities linking otherwise separate clusters</div>
        <div class="panel-body">${metricList(a.top_bridges)}</div>
      </div>
    </div>
    <div class="summary-note">These metrics describe network structure only (connectivity, bridging, clustering). They are not a measure of guilt or criminality, and are intended to help investigators prioritize which entities to review first.</div>
  `;
};
function metricList(items) {
  if (!items || !items.length) return emptyState("Not enough data yet.");
  const max = Math.max(...items.map(i => i.score), 0.0001);
  return `<ul class="metric-list">` + items.map(i => `
    <li>
      <span>${escapeHtml(i.name)} <span style="color:var(--text-faint);font-size:11px">(${i.type})</span></span>
      <span class="metric-bar-track"><span class="metric-bar-fill" style="width:${(i.score/max*100).toFixed(0)}%"></span></span>
      <span style="font-family:var(--font-mono);font-size:11.5px">${i.score}</span>
    </li>`).join("") + `</ul>`;
}

/* ---------------------------------------------------------------------
   TIMELINE
   --------------------------------------------------------------------- */
Pages.timeline = async (view, param, isStale) => {
  const caseId = NexusApp.State.currentCaseId;
  if (!caseId) { view.innerHTML = emptyState("No case selected."); return; }
  const t = await Api.timeline(caseId);
  if (isStale && isStale()) return;
  view.innerHTML = `
    <div class="page-header"><div><h1>Temporal Analysis</h1><div class="sub">Investigation activity over time</div></div></div>
    <div class="panel panel-body">
      <div class="timeline-current-date" id="tl-date"></div>
      <input type="range" class="timeline-slider" id="tl-slider" min="0" max="100" value="100" />
      <div class="event-list" id="tl-events"></div>
    </div>
  `;
  const events = (t.events || []).slice().sort((a,b) => a.timestamp.localeCompare(b.timestamp));
  const dateEl = view.querySelector("#tl-date");
  const eventsEl = view.querySelector("#tl-events");
  const slider = view.querySelector("#tl-slider");

  if (!events.length) { eventsEl.innerHTML = emptyState("No timestamped events recorded for this case."); dateEl.textContent = ""; }
  else {
    const first = new Date(events[0].timestamp), last = new Date(events[events.length-1].timestamp);
    const render = () => {
      const pct = slider.value / 100;
      const cutoff = new Date(first.getTime() + pct * (last.getTime() - first.getTime()));
      dateEl.textContent = pct >= 1 ? "Full investigation period" : "Up to " + cutoff.toLocaleDateString();
      const visible = events.filter(e => new Date(e.timestamp) <= cutoff);
      eventsEl.innerHTML = visible.length
        ? visible.map(e => `<div class="event-row"><span class="event-date">${formatDate(e.timestamp)}</span><span>${escapeHtml(e.type)} — ${escapeHtml(e.description)}</span></div>`).join("")
        : emptyState("No events in this window yet.");
    };
    slider.addEventListener("input", render);
    render();
  }
};

/* ---------------------------------------------------------------------
   NL QUERY
   --------------------------------------------------------------------- */
Pages.query = async (view) => {
  const examples = [
    "Show people connected to Rajesh Kumar within 2 degrees",
    "Which entities connect Case 001 and Case 002?",
    "Show important bridge entities",
    "Show highly connected entities",
  ];
  view.innerHTML = `
    <div class="page-header"><div><h1>Investigation Query</h1><div class="sub">Controlled natural-language queries over the current network. Runs entirely locally — no external LLM required.</div></div></div>
    <div class="query-bar">
      <input type="text" id="nl-input" placeholder="Ask a question about the investigation…" />
      <button class="btn primary" id="nl-run">Ask</button>
    </div>
    <div class="query-examples">${examples.map(ex => `<span class="query-example" data-q="${escapeHtml(ex)}">${escapeHtml(ex)}</span>`).join("")}</div>
    <div id="query-result"></div>
  `;
  const input = view.querySelector("#nl-input");
  const resultEl = view.querySelector("#query-result");
  const run = async () => {
    const q = input.value.trim();
    if (!q) return;
    resultEl.innerHTML = `<div class="loading-state"><span class="spinner"></span></div>`;
    try {
      const res = await Api.nlQuery(q);
      resultEl.innerHTML = `
        <div class="panel panel-body">
          <p>${escapeHtml(res.answer)}</p>
          ${res.results && res.results.length ? `<ul class="metric-list">${res.results.slice(0,20).map(r => `
            <li><span>${escapeHtml(r.name)} <span style="color:var(--text-faint);font-size:11px">(${r.type})</span></span><span style="font-family:var(--font-mono);font-size:11.5px">${r.hops !== undefined ? r.hops + " hop(s)" : (r.score !== undefined ? r.score : "")}</span></li>`).join("")}</ul>` : ""}
        </div>`;
    } catch (e) { resultEl.innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`; }
  };
  view.querySelector("#nl-run").addEventListener("click", run);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") run(); });
  view.querySelectorAll(".query-example").forEach(ex => ex.addEventListener("click", () => { input.value = ex.dataset.q; run(); }));
};

/* ---------------------------------------------------------------------
   INVESTIGATION SUMMARY
   --------------------------------------------------------------------- */
Pages.summary = async (view, param, isStale) => {
  const caseId = NexusApp.State.currentCaseId;
  if (!caseId) { view.innerHTML = emptyState("No case selected."); return; }
  const s = await Api.summary(caseId);
  if (isStale && isStale()) return;
  view.innerHTML = `
    <div class="page-header"><div><h1>Investigation Summary</h1><div class="sub">${escapeHtml(s.case.name)}</div></div></div>
    <div class="panel panel-body">
      <div class="summary-section">
        <h3>Key entities</h3>
        ${listOrEmpty(s.key_entities, e => `${escapeHtml(e.name)} (${e.type}) — connectivity ${e.score}`)}
      </div>
      <div class="summary-section">
        <h3>Important relationships (bridge entities)</h3>
        ${listOrEmpty(s.important_relationships, e => `${escapeHtml(e.name)} (${e.type}) — bridge score ${e.score}`)}
      </div>
      <div class="summary-section">
        <h3>Potential investigative leads</h3>
        ${listOrEmpty(s.potential_investigative_leads, l => `${escapeHtml(l.name_a)} &harr; ${escapeHtml(l.name_b)} — ${Math.round(l.confidence*100)}% confidence`)}
      </div>
      <div class="summary-section">
        <h3>Timeline observations</h3>
        <p style="font-size:13px;color:var(--text-muted)">${escapeHtml(s.timeline_observation)}</p>
      </div>
      <div class="summary-section">
        <h3>Unresolved entities</h3>
        ${listOrEmpty(s.unresolved_entities, m => `${escapeHtml(m.entity_a.name)} ≟ ${escapeHtml(m.entity_b.name)} — ${Math.round(m.confidence*100)}% confidence`)}
      </div>
      <div class="summary-note">${escapeHtml(s.evidence_note)}</div>
    </div>
  `;
};
function listOrEmpty(items, fmt) {
  if (!items || !items.length) return `<p style="font-size:13px;color:var(--text-faint)">None recorded.</p>`;
  return `<ul class="metric-list" style="display:block">` + items.map(i => `<li style="display:block;border:none;padding:5px 0;font-size:13px">${fmt(i)}</li>`).join("") + `</ul>`;
}

/* ---------------------------------------------------------------------
   SEARCH
   --------------------------------------------------------------------- */
Pages.search = async (view, param, isStale) => {
  const q = (param && param.q) || "";
  const { entities, message } = await Api.entities(q);
  if (isStale && isStale()) return;
  view.innerHTML = `
    <div class="page-header"><div><h1>Search results</h1><div class="sub">"${escapeHtml(q)}"</div></div></div>
    <div class="panel" id="search-results"></div>
  `;
  const container = view.querySelector("#search-results");
  if (!entities || !entities.length) { container.innerHTML = emptyState(message || "No results."); return; }
  container.innerHTML = entities.map(e => `
    <div class="entity-row" data-id="${e.id}">
      <span class="entity-type-badge">${e.type}</span>
      <span class="entity-name">${escapeHtml(e.name)}</span>
      <span class="entity-meta">${e.connection_count} connection(s) · ${(e.cases||[]).join(", ") || "no case"}</span>
    </div>`).join("");
  container.querySelectorAll(".entity-row").forEach(row => {
    row.addEventListener("click", async () => {
      navigateTo("graph");
      // wait a tick for graph page to mount, then select the node
      setTimeout(() => {
        if (cy && cy.getElementById(row.dataset.id).length) {
          cy.getElementById(row.dataset.id).select();
          highlightNeighborhood(row.dataset.id);
          showNodeInspector(row.dataset.id);
        }
      }, 500);
    });
  });
};
