/* ==========================================================================
   graph.js — Cytoscape.js network graph rendering + inspector panel.
   Node color encodes entity TYPE. Edge color/style encodes relationship
   STATUS (observed = solid teal, inferred/hypothesis = dashed violet) so
   the investigator can always tell fact from AI-generated hypothesis at a
   glance, per the "distinguish observed evidence from AI-generated
   hypotheses" requirement.
   ========================================================================== */

const TYPE_COLORS = {
  Person: "#4d8fa3",
  Phone: "#d9a441",
  Vehicle: "#c1728f",
  Location: "#6b9e6f",
  Organization: "#6f7fd1",
  Case: "#8a96a6",
  Event: "#59b3b0",
};
const TYPE_SHAPES = {
  Person: "ellipse", Phone: "diamond", Vehicle: "rectangle",
  Location: "triangle", Organization: "hexagon", Case: "octagon", Event: "star",
};

let cy = null;

function renderGraph(container, nodes, edges, onNodeSelect, onEdgeSelect) {
  const elements = [
    ...nodes.map(n => ({ data: { id: n.id, label: n.name, type: n.type } })),
    ...edges.map(e => ({
      data: {
        id: e.id, source: e.source, target: e.target, relType: e.type,
        confidence: e.confidence, timestamp: e.timestamp,
        status: (e.type === "POSSIBLE_SAME_AS" || e.type === "POSSIBLE_LINK") ? "inferred" : "observed",
      },
    })),
  ];

  cy = cytoscape({
    container,
    elements,
    style: [
      {
        selector: "node",
        style: {
          "background-color": (ele) => TYPE_COLORS[ele.data("type")] || "#8a96a6",
          "shape": (ele) => TYPE_SHAPES[ele.data("type")] || "ellipse",
          "label": "data(label)",
          "color": "#c7d0d9",
          "font-size": 9,
          "text-valign": "bottom",
          "text-margin-y": 4,
          "width": 22, "height": 22,
          "border-width": 1.5, "border-color": "#0e1217",
        },
      },
      {
        selector: "node:selected",
        style: { "border-width": 3, "border-color": "#ffffff" },
      },
      {
        selector: "edge",
        style: {
          "width": (ele) => 1 + Math.min(3, (ele.data("confidence") || 0.5) * 3),
          "line-color": (ele) => ele.data("status") === "inferred" ? "#9b72d1" : "#4d8fa3",
          "line-style": (ele) => ele.data("status") === "inferred" ? "dashed" : "solid",
          "target-arrow-shape": "none",
          "curve-style": "bezier",
          "opacity": 0.75,
        },
      },
      {
        selector: "edge:selected",
        style: { "width": 4, "opacity": 1 },
      },
      {
        selector: ".faded",
        style: { "opacity": 0.08 },
      },
      {
        selector: ".highlighted",
        style: { "opacity": 1 },
      },
    ],
    layout: { name: "cose", animate: false, nodeRepulsion: 9000, idealEdgeLength: 70, padding: 30 },
    minZoom: 0.15,
    maxZoom: 4,
    wheelSensitivity: 0.2,
  });

  cy.on("tap", "node", (evt) => {
    highlightNeighborhood(evt.target.id());
    onNodeSelect(evt.target.id());
  });
  cy.on("tap", "edge", (evt) => {
    onEdgeSelect(evt.target.data("id"));
  });
  cy.on("tap", (evt) => {
    if (evt.target === cy) {
      cy.elements().removeClass("faded highlighted");
    }
  });

  return cy;
}

function highlightNeighborhood(nodeId) {
  if (!cy) return;
  const node = cy.getElementById(nodeId);
  const neighborhood = node.closedNeighborhood();
  cy.elements().addClass("faded").removeClass("highlighted");
  neighborhood.removeClass("faded").addClass("highlighted");
}

function filterGraphByType(relType) {
  if (!cy) return;
  cy.edges().forEach(e => {
    e.style("display", (!relType || e.data("relType") === relType) ? "element" : "none");
  });
}

function filterGraphByTime(beforeIso) {
  if (!cy) return;
  cy.edges().forEach(e => {
    const ts = e.data("timestamp");
    const visible = !beforeIso || !ts || ts <= beforeIso;
    e.style("display", visible ? "element" : "none");
  });
}

function searchHighlight(query) {
  if (!cy || !query) { cy && cy.elements().removeClass("faded highlighted"); return; }
  const q = query.toLowerCase();
  const matches = cy.nodes().filter(n => n.data("label").toLowerCase().includes(q));
  cy.elements().addClass("faded").removeClass("highlighted");
  matches.union(matches.closedNeighborhood()).removeClass("faded").addClass("highlighted");
  if (matches.length) cy.animate({ fit: { eles: matches, padding: 80 } }, { duration: 300 });
}
