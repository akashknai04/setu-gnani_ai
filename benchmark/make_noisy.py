"""Mix a user-supplied noise recording into every clean benchmark clip at SNR 20, 10 and 5 dB.

    python benchmark/make_noisy.py --noise path/to/street_noise.wav

Reads benchmark/audio/<id>.wav (human recordings), writes benchmark/audio/noisy/<id>_snr{N}.wav.
The noise is looped/trimmed to the clip length and scaled so that
10*log10(P_speech / P_noise) == SNR. Sidecar .txt transcripts are copied for mock runs.
Never feed this script Timbre output: benchmark speech must be recorded by humans.
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
SNRS = (20, 10, 5)


def mix_at_snr(speech: np.ndarray, noise: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    if len(noise) < len(speech):
        noise = np.tile(noise, int(np.ceil(len(speech) / len(noise))))
    start = int(rng.integers(0, len(noise) - len(speech) + 1))
    n = noise[start:start + len(speech)]
    ps = float(np.mean(speech ** 2)) or 1e-12
    pn = float(np.mean(n ** 2)) or 1e-12
    scaled = n * np.sqrt(ps / (pn * 10 ** (snr_db / 10)))
    out = speech + scaled
    peak = float(np.max(np.abs(out))) or 1.0
    return out / peak * 0.95 if peak > 0.99 else out


def measured_snr(speech: np.ndarray, mixed: np.ndarray) -> float:
    noise = mixed - speech
    return 10 * np.log10(np.mean(speech ** 2) / max(np.mean(noise ** 2), 1e-12))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--noise", required=True, help="noise recording (any format ffmpeg reads)")
    ap.add_argument("--audio-dir", default=str(HERE / "audio"))
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)
    audio_dir = Path(a.audio_dir)
    out_dir = audio_dir / "noisy"
    out_dir.mkdir(parents=True, exist_ok=True)
    noise, rate = read_wav(to_wav(Path(a.noise).read_bytes(), rate=16000))
    rng = np.random.default_rng(a.seed)
    clips = sorted(audio_dir.glob("*.wav"))
    if not clips:
        print(f"no clean clips in {audio_dir} — record them first (see benchmark/README.md)")
        return 1
    for clip in clips:
        speech, r = read_wav(to_wav(clip.read_bytes(), rate=16000))
        for snr in SNRS:
            dst = out_dir / f"{clip.stem}_snr{snr}.wav"
            mixed = mix_at_snr(speech, noise, snr, rng)
            dst.write_bytes(write_wav(mixed, 16000))
            side = clip.with_suffix(".txt")
            if side.exists():
                shutil.copy(side, dst.with_suffix(".txt"))
    print(f"wrote {len(clips) * len(SNRS)} noisy clips to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
