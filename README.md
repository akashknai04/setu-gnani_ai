# SETU AI

**A bridge between the delivery rider and the customer: live translation when the customer answers,
an honest AI agent when she can't.**

*Setu* means bridge. Two things go wrong when a rider calls a customer, and SETU AI fixes both:

1. **They don't share a language.** The rider speaks Kannada, the customer speaks English or Hindi.
   When the customer answers, **SETU translates live, both ways**: each sentence is heard, translated
   into the other person's language, and spoken to them, with the original words on screen.
2. **The customer can't answer** (meeting, driving, class). **SETU's AI agent** picks up, understands
   the rider in **Hindi, Kannada, English or code-mixed** speech, follows only the rules the customer
   set in advance, sends her a **silent one-tap card** when a rule is missing, and tells her exactly
   what happened and nothing more.

Either way, the OTP is never spoken or translated, and nothing is confirmed that didn't happen.

> Prototype for Gnani AI's **Great Indian AI Internship Challenge** (deadline Nov 10, 2026).
> Everything outside Gnani's models is **simulated**: delivery provider, orders, customers, addresses.

## Why it is safe by design

| Risk | What SETU AI does |
|---|---|
| Rider (or a scammer) asks for the OTP | Refused every time, in any language or phrasing. Never customer-approvable. OTP-looking digits are redacted before they are logged, stored or shown to a model. |
| An LLM decides something it shouldn't | A **deterministic policy engine** decides every permission. The LLM (Evon) may only *label* an unclear sentence, as schema-checked JSON. |
| Handover of an order that needs verification | Refused; the guard/neighbour option is never even offered to the customer. |
| Customer approval forged or replayed | HMAC-signed, single-use tokens bound to call + order + action + 30 s expiry + nonce. |
| "Your delivery is arriving" when nothing was confirmed | Customer messages are **fixed templates** chosen from the **Never-Lie Ledger**; a template that claims more than the ledger proves is automatically downgraded. |
| Silent tampering with the record | Append-only, SHA-256 hash-chained ledger; the DB itself blocks UPDATE/DELETE; `verify_chain()` catches edits. |
| Provider down / rejects / returns junk | Every failure path ends safely: rider told, customer told, ledger event written, no false success. |

## Gnani models used (one narrow job each)

- **Prisma v3.0 (STT)** — REST short-clip endpoint, `language_code=hi-IN,kn-IN,en-IN`, `format=codemix`,
  `keyterms` (all confirmed in Gnani's docs). Detects the rider's language.
- **Timbre v2.5 (TTS, beta)** — speaks pre-approved reply templates in hi / kn / en (voices Nalini /
  Saanvi / Kaveri). Fixed phrases are pre-rendered and cached; Kannada falls back to English → Hindi if
  synthesis fails, and the fallback is logged.
- **Evon v3.3 (optional)** — classifies only the utterances the rule-based fast path can't. Open
  weights only, so it runs as `EVON_MODE=local` against your own server; default `off`.

## Run it

Requirements: Python 3.11+, ffmpeg.

```bash
pip install -r requirements.txt
cp .env.example .env          # put GNANI_API_KEY here and set MOCK_VOICE=0 for real Gnani voice
python live_check.py          # optional: checks your key against Prisma and Timbre
python run.py                 # http://127.0.0.1:8000
```

Open **http://127.0.0.1:8000** and pick a phone:

| page | who | what it is |
|---|---|---|
| `/call` | the rider | A phone call screen. Tap **Call Asha**: her phone rings; if she answers, SETU translates live; if not, SETU's AI agent picks up and speaks first. Then just talk: it detects when you stop, understands Hindi, Kannada, English or a mix, and answers by voice. |
| `/customer` | Asha | Her phone: incoming calls with live translation, silent approval cards (Approve / Do not allow / Contact me later), what actually happened, the hash-chained activity log, her rules. |
| `/console` | developer | The original console with the full decision pipeline. |

**Two real phones on the same Wi-Fi:** `python run.py --lan --https`, then open the printed
`https://<your-ip>:8000/call` on the rider's phone (accept the certificate warning once; phones only
allow the microphone on https) and `/customer` on Asha's phone.

**Voice**
- With `GNANI_API_KEY` and `MOCK_VOICE=0`: **Prisma** hears the rider (language detected per turn, codemix),
  **Timbre** speaks every reply. Hands-free: the phone listens, sends a clip when you pause, plays the answer.
