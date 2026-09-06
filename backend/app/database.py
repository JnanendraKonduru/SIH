"""
backend/app/database.py
========================
Lightweight SQLite persistence layer.

ARCHITECTURE NOTE (read this):
The original brief suggested Neo4j (graph DB) + PostgreSQL (metadata).
For this preliminary prototype we deliberately use a single SQLite file
instead. Reasons:
  1. Zero external services to install/configure - a judge or teammate
     can run the whole system with just Python, no Docker/DB server.
  2. The graph in this prototype (a few hundred nodes / ~1500 edges) is
     small enough that in-memory NetworkX (built from SQLite rows) gives
     us all the graph-analytics power of Neo4j (centrality, betweenness,
     communities, path-finding) without operational complexity.
  3. Nothing about the data model is SQLite-specific - the same schema
     maps cleanly onto Neo4j/Postgres later; docs/architecture.md shows
     exactly how a production deployment would swap this layer out.

This keeps the promise of the brief ("prefer reliability over
technological complexity... you may simplify... but explain why").
"""

import sqlite3
import json
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "nexus.db")
DB_PATH = os.path.abspath(DB_PATH)

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT,
    status TEXT,
    period_start TEXT,
    period_end TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,   -- Person | Phone | Vehicle | Location | Organization
    name TEXT NOT NULL,
    attributes TEXT              -- JSON blob of type-specific fields
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    type TEXT,
    timestamp TEXT,
    location_id TEXT,
    description TEXT,
    case_id TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    type TEXT,
    description TEXT,
    source_record TEXT,
    timestamp TEXT,
    extraction_confidence REAL
);

CREATE TABLE IF NOT EXISTS relationships (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    type TEXT NOT NULL,
    timestamp TEXT,
    confidence REAL,
    status TEXT,                 -- observed | inferred
    evidence_ids TEXT,           -- JSON list
    notes TEXT,
    review_state TEXT DEFAULT 'pending'  -- pending | accepted | rejected | dismissed
);

CREATE INDEX IF NOT EXISTS idx_rel_source ON relationships(source);
CREATE INDEX IF NOT EXISTS idx_rel_target ON relationships(target);
CREATE INDEX IF NOT EXISTS idx_rel_status ON relationships(status);

CREATE TABLE IF NOT EXISTS potential_links (
    id TEXT PRIMARY KEY,
    entity_a TEXT NOT NULL,
    entity_b TEXT NOT NULL,
    confidence REAL,
    reasons TEXT,                -- JSON list of strings
    evidence_chain TEXT,         -- JSON list of entity ids forming the path
    review_state TEXT DEFAULT 'pending',  -- pending | investigate | dismissed
    generated_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT,
    target_id TEXT,
    detail TEXT,
    timestamp TEXT
);
"""


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_cursor():
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    finally:
        conn.close()


def init_db(reset: bool = False):
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def log_action(action: str, target_id: str, detail: str):
    from datetime import datetime
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO audit_log (action, target_id, detail, timestamp) VALUES (?, ?, ?, ?)",
            (action, target_id, detail, datetime.now().isoformat()),
        )
