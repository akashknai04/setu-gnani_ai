"""Disk cache for spoken phrases + the speak() policy (cache -> live -> fallback).

Fixed replies are pre-rendered at startup so most turns play from disk. Timbre is
called live only for text not in the cache (e.g. a rider-proposed time).
If Kannada synthesis fails, the same template is spoken in English (then Hindi)
and the fallback is reported so the caller can log it.
"""
from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from backend.engine import messages as M


@dataclass
class Spoken:
    ok: bool
    audio: bytes
    lang: str
    text: str
    cached: bool
    tts_ms: float
    fallback_from: str | None = None
    error: str | None = None


class PhraseCache:
    def __init__(self, cache_dir: str, tts, tag: str = "default"):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.tts = tts
        self.tag = tag  # include model + voices so a voice change invalidates the cache
        self.stats = {"hits": 0, "misses": 0, "failures": 0}
        self._lock = threading.Lock()

    def _path(self, text: str, lang: str) -> Path:
        h = hashlib.sha1(f"{self.tag}|{lang}|{text}".encode()).hexdigest()[:20]
        return self.dir / f"{lang}_{h}.wav"

    def get(self, text: str, lang: str) -> bytes | None:
        p = self._path(text, lang)
        return p.read_bytes() if p.exists() else None

    def render(self, text: str, lang: str) -> tuple[bytes | None, bool, float, str | None]:
        cached = self.get(text, lang)
        if cached:
            self.stats["hits"] += 1
            return cached, True, 0.0, None
        self.stats["misses"] += 1
        t0 = time.perf_counter()
        r = self.tts.synthesize(text, lang)
        ms = (time.perf_counter() - t0) * 1000
        if not r.ok:
            self.stats["failures"] += 1
            return None, False, ms, r.error
        with self._lock:
            self._path(text, lang).write_bytes(r.audio)
        return r.audio, False, ms, None

    def prerender(self, phrases: list[tuple[str, str, str]]) -> dict:
        ok = fail = 0
        for _key, lang, text in phrases:
            audio, _, _, _ = self.render(text, lang)
            ok, fail = (ok + 1, fail) if audio else (ok, fail + 1)
        return {"rendered": ok, "failed": fail}

    def speak(self, key: str, lang: str, slots: dict | None = None) -> Spoken:
        """Speak a template in `lang`, falling back kn -> en -> hi on TTS failure."""
        slots = slots or {}
        order = [lang] + [x for x in ("en", "hi") if x != lang]
        first_err, total_ms = None, 0.0
        for i, lg in enumerate(order):
            text = M.rider_reply(key, lg, **slots)
            audio, cached, ms, err = self.render(text, lg)
            total_ms += ms
            if audio:
                return Spoken(True, audio, lg, text, cached, total_ms, fallback_from=lang if i else None)
            first_err = first_err or err
            if err == "no_recording":
                break  # recorded-voice mode: let the page speak this line itself, in the right language
        return Spoken(False, b"", lang, M.rider_reply(key, lang, **slots), False, total_ms, error=first_err)
