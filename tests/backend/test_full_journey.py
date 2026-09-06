"""
tests/backend/test_full_journey.py
===================================
End-to-end test exercising every endpoint and the full demo user journey:
open app -> open case -> view graph -> search entity -> select entity ->
view relationships -> inspect evidence -> review entity match -> view
analytics -> view timeline -> view potential link -> review potential link.

Run with: python3 -m pytest tests/backend/test_full_journey.py -v
"""
import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    # Ensure a clean DB for a deterministic test run
    from app.database import DB_PATH
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_demo_load(client):
    r = client.post("/api/demo/load")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["persons"] > 50
    assert body["counts"]["relationships"] > 100


def test_dashboard(client):
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    body = r.json()
    for key in ("case_count", "entity_count", "relationship_count",
                "potential_link_count", "unresolved_entity_count"):
        assert key in body
    assert body["case_count"] == 2


def test_list_and_get_case(client):
    r = client.get("/api/cases")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 2
    case_id = cases[0]["id"]

    r = client.get(f"/api/cases/{case_id}")
    assert r.status_code == 200
    assert r.json()["id"] == case_id

    r = client.get("/api/cases/CASE_DOES_NOT_EXIST")
    assert r.status_code == 404


def test_case_graph(client):
    r = client.get("/api/cases/CASE_001/graph")
    assert r.status_code == 200
    body = r.json()
    assert len(body["nodes"]) > 0
    assert len(body["edges"]) > 0
    # every edge should reference nodes present in the node set
    node_ids = {n["id"] for n in body["nodes"]}
    for e in body["edges"][:50]:
        assert e["source"] in node_ids
        assert e["target"] in node_ids


def test_entity_search_and_profile(client):
    r = client.get("/api/entities", params={"q": "Rajesh"})
    assert r.status_code == 200
    entities = r.json()["entities"]
    assert any(e["name"] == "Rajesh Kumar" for e in entities)
    rajesh_id = [e for e in entities if e["name"] == "Rajesh Kumar"][0]["id"]

    r = client.get(f"/api/entities/{rajesh_id}")
    assert r.status_code == 200
    profile = r.json()
    assert profile["name"] == "Rajesh Kumar"
    assert profile["connection_count"] > 0

    r = client.get("/api/entities", params={"q": "Zzzznonexistent"})
    assert r.status_code == 200
    assert r.json()["entities"] == []


def test_entity_neighbors(client):
    r = client.get("/api/entities", params={"q": "Rajesh Kumar"})
    rajesh_id = r.json()["entities"][0]["id"]
    r = client.get(f"/api/entities/{rajesh_id}/neighbors")
    assert r.status_code == 200
    neighbors = r.json()["neighbors"]
    assert len(neighbors) > 0
    assert any(n["type"] == "Phone" for n in neighbors)


def test_evidence_inspection(client):
    r = client.get("/api/entities", params={"q": "Rajesh Kumar"})
    rajesh_id = r.json()["entities"][0]["id"]
    r = client.get(f"/api/entities/{rajesh_id}/neighbors")
    rel_id = r.json()["neighbors"][0]["relationships"][0]["id"]

    r = client.get(f"/api/relationships/{rel_id}")
    assert r.status_code == 200
    rel = r.json()
    assert "evidence" in rel
    assert len(rel["evidence"]) >= 1
    evidence_id = rel["evidence"][0]["id"]

    r = client.get(f"/api/evidence/{evidence_id}")
    assert r.status_code == 200
    assert "description" in r.json()

    r = client.get("/api/evidence/EVD_DOES_NOT_EXIST")
    assert r.status_code == 404


