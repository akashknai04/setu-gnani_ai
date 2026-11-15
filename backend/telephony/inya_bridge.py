"""Bridge between a real phone call (Gnani Inya) and the SETU AI policy engine.

Inya owns the phone line: it dials the rider, listens (its streaming ASR, kn/hi/en with language
switching) and speaks (Gnani TTS). It does NOT decide anything. On every rider sentence the Inya agent
runs an On-Call action that POSTs the words here; this endpoint runs the same deterministic pipeline as
the web call (OTP redaction -> fast path -> policy engine -> ledger -> fixed template) and returns the
exact sentence Inya must say, in the rider's language.

When a request needs Asha's approval, this endpoint holds the HTTP request open (up to INYA_WAIT_S)
while her phone shows the one-tap card, then returns the outcome. If she has not answered by then, the
rider hears "still asking"; the outcome is spoken on the rider's next sentence.

    POST /inya/turn        {conversation_id, user_text}        -> {reply, language, end_call, ...}
    POST /inya/call-ended  Inya post-call webhook               -> closes the call, unanswered cards die
    GET  /inya/status      for live_check / the setup script (no secrets)

Both POSTs require  Authorization: Bearer <INYA_BRIDGE_TOKEN>.
"""
from __future__ import annotations

import hmac
import threading
import time
import unicodedata

from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from backend.engine import messages as M
from backend.engine.otp_guard import redact_otp

LANG_CODES = {"hi": "hi-IN", "kn": "kn-IN", "en": "en-IN"}

STILL_WAITING = {
    "hi": "ग्राहक ने अभी जवाब नहीं दिया है। मैं पूछ रहा हूँ, कृपया थोड़ा रुकिए।",
    "kn": "ಗ್ರಾಹಕರು ಇನ್ನೂ ಉತ್ತರಿಸಿಲ್ಲ. ನಾನು ಕೇಳುತ್ತಿದ್ದೇನೆ, ದಯವಿಟ್ಟು ಸ್ವಲ್ಪ ಕಾಯಿರಿ.",
    "en": "The customer hasn't answered yet. I'm still asking, please hold on.",
}

# Spoken first when Inya picks up. Short, all three languages, and honest that it is an AI and a test.
PHONE_GREETING = ("ನಮಸ್ಕಾರ, नमस्ते, hello! I am Asha's AI assistant, answering for her. This is a test call. "
                  "You can speak in ಕನ್ನಡ, हिंदी or English.")
PHONE_END = "ಧನ್ಯವಾದ. धन्यवाद. Thank you."


def _first(d: dict, *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, (int, float)):
            return str(v)
    return ""


