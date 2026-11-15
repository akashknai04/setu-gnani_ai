# Limitations (stated plainly)

- **Simulated world.** No real delivery platform, order or customer. "Provider accepted" is a mock.
  A real integration needs the platform's API, auth, and its own notion of evidence.
- **Not a phone call.** Push-to-talk in a browser, not SIP/PSTN. Phone conditions are approximated with
  8 kHz band-limiting + mu-law in the benchmark, not measured on real carrier audio.
- **Fast path is rules.** It covers the phrasings in the tests and benchmark; real riders will say
  things it misses. Misses become `unclear` → one retry → escalate, which is safe but not always helpful.
  Evon is the intended fix but needs a self-hosted 30B MoE model.
- **Time parsing is heuristic.** Unmarked 1–7 is read as PM; "tomorrow" is ignored (time only).
  A wrong time can only produce a wrong *proposal* — inside the window it is logged as the rider's word,
  outside it goes to the customer.
- **Kannada and Hindi templates and scripts need native review** (REVIEW.md lists every line).
- **Language ID on very short clips is weak** (Gnani's docs say clips under ~1 s are least reliable).
  We ask the rider to repeat or choose a language instead of guessing.
- **Single customer, single process.** SQLite, one FastAPI worker, in-memory WebSocket hub. No auth
  on the customer page — it is a demo device, not a product.
- **Benchmark is small** (40 scripts). The dry run is a self-check (scripts were written with the rules).
  Real numbers require the human recordings and `--mode live`.
- **Timbre details partially verified** (see REVIEW.md); the adapter is configurable and fails safe.
- **Approval TTL 30 s** is a demo value; a real rider can't wait long. Tune `APPROVAL_TTL_S`.
