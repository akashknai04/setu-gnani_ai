"""SETU AI — FastAPI app.

Run:  python -m uvicorn backend.main:app --port 8000   (or: python run.py)
Pages: /rider  /customer
"""
from __future__ import annotations

import asyncio
import json
import re
import socket
import statistics
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import ROOT, Settings, check_ffmpeg
from backend.config import settings as default_settings
from backend.db import Database
from backend.engine import messages as M
from backend.engine.approvals import ApprovalService
from backend.engine.ledger import Ledger
from backend.engine.orchestrator import Agent, CallEnded, TurnResult
from backend.engine.state_machine import PermitDenied
from backend.intent.evon_intent import EvonClassifier
from backend.providers.mock_delivery import MODES, MockDeliveryProvider
from backend.seed import seed
from backend.voice.audio import AudioError, to_wav, wav_duration_s
from backend.voice.mock_voice import MockSTT, MockTTS, sidecar_path
from backend.voice.phrase_cache import PhraseCache
from backend.voice.prisma import PrismaSTT
from backend.voice.timbre import TimbreTTS

FRONTEND = ROOT / "frontend"
SHORT_CLIP_S = 1.2
MAX_CLIP_S = 30.0  # Prisma REST limit (confirmed)


def _lan_ip() -> str | None:
    """Best guess at this machine's address on the local network (no packets are sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.connect(("10.255.255.255", 1))
            ip = sk.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


class Hub:
    """Thread-safe fan-out to WebSocket clients (customer page + rider pages)."""

    def __init__(self):
        self.loop: asyncio.AbstractEventLoop | None = None
        self.customers: set[WebSocket] = set()
        self.riders: dict[str, set[WebSocket]] = {}

    async def _send(self, sockets, msg):
        for ws in list(sockets):
            try:
                await ws.send_text(msg)
            except Exception:
                sockets.discard(ws)

    def publish(self, kind: str, payload: dict, call_id: str | None = None) -> None:
        if not self.loop:
            return
        msg = json.dumps({"type": kind, "data": payload}, ensure_ascii=False, default=str)
        targets = self.riders.get(call_id, set()) if call_id else self.customers
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        coro = self._send(targets, msg)
        if running is self.loop:
            self.loop.create_task(coro)
        else:
            asyncio.run_coroutine_threadsafe(coro, self.loop)


class PrefsIn(BaseModel):
    window_start: str | None = None
    window_end: str | None = None
    allow_guard: bool | None = None
    allow_neighbor: bool | None = None
    meeting_mode: bool | None = None
    language: str | None = None


class StartIn(BaseModel):
    order_id: str
    language: str | None = None   # hi | kn | en: greet in one language; omitted = all three


class DecideIn(BaseModel):
    decision: str
    token: str


class TextIn(BaseModel):
    text: str
    language: str | None = None


class RiderLineIn(BaseModel):
    text: str = ""
    language: str = "hi"


class ModeIn(BaseModel):
    mode: str


_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or default_settings
    ffmpeg_version = check_ffmpeg()  # fail fast with a clear message

    db = Database(s.db_path)
    seed(db)
    ledger = Ledger(db)
    approvals = ApprovalService(db, s.approval_secret, s.approval_ttl_s)
    provider = MockDeliveryProvider("accept")
    hub = Hub()
    evon = EvonClassifier(s) if s.evon_mode != "off" else None

    if s.voice_live:
        stt_live, tts = PrismaSTT(s), TimbreTTS(s)
        tag = f"{s.timbre_model}|{json.dumps(s.timbre_voices, sort_keys=True)}|{s.timbre_sample_rate}"
    else:
        from backend.voice.recorded import RecordedVoice
        recorded = RecordedVoice("ai")
        stt_live = None
        tts, tag = (recorded, "recorded") if recorded.manifest else (MockTTS(), "mock")
    mock_stt = MockSTT()

    class _RiderVoice:
        """Speaks the scripted rider line in a different voice, for solo scenario playback only.
        Never used for benchmark audio (that must be recorded by people)."""
        def synthesize(self, text, lang, voice=None):
            return tts.synthesize(text, lang, voice=s.timbre_rider_voices.get(lang)) if s.voice_live else tts.synthesize(text, lang)
    rider_cache = PhraseCache(str(Path(s.phrase_cache_dir) / "rider"), _RiderVoice(), tag="rider|" + tag)
    cache = PhraseCache(s.phrase_cache_dir, tts, tag=tag)
    audio_dir = Path(s.db_path).parent / "audio"
    upload_dir = Path(s.db_path).parent / "uploads"
    audio_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)

    def notify(kind, payload):
        if kind == "rider_reply":
            return  # handled with audio by _deliver_rider_reply
        hub.publish(kind, payload)

    agent = Agent(db, ledger, approvals, provider, evon=evon, notify=notify)

    @asynccontextmanager
    async def lifespan(_app):
        hub.loop = asyncio.get_running_loop()
        if s.voice_live:
            threading.Thread(target=_prerender, daemon=True).start()
        else:
            _prerender()
        task = asyncio.create_task(_sweeper())
        yield
        task.cancel()

    app = FastAPI(title="SETU AI (simulated prototype)", lifespan=lifespan)
    app.state.agent, app.state.settings, app.state.hub, app.state.cache = agent, s, hub, cache
    app.state.provider = provider
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

    # ---------------------------------------------------------------- helpers
    def _prerender():
        cust = db.one("SELECT * FROM customers WHERE id='CUST_001'")
        phrases = M.all_fixed_rider_phrases(M.fmt_window(cust["window_start"], cust["window_end"]),
                                            cust["area"], cust["landmark"])
        app.state.prerender = {"status": "running", "total": len(phrases)}
        app.state.prerender = {"status": "done", **cache.prerender(phrases)}

    def _store_audio(data: bytes) -> str:
        aid = uuid.uuid4().hex[:12]
        (audio_dir / f"{aid}.wav").write_bytes(data)
        return f"/audio/{aid}"

    def _voice(res: TurnResult) -> dict:
        """Speak an already-approved template. Logs fallbacks and failures to the ledger."""
        if not res.reply_key:
            return {"audio_url": None, "tts_ms": 0.0, "cached": False}
        spoken = cache.speak(res.reply_key, res.language, res.reply_slots)
        if spoken.fallback_from:
            ledger.append(order_id=res.order_id, call_id=res.call_id, event_type="tts_language_fallback",
                          evidence_level="info", source="tts",
                          detail={"wanted": spoken.fallback_from, "used": spoken.lang})
        if not spoken.ok and spoken.error == "no_recording":
            # No key and no recording for this exact line: the page speaks it with the browser's voice.
            return {"audio_url": None, "tts_ms": 0.0, "cached": False, "browser_tts": True,
                    "spoken_text": spoken.text, "spoken_lang": spoken.lang}
        if not spoken.ok:
            ledger.append(order_id=res.order_id, call_id=res.call_id, event_type="tts_failed",
                          evidence_level="rejected_or_unresolved", source="tts",
                          detail={"error": spoken.error or "tts failed", "customer_message": "system_failure",
                                  "slots": {}})
            res.customer_message = agent.customer_view(res.call_id)
            hub.publish("status", {"call_id": res.call_id, "order_id": res.order_id,
                                   "customer_message": res.customer_message})
            return {"audio_url": None, "tts_ms": spoken.tts_ms, "cached": False, "tts_error": spoken.error,
                    "spoken_text": spoken.text, "spoken_lang": spoken.lang}
        return {"audio_url": _store_audio(spoken.audio), "tts_ms": round(spoken.tts_ms, 1), "cached": spoken.cached,
                "spoken_text": spoken.text, "spoken_lang": spoken.lang, "tts_fallback_from": spoken.fallback_from}

    reply_listeners: dict = {}  # call_id -> callable(TurnResult); used by the phone-call bridge

    def _deliver_rider_reply(res: TurnResult) -> dict:
        listener = reply_listeners.get(res.call_id)
        if listener:
            listener(res)
        out = {**res.to_dict(), **_voice(res)}
        hub.publish("rider_reply", out, call_id=res.call_id)
        hub.publish("status", {"call_id": res.call_id, "order_id": res.order_id,
                               "customer_message": res.customer_message})
        return out

    def _run_turn(call_id: str, transcript, stt_meta: dict, *, stt_ok=True, language=None, short=False,
                  t_start: float | None = None) -> dict:
        try:
            res = agent.handle_transcript(call_id, transcript, stt_language=language, stt_ok=stt_ok, short_clip=short)
        except CallEnded:
            raise HTTPException(409, "This call has ended. Start a new call.")
        voice = _voice(res)
        timings = {"stt": stt_meta.get("stt_ms"), "intent": res.timings_ms.get("intent"),
                   "policy": res.timings_ms.get("policy"), "tts": voice.get("tts_ms")}
        timings["total"] = round((time.perf_counter() - (t_start or time.perf_counter())) * 1000, 1)
        agent.record_latency(call_id, timings)
        out = {**res.to_dict(), **voice, "stt": stt_meta, "timings_ms": timings}
        hub.publish("rider_reply", out, call_id=call_id)
        return out

    async def _sweeper():
        while True:
            await asyncio.sleep(1.0)
            try:
                for res in await run_in_threadpool(agent.expire_due):
                    await run_in_threadpool(_deliver_rider_reply, res)
            except Exception as e:  # never kill the sweeper
                print("sweeper error:", e)

    # ---------------------------------------------------------------- pages
    @app.get("/")
    def index():
        return FileResponse(FRONTEND / "index.html")

    @app.get("/call")
    def call_page():
        return FileResponse(FRONTEND / "call.html")

    @app.get("/console")
    def console_page():
        return FileResponse(FRONTEND / "rider.html")

    @app.get("/rider")
    def rider_page():
        return FileResponse(FRONTEND / "rider.html")

    @app.get("/customer")
    def customer_page():
        return FileResponse(FRONTEND / "customer.html")

    @app.get("/audio/{aid}")
    def audio(aid: str):
        stem = re.sub(r'[^a-f0-9]', '', aid)
        for ext, mime in (("wav", "audio/wav"), ("mp3", "audio/mpeg")):
            p = audio_dir / f"{stem}.{ext}"
            if p.exists():
                return FileResponse(p, media_type=mime)
        raise HTTPException(404)

    @app.get("/health")
    def health():
        port = getattr(app.state, "port", 8000)
        scheme = getattr(app.state, "scheme", "http")
        lan = _lan_ip()
        return {"ok": True, "mock_voice": not s.voice_live, "evon_mode": s.evon_mode, "ffmpeg": ffmpeg_version,
                "provider": {"name": provider.name, "mode": provider.mode, "simulated": True},
                "prerender": getattr(app.state, "prerender", None), "cache": cache.stats,
                "models": {"stt": s.prisma_model if s.voice_live else "mock", "tts": s.timbre_model if s.voice_live else "mock"},
                "voice": "gnani" if s.voice_live else ("recorded" if tag == "recorded" else "browser"),
                "lan_url": f"{scheme}://{lan}:{port}" if lan else None, "approval_ttl_s": s.approval_ttl_s}

    # ---------------------------------------------------------------- data
    @app.get("/orders")
    def orders():
        return db.all("SELECT o.*, c.name AS customer_name FROM orders o JOIN customers c ON c.id=o.customer_id")

    @app.get("/customers/{cid}")
    def customer(cid: str):
        row = db.one("SELECT * FROM customers WHERE id=?", (cid,))
        if not row:
            raise HTTPException(404)
        return row

    @app.put("/customers/{cid}/preferences")
    def put_prefs(cid: str, body: PrefsIn):
        row = db.one("SELECT * FROM customers WHERE id=?", (cid,))
        if not row:
            raise HTTPException(404)
        upd = body.model_dump(exclude_none=True)
        for k in ("window_start", "window_end"):
            if k in upd and not _HHMM.match(upd[k]):
                raise HTTPException(422, f"{k} must be HH:MM")
        ws, we = upd.get("window_start", row["window_start"]), upd.get("window_end", row["window_end"])
        if ws >= we:
            raise HTTPException(422, "window_start must be before window_end")
        if "language" in upd and upd["language"] not in ("kn", "hi", "en"):
            raise HTTPException(422, "language must be kn|hi|en")
        for k, v in upd.items():
            db.execute(f"UPDATE customers SET {k}=? WHERE id=?", (int(v) if isinstance(v, bool) else v, cid))
        for o in db.all("SELECT id FROM orders WHERE customer_id=?", (cid,)):
            ev = ledger.append(order_id=o["id"], call_id=None, event_type="preferences_updated",
                               evidence_level="info", source="customer_settings", detail=upd)
            hub.publish("ledger", ev)
        # pre-rendered phrases embed the window; refresh them in the background
        threading.Thread(target=_prerender, daemon=True).start()
        return db.one("SELECT * FROM customers WHERE id=?", (cid,))

    @app.get("/orders/{oid}/ledger")
    def order_ledger(oid: str):
        events = ledger.events(order_id=oid)
        chain = ledger.verify_chain()
        last_call = next((e["call_id"] for e in reversed(events) if e["call_id"]), None)
        return {"order_id": oid, "events": events,
                "chain": {"ok": chain.ok, "checked": chain.checked, "broken_at": chain.broken_at,
                          "reason": chain.reason},
                "highest_evidence": Ledger.highest_evidence(events),
                "customer_message": agent.customer_view(last_call) if last_call else None,
                "simulated": True}

    @app.get("/latency")
    def latency():
        rows = db.all("SELECT * FROM latency")
        out = {}
        for k in ("stt_ms", "intent_ms", "policy_ms", "tts_ms", "total_ms"):
            vals = sorted(r[k] for r in rows if r[k] is not None)
            if vals:
                out[k] = {"n": len(vals), "median": round(statistics.median(vals), 1),
                          "p95": round(vals[min(len(vals) - 1, int(0.95 * len(vals)))], 1)}
        return out

    # ---------------------------------------------------------------- calls
    @app.post("/calls/start")
    def start_call(body: StartIn):
        info = agent.start_call(body.order_id)
        langs = [body.language] if body.language in ("hi", "kn", "en") else ["hi", "kn", "en"]
        parts = []
        for lang in langs:
            sp = cache.speak("greeting", lang)
            if sp.ok:
                parts.append(sp.audio)
        from backend.voice.audio import concat_wavs
        info["audio_url"] = _store_audio(concat_wavs(parts)) if parts else None
        info["greeting_langs"] = langs
        if len(langs) == 1:
            agent.db.execute("UPDATE calls SET language=? WHERE id=?", (langs[0], info["call_id"]))
        info["simulated"] = True
        hub.publish("status", {"call_id": info["call_id"], "order_id": body.order_id, "started": True,
                               "customer_message": agent.customer_view(info["call_id"])})
        return info

    @app.post("/calls/{call_id}/audio")
    def call_audio(call_id: str, audio: UploadFile = File(...), mock_transcript: str = Form(""),
                   telephony: bool = Form(False)):
        t0 = time.perf_counter()
        try:
            agent._call(call_id)
        except KeyError:
            raise HTTPException(404, "unknown call")
        raw = audio.file.read()
        ext = Path(audio.filename or "clip.webm").suffix or ".webm"
        up = upload_dir / f"{call_id}_{uuid.uuid4().hex[:6]}{re.sub(r'[^.a-z0-9]', '', ext.lower())}"
        up.write_bytes(raw)
        duration = None
        wav = None
        try:
            wav = to_wav(raw, telephony=telephony)
            duration = round(wav_duration_s(wav), 2)
        except AudioError:
            pass  # mock mode tolerates undecodable bytes; live mode fails below
        t_stt = time.perf_counter()
        if not s.voice_live:
            if mock_transcript.strip():
                sidecar_path(up).write_text(mock_transcript, encoding="utf-8")
            r = mock_stt.transcribe_file(up)
        elif wav is None:
            r = None
        elif duration and duration > MAX_CLIP_S:
            r = None
        else:
            r = stt_live.transcribe(wav)
        stt_ms = round((time.perf_counter() - t_stt) * 1000, 1)
        if r is None or not r.ok:
            meta = {"ok": False, "error": (r.error if r else "audio not decodable or > 30 s"), "stt_ms": stt_ms,
                    "duration_s": duration, "engine": "mock" if not s.voice_live else s.prisma_model}
            return _run_turn(call_id, None, meta, stt_ok=False, t_start=t0)
        if not r.transcript.strip():
            # Prisma heard no words (cough, traffic, breath). Not a turn: the agent keeps listening.
            return {"call_id": call_id, "heard_nothing": True, "transcript": "",
                    "stt": {"ok": True, "engine": r.model or s.prisma_model, "stt_ms": stt_ms, "duration_s": duration}}
        short = duration is not None and duration < SHORT_CLIP_S and not r.language
        meta = {"ok": True, "language": r.language, "raw_language_code": r.raw_language_code, "stt_ms": stt_ms,
                "duration_s": duration, "truncated": r.truncated,
                "engine": "mock" if not s.voice_live else (r.model or s.prisma_model)}
        return _run_turn(call_id, r.transcript, meta, language=r.language, short=short, t_start=t0)

    SOUND_CHECK = {"en": "Sound check. If you can hear this, the call audio works.",
                   "hi": "साउंड चेक। अगर आपको यह सुनाई दे रहा है, तो कॉल की आवाज़ ठीक है।",
                   "kn": "ಧ್ವನಿ ಪರೀಕ್ಷೆ. ಇದು ಕೇಳಿಸುತ್ತಿದ್ದರೆ, ಕರೆಯ ಧ್ವನಿ ಸರಿಯಾಗಿದೆ."}

    @app.post("/tts/check")
    def sound_check(body: RiderLineIn):
        """Speaker test on the call screen: one fixed sentence in the chosen language."""
        lang = body.language if body.language in SOUND_CHECK else "en"
        audio, cached, ms, err = cache.render(SOUND_CHECK[lang], lang)
        return {"audio_url": _store_audio(audio) if audio else None, "error": err, "text": SOUND_CHECK[lang],
                "voice": "gnani" if s.voice_live else "recorded"}

    @app.post("/tts/rider")
    def rider_line(body: RiderLineIn):
        """Demo playback: the rider's scripted line in a second Timbre voice. Text is OTP-redacted first."""
        from backend.engine.otp_guard import redact_otp
        lang = body.language if body.language in ("hi", "kn", "en") else "hi"
        text = redact_otp(body.text)[:300]
        if not s.voice_live:
            from backend.voice.recorded import RecordedVoice
            mp3 = RecordedVoice("rider").mp3(text, lang)
            if mp3:
                aid = uuid.uuid4().hex[:12]
                (audio_dir / f"{aid}.mp3").write_bytes(mp3)
                return {"audio_url": f"/audio/{aid}", "voice": "recorded"}
            return {"audio_url": None, "voice": "browser"}
        audio, cached, ms, err = rider_cache.render(text, lang)
        return {"audio_url": _store_audio(audio) if audio else None, "cached": cached, "error": err,
                "voice": s.timbre_rider_voices.get(lang)}

    @app.post("/calls/{call_id}/end")
    def end_call(call_id: str):
        """Rider hung up. Any approval the customer has not answered is closed, never acted on."""
        try:
            agent._call(call_id)
        except KeyError:
            raise HTTPException(404, "unknown call")
        res = agent.end_call(call_id, by="rider_hung_up")
        hub.publish("status", {"call_id": call_id, "order_id": res.order_id, "ended": True,
                               "customer_message": res.customer_message})
        return {**res.to_dict(), "summary": agent.call_summary(call_id)}

    @app.get("/calls/{call_id}")
    def call_info(call_id: str):
        try:
            return agent.call_summary(call_id)
        except KeyError:
            raise HTTPException(404, "unknown call")

    @app.post("/calls/{call_id}/text")
    def call_text(call_id: str, body: TextIn):
        """Typed rider input (no STT). Same pipeline from intent onward. For demos and tests."""
        try:
            agent._call(call_id)
        except KeyError:
            raise HTTPException(404, "unknown call")
        return _run_turn(call_id, body.text, {"ok": True, "engine": "typed", "stt_ms": 0.0},
                         language=body.language, t_start=time.perf_counter())

    # ---------------------------------------------------------------- approvals
    @app.get("/approvals/pending")
    def pending():
        for res in agent.expire_due():
            _deliver_rider_reply(res)
        return [agent.public_approval(a) for a in approvals.pending()]

    @app.post("/approvals/{apr_id}/decide")
    def decide(apr_id: str, body: DecideIn):
        if body.decision not in ("approve", "reject", "contact_later"):
            raise HTTPException(422, "decision must be approve | reject | contact_later")
        try:
            res = agent.decide_approval(apr_id, body.decision, body.token)
        except KeyError:
            raise HTTPException(404, "unknown approval")
        if res.error and not res.reply_key:
            raise HTTPException(409, res.error)
        return _deliver_rider_reply(res)

    # ---------------------------------------------------------------- mock provider
    @app.post("/mock-provider/mode")
    def provider_mode(body: ModeIn):
        if body.mode not in MODES:
            raise HTTPException(422, f"mode must be one of {MODES}")
        provider.set_mode(body.mode)
        hub.publish("provider_mode", {"mode": body.mode, "simulated": True})
        return {"mode": provider.mode, "simulated": True}

    @app.post("/mock-provider/request")
    def provider_direct(body: dict):
        """Direct provider calls are impossible by design: only the policy path holds a permit."""
        try:
            provider.request(None, str(body.get("action", "")))
        except PermitDenied as e:
            raise HTTPException(403, f"{e}. Provider requests are only made by the agent after a policy permit.")
        raise HTTPException(500, "unreachable")

    # ---------------------------------------------------------------- websockets
    @app.websocket("/ws/customer")
    async def ws_customer(ws: WebSocket):
        await ws.accept()
        hub.customers.add(ws)
        try:
            await ws.send_text(json.dumps({"type": "hello", "data": {
                "pending": [agent.public_approval(a) for a in approvals.pending()],
                "provider_mode": provider.mode, "simulated": True}}, default=str))
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            hub.customers.discard(ws)

    @app.websocket("/ws/rider/{call_id}")
    async def ws_rider(ws: WebSocket, call_id: str):
        await ws.accept()
        hub.riders.setdefault(call_id, set()).add(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            hub.riders.get(call_id, set()).discard(ws)

    # ---------------------------------------------------------------- SETU live interpreter
    _recorded_voices: dict = {}

    def _speak_line(text: str, lang: str, role: str) -> dict:
        """Any sentence, spoken: Gnani Timbre when live, else a built-in recording if one exists, else the
        browser's own voice. role 'rider' = the rider's (male) voice, 'ai' = SETU / customer side."""
        if not text:
            return {"audio_url": None, "voice": None}
        lang = lang if lang in ("hi", "kn", "en") else "en"
        if s.voice_live:
            audio, cached, ms, err = (rider_cache if role == "rider" else cache).render(text, lang)
            return {"audio_url": _store_audio(audio) if audio else None,
                    "voice": (s.timbre_rider_voices if role == "rider" else s.timbre_voices).get(lang),
                    "browser_tts": not audio}
        from backend.voice.recorded import RecordedVoice
        rv = _recorded_voices.setdefault(role, RecordedVoice("rider" if role == "rider" else "ai"))
        mp3 = rv.mp3(text, lang)
        if mp3:
            aid = uuid.uuid4().hex[:12]
            (audio_dir / f"{aid}.mp3").write_bytes(mp3)
            return {"audio_url": f"/audio/{aid}", "voice": "recorded", "browser_tts": False}
        return {"audio_url": None, "voice": "browser", "browser_tts": True}

    def _stt_bytes(raw: bytes, filename: str, mock_transcript: str = "") -> dict:
        ext = Path(filename or "clip.webm").suffix or ".webm"
        up = upload_dir / f"interp_{uuid.uuid4().hex[:8]}{re.sub(r'[^.a-z0-9]', '', ext.lower())}"
        up.write_bytes(raw)
        wav, duration = None, None
        try:
            wav = to_wav(raw)
            duration = round(wav_duration_s(wav), 2)
        except AudioError:
            pass
        if not s.voice_live:
            if mock_transcript.strip():
                sidecar_path(up).write_text(mock_transcript, encoding="utf-8")
            r = mock_stt.transcribe_file(up)
        elif wav is None or (duration and duration > MAX_CLIP_S):
            r = None
        else:
            r = stt_live.transcribe(wav)
        if r is None or not r.ok:
            return {"ok": False, "error": (r.error if r else "audio not decodable or > 30 s"), "duration_s": duration}
        return {"ok": True, "transcript": r.transcript, "language": r.language, "duration_s": duration,
                "engine": "mock" if not s.voice_live else (r.model or s.prisma_model)}

    from backend.interpreter.routes import mount_interpreter
    mount_interpreter(app, db=db, hub=hub, settings=s, speak=_speak_line, stt=_stt_bytes)

    from backend.telephony.inya_bridge import mount_inya_bridge
    mount_inya_bridge(app, agent, s, hub, reply_listeners)
    return app


app = create_app()
