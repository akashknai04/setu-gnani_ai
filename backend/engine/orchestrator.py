"""Call orchestration: transcript -> intent -> policy -> action -> reply + ledger.

Voice-free on purpose so every rule can be tested without audio. The FastAPI layer
wraps it with STT before and TTS after.

Invariants enforced here:
- every transcript is OTP-redacted before it is stored, logged or classified;
- only policy.evaluate() decides; the classifier only proposes an intent label;
- a provider call needs a ProviderPermit from the state machine;
- every outcome (including failures) writes a ledger event and a customer message key;
- any unexpected exception ends the turn safely (escalated reply, system_failure message).
"""
from __future__ import annotations

import time
import traceback
import uuid
from dataclasses import dataclass, field

from backend.db import Database
from backend.engine import messages as M
from backend.engine.approvals import ApprovalError, ApprovalService
from backend.engine.ledger import Ledger
from backend.engine.otp_guard import redact_otp
from backend.engine.policy import (APPROVED, CONTACT_LATER, EXPIRED, NO_APPROVAL, REJECTED, Decision, Order,
                                   Prefs, evaluate)
from backend.engine.state_machine import CallSession, State
from backend.intent import fast_path
from backend.intent.schema import IntentResult
from backend.providers.base import DeliveryProvider

class CallEnded(RuntimeError):
    """The call is over; nothing more can be said on it."""


DECISION_MAP = {"approve": APPROVED, "reject": REJECTED, "contact_later": CONTACT_LATER}


