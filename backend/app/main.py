"""
backend/app/main.py
====================
FastAPI application exposing the Operation Nexus investigative API.

Runs entirely on a local SQLite file + in-memory NetworkX graph — no
external services required. See database.py for the architecture note on
why this is used instead of Neo4j/PostgreSQL for the prototype.
"""

import json
import os
import time
import uuid
from datetime import datetime
from typing import Optional

import re
from contextlib import asynccontextmanager

import networkx as nx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .database import db_cursor, init_db, log_action
from .seed import seed_database
from . import analytics
from . import entity_resolution as ER


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_path = os.path.join(os.path.dirname(__file__), "..", "nexus.db")
    if not os.path.exists(os.path.abspath(db_path)):
        seed_database(reset=True)
    else:
        init_db(reset=False)  # ensure schema exists, keep existing data
    yield


app = FastAPI(
    title="Operation Nexus — Investigative Network Intelligence API",
    description="Prototype API for SIH 2026 PS-189 (AI-Powered Criminal "
                "Network Analysis System). Operates on a fully synthetic "
                "demonstration dataset.",
    version="0.1.0",
    lifespan=lifespan,
)

# --- CORS -------------------------------------------------------------
# The frontend is a static page served separately (e.g. python -m http.server
# or a simple file:// open with a configured API base). Kept permissive for
# local development only; docs/architecture.md notes how this should be
# tightened for any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# --- basic request/response logging + safe error handling -------------
@app.middleware("http")
async def audit_and_guard(request: Request, call_next):
    start = time.time()
    try:
        response = await call_next(request)
    except Exception as exc:  # last-resort guard so the API never hard-crashes
        import traceback
        traceback.print_exc()  # logged server-side for debugging
        return _json_error("An internal error occurred while processing this request.", status_code=500)
    duration_ms = round((time.time() - start) * 1000, 1)
    response.headers["X-Process-Time-ms"] = str(duration_ms)
    return response


def _json_error(message: str, status_code: int = 400):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status_code, content={"error": message})


# ---------------------------------------------------------------------
# Demo mode
# ---------------------------------------------------------------------
@app.post("/api/demo/load")
def load_demo():
    """'Load Demo Investigation' button — (re)seeds Operation Nexus."""
    counts = seed_database(reset=True)
    invalidate_link_cache()
    log_action("LOAD_DEMO", "-", json.dumps(counts))
    return {"message": "Operation Nexus demo investigation loaded.", "counts": counts}


# ---------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------
@app.get("/api/dashboard")
def dashboard():
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) c FROM cases")
        n_cases = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) c FROM entities")
        n_entities = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) c FROM relationships WHERE status='observed'")
        n_rel_observed = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) c FROM relationships WHERE type='POSSIBLE_SAME_AS' AND review_state='pending'")
        n_unresolved = cur.fetchone()["c"]
        cur.execute("SELECT entity_type, COUNT(*) c FROM entities GROUP BY entity_type")
        by_type = {r["entity_type"]: r["c"] for r in cur.fetchall()}
        cur.execute(
            "SELECT r.*, e1.name as source_name, e2.name as target_name FROM relationships r "
            "LEFT JOIN entities e1 ON r.source=e1.id LEFT JOIN entities e2 ON r.target=e2.id "
            "WHERE r.status='observed' ORDER BY r.timestamp DESC LIMIT 8"
        )
        recent = [dict(r) for r in cur.fetchall()]

    links = _cached_predict_hidden_links(top_k=50)

    return {
        "case_count": n_cases,
        "entity_count": n_entities,
        "relationship_count": n_rel_observed,
        "potential_link_count": len(links),
        "unresolved_entity_count": n_unresolved,
        "entities_by_type": by_type,
        "recent_activity": recent,
        "alerts": [
            {"level": "high", "message": f"{len(links)} potential hidden link(s) awaiting review"}
            if links else None,
            {"level": "medium", "message": f"{n_unresolved} entity match(es) awaiting review"}
            if n_unresolved else None,
        ],
    }


