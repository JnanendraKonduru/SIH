"""
backend/app/entity_resolution.py
=================================
Formats POSSIBLE_SAME_AS relationships (seeded by generate_dataset.py, i.e.
representing an automated name/attribute-similarity scan) into a review
queue the investigator can accept or reject.

For each candidate pair this recomputes *why* the system thinks they might
be the same entity by directly comparing their attributes and shared
neighbors, so the "reasons" shown are always grounded in the current data,
not just a hardcoded string.
"""

import json
import difflib
from .database import db_cursor
from .analytics import build_graph


def _name_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def get_review_queue():
    g = build_graph()
    results = []
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM relationships WHERE type='POSSIBLE_SAME_AS' ORDER BY confidence DESC"
        )
        rows = cur.fetchall()
        cur.execute("SELECT id, name, attributes FROM entities WHERE entity_type='Person'")
        persons = {r["id"]: (r["name"], json.loads(r["attributes"])) for r in cur.fetchall()}

    for row in rows:
        a_id, b_id = row["source"], row["target"]
        if a_id not in persons or b_id not in persons:
            continue
        name_a, attrs_a = persons[a_id]
        name_b, attrs_b = persons[b_id]

        reasons, contradictions = [], []

        sim = _name_similarity(name_a, name_b)
        if sim > 0.4:
            reasons.append(f"Similar name ({int(sim*100)}% string similarity)")

        neighbors_a = set(g.neighbors(a_id)) if a_id in g else set()
        neighbors_b = set(g.neighbors(b_id)) if b_id in g else set()
        shared = neighbors_a & neighbors_b
        shared_phones = [n for n in shared if g.nodes[n]["entity_type"] == "Phone"]
        shared_vehicles = [n for n in shared if g.nodes[n]["entity_type"] == "Vehicle"]
        shared_locations = [n for n in shared if g.nodes[n]["entity_type"] == "Location"]

        if shared_phones:
            reasons.append("Same phone identifier")
        if shared_vehicles:
            reasons.append("Same associated vehicle")
        if shared_locations:
            reasons.append(f"Overlapping location history ({len(shared_locations)} shared location(s))")

        age_a, age_b = attrs_a.get("reported_age"), attrs_b.get("reported_age")
        if age_a is not None and age_b is not None and abs(age_a - age_b) >= 3:
            contradictions.append(f"Different reported age ({age_a} vs {age_b})")

        if not reasons:
            reasons.append("Flagged by automated similarity scan")

        results.append({
            "relationship_id": row["id"],
            "entity_a": {"id": a_id, "name": name_a},
            "entity_b": {"id": b_id, "name": name_b},
            "confidence": row["confidence"],
            "reasons": reasons,
            "contradictions": contradictions,
            "review_state": row["review_state"],
            "evidence_ids": json.loads(row["evidence_ids"]),
            "notes": row["notes"],
        })
    return results


def set_review_state(relationship_id: str, state: str):
    with db_cursor() as cur:
        cur.execute("SELECT id FROM relationships WHERE id=?", (relationship_id,))
        if not cur.fetchone():
            return False
        cur.execute("UPDATE relationships SET review_state=? WHERE id=?", (state, relationship_id))
    return True
