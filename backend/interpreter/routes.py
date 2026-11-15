"""SETU AI live interpreted call.

The rider calls the customer. Two outcomes:
  * the customer answers -> SETU translates both ways, live: each sentence is heard, translated into the
    other person's language and spoken to them (with the original words on screen);
  * the customer doesn't answer in INTERPRET_RING_S, or taps "Let SETU's agent handle it" -> the rider's
    phone switches to SETU's AI agent (the existing /calls flow), which follows the customer's rules.

    POST /interpret/start                  {order_id, rider_lang}            -> {sid, ring_s, customer_lang}
    POST /interpret/{sid}/answer           {customer_lang}                   customer picks up
    POST /interpret/{sid}/decline          customer hands the call to the AI agent
    POST /interpret/{sid}/timeout          rider side: nobody answered in time
    POST /interpret/{sid}/say              {who, text, lang?}                one sentence, typed or scripted
    POST /interpret/{sid}/audio            multipart: who, audio, mock_transcript
    POST /interpret/{sid}/end              {who}
    GET  /interpret/{sid}                  session + translated transcript (OTP-masked)
    GET  /interpret/status                 phrases / model availability
WebSocket events: rider page on /ws/rider/<sid>, customer page on /ws/customer.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass, field

from fastapi import File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.interpreter.service import Translator

STATES = ("ringing", "connected", "ai_agent", "ended")

SYSTEM = {
    "connected_rider": {"en": "The customer answered. SETU is translating. Speak normally.",
                        "hi": "ग्राहक ने कॉल उठाया। SETU अनुवाद कर रहा है। आराम से बोलिए।",
                        "kn": "ಗ್ರಾಹಕರು ಕರೆ ಸ್ವೀಕರಿಸಿದರು. SETU ಅನುವಾದ ಮಾಡುತ್ತಿದೆ. ಸಹಜವಾಗಿ ಮಾತನಾಡಿ."},
    "connected_customer": {"en": "You're connected to the rider. SETU translates both ways. Speak in your language.",
                           "hi": "आप डिलीवरी पार्टनर से जुड़ गए हैं। SETU दोनों तरफ़ अनुवाद करेगा। अपनी भाषा में बोलिए।",
                           "kn": "ನೀವು ಡೆಲಿವರಿ ಪಾರ್ಟ್ನರ್ ಜೊತೆ ಸಂಪರ್ಕದಲ್ಲಿದ್ದೀರಿ. SETU ಎರಡೂ ಕಡೆ ಅನುವಾದಿಸುತ್ತದೆ. ನಿಮ್ಮ ಭಾಷೆಯಲ್ಲಿ ಮಾತನಾಡಿ."},
}
LANG_NAME = {"en": "English", "hi": "हिंदी", "kn": "ಕನ್ನಡ"}


class StartIn(BaseModel):
    order_id: str
    rider_lang: str = "hi"
    rider_gender: str = "m"


class AnswerIn(BaseModel):
    customer_lang: str | None = None


class SayIn(BaseModel):
    who: str
    text: str
    lang: str | None = None


class EndIn(BaseModel):
    who: str = "rider"


@dataclass
class Session:
    sid: str
    order_id: str
    customer_name: str
    rider_lang: str
    customer_lang: str
    rider_gender: str = "m"
    customer_gender: str = "f"
    state: str = "ringing"
    created: float = field(default_factory=time.time)
    answered_at: float | None = None
    ended_by: str | None = None
    lines: list = field(default_factory=list)

    def public(self) -> dict:
        d = asdict(self)
        d["lines"] = self.lines[-60:]
        return d


def mount_interpreter(app, *, db, hub, settings, speak, stt):
    """speak(text, lang, role) -> {"audio_url", "voice"}; stt(raw, filename, mock_transcript) -> dict."""
    tr = Translator(settings)
    app.state.translator = tr
    sessions: dict[str, Session] = {}
    lock = threading.Lock()
    if settings.translate_mode != "phrases":
        threading.Thread(target=tr.model.warm, daemon=True).start()

    def get(sid: str) -> Session:
        with lock:
            se = sessions.get(sid)
        if not se:
            raise HTTPException(404, "unknown interpreted call")
        return se

    def to_rider(kind, data, sid):
        hub.publish(kind, data, call_id=f"interp-{sid}")

    def to_customer(kind, data):
        hub.publish(kind, data)

    def set_state(se: Session, state: str, **extra):
        se.state = state
        payload = {"sid": se.sid, "state": state, "order_id": se.order_id, **extra}
        to_rider("interpret_state", payload, se.sid)
        to_customer("interpret_state", payload)

    def system_line(se: Session, key: str):
        for who, lang in (("rider", se.rider_lang), ("customer", se.customer_lang)):
            text = SYSTEM[f"{key}_{who}"][lang]
            line = {"sid": se.sid, "id": uuid.uuid4().hex[:8], "from": "setu", "to": who, "text": text,
                    "tgt_lang": lang, "clips": [{"text": text, **speak(text, lang, "ai")}], "notes": [],
                    "note_audio": []}
            (to_rider("interpret_line", line, se.sid) if who == "rider" else to_customer("interpret_line", line))

    @app.get("/interpret/status")
    def interpret_status():
        return {**tr.status(), "ring_s": settings.interpret_ring_s}

    @app.post("/interpret/start")
    def interpret_start(body: StartIn):
        row = db.one("SELECT o.id, o.status, c.name, c.language FROM orders o JOIN customers c ON c.id = o.customer_id "
                     "WHERE o.id = ?", (body.order_id,))
        if not row:
            raise HTTPException(404, "unknown order")
        row = dict(row)
        rl = body.rider_lang if body.rider_lang in LANG_NAME else "hi"
        cl = row["language"] if row["language"] in LANG_NAME else "en"
        se = Session(uuid.uuid4().hex[:10], body.order_id, row["name"], rl, cl,
                     rider_gender="f" if body.rider_gender == "f" else "m")
        with lock:
            sessions[se.sid] = se
            if len(sessions) > 200:
                for k in sorted(sessions, key=lambda k: sessions[k].created)[:50]:
                    sessions.pop(k, None)
        to_customer("interpret_ring", {"sid": se.sid, "order_id": se.order_id, "rider_lang": rl,
                                       "rider_lang_name": LANG_NAME[rl], "customer_lang": cl,
                                       "ring_s": settings.interpret_ring_s, "simulated": True})
        return {"sid": se.sid, "state": se.state, "ring_s": settings.interpret_ring_s, "customer_lang": cl,
                "customer_name": se.customer_name, "translator": tr.status()}

    @app.post("/interpret/{sid}/answer")
    def interpret_answer(sid: str, body: AnswerIn):
        se = get(sid)
        if se.state != "ringing":
            raise HTTPException(409, f"call is {se.state}")
        if body.customer_lang in LANG_NAME:
            se.customer_lang = body.customer_lang
        se.answered_at = time.time()
        set_state(se, "connected", rider_lang=se.rider_lang, customer_lang=se.customer_lang)
        system_line(se, "connected")
        return se.public()

    def _to_agent(se: Session, why: str):
        if se.state != "ringing":
            raise HTTPException(409, f"call is {se.state}")
        set_state(se, "ai_agent", reason=why)
        return se.public()

    @app.post("/interpret/{sid}/decline")
    def interpret_decline(sid: str):
        return _to_agent(get(sid), "customer_busy")

    @app.post("/interpret/{sid}/timeout")
    def interpret_timeout(sid: str):
        return _to_agent(get(sid), "no_answer")

    def _say(se: Session, who: str, text: str, lang: str | None, stt_meta: dict | None = None):
        if who not in ("rider", "customer"):
            raise HTTPException(422, "who must be rider or customer")
        if se.state != "connected":
            raise HTTPException(409, f"call is {se.state}")
        src = lang or (se.rider_lang if who == "rider" else se.customer_lang)
        tgt = se.customer_lang if who == "rider" else se.rider_lang
        gender = se.rider_gender if who == "rider" else se.customer_gender
        t = tr.translate(text, who, src, tgt, gender)
        listener = "customer" if who == "rider" else "rider"
        role = "rider" if who == "rider" else "ai"
        clips = [{"text": p, **speak(p, tgt, role)} for p in t.parts]
        line = {"sid": se.sid, "id": uuid.uuid4().hex[:8], "from": who, "to": listener, **t.to_dict(),
                "clips": clips, "ts": time.time(), "stt": stt_meta}
        notes = [{"text": n, **speak(n, tgt, "ai")} for n in t.notes] if t.notes else []
        line["note_audio"] = notes
        se.lines.append({k: v for k, v in line.items() if k not in ("clips", "note_audio")})
        if listener == "customer":
            to_customer("interpret_line", line)
        else:
            to_rider("interpret_line", line, se.sid)
        return line

    @app.post("/interpret/{sid}/say")
    def interpret_say(sid: str, body: SayIn):
        return _say(get(sid), body.who, body.text, body.lang)

    @app.post("/interpret/{sid}/audio")
    def interpret_audio(sid: str, who: str = Form(...), audio: UploadFile = File(...), mock_transcript: str = Form(""),
                        lang: str = Form("")):
        se = get(sid)
        r = stt(audio.file.read(), audio.filename or "clip.webm", mock_transcript)
        if not r.get("ok"):
            return {"sid": sid, "heard_nothing": True, "error": r.get("error"), "stt": r}
        if not r.get("transcript", "").strip():
            return {"sid": sid, "heard_nothing": True, "stt": r}
        return _say(se, who, r["transcript"], r.get("language") or lang or None, stt_meta=r)

    @app.post("/interpret/{sid}/end")
    def interpret_end(sid: str, body: EndIn):
        se = get(sid)
        if se.state == "ended":
            return se.public()
        se.ended_by = body.who
        set_state(se, "ended", by=body.who, lines=len(se.lines))
        return se.public()

    @app.get("/interpret/{sid}")
    def interpret_get(sid: str):
        return get(sid).public()

    return tr