# ---------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------
@app.get("/api/cases")
def list_cases():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM cases")
        cases = [dict(r) for r in cur.fetchall()]
        for c in cases:
            cur.execute(
                "SELECT COUNT(DISTINCT source) + COUNT(DISTINCT target) as c "
                "FROM relationships WHERE (source=? OR target=?)", (c["id"], c["id"])
            )
            cur.execute("SELECT COUNT(*) c FROM relationships WHERE target=? AND type='INVOLVED_IN'", (c["id"],))
            c["entity_count"] = cur.fetchone()["c"]
            cur.execute(
                "SELECT COUNT(*) c FROM relationships r JOIN evidence ev ON ev.id IN "
                "(SELECT value FROM json_each(r.evidence_ids)) WHERE r.target=? OR r.source=?",
                (c["id"], c["id"]),
            )
            try:
                c["evidence_count"] = cur.fetchone()["c"]
            except Exception:
                c["evidence_count"] = None
    return {"cases": cases}


@app.get("/api/cases/{case_id}")
def get_case(case_id: str):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM cases WHERE id=?", (case_id,))
        case = cur.fetchone()
        if not case:
            raise HTTPException(404, f"Case {case_id} not found")
    return dict(case)


@app.get("/api/cases/{case_id}/graph")
def get_case_graph(case_id: str, before: Optional[str] = None):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM cases WHERE id=?", (case_id,))
        if not cur.fetchone():
            raise HTTPException(404, f"Case {case_id} not found")

    g = analytics.build_graph(case_id=case_id, time_before=before)
    nodes = [
        {"id": n, "type": d["entity_type"], "name": d["name"]}
        for n, d in g.nodes(data=True)
    ]
    edges = []
    seen = set()
    for u, v, d in g.edges(data=True):
        key = d.get("rel_id")
        if key in seen:
            continue
        seen.add(key)
        edges.append({
            "id": key, "source": u, "target": v, "type": d.get("rel_type"),
            "confidence": d.get("confidence"), "timestamp": d.get("timestamp"),
        })

    if not nodes:
        return {"nodes": [], "edges": [], "message": "No graph data available for this case yet."}
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------
@app.get("/api/entities")
def list_entities(q: Optional[str] = None, entity_type: Optional[str] = None, limit: int = 50):
    sql = "SELECT id, entity_type, name, attributes FROM entities WHERE 1=1"
    params = []
    if q:
        sql += " AND name LIKE ?"
        params.append(f"%{q}%")
    if entity_type:
        sql += " AND entity_type=?"
        params.append(entity_type)
    sql += " LIMIT ?"
    params.append(limit)

    with db_cursor() as cur:
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]

    results = []
    for r in rows:
        with db_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) c FROM relationships WHERE (source=? OR target=?) AND status='observed'",
                (r["id"], r["id"]),
            )
            conn_count = cur.fetchone()["c"]
            cur.execute(
                "SELECT DISTINCT target FROM relationships WHERE source=? AND type='INVOLVED_IN'", (r["id"],)
            )
            cases = [row["target"] for row in cur.fetchall()]
        results.append({
            "id": r["id"], "type": r["entity_type"], "name": r["name"],
            "attributes": json.loads(r["attributes"]),
            "connection_count": conn_count, "cases": cases,
        })
    if not results:
        return {"entities": [], "message": "No entities matched your search."}
    return {"entities": results}


@app.get("/api/entities/{entity_id}")
def get_entity(entity_id: str):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM entities WHERE id=?", (entity_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, f"Entity {entity_id} not found")
        cur.execute("SELECT DISTINCT target FROM relationships WHERE source=? AND type='INVOLVED_IN'", (entity_id,))
        cases = [r["target"] for r in cur.fetchall()]
        cur.execute(
            "SELECT * FROM relationships WHERE (source=? OR target=?) AND type='POSSIBLE_SAME_AS'",
            (entity_id, entity_id),
        )
        possible_matches = [dict(r) for r in cur.fetchall()]

    g = analytics.build_graph()
    conn_count = g.degree(entity_id) if entity_id in g else 0

    return {
        "id": row["id"], "type": row["entity_type"], "name": row["name"],
        "attributes": json.loads(row["attributes"]),
        "cases": cases, "connection_count": conn_count,
        "possible_matches": possible_matches,
    }


