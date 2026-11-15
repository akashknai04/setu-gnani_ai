# Architecture

## One turn, step by step

1. **Audio in.** The rider page records push-to-talk with `MediaRecorder` (webm/opus) and posts it to
   `POST /calls/{id}/audio`. ffmpeg converts it to 16 kHz mono WAV (or 8 kHz band-limited for phone
   tests). Clips over 30 s are rejected (Prisma REST limit).
2. **STT.** `voice/prisma.py` calls Prisma v3.0 with a language hint list and `codemix`. The
   reply's `detected_language_code` picks the rider's language. In `MOCK_VOICE=1` a sidecar `.txt`
   stands in for the transcript.
3. **Redaction.** `engine/otp_guard.py` replaces any 4–8 digit run (Latin, Devanagari, Kannada
   numerals) and any run of 4+ spoken digit words (en/hi/kn) with `[REDACTED]`. Nothing downstream
   sees the raw digits.
4. **Intent.** `intent/fast_path.py` — ordered regex rules in three scripts plus romanized Hindi and
   Kannada, time extraction ("saade chhe baje", "ಏಳು ಗಂಟೆಗೆ", "6:30"). Only if the result is `unclear`
   is Evon asked, and its JSON must pass `intent/schema.validate_evon_output`.
5. **Policy.** `engine/policy.evaluate()` — pure function of (intent, customer prefs, order,
   approval state, provider capabilities). Returns one of five actions.
6. **State machine.** `engine/state_machine.CallSession` enforces
   `GREETING → LISTENING → POLICY_CHECK → {INSTANT_ACTION | WAITING_APPROVAL | ESCALATED} → REPLY_AND_RECORD`.
   Only `authorize_provider()` can mint a `ProviderPermit`, and only from `INSTANT_ACTION` with the
   exact `Decision` object policy just returned and `provider_request=True`.
7. **Action.** Provider calls (simulated) need the permit; approvals create an HMAC token and push a
   card over `WS /ws/customer`.
8. **Ledger.** Every step appends a hash-chained event with an evidence level.
9. **Reply.** A fixed template in the rider's language, spoken from the phrase cache (or Timbre live
   for time-bearing phrases). Latency per stage is recorded.

When the customer taps, `POST /approvals/{id}/decide` consumes the token and the original intent
**re-enters the policy check** with the approval state — the tap never triggers an action directly.
A background sweeper expires unanswered approvals every second and falls back to the customer's
preferred window only.

## Modules

| module | job | depends on |
|---|---|---|
| `engine/policy.py` | every permission decision | nothing (pure) |
| `engine/state_machine.py` | legal transitions, provider permits | policy types |
| `engine/approvals.py` | sign / verify / burn tokens | db |
| `engine/ledger.py` | append-only hash chain | db, otp_guard |
| `engine/messages.py` | all user-facing text, evidence gating | ledger levels |
| `engine/orchestrator.py` | the call loop, failure handling | all of the above |
| `intent/*` | label the utterance | otp_guard |
| `voice/*` | ffmpeg, Prisma, Timbre, cache, mocks | config |
| `main.py` | HTTP + WebSocket, wiring | everything |

## Evidence levels (lowest → highest)

`info` < `rejected_or_unresolved` < `requested` < `rider_agreed` < `pre_approved` <
`customer_approved` < `provider_accepted (simulated)`

A customer template may only be shown if the ledger for that call contains the evidence it needs:

| template | needs |
|---|---|
| handover / address change "provider accepted the request" | `provider_accepted` |
| "You approved a delivery attempt at …" | `customer_approved` |
| "The rider agreed to attempt delivery at …" | `rider_agreed` |

Otherwise it is downgraded to "A rider called about your order. Nothing is confirmed yet."

## Data

SQLite: `customers`, `orders`, `calls`, `approvals`, `used_nonces`, `ledger` (UPDATE/DELETE blocked
by triggers), `latency`. All rows are synthetic and flagged `simulated`.

## Latency design

At startup every fixed reply (greeting, holding line, refusals, instructions, window and address
lines for the seeded customer) is rendered in hi/kn/en into `data/phrase_cache/` — 51 clips. Only
replies containing a rider-proposed time are synthesised live. Changing preferences re-renders in
the background. Per-turn STT / intent / policy / TTS / total timings go to the `latency` table
(`GET /latency` gives median and p95).

## The voice call (rider's phone, `/call`)

```
tap Call ─▶ ringback tone ─▶ POST /calls/start (greeting in the chosen language) ─▶ AI disclosure spoken
   ┌──────────────────────────────── loop while the call is live ───────────────────────────────┐
   │ listen: mic level > room floor for 150 ms = speech; 850 ms quiet = done (max 15 s)          │
   │   └─▶ POST /calls/{id}/audio ─▶ Prisma ─▶ same pipeline as above ─▶ Timbre reply ─▶ play    │
   │ empty transcript (cough, traffic) ─▶ ignored, keep listening                                │
   │ request_approval ─▶ "please wait" ─▶ Asha's phone (WS /ws/customer) ─▶ her tap re-enters     │
   │   policy ─▶ reply pushed to the rider (WS /ws/rider/{id}) ─▶ spoken, listening resumes      │
   │ end_call ("thank you, bye") or hang-up ─▶ POST /calls/{id}/end ─▶ unanswered approvals      │
   │   closed as call_ended_unresolved ─▶ summary screen                                         │
   └────────────────────────────────────────────────────────────────────────────────────────────┘
```

Half duplex: the phone never listens while the assistant speaks, so it can't hear itself. Without a
Gnani key, browser speech recognition and voices take the place of Prisma and Timbre (labelled on screen).
