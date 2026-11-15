"""Pre-recorded voice for running without a Gnani key (MOCK_VOICE=1).

frontend/voice/ holds one MP3 per fixed line the call can say, in hi / kn / en, for the assistant and
(for solo scenario playback) the rider. They were rendered offline with open models: Piper voices
(Hindi priyamvada / pratham, English lessac / ryan) and AI4Bharat Indic-TTS Kannada (female / male).
They are a stand-in so the demo talks without a key. With a key, Gnani Timbre speaks every line live.

A line that has no recording (typed free text, changed rules) returns ok=False with
error="no_recording": the page then uses the browser's own voice. That is not a failure.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.voice.audio import AudioError, to_wav
from backend.voice.timbre import TTSResult

VOICE_DIR = Path(__file__).resolve().parents[2] / "frontend" / "voice"
NO_RECORDING = "no_recording"
_WAV_CACHE: dict[str, bytes] = {}   # converted clips, shared by every app instance in this process


def clip_key(role: str, lang: str, text: str) -> str:
    return hashlib.sha1(f"{role}|{lang}|{text}".encode()).hexdigest()[:12]


class RecordedVoice:
    def __init__(self, role: str = "ai", voice_dir: Path = VOICE_DIR):
        self.role = role
        self.dir = Path(voice_dir)
        man = self.dir / "manifest.json"
        self.manifest = json.loads(man.read_text(encoding="utf-8")) if man.exists() else {}

    def has(self, text: str, lang: str) -> bool:
        return clip_key(self.role, lang, text) in self.manifest

    def mp3(self, text: str, lang: str) -> bytes | None:
        k = clip_key(self.role, lang, text)
        return (self.dir / self.manifest[k]["file"]).read_bytes() if k in self.manifest else None

    def synthesize(self, text: str, lang: str, voice: str | None = None) -> TTSResult:
        k = clip_key(self.role, lang, text)
        if k in _WAV_CACHE:
            return TTSResult(True, _WAV_CACHE[k])
        data = self.mp3(text, lang)
        if data is None:
            return TTSResult(False, error=NO_RECORDING)
        try:
            _WAV_CACHE[k] = to_wav(data, rate=22050)
            return TTSResult(True, _WAV_CACHE[k])
        except AudioError as e:
            return TTSResult(False, error=str(e))