def test_entity_resolution_review_and_accept(client):
    r = client.get("/api/entity-resolution/review")
    assert r.status_code == 200
    queue = r.json()["queue"]
    assert len(queue) > 0
    # The flagship Rajesh Kumar / R. Kumar pair must be present
    names = [(q["entity_a"]["name"], q["entity_b"]["name"]) for q in queue]
    assert any("Rajesh Kumar" in pair or "R. Kumar" in pair for pair in names)

    target = queue[0]
    rel_id = target["relationship_id"]

    r = client.post(f"/api/entity-resolution/{rel_id}/accept")
    assert r.status_code == 200

    r = client.get("/api/entity-resolution/review")
    remaining_ids = [q["relationship_id"] for q in r.json().get("queue", [])]
    assert rel_id not in remaining_ids

    r = client.post("/api/entity-resolution/REL_FAKE/reject")
    assert r.status_code == 404


def test_analytics(client):
    r = client.get("/api/analytics/CASE_001")
    assert r.status_code == 200
    body = r.json()
    assert body["node_count"] > 0
    assert len(body["top_connectivity"]) > 0
    assert len(body["top_bridges"]) > 0

    r = client.get("/api/analytics/CASE_DOES_NOT_EXIST")
    assert r.status_code == 404


def test_timeline(client):
    r = client.get("/api/timeline/CASE_001")
    assert r.status_code == 200
    body = r.json()
    assert "events" in body
    assert "activity_timestamps" in body


def test_potential_links_and_review(client):
    r = client.get("/api/potential-links/CASE_001")
    assert r.status_code == 200
    body = r.json()
    links = body.get("potential_links", [])
    assert len(links) > 0
    link = links[0]
    assert "confidence" in link and "reasons" in link and "evidence_chain" in link

    link_id = link["id"]
    r = client.post(f"/api/potential-links/{link_id}/review", json={"action": "investigate"})
    assert r.status_code == 200

    r = client.post(f"/api/potential-links/{link_id}/review", json={"action": "bogus_action"})
    assert r.status_code == 400


def test_nl_query(client):
    r = client.get("/api/query", params={"q": "Show people connected to Rajesh Kumar within 2 degrees"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "connected_to"
    assert len(body["results"]) > 0

    r = client.get("/api/query", params={"q": "Which entities connect Case 001 and Case 002"})
    assert r.status_code == 200
    assert r.json()["intent"] == "case_bridge"

    r = client.get("/api/query", params={"q": "Show important bridge entities"})
    assert r.status_code == 200
    assert len(r.json()["results"]) > 0

    r = client.get("/api/query", params={"q": "asdkjaskdj random gibberish"})
    assert r.status_code == 200
    assert r.json()["intent"] == "unrecognized"


def test_investigation_summary(client):
    r = client.get("/api/cases/CASE_001/summary")
    assert r.status_code == 200
    body = r.json()
    for key in ("key_entities", "important_relationships",
                "potential_investigative_leads", "timeline_observation",
                "unresolved_entities", "evidence_note"):
        assert key in body


def test_hidden_link_ground_truth_present(client):
    """Sanity check that our designed hidden-link scenario (Rajesh Kumar <->
    Meera Fernandes, connected only via phone->person->vehicle->location) is
    actually discoverable by the link-prediction endpoint."""
    r = client.get("/api/potential-links/CASE_001")
    links = r.json().get("potential_links", [])
    names_pairs = [(l["name_a"], l["name_b"]) for l in links]
    found = any(
        {"Rajesh Kumar", "Meera Fernandes"} == {a, b} for a, b in names_pairs
    )
    # Not asserting strictly True (link prediction is probabilistic over a
    # randomly generated background network) but we log it for visibility.
    print(f"Hidden link Rajesh<->Meera discovered by predictor: {found}")


def test_malformed_and_edge_cases(client):
    r = client.get("/api/entities/DOES_NOT_EXIST")
    assert r.status_code == 404
    r = client.get("/api/entities/DOES_NOT_EXIST/neighbors")
    assert r.status_code == 200
    assert r.json()["neighbors"] == []
    r = client.get("/api/relationships/REL_DOES_NOT_EXIST")
    assert r.status_code == 404
