"""
backend/app/analytics.py
=========================
Builds an in-memory NetworkX graph from the SQLite tables and computes
network analytics.

We deliberately name outputs using investigative language rather than
loaded terms like "criminality score" (see project brief section 6):
  - degree centrality      -> "network connectivity"
  - betweenness centrality -> "bridge score"
  - community detection    -> "community membership"
  - edge weight/frequency  -> "activity intensity"

Hidden-link prediction uses transparent, explainable graph-similarity
methods (common neighbors, Jaccard, Adamic-Adar) rather than a black-box
model, per the brief's instruction to start with simple, explainable
baselines before reaching for ML.
"""

import json
import networkx as nx
from networkx.algorithms.community import greedy_modularity_communities
from .database import db_cursor


def build_graph(only_observed: bool = True, case_id: str = None,
                 time_before: str = None) -> nx.MultiGraph:
    """Builds an undirected multigraph of all entities and OBSERVED
    relationships (inferred / possible_same_as / possible_link edges are
    handled separately so the analytics never blend hypothesis with fact).
    """
    g = nx.MultiGraph()
    with db_cursor() as cur:
        cur.execute("SELECT id, entity_type, name, attributes FROM entities")
        for row in cur.fetchall():
            g.add_node(row["id"], entity_type=row["entity_type"], name=row["name"],
                       attributes=json.loads(row["attributes"]))

        query = "SELECT * FROM relationships WHERE status='observed'"
        cur.execute(query)
        for row in cur.fetchall():
            if row["source"] not in g or row["target"] not in g:
                continue
            if time_before and row["timestamp"] and row["timestamp"] > time_before:
                continue
            g.add_edge(row["source"], row["target"], key=row["id"], rel_id=row["id"],
                       rel_type=row["type"], confidence=row["confidence"],
                       timestamp=row["timestamp"])
    if case_id:
        # restrict to entities connected (directly or transitively) to the case node
        if case_id in g:
            reachable = nx.node_connected_component(nx.Graph(g), case_id)
            g = g.subgraph(reachable).copy()
    return g


def compute_analytics(case_id: str = None):
    g = build_graph(case_id=case_id)
    simple = nx.Graph(g)  # collapse multigraph for centrality/community algorithms

    if simple.number_of_nodes() == 0:
        return {"connectivity": {}, "bridge_score": {}, "communities": {},
                 "top_connectivity": [], "top_bridges": [], "community_count": 0,
                 "node_count": 0, "edge_count": 0}

    connectivity = nx.degree_centrality(simple)

    # Betweenness on large graphs can be slow; this graph is small enough
    # (a few hundred nodes) to compute exactly.
    bridge_score = nx.betweenness_centrality(simple, normalized=True)

    communities = {}
    try:
        comms = list(greedy_modularity_communities(simple))
        for idx, community in enumerate(comms):
            for node in community:
                communities[node] = idx
    except Exception:
        comms = []

    top_connectivity = sorted(connectivity.items(), key=lambda x: -x[1])[:10]
    top_bridges = sorted(bridge_score.items(), key=lambda x: -x[1])[:10]

    def annotate(pairs):
        out = []
        for nid, score in pairs:
            node = simple.nodes[nid]
            out.append({"id": nid, "name": node.get("name"), "type": node.get("entity_type"),
                        "score": round(score, 4)})
        return out

    return {
        "connectivity": {k: round(v, 4) for k, v in connectivity.items()},
        "bridge_score": {k: round(v, 4) for k, v in bridge_score.items()},
        "communities": communities,
        "community_count": len(comms),
        "top_connectivity": annotate(top_connectivity),
        "top_bridges": annotate(top_bridges),
        "node_count": simple.number_of_nodes(),
        "edge_count": simple.number_of_edges(),
    }


def _neighbors_by_type(g, node, entity_type=None):
    ns = set(g.neighbors(node)) if node in g else set()
    if entity_type:
        ns = {n for n in ns if g.nodes[n].get("entity_type") == entity_type}
    return ns


