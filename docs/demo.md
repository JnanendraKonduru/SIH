# Demo Guide — Operation Nexus (SIH PS-189)

Start both servers first: `bash scripts/run.sh`, then open
`http://127.0.0.1:5173`.

## 5-minute demo flow

1. **Sign in** — mention in passing that this is a simplified fictional
   login for the prototype (any credentials work); don't dwell on it.
2. **Dashboard** — "This is Operation Nexus, a synthetic demonstration
   investigation. Two active cases, ~230 tracked entities, several
   hundred observed relationships, and — this is the important number —
   some potential leads and unresolved identity matches waiting for
   investigator review."
3. **Network Graph** (Cases → Operation Nexus - Phase I → graph loads) —
   click a well-connected node (search "Rajesh Kumar" if needed). Show
   the inspector panel: attributes, cases, direct connections. Click one
   of its edges → show the evidence panel underneath: source record,
   timestamp, extraction confidence. **This is the core idea**: every
   relationship traces back to a specific synthetic evidence record, not
   just "the graph says so."
4. **Entity Resolution** — show the Rajesh Kumar / "R. Kumar" candidate:
   confidence, the checkmark reasons (name similarity, shared phone,
   shared vehicle), and the contradiction (different reported age).
   Click Accept or Reject — point out the badge count in the nav rail
   dropping.
5. **Potential Hidden Links** — show the AI-generated lead. Read the
   reasons and the evidence chain (the literal path of intermediate
   entities). Emphasize the label: **"AI-generated investigative
   lead"** — never presented as a confirmed relationship. Click
   Investigate.

That's the whole story: fragmented records → evidence-backed graph →
uncertain matches surfaced for review → hidden connections surfaced as
leads, not facts.

## 10-minute demo flow

Everything above, plus:

6. **Analytics** — connectivity and bridge-score rankings. Explicitly
   say: "these describe network structure — how connected, how much of
   a bridge between clusters — not guilt. We were careful never to call
   this a criminality score."
7. **Timeline** — scrub the slider, show events entering/leaving the
   visible window.
8. **Query** — type or click one of the example natural-language
   queries ("Which entities connect Case 001 and Case 002?"). Mention:
   rule-based intent parsing, zero external LLM dependency, so the whole
   system works offline / without an API key.
9. **Investigation Summary** — the evidence-grounded auto-generated
   summary: key entities, important relationships, leads, timeline note,
   unresolved entities — all pulled directly from the live data, nothing
   invented.

## Key talking points

- **"We're not claiming to invent criminal network analysis."** CCTNS/
  ICJS already has a link-analysis module; commercial tools like i2
  Analyst's Notebook and Maltego exist. Our contribution is the specific
  combination: evidence provenance + uncertainty-aware entity resolution
  + temporal filtering + *transparent* (not black-box) link prediction +
  mandatory human-in-the-loop review, in one coherent workflow.
- **"Every prediction is a hypothesis, never a fact."** Point at the
  "AI-generated investigative lead" label and the Accept/Reject buttons
  whenever this comes up.
- **"We chose SQLite over Neo4j/PostgreSQL deliberately, not out of
  ignorance."** At this scale, in-memory NetworkX gives every graph
  algorithm we need, and it means a judge can run this with nothing but
  Python installed. We documented the production path to a graph
  database in `docs/architecture.md`.
- **"Hidden-link prediction is explainable by construction."** Common
  neighbors, Jaccard, Adamic-Adar, indirect evidence chains — every
  number shown is directly computed and inspectable, not a model score
  with no explanation. We chose this over a GNN deliberately, because
  we have no labelled real-world data to validate a trained model
  against, and an unvalidated black-box model would be *less*
  trustworthy here, not more impressive.

## Expected judge questions (and how we'd answer)

- **"Does this scale to real CCTNS-sized data?"** Not as-is — SQLite +
  in-memory NetworkX is the right choice at this dataset's scale (a few
  hundred nodes), but a production deployment would move to a graph
  database as described in `docs/architecture.md`. The data model
  doesn't change, only the storage layer.
- **"How accurate is the link prediction?"** We don't claim an accuracy
  number, because we don't have labelled real-world data to validate
  against — see Limitations. What we can show is that our designed
  hidden-link scenario (two people, no direct link, connected only
  through phone→person→vehicle→location) is discoverable by the
  detector; that's a demonstration of the *mechanism*, not a benchmark.
- **"What stops an investigator from just accepting every AI
  suggestion?"** Nothing at the UI level in this prototype — that's a
  process/training question as much as a system one. What the system
  does guarantee is that every suggestion carries its confidence,
  reasons, and (for links) the underlying evidence chain, so an
  investigator has what they need to make an informed decision, and
  every decision is written to an audit log.
- **"Is this real data?"** No — entirely synthetic, generated by
  `scripts/generate_dataset.py`, explicitly to avoid any real personal
  or investigative data.

## Limitations to acknowledge proactively

See the README's "Limitations" section for the full list — the ones
worth saying out loud before a judge asks: SQLite instead of Neo4j/
Postgres (with reasoning), transparent link-prediction instead of a
trained model (with reasoning), no fabricated benchmark numbers, and the
login screen being a simplified stand-in rather than real authentication.