- Without a key: the assistant still talks, using **built-in recordings** of every line in Hindi, Kannada
  and English (`frontend/voice/`, made offline with open Piper and AI4Bharat voices; see
  `tools/voicegen/README.md`). The browser's speech recognition hears the rider (Chrome works best;
  it sends that audio to Google). Only lines you type freely fall back to the device's own voice.
- **Tap Test sound before calling.** If you hear nothing: turn the volume up, make sure the phone isn't
  sending sound to a Bluetooth device, and on iPhone turn off Low Power Mode. Sound plays even when
  the iPhone's silent switch is on.

**Real phone call (Gnani calls your phone, you are the rider):** Gnani's Inya platform dials your
whitelisted number and carries the voice; every sentence you say is sent to `/inya/turn`, where the
same policy engine decides the reply, and Inya speaks it in your language (Kannada, Hindi, English or a
mix, switching automatically). Asha approves on `/customer` while you're on the call.
`python run.py --public` → `python call_me.py setup --public-url <url>` → `python call_me.py call`.
Full steps: [docs/phone_call.md](docs/phone_call.md).

**Live translation (customer answers):** keep **Ring Asha first** on (the default) and tap **Call Asha**.
Asha's phone (`/customer`) rings: she picks her language (ಕನ್ನಡ / English / हिंदी) and taps **Answer with
SETU translation**. Now each side speaks their own language; SETU translates and speaks it to the other
side. If she taps **Let SETU's agent handle it**, or doesn't answer in 20 s (`INTERPRET_RING_S`), SETU's AI
agent takes the call. Solo demo: the rider screen shows **Asha answers / Asha is busy** while ringing, and
quick lines for both sides once connected.

How the translation works (`TRANSLATE_MODE`, default `both`):
- **Doorstep phrases** (always on, offline): what riders and customers actually say at a delivery (at
  the gate, where is the house, leave it with the guard / neighbour / at the door, wait N minutes, I'm
  coming, come at 7, traffic, not at home, yes / no, thank you) is recognised in Hindi, Kannada, English
  or Hinglish and said in the listener's language from a fixed, reviewed sentence, with built-in
  recordings for every one.
- **Word-for-word model** (optional, on your laptop): anything the phrases don't cover goes to
  AI4Bharat **IndicTrans2**. `pip install -r requirements-translate.txt` (about 1-2 GB on first use).
  Without it, SETU says plainly that it couldn't translate and shows the original words.
- OTP-like numbers are masked before translation; when the rider asks for the OTP, the customer is
  told to share it only in person.