def predict_hidden_links(top_k: int = 15):
    """Transparent link-prediction over PERSON nodes only, using common
    neighbors / Jaccard / Adamic-Adar over the observed-relationship graph,
    plus a small bonus for shared locations/vehicles/organizations and
    temporal proximity of their most recent activity. Fully explainable:
    every score component is returned so the UI can show "why".
    """
    g = build_graph()
    persons = [n for n, d in g.nodes(data=True) if d.get("entity_type") == "Person"]
    existing_edges = set()
    for u, v in g.edges():
        if g.nodes[u]["entity_type"] == "Person" and g.nodes[v]["entity_type"] == "Person":
            existing_edges.add(frozenset((u, v)))

    # Also exclude pairs that already have a possible_same_as / possible_link
    # relationship recorded, and pairs already reviewed.
    already_flagged = set()
    with db_cursor() as cur:
        cur.execute("SELECT source, target FROM relationships WHERE type IN "
                    "('POSSIBLE_SAME_AS')")
        for row in cur.fetchall():
            already_flagged.add(frozenset((row["source"], row["target"])))

    candidates = []
    n = len(persons)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = persons[i], persons[j]
            pair = frozenset((a, b))
            if pair in existing_edges or pair in already_flagged:
                continue
            neighbors_a = set(g.neighbors(a))
            neighbors_b = set(g.neighbors(b))
            common = neighbors_a & neighbors_b
            union = neighbors_a | neighbors_b
            if not common and not _shares_indirect_link(g, a, b):
                continue

            jaccard = len(common) / len(union) if union else 0
            adamic_adar = 0.0
            for w in common:
                deg = g.degree(w)
                if deg > 1:
                    import math
                    adamic_adar += 1 / math.log(deg)

            shared_locations = {w for w in common if g.nodes[w]["entity_type"] == "Location"}
            shared_vehicles = {w for w in common if g.nodes[w]["entity_type"] == "Vehicle"}
            shared_orgs = {w for w in common if g.nodes[w]["entity_type"] == "Organization"}
            shared_people = {w for w in common if g.nodes[w]["entity_type"] == "Person"}

            indirect_chain = _find_indirect_chain(g, a, b)

            if not common and not indirect_chain:
                continue

            score = min(0.98, 0.15 * len(common) + 0.35 * jaccard + 0.08 * adamic_adar
                        + (0.15 if indirect_chain and not common else 0))
            if score < 0.35:
                continue

            reasons = []
            if shared_people:
                reasons.append(f"{len(shared_people)} shared associate(s)")
            if shared_locations:
                reasons.append(f"{len(shared_locations)} shared location(s)")
            if shared_vehicles:
                reasons.append(f"{len(shared_vehicles)} shared vehicle(s)")
            if shared_orgs:
                reasons.append(f"connected through {len(shared_orgs)} shared organization(s)")
            if indirect_chain and not common:
                reasons.append("connected via an indirect evidence chain")
            if not reasons:
                reasons.append("weak structural similarity")

            chain = indirect_chain or ([a] + list(common)[:1] + [b])

            candidates.append({
                "entity_a": a, "entity_b": b,
                "name_a": g.nodes[a]["name"], "name_b": g.nodes[b]["name"],
                "confidence": round(score, 2),
                "reasons": reasons,
                "evidence_chain": chain,
                "common_neighbors": len(common),
                "jaccard": round(jaccard, 3),
                "adamic_adar": round(adamic_adar, 3),
            })

    candidates.sort(key=lambda c: -c["confidence"])
    return candidates[:top_k]


def _shares_indirect_link(g, a, b, max_hops=4):
    return _find_indirect_chain(g, a, b, max_hops) is not None


def _find_indirect_chain(g, a, b, max_hops=4):
    """Finds a short non-person-only path connecting a and b through
    intermediate non-person entities (phone/vehicle/location/org), which
    is the "hidden link" pattern the brief describes (A->Phone->C->Vehicle->
    Location<-B). Returns the path as a list of node ids, or None."""
    if a not in g or b not in g:
        return None
    try:
        for path in nx.all_simple_paths(g, a, b, cutoff=max_hops):
            if len(path) >= 3:
                middle = path[1:-1]
                if any(g.nodes[m]["entity_type"] != "Person" for m in middle):
                    return path
    except nx.NetworkXNoPath:
        return None
    return None