@app.get("/api/entities/{entity_id}/neighbors")
def get_neighbors(entity_id: str):
    g = analytics.build_graph()
    if entity_id not in g:
        return {"neighbors": [], "message": "This entity currently has no recorded connections."}
    out = []
    for n in g.neighbors(entity_id):
        edge_data = g.get_edge_data(entity_id, n)
        edges = list(edge_data.values())
        out.append({
            "id": n, "name": g.nodes[n]["name"], "type": g.nodes[n]["entity_type"],
            "relationship_count": len(edges),
            "relationships": [{"type": e.get("rel_type"), "confidence": e.get("confidence"),
                                "timestamp": e.get("timestamp"), "id": e.get("rel_id")} for e in edges],
        })
    return {"neighbors": out}


# ---------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------
@app.get("/api/evidence/{evidence_id}")
def get_evidence(evidence_id: str):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, f"Evidence record {evidence_id} not found")
    return dict(row)


@app.get("/api/relationships/{relationship_id}")
def get_relationship(relationship_id: str):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM relationships WHERE id=?", (relationship_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, f"Relationship {relationship_id} not found")
        rel = dict(row)
        rel["evidence_ids"] = json.loads(rel["evidence_ids"])
        evidence = []
        for eid in rel["evidence_ids"]:
            cur.execute("SELECT * FROM evidence WHERE id=?", (eid,))
            e = cur.fetchone()
            if e:
                evidence.append(dict(e))
        cur.execute("SELECT name FROM entities WHERE id=?", (rel["source"],))
        s = cur.fetchone()
        cur.execute("SELECT name FROM entities WHERE id=?", (rel["target"],))
        t = cur.fetchone()
    rel["source_name"] = s["name"] if s else rel["source"]
    rel["target_name"] = t["name"] if t else rel["target"]
    rel["evidence"] = evidence
    return rel


# ---------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------
@app.get("/api/analytics/{case_id}")
def get_analytics(case_id: str):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM cases WHERE id=?", (case_id,))
        if not cur.fetchone():
            raise HTTPException(404, f"Case {case_id} not found")
    return analytics.compute_analytics(case_id=case_id)


@app.get("/api/analytics")
def get_global_analytics():
    return analytics.compute_analytics()


# ---------------------------------------------------------------------
# Entity resolution
# ---------------------------------------------------------------------
@app.get("/api/entity-resolution/review")
def entity_resolution_queue():
    queue = ER.get_review_queue()
    pending = [q for q in queue if q["review_state"] == "pending"]
    if not pending:
        return {"queue": [], "message": "No entity matches currently awaiting review."}
    return {"queue": pending}


class ReviewAction(BaseModel):
    reviewer: Optional[str] = "demo_investigator"


@app.post("/api/entity-resolution/{relationship_id}/accept")
def accept_match(relationship_id: str, action: ReviewAction = ReviewAction()):
    if not ER.set_review_state(relationship_id, "accepted"):
        raise HTTPException(404, "Match candidate not found")
    log_action("ACCEPT_MATCH", relationship_id, f"reviewer={action.reviewer}")
    return {"message": "Match accepted.", "relationship_id": relationship_id}


@app.post("/api/entity-resolution/{relationship_id}/reject")
def reject_match(relationship_id: str, action: ReviewAction = ReviewAction()):
    if not ER.set_review_state(relationship_id, "rejected"):
        raise HTTPException(404, "Match candidate not found")
    log_action("REJECT_MATCH", relationship_id, f"reviewer={action.reviewer}")
    return {"message": "Match rejected.", "relationship_id": relationship_id}


# ---------------------------------------------------------------------
# Potential hidden links
# ---------------------------------------------------------------------
_link_cache = {"data": None, "computed_at": 0.0}
_LINK_CACHE_TTL_SECONDS = 60