**Solo demo, no second person:** on the call screen tap **What to say**. Every one of the 23 scenarios is
there in the language you picked. **Play** runs a whole call by itself (the rider's lines are spoken in a
second Timbre voice, Asha's taps happen on cue); **Play all** runs all 23. While waiting for Asha you
can also answer as her right on the call screen.

**Tests:** `python -m pytest` → 331 passed, 1 skipped (the live Gnani check, which needs a key).

## Every scenario (all tested in Hindi, Kannada and English)

| group | scenarios |
|---|---|
| Starting the call | rider says hello · at the gate, customer not answering |
| Timing | when is the customer free · time inside the window (logged as the rider's word) · time outside the window, Asha approves |
| Handover | guard, Asha approves · guard, Asha says no · neighbour, Asha says contact me later · Asha doesn't answer in time · neighbour pre-approved · order needs verification, refused |
| Safety | rider asks for the OTP · rider reads out digits (hidden before logging) · caller claims head office · rider tries to override the rules |
| Directions | where is the house · deliver to a different address |
| Problems | can't understand twice · delivery system rejects · delivery system down · order not out for delivery |
| Ending | thank you and bye · rider hangs up before Asha answers (her late tap does nothing) |

The list lives in `frontend/scenarios.json`; `backend/tests/test_scenarios.py` plays every scenario in all
three languages (69 calls) through the API, so the screen and the tests can't drift apart.

## Demo script (voice)

1. `/call` on the rider's phone, `/customer` on Asha's. Pick हिंदी, tap **Call Asha**. It rings; the assistant answers: *"नमस्ते, मैं ग्राहक की ओर से… AI सहायक…"*
2. Say **"कस्टमर फोन नहीं उठा रहा। गार्ड को दे दूँ?"** → *"मैं ग्राहक से पूछ रहा हूँ…"* and Asha's phone buzzes with a silent card.
3. Asha taps **Approve** → the policy is checked again → simulated provider accepts → the rider hears *"ग्राहक ने गार्ड को देने की अनुमति दी है…"*. Asha reads, in Kannada and English, exactly what happened.
4. Say **"कस्टमर से ओटीपी बताओ"** → refused, every time.
5. Say **"ठीक है, धन्यवाद"** → the assistant says goodbye and the call ends with a summary.
6. Call again in ಕನ್ನಡ on ORD_2048: **"ಸೆಕ್ಯುರಿಟಿ ಗಾರ್ಡ್‌ಗೆ ಕೊಡ್ಲಾ?"** → refused, this order needs verification. No card is shown.

### 60-second video plan

1. **0–8 s** Two phones on the table. "I'm in a meeting. The delivery rider is calling."
2. **8–25 s** Rider phone rings, the assistant picks up in Hindi. The rider asks to leave it with the guard; Asha's phone buzzes; she taps Approve; the rider hears the answer.
3. **25–35 s** Show Asha's "what happened" in Kannada and the activity log: requested → approved → provider accepted, chain verified.
4. **35–48 s** Rider asks for the OTP → refused. New call in Kannada on ORD_2048 → refused.
5. **48–55 s** Rider says thank you → goodbye, call summary.
6. **55–60 s** "Prisma and Timbre by Gnani. The AI never decides permissions, and never claims more than it can prove."

## How it works

```
rider audio ──ffmpeg──▶ Prisma STT ──▶ OTP redaction ──▶ fast path (hi/kn/en rules)
                                                          │ unclear only
                                                          ▼
                                                 Evon (strict JSON) — optional
                                                          │ intent label
                                                          ▼
                       ┌────────── deterministic POLICY ENGINE ──────────┐
                       │ customer rules · order · approval · provider caps│
                       └──┬────────────┬──────────────┬─────────────┬─────┘
                  instant_action  request_approval  record_rider_agreed  refuse / escalate
                       │            │ HMAC one-tap card    │
              permit ──▶ simulated  ▼ (re-enters policy)   │
              provider          customer                   │
                       └────────────┴──── Never-Lie Ledger ┴──▶ fixed templates ──▶ Timbre (cached)
```

Details: [docs/architecture.md](docs/architecture.md) · [docs/safety.md](docs/safety.md) ·
[docs/limitations.md](docs/limitations.md) · [docs/gnani_notes.md](docs/gnani_notes.md) ·
[benchmark/README.md](benchmark/README.md) · [REVIEW.md](REVIEW.md)

## DoorstepBench

40 rider scripts × clean / SNR 20 / 10 / 5 dB / 8 kHz phone audio. Measures WER (and CER for
Kannada), language-ID (separately for clips under 3 s), intent accuracy with and without Evon,
correct-action rate, OTP/scam refusal rate, **false-confirmation rate** on hard cases (provider
reject, provider timeout, expired approval, rider disagrees), keyterms on/off, and latency.
The audio must be recorded by people — see [benchmark/README.md](benchmark/README.md).

## Project layout

```
backend/   main.py (FastAPI) · config.py · db.py · seed.py
  engine/  policy.py · state_machine.py · approvals.py · ledger.py · messages.py · orchestrator.py · otp_guard.py
  intent/  fast_path.py · evon_intent.py · schema.py
  interpreter/ phrases.py · model.py (IndicTrans2) · service.py · routes.py (live translated call)
  telephony/ inya_bridge.py (real phone calls through Gnani Inya)
  voice/   prisma.py · timbre.py · audio.py · mock_voice.py · phrase_cache.py
  providers/ base.py · mock_delivery.py
  tests/   policy · otp_safety · state_machine · approvals · ledger · messages · fast_path · voice · end_to_end · scenarios · benchmark
frontend/  index.html · call.html + call.js (rider's phone) · customer.html + customer.js (Asha's phone)
           phone.css · scenarios.json · rider.html + app.js + style.css (developer console)   (vanilla, no build step)
benchmark/ transcripts.csv · make_noisy.py · make_8khz.py · evaluate.py
docs/      architecture · safety · limitations · gnani_notes
```
