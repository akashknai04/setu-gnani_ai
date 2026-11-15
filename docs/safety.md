# Safety

The rider's speech is **untrusted input**. A model's confidence is **never** permission.

## Hard rules and where they are enforced

| rule | enforced in | proven by |
|---|---|---|
| OTP never asked, spoken, stored, logged, or put in a prompt | `otp_guard.redact_otp` runs before storage, classification and Evon; `Ledger.append` redacts every string again; no template contains digit runs | `test_otp_safety.py` (incl. digits in hi/kn numerals and spoken words), `test_end_to_end::test_otp_digits_never_reach_ledger_or_response`, `test_voice::test_evon_*` (prompt check) |
| OTP requests always refused, never customer-approvable | `policy.evaluate` step 2, before any approval logic | `test_policy::test_otp_always_refused_even_if_approved` |
| LLM never decides permissions | Evon output is only an intent label; schema rejects extra keys such as `confidence`; OTP fast-path match overrides Evon | `test_voice::test_evon_*`, `test_voice::test_schema_rejects_confidence_key` |
| Provider request impossible without policy permission | `ProviderPermit` cannot be constructed outside `CallSession.authorize_provider`; provider checks the permit and burns it | `test_state_machine.py` (9 permit tests), `POST /mock-provider/request` → 403 |
| Verified orders never handed to a third party | policy refuses before checking pre-approval or customer approval | `test_policy::test_verified_order_*`, demo 2 |
| Approvals can't be forged, replayed, moved or kept past expiry | HMAC-SHA256, bound fields, nonce burned in `used_nonces` (UNIQUE) | `test_approvals.py` |
| A customer approval never triggers an action directly | decision re-enters `evaluate()` with the approval state | `test_state_machine::test_approval_reenters_policy_check` |
| No false success | evidence-gated templates; provider `accepted` means request accepted, never delivered | `test_messages.py`, benchmark hard cases (0/20 false confirmations) |
| Ledger can't be silently edited | triggers block UPDATE/DELETE; hash chain detects edits even if triggers are dropped | `test_ledger.py` |
| Every failure path ends safely | STT fail → ask once → escalate; Evon timeout → fast-path result; TTS fail → cache → fallback language → customer notified; provider fail → "not accepted"; any exception → escalated reply + `system_failure` message + ledger event | `test_end_to_end.py`, `test_voice.py` |
| Customer messages only from fixed templates | `messages.py`; no model output reaches a customer | code review: no path writes free text to `customer_message` |
| Everything simulated is labelled | `simulated=true` on every ledger event and provider response; UI badges | `test_ledger::test_every_event_is_simulated`, `test_pages_and_health` |

## Prompt injection

"Ignore your rules…", "you are now…", "system prompt", "नियम भूल…", "ನಿಯಮ ಮರೆ…" set an injection flag.
If the sentence also asks for an OTP it is refused; otherwise the turn escalates immediately with
no retry and no approval card. Evon is never called on a flagged utterance.

## Privacy

No real personal data anywhere. The address answer gives **area and landmark only**. API keys live in
`.env` (git-ignored); `.env.example` has none. Uploaded rider clips are stored locally under
`data/uploads/` for debugging — delete that folder before sharing the repo.
