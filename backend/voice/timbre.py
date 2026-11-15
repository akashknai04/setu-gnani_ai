"""Gnani Timbre TTS adapter — REST inference endpoint (beta model).

From Gnani's quick start / TTS REST page: POST {base}/api/v1/tts/inference, JSON,
header X-API-Key-ID, body {text, voice, model, language, audio_config{sample_rate,
num_channels, encoding, container}} -> binary audio. Voices for timbre-v2.5 include
Nalini (hi), Kaveri (en), Saanvi / Kavin (kn).
TODO(REVIEW.md): full error table not seen; we treat any non-2xx or non-audio body as failure.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import httpx

from backend.config import Settings

LANG_CODE = {"hi": "hi-IN", "kn": "kn-IN", "en": "en-IN"}


@dataclass
class TTSResult:
    ok: bool
    audio: bytes = b""
    latency_ms: float = 0.0
    error: str | None = None


class TimbreTTS:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.s = settings
        self.client = httpx.Client(base_url=settings.gnani_base_url, timeout=settings.timbre_timeout_s,
                                   transport=transport)
        self._lock = threading.Lock()

    def body(self, text: str, lang: str, voice: str | None = None) -> dict:
        return {
            "text": text,
            "voice": voice or self.s.timbre_voices.get(lang, self.s.timbre_voices["en"]),
            "model": self.s.timbre_model,
            "language": LANG_CODE.get(lang, "en-IN"),
            "audio_config": {
                "sample_rate": self.s.timbre_sample_rate,
                "num_channels": 1,
                "encoding": "linear_pcm",
                "container": "wav",
            },
        }

    def synthesize(self, text: str, lang: str, voice: str | None = None) -> TTSResult:
        if not self.s.gnani_api_key:
            return TTSResult(False, error="GNANI_API_KEY missing")
        t0 = time.perf_counter()
        try:
            with self._lock:
                r = self.client.post(self.s.timbre_path, json=self.body(text, lang, voice),
                                     headers={"X-API-Key-ID": self.s.gnani_api_key})
        except httpx.HTTPError as e:
            return TTSResult(False, error=f"network: {type(e).__name__}", latency_ms=(time.perf_counter() - t0) * 1000)
        ms = (time.perf_counter() - t0) * 1000
        ctype = r.headers.get("content-type", "")
        if r.status_code != 200 or "json" in ctype or len(r.content) < 44 or r.content[:4] != b"RIFF":
            return TTSResult(False, error=f"http {r.status_code}: {r.text[:120] if 'json' in ctype else ctype}",
                             latency_ms=ms)
        return TTSResult(True, r.content, ms)
