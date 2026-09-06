# Operation Nexus — SIH 2026 PS-189 Prototype

**AI-Powered Criminal Network Analysis System**
Ministry of Home Affairs, Government of India — Problem Statement 189

A demonstration prototype that turns fragmented, messy investigative
records into an evidence-aware, temporal criminal-network graph, and
helps an investigator discover, inspect, and prioritize meaningful
relationships — while always keeping AI-generated hypotheses clearly
separate from confirmed, evidence-backed facts.

> **All data in this prototype is entirely synthetic.** No real people,
> phone numbers, vehicles, organizations, or locations are represented.
> See "Dataset" below.

---

## 1. Project overview

Investigations generate huge amounts of fragmented information — people,
aliases, phone numbers, vehicles, locations, organizations, and
communication/financial records — often duplicated, inconsistent, or
incomplete across multiple cases. PS-189 asks for a system that can turn
this into an understandable network representation and help an
investigator find what matters.

This prototype demonstrates the full pipeline end-to-end on a synthetic
case called **Operation Nexus**:

```
Raw investigative records → entity extraction/normalization → entity
resolution (duplicate detection) → graph construction → network analytics
(centrality, bridges, communities) → temporal analysis → transparent
hidden-link prediction → evidence inspection → investigator review
```

The system deliberately does **not** claim guilt from network position —
every AI-generated relationship or match is labelled a hypothesis / lead
that an investigator must accept or reject, with the full evidence chain
visible for "why did the system show me this?"

We are not claiming to reinvent criminal network analysis from scratch —
India already has CCTNS/ICJS infrastructure including a link-analysis
module. This prototype's contribution is the *combination* of
evidence-aware provenance, uncertainty-aware entity resolution, temporal
filtering, transparent (non-black-box) link prediction, and a
human-in-the-loop review workflow, in one coherent tool — see
`docs/architecture.md` for the fuller comparison.

---

## 2. Architecture — and one deliberate simplification