@dataclass
class TurnResult:
    call_id: str
    order_id: str
    transcript: str = ""
    language: str = "hi"
    intent: dict | None = None
    decision: dict | None = None
    reply_key: str = ""
    reply_text: str = ""
    reply_slots: dict = field(default_factory=dict)
    state: str = ""
    approval_id: str | None = None
    customer_message: dict | None = None
    provider: dict | None = None
    ended: bool = False
    timings_ms: dict = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class Agent:
    def __init__(self, db: Database, ledger: Ledger, approvals: ApprovalService, provider: DeliveryProvider,
                 evon=None, clock=time.time, notify=None):
        self.db, self.ledger, self.approvals, self.provider = db, ledger, approvals, provider
        self.evon = evon
        self.clock = clock
        self.notify = notify or (lambda kind, payload: None)

    # ------------------------------------------------------------------ loading
    def load_order(self, order_id: str) -> tuple[Order, Prefs | None]:
        row = self.db.one("SELECT * FROM orders WHERE id=?", (order_id,))
        if not row:
            return Order(order_id, False, "unknown", False), None
        cust = self.db.one("SELECT * FROM customers WHERE id=?", (row["customer_id"],))
        return Order(row["id"], True, row["status"], bool(row["requires_otp"])), Prefs.from_row(cust)

    def _call(self, call_id: str) -> dict:
        row = self.db.one("SELECT * FROM calls WHERE id=?", (call_id,))
        if not row:
            raise KeyError(f"unknown call {call_id}")
        return row

    def _save_state(self, session: CallSession, **extra) -> None:
        sets = ["state=?"] + [f"{k}=?" for k in extra]
        self.db.execute(f"UPDATE calls SET {', '.join(sets)} WHERE id=?",
                        (session.state.value, *extra.values(), session.call_id))

    def _window(self, prefs: Prefs | None) -> str:
        return M.fmt_window(prefs.window_start, prefs.window_end) if prefs else "the customer's preferred time"

    def _log(self, order_id, call_id, event_type, evidence, detail=None, source="agent"):
        ev = self.ledger.append(order_id=order_id, call_id=call_id, event_type=event_type,
                                evidence_level=evidence, source=source, detail=detail or {})
        self.notify("ledger", ev)
        return ev

    def customer_view(self, call_id: str) -> dict:
        return M.select_customer_message(self.ledger.events(call_id=call_id))

    # ------------------------------------------------------------------ call start
    def start_call(self, order_id: str) -> dict:
        call_id = f"call_{uuid.uuid4().hex[:10]}"
        self.db.execute("INSERT INTO calls (id,order_id,state,created_at) VALUES (?,?,?,?)",
                        (call_id, order_id, State.GREETING.value, self.clock()))
        session = CallSession(call_id, order_id)
        order, _ = self.load_order(order_id)
        self._log(order_id, call_id, "call_started", "info",
                  {"ai_disclosure": True, "order_valid": order.order_valid,
                   "customer_message": "rider_called", "slots": {}})
        session.transition(State.LISTENING)
        self._save_state(session)
        greeting = {lang: M.rider_reply("greeting", lang) for lang in M.LANGS}
        return {"call_id": call_id, "order_id": order_id, "state": session.state.value, "greeting": greeting}

    # ------------------------------------------------------------------ rider turn
    def handle_transcript(self, call_id: str, transcript: str | None, *, stt_language: str | None = None,
                          stt_ok: bool = True, short_clip: bool = False) -> TurnResult:
        call = self._call(call_id)
        if call.get("ended_at"):
            raise CallEnded(call_id)
        res = TurnResult(call_id=call_id, order_id=call["order_id"], language=call["language"])
        try:
            return self._handle(call, res, transcript, stt_language, stt_ok, short_clip)
        except Exception as e:  # never crash silently, never claim success
            return self._fail_safely(call, res, e)

    def _handle(self, call, res: TurnResult, transcript, stt_language, stt_ok, short_clip) -> TurnResult:
        call_id, order_id = call["id"], call["order_id"]
        session = CallSession(call_id, order_id, call["state"])
        if session.state != State.LISTENING:
            # e.g. still waiting for the customer: keep the rider on the holding line
            if session.state == State.WAITING_APPROVAL:
                clean = redact_otp(transcript or "")
                said, _ = fast_path.classify(clean, stt_language)
                res.transcript, res.language = clean, said.language
                res.intent = said.to_dict()
                if said.intent == "end_call":  # rider says bye while the customer is still deciding
                    return self.end_call(call["id"], by="rider_said_goodbye", language=said.language, res=res)
                self._log(call["order_id"], call["id"], "rider_utterance_while_waiting", "info",
                          {"transcript": clean, "intent": said.intent}, source="rider_untrusted")
                res.reply_key, res.reply_text = "holding", M.rider_reply("holding", said.language)
                res.state = session.state.value
                return res
            raise RuntimeError(f"call not listening (state={session.state.value})")
        order, prefs = self.load_order(order_id)
        window = self._window(prefs)

        # ---- STT failure path: ask once, then escalate
        if not stt_ok or transcript is None:
            fails = call["stt_failures"] + 1
            self.db.execute("UPDATE calls SET stt_failures=? WHERE id=?", (fails, call_id))
            self._log(order_id, call_id, "stt_failed", "info", {"attempt": fails})
            if fails < 2:
                res.reply_key, res.reply_text = "ask_repeat", M.rider_reply("ask_repeat", call["language"])
                res.state = session.state.value
                return res
            intent = IntentResult("unclear", None, call["language"], "fallback", ["stt_failed_twice"])
            return self._decide(session, res, order, prefs, intent, clarify_attempts=1, window=window)

        # ---- redact before anything else touches the text
        t0 = time.perf_counter()
        clean = redact_otp(transcript)
        res.transcript = clean
        intent, flags = fast_path.classify(clean, stt_language)
        if intent.intent == "unclear" and self.evon is not None and not flags["injection"]:
            intent = self.evon.classify(clean, intent, flags)
        res.timings_ms["intent"] = round((time.perf_counter() - t0) * 1000, 2)
        res.language = intent.language
        self.db.execute("UPDATE calls SET language=? WHERE id=?", (intent.language, call_id))
        self._log(order_id, call_id, "rider_utterance", "info",
                  {"transcript": clean, "language": intent.language, "intent": intent.intent,
                   "time": intent.time, "intent_source": intent.source, "injection_flag": flags["injection"]},
                  source="rider_untrusted")

        clarify = call["clarify_attempts"]
        if flags["injection"] and intent.intent != "request_otp":
            # Manipulation attempt: whatever else was asked, no approval card and no retry -> escalate.
            intent = IntentResult("unclear", None, intent.language, "fast_path", intent.matched + ["injection"])
            clarify = 1
        if short_clip and intent.intent == "unclear" and clarify == 0:
            self.db.execute("UPDATE calls SET clarify_attempts=1 WHERE id=?", (call_id,))
            self._log(order_id, call_id, "language_uncertain", "info", {"short_clip": True})
            res.intent = intent.to_dict()
            res.reply_key, res.reply_text = "choose_language", M.rider_reply("choose_language", intent.language)
            res.state = session.state.value
            return res
        return self._decide(session, res, order, prefs, intent, clarify_attempts=clarify, window=window)

    # ------------------------------------------------------------------ policy + outcome
    def _decide(self, session: CallSession, res: TurnResult, order: Order, prefs: Prefs | None,
                intent: IntentResult, *, clarify_attempts: int, window: str, approval: str = NO_APPROVAL,
                approval_id: str | None = None) -> TurnResult:
        t0 = time.perf_counter()
        session.transition(State.POLICY_CHECK)
        safe_prefs = prefs or Prefs("00:00", "00:00")
        decision = evaluate(intent.intent, safe_prefs, order, approval, self.provider.capabilities,
                            time=intent.time, clarify_attempts=clarify_attempts)
        session.apply_decision(decision)
        res.timings_ms["policy"] = round((time.perf_counter() - t0) * 1000, 3)
        res.intent, res.decision, res.language = intent.to_dict(), decision.to_dict(), intent.language
        self._log(order.id, session.call_id, "policy_decision", "info",
                  {"intent": intent.intent, "approval": approval, **decision.to_dict()}, source="policy_engine")

        lang = intent.language
        who = "guard" if intent.intent == "guard_drop_request" else "neighbor"
        cid, oid = session.call_id, order.id

        if decision.action == "request_approval":
            apr = self.approvals.create(call_id=cid, order_id=oid, action=intent.intent, intent=intent.to_dict())
            res.approval_id = apr["id"]
            self._log(oid, cid, "approval_requested", "requested",
                      {"approval_id": apr["id"], "action": intent.intent, "expires_at": apr["expires_at"],
                       "customer_message": "approval_requested",
                       "slots": {"request_intent": intent.intent, "time": intent.time}})
            self.notify("approval", self.public_approval(apr))
            res.reply_key, res.reply_text = "holding", M.rider_reply("holding", lang)
            self._save_state(session)
            res.state = session.state.value
            res.customer_message = self.customer_view(cid)
            return res

        reply_key, slots, cmsg, cslots = self._outcome(decision, intent, approval, who, window, prefs)

        if decision.action == "instant_action" and decision.provider_request:
            evidence = "pre_approved" if decision.reason.endswith("pre_approved") else None
            if evidence:
                self._log(oid, cid, "pre_approved_rule", "pre_approved", {"rule": decision.reason})
            permit = session.authorize_provider(decision, order)
            try:
                resp = self.provider.request(permit, intent.intent)
            except Exception as e:  # provider blew up: safe failure
                resp = None
                err = str(e)
            res.provider = resp.to_dict() if resp else {"status": "error", "simulated": True}
            if resp and resp.accepted:
                self._log(oid, cid, "provider_response", "provider_accepted", resp.to_dict(),
                          source="mock_delivery_provider")
                if intent.intent == "change_address":
                    reply_key, cmsg = "address_change_ok", "address_change_provider_accepted"
                else:
                    reply_key, cmsg = "handover_ok", "handover_provider_accepted"
            else:
                self._log(oid, cid, "provider_response", "rejected_or_unresolved",
                          resp.to_dict() if resp else {"status": "error", "detail": err, "simulated": True},
                          source="mock_delivery_provider")
                reply_key, cmsg = "handover_provider_failed", "handover_provider_failed"
        elif decision.action == "record_rider_agreed":
            self._log(oid, cid, "rider_commitment", "rider_agreed",
                      {"time": intent.time, "platform_confirmed": False})

        if decision.reason == "end_call":
            self._end(cid, oid, "rider_said_goodbye")
            res.ended = True
        if decision.reason == "ask_to_repeat_once":
            self.db.execute("UPDATE calls SET clarify_attempts=clarify_attempts+1 WHERE id=?", (cid,))

        outcome_level = {"refuse": "rejected_or_unresolved", "escalate": "rejected_or_unresolved"}.get(
            decision.action, "info")
        if cmsg:
            self._log(oid, cid, "outcome", outcome_level,
                      {"reason": decision.reason, "customer_message": cmsg, "slots": cslots,
                       "approval_id": approval_id})
        res.reply_key = reply_key
        res.reply_slots = {**slots, "who": who}
        res.reply_text = M.rider_reply(reply_key, lang, **res.reply_slots)
        session.transition(State.REPLY_AND_RECORD)
        session.transition(State.LISTENING)
        self._save_state(session)
        res.state = session.state.value
        res.customer_message = self.customer_view(cid)
        self.notify("status", {"call_id": cid, "order_id": oid, "customer_message": res.customer_message})
        return res

    def _outcome(self, d: Decision, intent: IntentResult, approval: str, who: str, window: str, prefs):
        """Map a decision to (rider_key, rider_slots, customer_key, customer_slots). Templates only."""
        w = {"window": window}
        r = d.reason
        if r == "otp_protection":
            return "otp_refused", {}, "otp_refused", {}
        if r == "order_not_valid" or d.action == "escalate":
            return "escalated", {}, "escalated", {}
        if r == "handover_not_possible_for_verified_order":
            return "handover_refused_verified", w, "handover_refused_verified", {"who": who}
        if r == "greet_back":
            return "listening", {}, None, {}
        if r == "end_call":
            return "goodbye", {}, None, {}
        if r == "agent_answering_for_customer":
            return "customer_unavailable", w, None, {}
        if r == "share_preferred_window":
            return "availability", w, "availability_shared", w
        if r == "share_area_and_landmark_only":
            return "address", {"area": prefs.area, "landmark": prefs.landmark}, "address_shared", {}
        if r == "ask_to_repeat_once":
            return "ask_repeat", {}, None, {}
        if r == "inside_customer_window":
            return "rider_agreed", {"time": intent.time}, "rider_agreed_time", {"time": intent.time}
        if r == "customer_approved_time":
            return "time_approved", {"time": intent.time}, "time_approved", {"time": intent.time}
        if d.provider_request:
            return "handover_ok", w, "handover_provider_accepted", {"who": who}  # overwritten by provider result
        if d.action == "refuse":
            if approval == CONTACT_LATER:
                return "contact_later", {}, "contact_later", {}
            if approval == EXPIRED:
                return "unresolved_fallback", w, "unresolved", w
            return "declined", w, "declined", {}
        return "escalated", {}, "escalated", {}

    # ------------------------------------------------------------------ call end
    def _end(self, call_id: str, order_id: str, by: str) -> None:
        """Mark the call over and close any approval the customer has not answered yet.

        A late tap must not trigger anything: the rider is gone, so nobody could be told.
        """
        self.db.execute("UPDATE calls SET ended_at=? WHERE id=? AND ended_at IS NULL", (self.clock(), call_id))
        for apr in self.approvals.pending():
            if apr["call_id"] == call_id:
                self.approvals.set_status(apr["id"], "call_ended")
                self._log(order_id, call_id, "approval_cancelled", "rejected_or_unresolved",
                          {"approval_id": apr["id"], "reason": by, "customer_message": "call_ended_unresolved",
                           "slots": {}})
                self.notify("approval_closed", {"id": apr["id"], "status": "call_ended"})
        self._log(order_id, call_id, "call_ended", "info", {"by": by})
        self.notify("status", {"call_id": call_id, "order_id": order_id, "ended": True,
                               "customer_message": self.customer_view(call_id)})

    def end_call(self, call_id: str, by: str = "rider_hung_up", language: str | None = None,
                 res: TurnResult | None = None) -> TurnResult:
        call = self._call(call_id)
        res = res or TurnResult(call_id=call_id, order_id=call["order_id"], language=call["language"])
        if not call.get("ended_at"):
            self._end(call_id, call["order_id"], by)
            self.db.execute("UPDATE calls SET state=? WHERE id=?", (State.LISTENING.value, call_id))
        lang = language or call["language"]
        res.language, res.ended, res.state = lang, True, "ENDED"
        if by != "rider_hung_up":  # the rider is still on the line to hear it
            res.reply_key, res.reply_text = "goodbye", M.rider_reply("goodbye", lang)
        res.customer_message = self.customer_view(call_id)
        return res

    def call_summary(self, call_id: str) -> dict:
        call = self._call(call_id)
        events = self.ledger.events(call_id=call_id)
        turns = [e["detail"] for e in events if e["event_type"] == "rider_utterance"]
        return {"call_id": call_id, "order_id": call["order_id"], "language": call["language"],
                "started_at": call["created_at"], "ended_at": call.get("ended_at"),
                "turns": len(turns), "intents": [t.get("intent") for t in turns],
                "highest_evidence": Ledger.highest_evidence(events),
                "customer_message": self.customer_view(call_id), "chain_ok": self.ledger.verify_chain().ok,
                "events": len(events), "simulated": True}

    # ------------------------------------------------------------------ customer decision
    def public_approval(self, apr: dict) -> dict:
        order, _ = self.load_order(apr["order_id"])
        return {"id": apr["id"], "call_id": apr["call_id"], "order_id": apr["order_id"],
                "action": apr["action"], "label": M.request_label(apr["action"], apr["intent"].get("time")),
                "expires_at": apr["expires_at"], "token": apr["token"], "status": apr["status"],
                "requires_otp": order.requires_otp, "simulated": True}

    def decide_approval(self, approval_id: str, choice: str, token: str) -> TurnResult:
        apr = self.approvals.get(approval_id)
        if not apr:
            raise KeyError("unknown approval")
        call = self._call(apr["call_id"])
        res = TurnResult(call_id=call["id"], order_id=call["order_id"], language=call["language"],
                         approval_id=approval_id)
        if choice not in DECISION_MAP:
            raise ValueError("choice must be approve | reject | contact_later")
        if apr["status"] != "pending":
            res.error = f"approval already {apr['status']}"
            return res
        try:
            self.approvals.consume(token, call_id=apr["call_id"], order_id=apr["order_id"], action=apr["action"])
        except ApprovalError as e:
            if e.code == "expired":
                return self.expire(approval_id)
            self._log(apr["order_id"], apr["call_id"], "approval_token_rejected", "info", {"code": e.code})
            res.error = f"token rejected: {e.code}"
            return res
        state = DECISION_MAP[choice]
        self.approvals.set_status(approval_id, choice)
        self._log(apr["order_id"], apr["call_id"], "customer_decision",
                  "customer_approved" if state == APPROVED else "rejected_or_unresolved",
                  {"approval_id": approval_id, "choice": choice}, source="customer_one_tap")
        return self._reenter_policy(call, apr, state, res)

    def expire(self, approval_id: str) -> TurnResult:
        apr = self.approvals.get(approval_id)
        call = self._call(apr["call_id"])
        res = TurnResult(call_id=call["id"], order_id=call["order_id"], language=call["language"],
                         approval_id=approval_id)
        if apr["status"] != "pending":
            res.error = f"approval already {apr['status']}"
            return res
        self.approvals.set_status(approval_id, "expired")
        self._log(apr["order_id"], apr["call_id"], "approval_expired", "rejected_or_unresolved",
                  {"approval_id": approval_id})
        return self._reenter_policy(call, apr, EXPIRED, res)

    def expire_due(self) -> list[TurnResult]:
        return [self.expire(a["id"]) for a in self.approvals.due_for_expiry()]

    def _reenter_policy(self, call: dict, apr: dict, approval_state: str, res: TurnResult) -> TurnResult:
        try:
            session = CallSession(call["id"], call["order_id"], call["state"])
            order, prefs = self.load_order(call["order_id"])
            i = apr["intent"]
            intent = IntentResult(i["intent"], i.get("time"), i.get("language", call["language"]),
                                  i.get("source", "fast_path"), i.get("matched", []))
            out = self._decide(session, res, order, prefs, intent, clarify_attempts=call["clarify_attempts"],
                               window=self._window(prefs), approval=approval_state, approval_id=apr["id"])
            self.notify("rider_reply", out.to_dict())
            return out
        except Exception as e:
            return self._fail_safely(call, res, e)

    # ------------------------------------------------------------------ failure
    def _fail_safely(self, call: dict, res: TurnResult, e: Exception) -> TurnResult:
        self._log(call["order_id"], call["id"], "system_error", "rejected_or_unresolved",
                  {"error": type(e).__name__, "message": str(e)[:200], "customer_message": "system_failure",
                   "slots": {}})
        traceback.print_exc()
        res.error = f"{type(e).__name__}: {e}"
        res.reply_key = "escalated"
        res.reply_text = M.rider_reply("escalated", res.language or "hi")
        # put the call back into a listening state so the rider is never stuck
        self.db.execute("UPDATE calls SET state=? WHERE id=?", (State.LISTENING.value, call["id"]))
        res.state = State.LISTENING.value
        res.customer_message = self.customer_view(call["id"])
        self.notify("status", {"call_id": call["id"], "order_id": call["order_id"],
                               "customer_message": res.customer_message})
        return res

    def record_latency(self, call_id: str, timings: dict) -> None:
        turn = (self.db.one("SELECT COUNT(*) AS n FROM latency WHERE call_id=?", (call_id,)) or {"n": 0})["n"] + 1
        self.db.execute("INSERT INTO latency (call_id,turn,stt_ms,intent_ms,policy_ms,tts_ms,total_ms,ts)"
                        " VALUES (?,?,?,?,?,?,?,?)",
                        (call_id, turn, timings.get("stt"), timings.get("intent"), timings.get("policy"),
                         timings.get("tts"), timings.get("total"), self.clock()))
