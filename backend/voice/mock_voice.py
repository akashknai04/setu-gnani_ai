"""MOCK_VOICE=1: fake STT + fake TTS. No keys, no network.

Fake STT reads the transcript from a sidecar .txt next to the audio file
(recording.webm -> recording.txt). Optional directives on their own lines:
    #lang=kn        force the detected language
    #stt_fail       simulate an STT failure
Fake TTS returns a short silent WAV.
"""
from __future__ import annotations

from pathlib import Path

from backend.intent.fast_path import guess_language
from backend.voice.audio import silent_wav
from backend.voice.prisma import STTResult
from backend.voice.timbre import TTSResult


def sidecar_path(audio_path: str | Path) -> Path:
    return Path(audio_path).with_suffix(".txt")


class MockSTT:
    def transcribe_file(self, audio_path: str | Path) -> STTResult:
        side = sidecar_path(audio_path)
        if not side.exists():
            return STTResult(False, error=f"mock: no sidecar {side.name}")
        lines = side.read_text(encoding="utf-8").splitlines()
        if any(line.strip() == "#stt_fail" for line in lines):
            return STTResult(False, error="mock: simulated STT failure")
        lang = next((line.split("=", 1)[1].strip() for line in lines if line.startswith("#lang=")), None)
        text = " ".join(line for line in lines if not line.startswith("#")).strip()
        return STTResult(True, transcript=text, language=lang or guess_language(text),
                         raw_language_code=None, latency_ms=0.0, model="mock")


class MockTTS:
    def __init__(self, fail_langs: set[str] | None = None):
        self.fail_langs = fail_langs or set()

    def synthesize(self, text: str, lang: str, voice: str | None = None) -> TTSResult:
        if lang in self.fail_langs:
            return TTSResult(False, error=f"mock: tts failure for {lang}")
        return TTSResult(True, silent_wav(300), 0.0)
