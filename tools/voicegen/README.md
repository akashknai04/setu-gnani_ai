# Built-in voice recordings

`frontend/voice/` holds one MP3 for every fixed line the call can say, in Hindi, Kannada and English:
the assistant (woman's voice) and, for solo scenario playback, the rider (man's voice). They let the
demo talk on any device without a Gnani key and without depending on the device having Hindi or
Kannada voices. With `GNANI_API_KEY` set, Gnani Timbre speaks every line live instead.

| language | assistant | rider | engine |
|---|---|---|---|
| Hindi | Piper `hi_IN-priyamvada-medium` | Piper `hi_IN-pratham-medium` | sherpa-onnx 1.12 |
| English | Piper `en_US-lessac-medium` | Piper `en_US-ryan-medium` | sherpa-onnx 1.12 |
| Kannada | AI4Bharat Indic-TTS `kn` female | AI4Bharat Indic-TTS `kn` male | Coqui TTS (FastPitch + HiFi-GAN) |

`speakable.py` turns caption text into what the voice should say (times like "6 PM – 8 PM", digits,
"OTP", "AI" and the mock address spelled out per language; the Kannada model reads Kannada script only).

Regenerate after changing a template or scenario line:

```bash
node lines.js <web dir with engine.js + engine_data.json> lines.json   # every line the call can say
python gen_piper.py . <models dir>       # Hindi + English
python gen_kn.py .                        # Kannada (needs coqui-tts, torch, torchcodec, six)
python verify.py . <models dir> manifest_hi_en.json   # Whisper round trip, character error rate
```

Live-translation sentences: `python -c "import json; from backend.interpreter.phrases import all_fixed_sentences as f; json.dump(f(), open('lines.json','w'), ensure_ascii=False)"` from the repo root, then the same two generators.

Then copy the clips and merged manifest into `frontend/voice/`. `backend/tests/test_recorded_voice.py`
fails if any fixed reply or scenario line has no recording. These recordings are never benchmark audio
(the benchmark must be human recordings).
