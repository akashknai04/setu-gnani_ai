"""Customer approval tokens.

Token = base64url(payload_json) + "." + base64url(HMAC-SHA256(secret, payload)).
Payload binds call_id + order_id + action + expiry + nonce. Tokens are single use:
the nonce is burned (INSERT into used_nonces) the first time it is accepted.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid

from backend.db import Database


class ApprovalError(Exception):
    """Raised for any token that must not be honoured. .code says why."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class ApprovalService:
    def __init__(self, db: Database, secret: str, ttl_s: int = 30, clock=time.time):
        if not secret:
            raise ValueError("approval secret required")
        self.db = db
        self.secret = secret.encode()
        self.ttl_s = ttl_s
        self.clock = clock

    # ---- token primitives -------------------------------------------------
    def _sign(self, payload: bytes) -> str:
        return _b64(hmac.new(self.secret, payload, hashlib.sha256).digest())

    def issue_token(self, call_id: str, order_id: str, action: str) -> tuple[str, dict]:
        payload = {
            "call_id": call_id,
            "order_id": order_id,
            "action": action,
            "exp": round(self.clock() + self.ttl_s, 3),
            "nonce": secrets.token_hex(16),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return f"{_b64(raw)}.{self._sign(raw)}", payload

    def verify_token(self, token: str, *, call_id: str, order_id: str, action: str) -> dict:
        """Check signature, binding and expiry. Does NOT burn the nonce."""
        try:
            p64, sig = token.split(".", 1)
            raw = _unb64(p64)
        except Exception:
            raise ApprovalError("malformed")
        if not hmac.compare_digest(sig, self._sign(raw)):
            raise ApprovalError("bad_signature")
        payload = json.loads(raw)
        if payload.get("call_id") != call_id:
            raise ApprovalError("wrong_call")
        if payload.get("order_id") != order_id:
            raise ApprovalError("wrong_order")
        if payload.get("action") != action:
            raise ApprovalError("wrong_action")
        if self.clock() > float(payload["exp"]):
            raise ApprovalError("expired")
        if self.db.one("SELECT 1 AS x FROM used_nonces WHERE nonce=?", (payload["nonce"],)):
            raise ApprovalError("reused")
        return payload

    def consume(self, token: str, *, call_id: str, order_id: str, action: str) -> dict:
        """Verify and burn atomically. Second use raises ApprovalError('reused')."""
        with self.db.lock:
            payload = self.verify_token(token, call_id=call_id, order_id=order_id, action=action)
            try:
                self.db.execute("INSERT INTO used_nonces (nonce, used_at) VALUES (?,?)",
                                (payload["nonce"], self.clock()))
            except sqlite3.IntegrityError:
                raise ApprovalError("reused")
            return payload

    # ---- approval records ---------------------------------------------------
    def create(self, *, call_id: str, order_id: str, action: str, intent: dict) -> dict:
        token, payload = self.issue_token(call_id, order_id, action)
        apr_id = f"apr_{uuid.uuid4().hex[:10]}"
        self.db.execute(
            "INSERT INTO approvals (id,call_id,order_id,action,intent_json,token,nonce,expires_at,status,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (apr_id, call_id, order_id, action, json.dumps(intent, ensure_ascii=False), token,
             payload["nonce"], payload["exp"], "pending", self.clock()),
        )
        return self.get(apr_id)

    def get(self, apr_id: str) -> dict | None:
        row = self.db.one("SELECT * FROM approvals WHERE id=?", (apr_id,))
        if row:
            row["intent"] = json.loads(row.pop("intent_json"))
        return row

    def pending(self) -> list[dict]:
        rows = self.db.all("SELECT * FROM approvals WHERE status='pending' ORDER BY created_at")
        for r in rows:
            r["intent"] = json.loads(r.pop("intent_json"))
        return rows

    def due_for_expiry(self) -> list[dict]:
        return [r for r in self.pending() if self.clock() > r["expires_at"]]

    def set_status(self, apr_id: str, status: str) -> None:
        self.db.execute("UPDATE approvals SET status=?, decided_at=? WHERE id=?", (status, self.clock(), apr_id))
