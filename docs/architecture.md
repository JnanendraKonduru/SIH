# Architecture — Operation Nexus (SIH PS-189 Prototype)

## 1. High-level data flow

```
scripts/generate_dataset.py
        │  (one-time, produces synthetic records with a designed
        │   hidden-link scenario and duplicate-identity pair)
        ▼
data/operation_nexus.json
        │
        ▼
backend/app/seed.py  ──►  SQLite (backend/nexus.db)
        │                     │
        │                     ▼
        │            backend/app/analytics.py
        │            builds an in-memory NetworkX graph
        │            from the entities/relationships tables
        │            on each analytics/graph request
        ▼
backend/app/main.py (FastAPI routes)
        │
        ▼
frontend/js/api.js  ──►  frontend/js/pages.js (renders each screen)
                                │
                                ▼
                     frontend/js/graph.js (Cytoscape.js network view)
```

Every screen in the frontend is a thin, mostly-stateless render function
that fetches from the API and paints DOM. The backend holds no
session/user state beyond the SQLite file itself (audit log, review
decisions).

## 2. Frontend

Vanilla HTML/CSS/JS, no build step, no framework. This was a deliberate
choice: for a hackathon prototype that needs to be trivially runnable
and inspectable by teammates who may not know React/Vite tooling, static
files you can open directly (or serve with `python -m http.server`) beat
a build pipeline that can silently break.

- `index.html` — app shell: login screen + the persistent nav
  rail/topbar/main-view frame that every page renders into.
- `css/style.css` — the whole design system as CSS variables (colors,
  spacing, type). Status colors are semantic and used consistently:
  teal = observed/confirmed, violet = inferred/hypothesis, amber =
  alert/lead, red = contradiction/reject.
- `js/api.js` — a ~15-line fetch wrapper. Every backend call goes through
  here so there's exactly one place that knows the API base URL and
  error-handling convention.
- `js/graph.js` — Cytoscape.js setup and interaction handlers (node/edge
  selection, neighborhood highlighting, type/time filtering, search
  highlighting). Node color encodes entity *type*; edge color/style
  encodes relationship *status* (solid teal = observed, dashed violet =
  inferred) — two independent visual channels so you never have to
  guess which is which.
- `js/pages.js` — one function per screen (`Pages.dashboard`,
  `Pages.graph`, `Pages.resolution`, etc.), each responsible for
  fetching its own data and rendering into the shared `#main-view`
  element.
- `js/app.js` — routing (`navigateTo`), login handling, the case
  selector, global search debouncing, toast notifications, and review
  badges in the nav rail.

**Stale-render guard.** Because every page fetches asynchronously and
writes into the *same* `#main-view` DOM node, a slow response from a
page the user has since navigated away from could otherwise overwrite
newer content once it finally resolves. `navigateTo` stamps a generation
token on the view element on every navigation; each page checks
`isStale()` before committing its final render and silently discards its
result if the user has moved on. This was actually caught by our own
jsdom test harness under artificial network latency — see
`docs/demo.md` / testing notes.

## 3. Backend

FastAPI app (`backend/app/main.py`) with four supporting modules:

- **`database.py`** — SQLite schema (`cases`, `entities`, `events`,
  `evidence`, `relationships`, `potential_links`, `audit_log`) and a
  small connection-context-manager helper. Every important investigator
  action (accept/reject a match, review a potential link, load demo
  data) is written to `audit_log` with a timestamp — a deliberate nod to
  the brief's security requirements around auditability.
- **`seed.py`** — idempotent loader from `data/operation_nexus.json`
  into the SQLite tables. Powers the "Load Demo Investigation" button.
- **`analytics.py`** — builds a NetworkX `MultiGraph` from the
  `entities`/`relationships` tables (observed relationships only — see
  §5) and computes:
  - degree centrality → surfaced as **"network connectivity"**
  - betweenness centrality → surfaced as **"bridge score"**
  - greedy modularity communities → **"community membership"**
  - transparent hidden-link prediction (§6)

  None of these are ever labelled a "criminality score" — see the
  brief's explicit instruction on this — they describe network
  structure only.
- **`entity_resolution.py`** — for every `POSSIBLE_SAME_AS` relationship
  in the data, recomputes *why* the system flagged it (name similarity,
  shared phone/vehicle/location neighbors) and any contradicting
  attributes (e.g. reported age), rather than trusting a hardcoded
  string — so the review queue's "reasons" always reflect the live graph.

## 4. Data model

