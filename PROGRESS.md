# PROGRESS

| Gate | Status | Tests | Notes |
|---|---|---|---|
| 1 scaffold + docs | done | n/a (ffmpeg check OK) | Gnani STT REST confirmed; TTS partial; Evon open-weights only |
| 2 core (no voice) | done | 151 passed / 0 failed | policy, state machine, permits, HMAC approvals, hash-chained ledger (DB triggers block UPDATE/DELETE), OTP redaction, templates with evidence gating, fast path hi/kn/en |
| 3 voice | done | 180 passed / 0 failed / 1 skipped (live Gnani check, no key in this environment) | Prisma REST (confirmed fields), Timbre REST, Evon local/off, phrase cache with kn->en->hi fallback, mock voice. Fixed: ffmpeg pipe WAV header bug |
| 4 app | done | 200 passed / 0 failed / 1 skipped | FastAPI endpoints, /ws/customer + /ws/rider/{call}, rider + customer pages; full demo script verified in MOCK_VOICE via HTTP tests and a real Chrome run. Fixed: injection now escalates (no approval card). Real-voice run pending your API key |
| 5 proof (DoorstepBench) | done | 207 passed / 0 failed / 1 skipped | 40 scripts, make_noisy (SNR verified ±0.5 dB), make_8khz (mu-law), evaluate dry/mock/live; dry run: 40/40 action, 10/10 refusals, 0/20 false confirmations (self-check, not accuracy) |
| 6 docs | done | 207 passed / 0 failed / 1 skipped | README (one-command run, demo script, 60 s video plan), architecture, safety, limitations, REVIEW (unverified API items, Evon off, Kannada review list, manual steps) |

**Next (by hand):** add GNANI_API_KEY + MOCK_VOICE=0 and run the live check; native Kannada review; record 40 benchmark clips + noise; record demo; post + submit by Nov 10, 11:59 PM IST.
