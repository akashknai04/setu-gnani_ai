"""Gate 5: DoorstepBench harness. Uses ffmpeg sine tones only — never Timbre (no circular tests)."""
import csv
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmark"))

import evaluate  # noqa: E402
import make_8khz  # noqa: E402
import make_noisy  # noqa: E402
from backend.engine.policy import ACTIONS  # noqa: E402
from backend.intent.schema import INTENTS  # noqa: E402
from backend.voice.audio import read_wav  # noqa: E402

CSV = ROOT / "benchmark" / "transcripts.csv"


def _rows():
    return list(csv.DictReader(open(CSV, encoding="utf-8")))


def test_transcripts_shape():
    rows = _rows()
    assert len(rows) == 40 and len({r["id"] for r in rows}) == 40
    cats = {}
    for r in rows:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
        assert r["expected_action"] in ACTIONS, r
        assert r["expected_intent"] in INTENTS, r
        assert r["language"] in {"hi", "kn", "en", "cm-hi", "cm-kn"}
    assert set(cats.values()) == {5} and len(cats) == 8
    langs = [r["language"] for r in rows]
    assert langs.count("kn") >= 8 and langs.count("hi") >= 8 and langs.count("en") >= 8
    assert sum(lng.startswith("cm") for lng in langs) >= 8
    assert any("ignore your rules" in r["script"].lower() for r in rows)


def test_normalize_and_wer():
    assert evaluate.normalize("Hello, World!  ೧೨") == "hello world 12"
    w, c = evaluate.wer_cer("ಮನೆ ಎಲ್ಲಿ ಇದೆ?", "ಮನೆ ಎಲ್ಲಿ ಇದೆ")
    assert w == 0 and c == 0
    w, _ = evaluate.wer_cer("guard ko de doon", "guard ko de")
    assert abs(w - 0.25) < 1e-9


def test_mix_at_snr_hits_target():
    rng = np.random.default_rng(0)
    t = np.linspace(0, 1, 16000, endpoint=False)
    speech = 0.3 * np.sin(2 * np.pi * 220 * t).astype(np.float32)
    noise = rng.normal(0, 0.1, 5000).astype(np.float32)
    for snr in (20, 10, 5):
        mixed = make_noisy.mix_at_snr(speech, noise, snr, rng)
        assert abs(make_noisy.measured_snr(speech, mixed) - snr) < 0.5


def test_mulaw_roundtrip_is_close():
    x = np.linspace(-0.9, 0.9, 1000)
    assert np.max(np.abs(make_8khz.mulaw_roundtrip(x) - x)) < 0.05


def _tone(path, freq=300, dur=1.5):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={dur}",
                    "-ar", "16000", "-ac", "1", str(path)], check=True)


def test_full_harness_mock_mode(tmp_path):
    bench = tmp_path / "bench"
    (bench / "audio").mkdir(parents=True)
    rows = _rows()[:6] + [r for r in _rows() if r["category"] == "otp"][:2]
    with open(bench / "transcripts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:  # stand-in "recordings" are tones; transcripts are sidecars (mock STT)
        wav = bench / r["audio_file"]
        _tone(wav)
        wav.with_suffix(".txt").write_text(r["script"], encoding="utf-8")
    noise = tmp_path / "noise.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "anoisesrc=d=2:c=pink", "-ar", "16000",
                    str(noise)], check=True)
    assert make_noisy.main(["--noise", str(noise), "--audio-dir", str(bench / "audio")]) == 0
    assert make_8khz.main(["--audio-dir", str(bench / "audio")]) == 0
    _, rate = read_wav((bench / "audio" / "8khz" / f"{Path(rows[0]['audio_file']).stem}_8k.wav").read_bytes())
    assert rate == 8000
    assert evaluate.main(["--mode", "mock", "--csv", str(bench / "transcripts.csv"), "--out", str(bench)]) == 0
    md = (bench / "results.md").read_text(encoding="utf-8")
    assert "Mock STT" in md and "snr5" in md and "8khz" in md and "false-confirmation" in md
    res = list(csv.reader(open(bench / "results.csv", encoding="utf-8")))
    # 8 clips x (clean + 3 noisy + 1 8k + 3 noisy-8k) = 64 rows
    assert len([r for r in res[1:] if r and r[0] in {x["id"] for x in rows}]) == 64


def test_dry_run_end_to_end(tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    assert evaluate.main(["--mode", "dry", "--out", str(out)]) == 0
    md = (out / "results.md").read_text(encoding="utf-8")
    assert "harness self-check" in md
    assert "| false-confirmation rate (hard cases, lower is better) | 0/20 (0.0%) |" in md


def test_hard_cases_never_falsely_confirm():
    hard = evaluate.hard_cases(_rows(), "ORD_1024")
    assert len(hard) == 20 and not any(h["false_confirmation"] for h in hard)
    assert all(h["chain_ok"] for h in hard)