def _cached_predict_hidden_links(top_k: int = 25):
    now = time.time()
    if _link_cache["data"] is None or (now - _link_cache["computed_at"]) > _LINK_CACHE_TTL_SECONDS:
        # Always compute the broadest set (100) once; callers slice down.
        _link_cache["data"] = analytics.predict_hidden_links(top_k=100)
        _link_cache["computed_at"] = now
    return _link_cache["data"][:top_k]


def invalidate_link_cache():
    _link_cache["data"] = None


@app.get("/api/potential-links/{case_id}")
def get_potential_links(case_id: str):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM cases WHERE id=?", (case_id,))
        if not cur.fetchone():
            raise HTTPException(404, f"Case {case_id} not found")
        cur.execute("SELECT review_state, entity_a, entity_b FROM potential_links")
        reviewed = {(r["entity_a"], r["entity_b"]): r["review_state"] for r in cur.fetchall()}

    links = _cached_predict_hidden_links(top_k=25)
    out = []
    for i, link in enumerate(links):
        pid = f"LNK_{link['entity_a']}_{link['entity_b']}"
        state = reviewed.get((link["entity_a"], link["entity_b"]), "pending")
        if state == "dismissed":
            continue
        link["id"] = pid
        link["review_state"] = state
        out.append(link)

    if not out:
        return {"potential_links": [], "message": "No potential hidden links detected for this case."}
    return {"potential_links": out}


class LinkReviewAction(BaseModel):
    action: str  # investigate | dismiss | mark_for_review
    reviewer: Optional[str] = "demo_investigator"


@app.post("/api/potential-links/{link_id}/review")
def review_potential_link(link_id: str, action: LinkReviewAction):
    parts = link_id.split("_")
    if len(parts) < 3:
        raise HTTPException(400, "Invalid link id")
    entity_a, entity_b = parts[1], parts[2]
    state_map = {"investigate": "investigate", "dismiss": "dismissed", "mark_for_review": "mark_for_review"}
    state = state_map.get(action.action)
    if not state:
        raise HTTPException(400, f"Unknown action {action.action}")

    with db_cursor() as cur:
        cur.execute(
            "INSERT OR REPLACE INTO potential_links (id, entity_a, entity_b, confidence, reasons, "
            "evidence_chain, review_state, generated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (link_id, entity_a, entity_b, 0, "[]", "[]", state, datetime.now().isoformat()),
        )
    log_action("REVIEW_POTENTIAL_LINK", link_id, f"action={action.action} reviewer={action.reviewer}")
    return {"message": f"Potential link marked as '{state}'.", "link_id": link_id}


