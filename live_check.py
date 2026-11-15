"""Live Gnani smoke check. Run on your machine after putting GNANI_API_KEY in .env:

    python live_check.py                 # Timbre hi + kn, then Prisma on the Hindi audio
    python live_check.py --clip me.wav   # also transcribe your own recording (recommended)

Prints a JSON report (no key is printed). If a step fails, paste the report back.
Note: transcribing Timbre's own audio is only a connectivity check, never a benchmark.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.config import Settings, check_ffmpeg
from backend.voice.audio import to_wav, wav_duration_s
from backend.voice.prisma import PrismaSTT
from backend.voice.timbre import TimbreTTS

LINES = {
    "hi": "नमस्ते, मैं ग्राहक की ओर से जवाब देने वाला एक AI सहायक हूँ। कृपया थोड़ा रुकिए।",
    "kn": "ನಮಸ್ಕಾರ, ನಾನು ಗ್ರಾಹಕರ ಪರವಾಗಿ ಉತ್ತರಿಸುತ್ತಿರುವ AI ಸಹಾಯಕ. ದಯವಿಟ್ಟು ಸ್ವಲ್ಪ ಕಾಯಿರಿ.",
    "en": "Hello, this is an AI assistant answering for the customer. Please wait briefly.",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", help="your own recorded clip (any format ffmpeg reads, under 30 s)")
    a = ap.parse_args()
    s = Settings()
    report = {"ffmpeg": check_ffmpeg(), "key_present": bool(s.gnani_api_key),
              "base_url": s.gnani_base_url, "stt_model": s.prisma_model, "tts_model": s.timbre_model,
              "voices": s.timbre_voices, "tts": {}, "stt": {}}
    if not s.gnani_api_key:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("GNANI_API_KEY missing in .env")
        return 2
    out = Path("data/live_check")
    out.mkdir(parents=True, exist_ok=True)
    tts, stt = TimbreTTS(s), PrismaSTT(s)
    for lang, text in LINES.items():
        r = tts.synthesize(text, lang)
        entry = {"ok": r.ok, "ms": round(r.latency_ms), "error": r.error}
        if r.ok:
            p = out / f"timbre_{lang}.wav"
            p.write_bytes(r.audio)
            entry.update(file=str(p), seconds=round(wav_duration_s(r.audio), 2))
        report["tts"][lang] = entry
    if report["tts"]["hi"]["ok"]:
        wav = to_wav(Path(report["tts"]["hi"]["file"]).read_bytes())
        for kt in (True, False):
            r = stt.transcribe(wav, keyterms=kt)
            report["stt"][f"timbre_hi_keyterms_{'on' if kt else 'off'}"] = {
                "ok": r.ok, "transcript": r.transcript, "language": r.language,
                "detected_language_code": r.raw_language_code, "ms": round(r.latency_ms), "error": r.error}
    if a.clip:
        wav = to_wav(Path(a.clip).read_bytes())
        r = stt.transcribe(wav)
        report["stt"]["your_clip"] = {"ok": r.ok, "transcript": r.transcript, "language": r.language,
                                      "detected_language_code": r.raw_language_code,
                                      "seconds": round(wav_duration_s(wav), 2), "ms": round(r.latency_ms),
                                      "error": r.error}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    ok = all(v["ok"] for v in report["tts"].values()) and all(v["ok"] for v in report["stt"].values())
    print("\nALL LIVE CHECKS PASSED" if ok else "\nSOME CHECKS FAILED — paste this report back")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
