"""Make phone-style versions of every benchmark clip (clean and noisy).

    python benchmark/make_8khz.py

Telephony simulation: band-limit to 300–3400 Hz, resample to 8 kHz, then a G.711 mu-law
8-bit companding round trip (the quantisation noise real phone calls carry).
Writes benchmark/audio/8khz/<name>_8k.wav and copies sidecar transcripts.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.voice.audio import read_wav, to_wav, write_wav  # noqa: E402

HERE = Path(__file__).resolve().parent
MU = 255.0


def mulaw_roundtrip(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, -1.0, 1.0)
    y = np.sign(x) * np.log1p(MU * np.abs(x)) / np.log1p(MU)
    q = np.round((y + 1) / 2 * 255) / 255 * 2 - 1          # 8-bit
    return np.sign(q) * (np.power(1 + MU, np.abs(q)) - 1) / MU


def telephony(wav_bytes: bytes) -> bytes:
    narrow = to_wav(wav_bytes, telephony=True)   # 300–3400 Hz, 8 kHz
    x, rate = read_wav(narrow)
    return write_wav(mulaw_roundtrip(x), rate)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audio-dir", default=str(HERE / "audio"))
    a = ap.parse_args(argv)
    audio_dir = Path(a.audio_dir)
    out_dir = audio_dir / "8khz"
    out_dir.mkdir(parents=True, exist_ok=True)
    sources = sorted(audio_dir.glob("*.wav")) + sorted((audio_dir / "noisy").glob("*.wav"))
    for src in sources:
        dst = out_dir / f"{src.stem}_8k.wav"
        dst.write_bytes(telephony(src.read_bytes()))
        if src.with_suffix(".txt").exists():
            shutil.copy(src.with_suffix(".txt"), dst.with_suffix(".txt"))
    print(f"wrote {len(sources)} phone-style clips to {out_dir}")
    return 0 if sources else 1


if __name__ == "__main__":
    raise SystemExit(main())