# ---------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------
@app.get("/api/timeline/{case_id}")
def get_timeline(case_id: str):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM cases WHERE id=?", (case_id,))
        if not cur.fetchone():
            raise HTTPException(404, f"Case {case_id} not found")
        cur.execute("SELECT * FROM events WHERE case_id=? ORDER BY timestamp", (case_id,))
        events = [dict(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT timestamp FROM relationships WHERE status='observed' AND timestamp IS NOT NULL ORDER BY timestamp"
        )
        rel_timestamps = [r["timestamp"] for r in cur.fetchall()]

    return {"events": events, "activity_timestamps": rel_timestamps}


# ---------------------------------------------------------------------
# Natural-language query (rule-based; no external LLM dependency)
# ---------------------------------------------------------------------
@app.get("/api/query")
def nl_query(q: str):
    ql = q.lower().strip()
    g = analytics.build_graph()

    def find_person_by_name(fragment):
        with db_cursor() as cur:
            cur.execute("SELECT id, name FROM entities WHERE entity_type='Person' AND name LIKE ?",
                        (f"%{fragment}%",))
            return cur.fetchall()

    # Intent: "connected to X within N degrees"
    m = re.search(r"connected to ([a-zA-Z .]+?)( within (\d+) degrees?)?$", ql)
    if m:
        name_fragment = m.group(1).strip()
        degrees = int(m.group(3)) if m.group(3) else 2
        matches = find_person_by_name(name_fragment)
        if not matches:
            return {"intent": "connected_to", "answer": f"No person matching '{name_fragment}' found.", "results": []}
        target = matches[0]["id"]
        if target not in g:
            return {"intent": "connected_to", "answer": f"{matches[0]['name']} has no recorded connections.", "results": []}
        lengths = nx.single_source_shortest_path_length(g, target, cutoff=degrees)
        results = [{"id": n, "name": g.nodes[n]["name"], "type": g.nodes[n]["entity_type"], "hops": d}
                   for n, d in lengths.items() if n != target]
        return {"intent": "connected_to", "subject": matches[0]["name"],
                "answer": f"Found {len(results)} entities connected to {matches[0]['name']} within {degrees} degrees.",
                "results": results}

    # Intent: "which entities connect Case X and Case Y"
    m = re.search(r"connect (case\s*\w+) and (case\s*\w+)", ql)
    if m:
        c1 = m.group(1).upper().replace(" ", "_")
        c2 = m.group(2).upper().replace(" ", "_")
        with db_cursor() as cur:
            cur.execute("SELECT source FROM relationships WHERE target=? AND type='INVOLVED_IN'", (c1,))
            in_c1 = {r["source"] for r in cur.fetchall()}
            cur.execute("SELECT source FROM relationships WHERE target=? AND type='INVOLVED_IN'", (c2,))
            in_c2 = {r["source"] for r in cur.fetchall()}
        bridging = set()
        for p1 in in_c1:
            if p1 not in g:
                continue
            for nb in g.neighbors(p1):
                if nb in in_c2:
                    bridging.add(p1)
                    bridging.add(nb)
        results = [{"id": n, "name": g.nodes[n]["name"], "type": g.nodes[n]["entity_type"]}
                   for n in bridging if n in g]
        return {"intent": "case_bridge", "answer": f"Found {len(results)} entities bridging {c1} and {c2}.",
                "results": results}

    # Intent: "important bridge entities" / "show bridge entities"
    if "bridge" in ql:
        stats = analytics.compute_analytics()
        return {"intent": "bridge_entities",
                "answer": f"Top bridge (betweenness) entities across the network:",
                "results": stats["top_bridges"]}

    if "connectivity" in ql or "most connected" in ql or "highly connected" in ql:
        stats = analytics.compute_analytics()
        return {"intent": "connectivity",
                "answer": "Top entities by network connectivity (degree centrality):",
                "results": stats["top_connectivity"]}

    return {
        "intent": "unrecognized",
        "answer": "I couldn't match that to a supported query pattern. Try: "
                  "'Show people connected to <name> within <N> degrees', "
                  "'Which entities connect Case 001 and Case 002?', or "
                  "'Show important bridge entities'.",
        "results": [],
    }


# ---------------------------------------------------------------------
# Investigation summary (evidence-grounded, template-based — no invented facts)
# ---------------------------------------------------------------------
@app.get("/api/cases/{case_id}/summary")
def investigation_summary(case_id: str):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM cases WHERE id=?", (case_id,))
        case = cur.fetchone()
        if not case:
            raise HTTPException(404, f"Case {case_id} not found")

    stats = analytics.compute_analytics(case_id=case_id)
    links = _cached_predict_hidden_links(top_k=100)
    queue = ER.get_review_queue()
    pending_matches = [q for q in queue if q["review_state"] == "pending"]

    key_entities = stats["top_connectivity"][:5]
    bridges = stats["top_bridges"][:3]

    return {
        "case": dict(case),
        "key_entities": key_entities,
        "important_relationships": bridges,
        "potential_investigative_leads": links[:5],
        "timeline_observation": f"Activity recorded across the investigation period "
                                 f"{case['period_start']} to {case['period_end']}, with "
                                 f"{stats['edge_count']} observed relationships forming "
                                 f"{stats['community_count']} distinct community clusters.",
        "unresolved_entities": pending_matches[:5],
        "evidence_note": "All statements above are derived directly from recorded "
                         "entities, relationships and evidence in this system. "
                         "Potential investigative leads are AI-generated hypotheses, "
                         "not confirmed facts, and require investigator review.",
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}
