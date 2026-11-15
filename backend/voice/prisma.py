"""Gnani Prisma STT adapter — REST short-clip endpoint.

Confirmed in docs.gnani.ai (STT REST page): POST {base}/stt/v3, multipart/form-data,
header X-API-Key-ID, fields audio_file, model, language_code, format, keyterms.
prisma-v3.0 supports language_code=indic-auto or a 1–4 code list, format=codemix,
keyterms, and returns detected_language_code. Max clip 30 s.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass

import httpx

from backend.config import Settings

# Words riders actually say on these calls. Kept short: docs warn context can hurt accuracy,
# so the benchmark measures keyterms on vs off.
KEYTERMS = ["OTP", "guard", "security", "watchman", "neighbour", "address", "landmark", "delivery",
            "customer", "order", "गार्ड", "ओटीपी", "डिलीवरी", "पड़ोसी", "ಗಾರ್ಡ್", "ಒಟಿಪಿ", "ಡೆಲಿವರಿ",
            "ಸೆಕ್ಯುರಿಟಿ", "ಪಕ್ಕದ ಮನೆ"]

LANG_FROM_CODE = {"hi-IN": "hi", "kn-IN": "kn", "en-IN": "en"}


@dataclass
class STTResult:
    ok: bool
    transcript: str = ""
    language: str | None = None       # hi | kn | en | None (unknown / other)
    raw_language_code: str | None = None
    latency_ms: float = 0.0
    error: str | None = None
    truncated: bool = False
    model: str | None = None


class PrismaSTT:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.s = settings
        self.client = httpx.Client(base_url=settings.gnani_base_url, timeout=settings.prisma_timeout_s,
                                   transport=transport)
        self._lock = threading.Lock()  # some accounts allow 1 active request at a time

    def _form(self, keyterms: bool) -> dict:
        data = {"model": self.s.prisma_model, "language_code": self.s.prisma_language_code}
        if self.s.prisma_format:
            data["format"] = self.s.prisma_format
        if keyterms and self.s.prisma_model == "prisma-v3.0":
            data["keyterms"] = json.dumps(KEYTERMS, ensure_ascii=False)
        return data

    def transcribe(self, wav: bytes, *, keyterms: bool | None = None) -> STTResult:
        use_kt = self.s.prisma_use_keyterms if keyterms is None else keyterms
        if not self.s.gnani_api_key:
            return STTResult(False, error="GNANI_API_KEY missing")
        t0 = time.perf_counter()
        for attempt in range(2):
            try:
                with self._lock:
                    r = self.client.post(
                        self.s.prisma_path,
                        headers={"X-API-Key-ID": self.s.gnani_api_key},
                        files={"audio_file": ("clip.wav", wav, "audio/wav")},
                        data=self._form(use_kt),
                    )
            except httpx.HTTPError as e:
                return STTResult(False, error=f"network: {type(e).__name__}",
                                 latency_ms=(time.perf_counter() - t0) * 1000)
            if r.status_code == 429 and attempt == 0:
                time.sleep(0.8)
                continue
            break
        ms = (time.perf_counter() - t0) * 1000
        return self.parse(r.status_code, r.text, ms)

    @staticmethod
    def parse(status: int, body: str, latency_ms: float = 0.0) -> STTResult:
        try:
            j = json.loads(body)
        except ValueError:
            return STTResult(False, error=f"http {status}: non-JSON body", latency_ms=latency_ms)
        if status != 200 or not j.get("success"):
            err = None
            if isinstance(j.get("error"), dict):          # {"success":false,"error":{"type":..}}
                err = j["error"].get("type")
            elif isinstance(j.get("detail"), dict):       # auth / rate limit shape
                err = j["detail"].get("error_code")
            elif isinstance(j.get("detail"), list):       # 422 validation
                err = "VALIDATION_ERROR"
            err = err or j.get("code")                    # 504 UPSTREAM_TIMEOUT
            return STTResult(False, error=f"http {status}: {err or 'error'}", latency_ms=latency_ms)
        code = j.get("detected_language_code")
        return STTResult(
            ok=True,
            transcript=j.get("transcript") or "",
            language=LANG_FROM_CODE.get(code),
            raw_language_code=code,
            latency_ms=latency_ms,
            truncated=bool(j.get("truncated")),
            model=j.get("model"),
        )
