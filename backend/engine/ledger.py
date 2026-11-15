"""Never-Lie Ledger: append-only, hash-chained event log.

hash = sha256(prev_hash + canonical_json(event)). Any edit to a stored row breaks
verify_chain(). The DB itself rejects UPDATE/DELETE via triggers.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass

from backend.db import Database
from backend.engine.otp_guard import redact_free_text

GENESIS = "0" * 64

EVIDENCE_LEVELS = (
    "info",                    # informational, proves nothing about the delivery
    "rejected_or_unresolved",
    "requested",
    "rider_agreed",
    "pre_approved",
    "customer_approved",
    "provider_accepted",       # simulated provider accepted the REQUEST (never "delivered")
)
EVIDENCE_RANK = {lvl: i for i, lvl in enumerate(EVIDENCE_LEVELS)}


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _event_body(row: dict) -> dict:
    return {
        "ts": row["ts"],
        "order_id": row["order_id"],
        "call_id": row["call_id"],
        "event_type": row["event_type"],
        "evidence_level": row["evidence_level"],
        "source": row["source"],
        "evidence_id": row["evidence_id"],
        "simulated": bool(row["simulated"]),
        "detail": row["detail"],
    }


def compute_hash(prev_hash: str, body: dict) -> str:
    return hashlib.sha256((prev_hash + canonical_json(body)).encode("utf-8")).hexdigest()


@dataclass
class ChainReport:
    ok: bool
    checked: int
    broken_at: int | None = None
    reason: str = ""


class Ledger:
    def __init__(self, db: Database, clock=time.time):
        self.db = db
        self.clock = clock

    def append(self, *, order_id: str, call_id: str | None, event_type: str, evidence_level: str,
               source: str, detail: dict | None = None, evidence_id: str | None = None) -> dict:
        if evidence_level not in EVIDENCE_RANK:
            raise ValueError(f"unknown evidence level {evidence_level!r}")
        detail = redact_free_text(dict(detail or {}))
        with self.db.lock:
            last = self.db.one("SELECT hash FROM ledger ORDER BY seq DESC LIMIT 1")
            prev = last["hash"] if last else GENESIS
            row = {
                "ts": round(self.clock(), 3),
                "order_id": order_id,
                "call_id": call_id,
                "event_type": event_type,
                "evidence_level": evidence_level,
                "source": source,
                "evidence_id": evidence_id or f"ev_{uuid.uuid4().hex[:12]}",
                "simulated": True,  # everything in this prototype is simulated
                "detail": detail,
            }
            h = compute_hash(prev, _event_body(row))
            cur = self.db.execute(
                "INSERT INTO ledger (ts,order_id,call_id,event_type,evidence_level,source,evidence_id,"
                "simulated,detail_json,prev_hash,hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (row["ts"], order_id, call_id, event_type, evidence_level, source, row["evidence_id"],
                 1, canonical_json(detail), prev, h),
            )
            row.update(seq=cur.lastrowid, prev_hash=prev, hash=h)
            return row

    def _rows(self, where: str = "", params: tuple = ()) -> list[dict]:
        rows = self.db.all(f"SELECT * FROM ledger {where} ORDER BY seq", params)
        for r in rows:
            r["detail"] = json.loads(r.pop("detail_json"))
            r["simulated"] = bool(r["simulated"])
        return rows

    def events(self, order_id: str | None = None, call_id: str | None = None) -> list[dict]:
        if call_id:
            return self._rows("WHERE call_id=?", (call_id,))
        if order_id:
            return self._rows("WHERE order_id=?", (order_id,))
        return self._rows()

    def verify_chain(self) -> ChainReport:
        prev = GENESIS
        rows = self._rows()
        for r in rows:
            if r["prev_hash"] != prev:
                return ChainReport(False, len(rows), r["seq"], "prev_hash mismatch")
            if compute_hash(prev, _event_body(r)) != r["hash"]:
                return ChainReport(False, len(rows), r["seq"], "hash mismatch (row edited)")
            prev = r["hash"]
        return ChainReport(True, len(rows))

    @staticmethod
    def highest_evidence(events: list[dict]) -> str:
        best = "info"
        for e in events:
            if EVIDENCE_RANK[e["evidence_level"]] > EVIDENCE_RANK[best]:
                best = e["evidence_level"]
        return best