class InyaBridge:
    def __init__(self, agent, settings, hub, reply_listeners: dict):
        self.agent, self.s, self.hub = agent, settings, hub
        self.listeners = reply_listeners
        self.calls: dict[str, str] = {}          # Inya conversation id -> our call id
        self.outcomes: dict[str, object] = {}    # call id -> TurnResult not yet spoken
        self.events: dict[str, threading.Event] = {}
        self.lock = threading.Lock()

    # ------------------------------------------------------------ helpers
    def check_auth(self, request: Request) -> None:
        want = self.s.inya_bridge_token
        if not want:
            raise HTTPException(503, "Phone bridge is off: set INYA_BRIDGE_TOKEN in .env")
        got = request.headers.get("authorization", "")
        got = got[7:] if got.lower().startswith("bearer ") else request.headers.get("x-bridge-token", "")
        if not hmac.compare_digest(got.encode(), want.encode()):
            raise HTTPException(401, "bad bridge token")

    def _on_reply(self, res) -> None:
        """Called by the server whenever an approval outcome / expiry is ready for this call."""
        with self.lock:
            self.outcomes[res.call_id] = res
            ev = self.events.get(res.call_id)
        if ev:
            ev.set()

    def call_for(self, conv_id: str) -> str:
        with self.lock:
            cid = self.calls.get(conv_id)
        if cid:
            return cid
        info = self.agent.start_call(self.s.inya_order_id)
        cid = info["call_id"]
        self.agent.db.execute("UPDATE calls SET language=? WHERE id=?", ("en", cid))
        with self.lock:
            self.calls[conv_id] = cid
            self.events[cid] = threading.Event()
        self.listeners[cid] = self._on_reply
        self.hub.publish("status", {"call_id": cid, "order_id": self.s.inya_order_id, "started": True,
                                    "channel": "phone", "customer_message": self.agent.customer_view(cid)})
        return cid

    @staticmethod
    def spoken(res) -> str:
        if not res.reply_key:
            return ""
        return M.rider_reply(res.reply_key, res.language, **(res.reply_slots or {}))

    def payload(self, res, *, text: str | None = None, waiting=False) -> dict:
        lang = res.language if res.language in LANG_CODES else "en"
        return {"reply": text if text is not None else self.spoken(res), "language": lang,
                "language_code": LANG_CODES[lang], "end_call": bool(res.ended), "waiting_for_customer": waiting,
                "action": (res.decision or {}).get("action"), "reason": (res.decision or {}).get("reason"),
                "intent": (res.intent or {}).get("intent"), "call_id": res.call_id, "simulated_provider": True}

    # ------------------------------------------------------------ the turn
    def turn(self, conv_id: str, text: str) -> dict:
        cid = self.call_for(conv_id)
        # An answer from Asha that arrived after the last reply is spoken first.
        with self.lock:
            pending = self.outcomes.pop(cid, None)
        if pending is not None:
            return self.payload(pending)

        text = unicodedata.normalize("NFC", text)
        res = self.agent.handle_transcript(cid, text or None, stt_ok=bool(text))
        self.hub.publish("rider_reply", {**res.to_dict(), "channel": "phone",
                                          "transcript": redact_otp(text)}, call_id=cid)
        self.hub.publish("status", {"call_id": cid, "order_id": res.order_id,
                                    "customer_message": res.customer_message})
        if (res.decision or {}).get("action") != "request_approval":
            if res.ended:
                self.forget(conv_id)
            return self.payload(res)

        # Asha's card is on her phone. Hold the line until she taps (or INYA_WAIT_S passes).
        ev = self.events[cid]
        ev.clear()
        deadline = time.monotonic() + self.s.inya_wait_s
        while time.monotonic() < deadline:
            if ev.wait(0.25):
                break
            for r in self.agent.expire_due():      # the sweeper also does this; harmless if both run
                self._on_reply(r)
        with self.lock:
            outcome = self.outcomes.pop(cid, None)
        if outcome is not None:
            return self.payload(outcome)
        return self.payload(res, text=STILL_WAITING[res.language if res.language in STILL_WAITING else "en"],
                            waiting=True)

    def end(self, conv_id: str) -> dict:
        with self.lock:
            cid = self.calls.get(conv_id)
        if not cid:
            return {"ok": True, "known": False}
        res = self.agent.end_call(cid, by="rider_hung_up")
        self.hub.publish("status", {"call_id": cid, "order_id": res.order_id, "ended": True,
                                    "customer_message": res.customer_message})
        self.forget(conv_id)
        return {"ok": True, "known": True, "summary": self.agent.call_summary(cid)}

    def forget(self, conv_id: str) -> None:
        with self.lock:
            cid = self.calls.pop(conv_id, None)
            if cid:
                self.events.pop(cid, None)
                self.outcomes.pop(cid, None)
        if cid:
            self.listeners.pop(cid, None)


def mount_inya_bridge(app, agent, settings, hub, reply_listeners: dict) -> InyaBridge:
    bridge = InyaBridge(agent, settings, hub, reply_listeners)
    app.state.inya = bridge

    @app.post("/inya/turn")
    async def inya_turn(request: Request):
        bridge.check_auth(request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        conv = _first(body, "conversation_id", "conversationId", "sender_id", "senderId", "session_id",
                      "call_id", "phone") or "inya-default"
        text = _first(body, "user_text", "userText", "text", "transcript", "message", "query")
        try:
            return await run_in_threadpool(bridge.turn, conv, text)
        except Exception as e:  # the rider must always hear something safe
            from backend.engine.orchestrator import CallEnded
            if isinstance(e, CallEnded):
                bridge.forget(conv)
                return await run_in_threadpool(bridge.turn, conv, text)
            raise

    @app.post("/inya/call-ended")
    async def inya_call_ended(request: Request):
        bridge.check_auth(request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        body = body if isinstance(body, dict) else {}
        conv = _first(body, "conversation_id", "conversationId", "sender_id", "senderId", "session_id",
                      "call_id", "phone") or "inya-default"
        return await run_in_threadpool(bridge.end, conv)

    @app.get("/inya/status")
    def inya_status():
        return {"bridge_enabled": bool(settings.inya_bridge_token), "order_id": settings.inya_order_id,
                "active_calls": len(bridge.calls), "wait_s": settings.inya_wait_s,
                "greeting": PHONE_GREETING}

    return bridge
