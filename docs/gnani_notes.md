# Gnani API notes (read on 2026-11-03)

Sources read: docs.gnani.ai STT REST page (full), docs.gnani.ai quick start + TTS REST search
excerpts, the official LiveKit/Pipecat Gnani plugin docs, and the challenge page
(gnani.ai/internship). Anything below marked **CONFIRMED** was seen in Gnani's own docs;
**PARTIAL** means seen in Gnani docs excerpts or official plugin docs but not the full
reference page; **TODO** means not confirmed and kept configurable in `.env`.

## Auth (CONFIRMED)
- Header `X-API-Key-ID: <key>` on every request. Keys from https://app.gnani.ai/voice.
- Errors for auth/rate limit use `{"detail": {"error_code": ..., "message": ..., "status_code": ...}}`.
  401 MISSING_API_KEY / INVALID_API_KEY, 402 credit, 403 SCOPE_NOT_ALLOWED, 429 RATE_LIMITED
  (no Retry-After; some accounts allow only 1 active request at a time -> we serialise calls).

## Prisma STT — REST short clip (CONFIRMED)
- `POST https://api.vachana.ai/stt/v3`, `multipart/form-data`.
- `audio_file` (required): WAV/MP3/OGG/FLAC/AAC/M4A, **max 30 s**.
- `model`: send `prisma-v3.0`; omit for Prisma v2.5.
- `language_code` (required): v2.5 one code; **v3.0 accepts `indic-auto` or a comma list of 1–4 codes**
  e.g. `hi-IN,kn-IN,en-IN` (hints, not a lock). Codes are `xx-IN` exactly (lowercase `hi-in` -> 400).
- `format`: `verbatim` | `transcribe` (ITN) | **`codemix` (v3.0 only)** | `transliterate` (v3.0 only).
- **`keyterms` (v3.0)**: JSON array or comma list, up to 200 words/short phrases. `topic` (≤1600 chars),
  `previous_text`, `speaker_names` also supported. Docs warn: *context can lower accuracy — test with and without it.*
  -> this is exactly what the benchmark keyterms on/off comparison measures.
- 200 response: `success, request_id, transcript, model, detected_language_code (v3.0), truncated?,
  processing_time, end_to_end_latency`. Empty transcript is not an error. `truncated:true` = cut short.
- Errors: envelope `{"success":false,"error":{"type":...,"message":...}}`; 422 `{"detail":[...]}` for missing
  fields; 504 `{"error":"Gateway Timeout","code":"UPSTREAM_TIMEOUT"}` on v3.0.
- Very short utterances (< ~1 s) are least reliable -> we ask the rider to repeat on short/uncertain clips.

## Timbre TTS — REST (PARTIAL, enough to build)
- `POST https://api.vachana.ai/api/v1/tts/inference`, JSON, header `X-API-Key-ID`.
- Body seen in quick start: `{"text", "voice": "Nalini", "model": "timbre-v2.5", "language": "hi-IN",
  "speed": 1.0, "audio_config": {"sample_rate": 48000, "num_channels": 1, "sample_width": 2,
  "encoding": "linear_pcm", "container": "wav"}}`. Response = binary audio.
- Voices `timbre-v2.5` (Pipecat docs): Hindi Nalini, Bhavna, Deepak…; English Kaveri, Pranav…;
  **Kannada Saanvi, Kavin**; Hinglish Poorvi. `language` param is for timbre-v2.5.
- Sample rates listed: 8000, 16000, 22050, 24000, 44100, 48000. Output is 16-bit PCM WAV.
- **TODO (REVIEW.md):** full error table and whether `speed` / `sample_width` are still accepted
  (Pipecat says `sample_width` is deprecated). Adapter only sends confirmed-core fields; extras off.
- SSE (`/api/v1/tts/sse`) and WebSocket (`wss://api.vachana.ai/api/v1/tts`) exist; not used (we
  pre-render and cache fixed phrases, so REST is enough).

## Evon (CONFIRMED from challenge FAQ)
- "Evon v3.3 isn't on the API platform yet. It's open weights" — request on Hugging Face
  `gnani/gnani-evon-v3.3-30B-A3B` (30B MoE, ~3B active, Apache 2.0).
- Therefore: **no `api` mode is possible today.** `EVON_MODE=local` targets any OpenAI-compatible
  `/v1/chat/completions` server you run (vLLM / llama.cpp). Default `off`.

## Challenge facts that shape the build
- Deadline 11:59 PM IST, Nov 10, 2026. Must name Gnani models used; public demo post on LinkedIn/X
  with #GnaniAI #GreatIndianAIInternshipChallenge, nominated in the submission.
- Synthetic data only — no real phone numbers / recorded calls. (Matches our hard rules.)
- Award fit: Main Character (Kannada), Mixed Vibes (code-mixed), Real Deal, Noise Canceller (benchmark).

## Open questions (ask on Gnani Discord)
1. TTS REST full error table + rate limits per account tier.
2. Does `codemix` + a 3-language hint list beat `indic-auto` for short Kannada/Hindi clips?
3. Is `detected_language_code` reliable on clips < 3 s? (we measure it in the benchmark)
4. Any planned hosted Evon endpoint before Nov 10?