Entities are stored generically (`entities` table: `id`, `entity_type`,
`name`, `attributes` JSON blob) rather than one table per type. This
keeps the schema small and maps directly onto a future Neo4j label
system (`entity_type` → node label, `attributes` → node properties) with
no restructuring.

Relationships carry: `source`, `target`, `type`, `timestamp`,
`confidence`, `status` (`observed` | `inferred`), `evidence_ids` (JSON
list — the provenance link), `notes`, and `review_state` (`pending` |
`accepted` | `rejected` for matches; `pending` | `investigate` |
`dismissed` | `mark_for_review` for potential links).

**Observed vs. inferred is a hard separation, not a UI label.**
`analytics.build_graph()` only ever includes `status='observed'`
relationships when computing centrality/bridges/communities — an
inferred hypothesis can never silently influence a "network
connectivity" number. `POSSIBLE_SAME_AS` and hidden-link predictions are
computed and displayed through entirely separate code paths
(`entity_resolution.py` and `analytics.predict_hidden_links()`).

## 5. Entity resolution

For the flagship demo pair (Rajesh Kumar / "R. Kumar" aka "Raju"), the
dataset generator seeds a `POSSIBLE_SAME_AS` relationship with a fixed
confidence, but the *reasons and contradictions shown to the
investigator are recomputed live* from the current graph and attribute
data — string similarity on names, shared phone/vehicle/location
neighbors, and a reported-age contradiction check. This means the
review-queue screen is not just replaying a canned string; if you
changed the underlying data, the displayed reasons would change too.

Accepting or rejecting a match only updates `review_state` — it does
not currently merge the two entity records into one (that would be the
natural next step for a production version: on accept, redirect all of
entity B's relationships onto entity A and mark B as merged).

## 6. Hidden-link prediction

Deliberately **not** a black-box ML model. For every pair of `Person`
nodes with no existing direct or already-flagged relationship, we
compute:

- **Common neighbors** and **Jaccard similarity** over their observed
  1-hop neighborhoods
- **Adamic-Adar index** (weights rare shared neighbors more than common
  ones)
- Whether a **short indirect path** exists through non-person
  intermediate entities (phone/vehicle/location/organization) — this is
  the literal "A → phone → C → vehicle → location ← B" pattern the
  brief describes, found via `networkx.all_simple_paths` with a small
  hop cutoff

Every one of these numbers is returned in the API response and used to
build the human-readable "reasons" list (e.g. "3 shared associates", "2
shared locations", "connected via an indirect evidence chain") — so a
judge asking "why did the system suggest this?" gets a real, inspectable
answer, not a model score with no explanation.

We evaluated this against a small path-search cost: at ~95 person
nodes, computing all pairwise indirect-path checks took ~6 seconds
uncached. Since this doesn't need to be recomputed on every page view,
we added a 60-second in-process cache (`_cached_predict_hidden_links` in
`main.py`) rather than optimizing the algorithm further — the right
call for a prototype at this scale.

## 7. Security

- No hardcoded secrets; `.env.example` documents the (currently empty)
  configuration surface.
- CORS is permissive (`allow_origins=["*"]`) for local development only —
  a real deployment would restrict this to the actual frontend origin.
- All path/query parameters are typed by FastAPI/Pydantic, which
  rejects malformed input before it reaches application code.
- A catch-all middleware guarantees the API never leaks a raw stack
  trace to the client (logs the traceback server-side, returns a generic
  500 message) while still returning proper 404s for missing resources.
- Every accept/reject/demo-load/potential-link-review action is written
  to `audit_log` with a timestamp — full investigator-action auditability.
- The login screen is explicitly a simplified stand-in, not real
  authentication — documented as such in the README rather than
  presented as more secure than it is.

## 8. What a production architecture would look like

If this moved beyond a hackathon prototype:

- **SQLite → Neo4j** for the graph itself (the entity/relationship model
  above maps directly onto nodes/relationships with no redesign), with
  PostgreSQL for anything relational/transactional (case metadata, audit
  log, user accounts).
- **Real authentication** with role-based access control (investigator
  vs. supervisor vs. read-only), replacing the fictional login screen.
- **A trained, validated link-prediction model** (once real, labelled
  investigative data exists to validate against) — likely still
  presented alongside the transparent graph-similarity baseline rather
  than replacing it, since explainability matters more here than in a
  typical recommender system.
- **Merge-on-accept** entity resolution, with a reversible audit trail.
- **Ingestion pipeline** for real heterogeneous records (PDF case files,
  call detail records, financial statements) with NLP-based entity
  extraction feeding into the same normalization/resolution pipeline —
  the "raw investigative records → entity extraction" step this
  prototype currently starts from pre-structured synthetic JSON.
