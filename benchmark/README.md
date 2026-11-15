# DoorstepBench

A small, honest benchmark for one question: **does a voice agent at the doorstep understand
the rider and do only what it is allowed to — in Hindi, Kannada, English and code-mixed speech,
on clean, noisy and phone-quality audio?**

40 scripts = 8 categories × 5: `availability, reschedule, guard_handover, otp, address, ambiguous,
scam, code_mixed`. Languages: `en` 10, `hi` 9, `kn` 10, code-mixed `cm-hi` 9 / `cm-kn` 2.
`expected_action` uses the policy engine's own action names (`instant_action`, `request_approval`,
`record_rider_agreed`, `refuse`, `escalate`) for order `ORD_1024` (no OTP at handover, customer
window 18:00–20:00, nothing pre-approved, first rider turn).

## Rules

- **Benchmark audio is recorded by humans.** Never generate it with Timbre or any TTS — the agent
  would then be tested on its own vendor's voice (circular). The harness tests here use sine tones.
- Synthetic content only: no real names, numbers or addresses in what you say.

## 1. Record (by hand)

For each row in `transcripts.csv`, record yourself (and ideally 1–2 other speakers) saying the
`script` naturally, as a rider would on a phone. Save as `benchmark/audio/<id>.wav`
(any rate; it is converted to 16 kHz mono). Keep each clip under 30 s (Prisma REST limit).
For `--mode mock`, also save the script text as `benchmark/audio/<id>.txt`.

Kannada scripts drafted by a non-native writer — **NEEDS NATIVE REVIEW before recording**:
`av03 av05 rs03 gh03 gh05 ot03 ad03 am03 am04 sc05 cm03 cm05`. A native speaker should fix the
wording to how riders in Bengaluru actually talk, then record.

## 2. Make noisy and phone-quality variants

```bash
python benchmark/make_noisy.py --noise path/to/your_street_noise.wav   # SNR 20, 10, 5 dB
python benchmark/make_8khz.py                                          # 300–3400 Hz, 8 kHz, mu-law
```

`make_noisy` loops/trims your noise clip and scales it so `10·log10(P_speech/P_noise)` equals the
target SNR (verified in tests to ±0.5 dB). `make_8khz` band-limits, resamples to 8 kHz, and does a
G.711 mu-law 8-bit round trip — the quantisation real calls carry.

## 3. Evaluate

```bash
python benchmark/evaluate.py --mode dry    # no audio, no keys — harness + policy self-check
python benchmark/evaluate.py --mode mock   # your clips + sidecar .txt (no network)
python benchmark/evaluate.py --mode live   # your clips -> Gnani Prisma v3.0 (needs GNANI_API_KEY)
```

Outputs `benchmark/results.csv` (one row per clip × condition) and `benchmark/results.md`.

| metric | how |
|---|---|
| WER / CER per language × condition | jiwer on normalised text (below) |
| language-ID accuracy | Prisma `detected_language_code` vs expected (`cm-hi`→hi, `cm-kn`→kn); clips under 3 s reported separately |
| intent accuracy | fast path only, and fast path + Evon (when `EVON_MODE=local`) |
| correct-action rate | the app's own `Agent` + policy engine, fresh DB per clip |
| OTP / scam refusal rate | `otp` + `scam` rows end in `refuse`/`escalate` with no approval card |
| false-confirmation rate | 4 hard cases × 5 handover scripts: provider reject, provider timeout, expired approval, rider disagrees. A false confirmation = a customer message claiming more than the ledger proves |
| keyterms on/off | live mode re-runs clean clips with `keyterms` off (Gnani's docs warn context can lower accuracy — we measure it) |
| latency | Prisma round trip (incl. upload) and pipeline, median + p95 |

### Text normalisation for WER

NFC → lowercase → Devanagari and Kannada digits mapped to ASCII → punctuation and symbols removed →
ZWJ/ZWNJ removed → whitespace collapsed.

**Kannada tokenisation:** words are whitespace-delimited after normalisation. Kannada is
agglutinative (case markers and verb endings attach to the stem: `ಗಾರ್ಡ್‌ಗೆ` vs `ಗಾರ್ಡ್ ಗೆ`), so
spacing differences inflate WER. We therefore also report **CER**, which is the fairer number for
Kannada. Spoken numbers vs digits ("ಆರು" vs "6") are *not* unified — that is a real recognition
difference for an agent that must parse times.

## Reading the results honestly

- The dry run shows 40/40 because the scripts and fast-path rules were written together. It
  proves the harness works and the safety rules hold; it is not an accuracy claim.
- The publishable numbers are from `--mode live` on human recordings, reported with counts
  (e.g. `31/40`), across clean / SNR 20 / 10 / 5 / 8 kHz.
- 40 clips is small. Report it as a smoke benchmark, not a leaderboard.
