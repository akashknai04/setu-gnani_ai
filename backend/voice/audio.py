"""Audio helpers built on ffmpeg (browser webm/opus -> WAV mono 16 kHz)."""
from __future__ import annotations

import io
import subprocess
import wave

import numpy as np

from backend.config import check_ffmpeg


class AudioError(RuntimeError):
    pass


def to_wav(data: bytes, rate: int = 16000, telephony: bool = False, timeout: float = 20) -> bytes:
    """Decode any ffmpeg-readable bytes to 16-bit mono WAV at `rate`.

    telephony=True band-limits to 300–3400 Hz and resamples to 8 kHz (phone-style test).
    """
    check_ffmpeg()
    if not data:
        raise AudioError("empty audio")
    af = ["-af", "highpass=f=300,lowpass=f=3400"] if telephony else []
    out_rate = 8000 if telephony else rate
    # Raw PCM out, header written by us: a WAV streamed to a pipe has no valid length field.
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", *af,
           "-ac", "1", "-ar", str(out_rate), "-f", "s16le", "pipe:1"]
    p = subprocess.run(cmd, input=data, capture_output=True, timeout=timeout)
    if p.returncode != 0 or not p.stdout:
        raise AudioError(f"ffmpeg failed: {p.stderr.decode(errors='ignore')[:200]}")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(out_rate)
        w.writeframes(p.stdout)
    return buf.getvalue()


def wav_duration_s(wav_bytes: bytes) -> float:
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return w.getnframes() / float(w.getframerate())


def read_wav(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(wav_bytes)) as w:
        rate, n, ch, width = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    if width != 2:
        raise AudioError("expected 16-bit PCM")
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, rate


def write_wav(x: np.ndarray, rate: int) -> bytes:
    pcm = (np.clip(x, -1.0, 1.0) * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def silent_wav(ms: int = 300, rate: int = 16000) -> bytes:
    return write_wav(np.zeros(int(rate * ms / 1000), dtype=np.float32), rate)


def concat_wavs(parts: list[bytes], gap_ms: int = 250) -> bytes:
    """Join WAVs (resampled to the first one's rate via ffmpeg if rates differ)."""
    if not parts:
        return silent_wav()
    arrays, rate = [], None
    for p in parts:
        x, r = read_wav(p)
        if rate is None:
            rate = r
        elif r != rate:
            x, r = read_wav(to_wav(p, rate=rate))
        arrays.append(x)
        arrays.append(np.zeros(int(rate * gap_ms / 1000), dtype=np.float32))
    return write_wav(np.concatenate(arrays[:-1]), rate)