| Layer | Technology | Why |
|---|---|---|
| Frontend | Vanilla HTML/CSS/JS + [Cytoscape.js](https://js.cytoscape.org/) (via CDN) | Zero build step — open a URL, nothing to compile. Cytoscape is a mature, purpose-built graph library. |
| Backend API | Python + FastAPI | Clean, typed, self-documenting (auto Swagger docs at `/docs`), minimal boilerplate. |
| Data store | **SQLite** (see note below) | Zero-configuration, single file, no server to install. |
| Graph & analytics | **NetworkX** (in-memory, built from SQLite rows) | Gives centrality/betweenness/community-detection/path-finding for free, at this dataset's scale. |

### Why SQLite instead of Neo4j + PostgreSQL

The original brief suggested a Neo4j graph database plus a PostgreSQL
metadata store. We deliberately simplified this to a single SQLite file
for the preliminary prototype, for three concrete reasons:

1. **Zero operational complexity.** A teammate or judge can run the whole
   system with nothing but Python — no database server to install,
   configure, or troubleshoot mid-demo.
2. **The graph is small enough that it doesn't matter.** At a few hundred
   nodes and roughly a thousand edges, an in-memory NetworkX graph
   rebuilt from SQLite on each analytics call gives every capability a
   graph database would (centrality, betweenness, communities,
   shortest/simple paths) with no measurable downside.
3. **The data model doesn't change.** Every table maps directly onto a
   Neo4j node/relationship or a Postgres table — see
   `docs/architecture.md` for exactly how a production deployment would
   swap this layer out without touching the API contract.

This is exactly the "prefer reliability over technological complexity"
principle this project was scoped around — we are not using SQLite
because we don't understand graph databases; we're using it because it
is the right tool for a live, one-command demo of this size.

No Docker, Kubernetes, or cloud infrastructure is used or required.

---

## 3. Installation

Requirements: **Python 3.10+** (tested on 3.12). No Node.js, Docker, or
database server required to *run* the app (Node is only used by the
optional frontend test harness — see Testing below).

```bash
cd backend
pip install -r requirements.txt
```

That's the entire installation. The frontend has no dependencies at all —
it's static files.

---

## 4. Running the project

**Option A — one command (recommended):**

```bash
bash scripts/run.sh
```

This starts the backend API on `http://127.0.0.1:8000` and serves the
frontend on `http://127.0.0.1:5173`. Open the frontend URL in your
browser, sign in on the login screen (any input works — see "Demo
credentials"), and you're in.

**Option B — manually, in two terminals:**

```bash
# Terminal 1 — backend
cd backend
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — frontend (any static file server works)
cd frontend
python3 -m http.server 5173
```

Then open `http://127.0.0.1:5173` in your browser.

The database seeds itself automatically on first run — there's no
separate "setup the database" step. If you ever want to reset to a clean
Operation Nexus state, click **Load Demo Investigation** in the top bar,
or delete `backend/nexus.db` and restart the backend.

### Interactive API docs

FastAPI gives you a full interactive API explorer for free at
`http://127.0.0.1:8000/docs` once the backend is running — useful for
poking at endpoints directly or for judges who want to see the API
contract.

---

## 5. Demo credentials

The login screen is intentionally a **simplified, fictional** login for
the prototype (see project brief section 20) — it does not connect to a
real authentication backend. Any username/password works; the fields
are pre-filled for convenience. `docs/demo.md` explains what to say about
this if asked.

---

## 6. Demo workflow (what to click for judges)

See `docs/demo.md` for the full 5-minute and 10-minute walkthroughs. The
short version:

1. Sign in → **Dashboard** (overview of Operation Nexus)
2. **Cases** → open Operation Nexus - Phase I
3. **Network Graph** → click around, select a node, select an edge →
   evidence panel
4. **Entity Resolution** → show the Rajesh Kumar / R. Kumar possible-match
   candidate, its reasons and contradiction, Accept/Reject
5. **Potential Hidden Links** → show the AI-generated lead connecting the
   two cases through an indirect evidence chain, click "Why?" (the
   evidence chain), Investigate/Dismiss
6. **Analytics** → connectivity and bridge-score rankings
7. **Timeline** → scrub through the investigation period
8. **Query** → try a natural-language question, no API key needed

---

## 7. Dataset

Everything is generated by `scripts/generate_dataset.py` into
`data/operation_nexus.json`, then loaded into SQLite by
`backend/app/seed.py`. It contains:

- 2 cases, ~95 persons, ~56 phones, ~46 vehicles, 15 locations, 19
  organizations, ~660 relationships, ~600 evidence records
- A **deliberately designed hidden-link scenario**: two people in
  different cases (Rajesh Kumar, Case 001; Meera Fernandes, Case 002)
  share no direct recorded relationship, but are connected through an
  indirect chain (phone → contact → vehicle → location) that the
  hidden-link detector can surface as a lead
- A **deliberately designed duplicate-identity pair** (Rajesh Kumar /
  "R. Kumar" aka "Raju") with matching and contradicting attributes, for
  the entity-resolution review queue
- An internal `ground_truth` block (not exposed in the UI) recording
  which pairs are "actually" the same/linked, for our own evaluation

No real individuals, organizations, vehicles, or locations are
represented anywhere in this dataset.

---

## 8. API documentation

Full interactive docs at `/docs` once running. Key endpoints:

```
GET  /api/dashboard
GET  /api/cases
GET  /api/cases/{case_id}
GET  /api/cases/{case_id}/graph
GET  /api/entities?q=&entity_type=
GET  /api/entities/{entity_id}
GET  /api/entities/{entity_id}/neighbors
GET  /api/evidence/{evidence_id}
GET  /api/relationships/{relationship_id}
GET  /api/analytics/{case_id}
GET  /api/entity-resolution/review
POST /api/entity-resolution/{relationship_id}/accept
POST /api/entity-resolution/{relationship_id}/reject
GET  /api/potential-links/{case_id}
POST /api/potential-links/{link_id}/review     {"action": "investigate|dismiss|mark_for_review"}
GET  /api/timeline/{case_id}
GET  /api/query?q=...
GET  /api/cases/{case_id}/summary
POST /api/demo/load
```

See `docs/api.md` for request/response details.

---

## 9. Project structure

```
sih-ps189/
├── README.md                    ← you are here
├── .env.example
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py               FastAPI app + all API routes
│   │   ├── database.py           SQLite schema + connection helper
│   │   ├── seed.py               Loads data/operation_nexus.json into SQLite
│   │   ├── analytics.py          NetworkX graph build + centrality/community/link-prediction
│   │   └── entity_resolution.py  Possible-duplicate review-queue logic
│   └── nexus.db                  (created at runtime, gitignored)
├── frontend/
│   ├── index.html                App shell + login screen
│   ├── css/style.css             Design system
│   └── js/
│       ├── api.js                Backend API client
│       ├── graph.js               Cytoscape.js rendering + inspector interactions
│       ├── pages.js               One render function per screen/route
│       └── app.js                 Routing, login, nav, search, toasts
├── data/
│   └── operation_nexus.json      Generated synthetic dataset (see scripts/)
├── scripts/
│   ├── generate_dataset.py       Synthetic dataset generator (re-run to regenerate)
│   └── run.sh                    One-command dev launcher
├── tests/
│   ├── backend/test_full_journey.py   16 end-to-end API tests (pytest)
│   └── frontend/ui_test.js            jsdom-driven UI journey test (Node)
└── docs/
    ├── architecture.md
    ├── demo.md
    └── api.md
```

See `docs/architecture.md` for what every important file does in detail.

---

## 10. Testing

**Backend (pytest, 16 tests covering the full judge demo journey):**

```bash
pip install -r backend/requirements.txt pytest httpx
python3 -m pytest tests/backend/test_full_journey.py -v
```

**Frontend (jsdom-driven, drives the real app.js/pages.js against the
real running backend — requires the backend running separately):**

```bash
cd frontend && npm install jsdom
cd .. && NODE_PATH=frontend/node_modules node tests/frontend/ui_test.js
```

Both suites were run and passed during development — see "Testing
performed" in the final summary for what was found and fixed.

---

## 11. Troubleshooting

| Symptom | Fix |
|---|---|
| Frontend shows "Cannot reach the Operation Nexus backend API" | Make sure `uvicorn` is running on port 8000. Check `http://127.0.0.1:8000/api/health` directly in a browser. |
| `pip install` fails with an externally-managed-environment error | Add `--break-system-packages`, or use a virtualenv: `python3 -m venv venv && source venv/bin/activate`. |
| Graph looks empty / says "no graph data" | Click **Load Demo Investigation** in the top bar to (re)seed Operation Nexus. |
| Port 8000 or 5173 already in use | Edit the port in `scripts/run.sh`, and update `window.NEXUS_API_BASE` at the top of `frontend/index.html`'s inline config (or `js/api.js`'s `API_BASE` fallback) to match. |
| Graph nodes overlap / look messy on a very wide time filter | This is a cosmetic layout limitation of the force-directed layout at this node count — use the relationship-type or time filters in the graph toolbar to declutter. |

---

## 12. Limitations (read this before a judge asks)

Being honest, as instructed:

- **SQLite, not Neo4j/PostgreSQL** — a deliberate, documented
  simplification for this preliminary prototype (see section 2). A
  production deployment would move to a graph database at real scale;
  `docs/architecture.md` explains exactly how.
- **Hidden-link prediction uses transparent graph-similarity methods**
  (common neighbors, Jaccard, Adamic-Adar), not a trained ML/GNN model.
  This was a deliberate choice per the brief ("start with simpler
  baselines... only use advanced ML if it genuinely improves the
  prototype") — we did not have a labelled real-world dataset to train
  or validate a supervised model against, and an untrained/unvalidated
  ML model would be *less* trustworthy and *less* explainable than the
  transparent method actually implemented.
- **No performance benchmarks are claimed** because none were run in a
  way that would be meaningful on synthetic data — see `docs/demo.md`
  for how we'd talk about this if asked.
- **Entity resolution is similarity-based, not learned** — same
  reasoning as above; every "possible match" reason is directly
  computed and shown, not scored by an opaque model.
- **Login is a simplified, fictional screen** with no real authentication
  backend, as explicitly permitted by the brief for a preliminary
  prototype. Any credentials work.
- **Natural-language query is a rule-based intent parser**, not an LLM —
  by design, so the whole system works with zero external API
  dependency. It covers three intents (connected-to, case-bridging,
  bridge/connectivity ranking); anything else returns a clear
  "unrecognized" response with example phrasings rather than guessing.
- **The force-directed graph layout can look cluttered** at higher node
  counts; the type/time filters mitigate this but a production tool
  would likely offer alternate layouts (hierarchical, geographic).
- **This system does not replace ICJS or CCTNS**, and does not claim to.
  It is a demonstration of a specific analytical approach (evidence
  provenance + uncertainty-aware resolution + transparent link
  prediction + human-in-the-loop review) that could complement such
  systems.
- **All predictions and matches are presented as hypotheses**, never as
  fact or guilt — this is a hard design constraint, not just UI copy.
