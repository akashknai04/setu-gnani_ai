"""SQLite storage. One connection per Database object, guarded by a lock.

The ledger table is protected by triggers so UPDATE and DELETE abort at the
database level, not just by convention in Python.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    language TEXT NOT NULL,
    meeting_mode INTEGER NOT NULL DEFAULT 0,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    allow_guard INTEGER NOT NULL DEFAULT 0,
    allow_neighbor INTEGER NOT NULL DEFAULT 0,
    area TEXT NOT NULL,
    landmark TEXT NOT NULL,
    simulated INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(id),
    store TEXT NOT NULL,
    status TEXT NOT NULL,
    requires_otp INTEGER NOT NULL,
    simulated INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS calls (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    state TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'hi',
    clarify_attempts INTEGER NOT NULL DEFAULT 0,
    stt_failures INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    ended_at REAL
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    call_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    action TEXT NOT NULL,
    intent_json TEXT NOT NULL,
    token TEXT NOT NULL,
    nonce TEXT NOT NULL UNIQUE,
    expires_at REAL NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    decided_at REAL
);
CREATE TABLE IF NOT EXISTS used_nonces (
    nonce TEXT PRIMARY KEY,
    used_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    order_id TEXT NOT NULL,
    call_id TEXT,
    event_type TEXT NOT NULL,
    evidence_level TEXT NOT NULL,
    source TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    simulated INTEGER NOT NULL,
    detail_json TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS ledger_no_update BEFORE UPDATE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS ledger_no_delete BEFORE DELETE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TABLE IF NOT EXISTS latency (
    call_id TEXT NOT NULL,
    turn INTEGER NOT NULL,
    stt_ms REAL, intent_ms REAL, policy_ms REAL, tts_ms REAL, total_ms REAL,
    ts REAL NOT NULL
);
"""


class Database:
    def __init__(self, path: str = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        if path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(calls)")}
        if "ended_at" not in cols:  # databases created before the voice-call update
            self.conn.execute("ALTER TABLE calls ADD COLUMN ended_at REAL")

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.conn.execute(sql, params)

    def one(self, sql: str, params: tuple = ()):
        with self.lock:
            row = self.conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    def all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def close(self) -> None:
        with self.lock:
            self.conn.close()
