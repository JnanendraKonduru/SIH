# API Reference — Operation Nexus Backend

Base URL (local dev): `http://127.0.0.1:8000`
Interactive docs: `http://127.0.0.1:8000/docs` (Swagger UI, auto-generated)

All responses are JSON. Errors return `{"error": "..."}` with an
appropriate HTTP status code (400/404/500). List endpoints that find no
matching rows return `{"...": [], "message": "..."}` rather than a bare
error, so the frontend can show a proper empty state.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness check |
| POST | `/api/demo/load` | (Re)seed the Operation Nexus demo dataset |
| GET | `/api/dashboard` | Summary counts, recent activity, alerts |
| GET | `/api/cases` | List all cases with entity/evidence counts |
| GET | `/api/cases/{case_id}` | Single case detail |
| GET | `/api/cases/{case_id}/graph?before=` | Nodes/edges for the case network graph; optional ISO timestamp to filter to relationships up to that point |
| GET | `/api/entities?q=&entity_type=&limit=` | Search entities by name / type |
| GET | `/api/entities/{entity_id}` | Full entity profile: attributes, cases, connection count, possible identity matches |
| GET | `/api/entities/{entity_id}/neighbors` | Direct neighbors with relationship summaries |
| GET | `/api/evidence/{evidence_id}` | Single evidence record |
| GET | `/api/relationships/{relationship_id}` | Relationship detail including all linked evidence |
| GET | `/api/analytics/{case_id}` | Degree centrality, betweenness, communities for a case's subgraph |
| GET | `/api/analytics` | Same, across the whole network |
| GET | `/api/entity-resolution/review` | Pending possible-duplicate-identity candidates with computed reasons/contradictions |
| POST | `/api/entity-resolution/{relationship_id}/accept` | Mark a candidate match as accepted |
| POST | `/api/entity-resolution/{relationship_id}/reject` | Mark a candidate match as rejected |
| GET | `/api/potential-links/{case_id}` | AI-generated hidden-link leads (transparent graph-similarity method) |
| POST | `/api/potential-links/{link_id}/review` | Body: `{"action": "investigate"\|"dismiss"\|"mark_for_review"}` |
| GET | `/api/timeline/{case_id}` | Timestamped events + relationship activity timestamps for a case |
| GET | `/api/query?q=` | Rule-based natural-language query (no external LLM) |
| GET | `/api/cases/{case_id}/summary` | Evidence-grounded investigation summary |

## Notable response shapes

**`GET /api/potential-links/{case_id}`** — each item:
```json
{
  "id": "LNK_P0001_P0050",
  "entity_a": "P0001", "entity_b": "P0050",
  "name_a": "Rajesh Kumar", "name_b": "Meera Fernandes",
  "confidence": 0.62,
  "reasons": ["connected via an indirect evidence chain"],
  "evidence_chain": ["P0001", "PH0001", "P0030", "VH0010", "LOC0005", "P0050"],
  "common_neighbors": 0, "jaccard": 0.0, "adamic_adar": 0.0,
  "review_state": "pending"
}
```

**`GET /api/entity-resolution/review`** — each item:
```json
{
  "relationship_id": "REL_0007",
  "entity_a": {"id": "P0001", "name": "Rajesh Kumar"},
  "entity_b": {"id": "P0002", "name": "R. Kumar"},
  "confidence": 0.87,
  "reasons": ["Similar name (58% string similarity)", "Same phone identifier", "Same associated vehicle"],
  "contradictions": ["Different reported age (34 vs 29)"],
  "review_state": "pending"
}
```

Every relationship-status field is one of `observed` or `inferred` —
the frontend never has to guess which is which from context.
