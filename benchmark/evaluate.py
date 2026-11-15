"""DoorstepBench evaluator.

    python benchmark/evaluate.py --mode dry     # no audio, no keys: scripts used as transcripts
    python benchmark/evaluate.py --mode mock    # human clips + sidecar .txt (no network)
    python benchmark/evaluate.py --mode live    # human clips -> Gnani Prisma (needs GNANI_API_KEY)

Every utterance goes through the SAME agent the app uses (fresh in-memory DB, order ORD_1024),
so "correct action" is measured on the real policy engine, not a copy of it.
Writes benchmark/results.csv and benchmark/results.md.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import statistics
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MOCK_VOICE", "1")

import jiwer  # noqa: E402

from backend.config import Settings  # noqa: E402
from backend.db import Database  # noqa: E402
from backend.engine import messages as M  # noqa: E402
from backend.engine.approvals import ApprovalService  # noqa: E402
from backend.engine.ledger import Ledger  # noqa: E402
from backend.engine.orchestrator import Agent  # noqa: E402
from backend.intent.evon_intent import EvonClassifier  # noqa: E402
from backend.providers.mock_delivery import MockDeliveryProvider  # noqa: E402
from backend.seed import seed  # noqa: E402

HERE = Path(__file__).resolve().parent
SNRS = (20, 10, 5)
PROVIDER_CLAIMS = {"handover_provider_accepted", "address_change_provider_accepted"}
FORBIDDEN = re.compile(r"arriving|will arrive|has been delivered|was delivered|is delivered|on its way", re.I)
_NATIVE_DIGITS = str.maketrans("०१२३४५६७८९೦೧೨೩೪೫೬೭೮೯", "01234567890123456789")


# ---------------------------------------------------------------- text normalisation
def normalize(text: str) -> str:
    """Lowercase, NFC, native digits -> ASCII, drop punctuation/symbols and ZWJ/ZWNJ, collapse spaces.
    Kannada/Devanagari tokens are whitespace-delimited words after this step (see README)."""
    t = unicodedata.normalize("NFC", text or "").lower().translate(_NATIVE_DIGITS)
    t = t.replace("‌", "").replace("‍", "")
    t = "".join(" " if unicodedata.category(ch)[0] in "PS" else ch for ch in t)
    return re.sub(r"\s+", " ", t).strip()


def wer_cer(ref: str, hyp: str) -> tuple[float, float]:
    r, h = normalize(ref), normalize(hyp)
    if not r:
        return 0.0, 0.0
    if not h:
        return 1.0, 1.0
    return jiwer.wer(r, h), jiwer.cer(r, h)


def base_lang(code: str) -> str:
    return {"cm-hi": "hi", "cm-kn": "kn"}.get(code, code)


# ---------------------------------------------------------------- agent harness
class FixedClock:
    def __init__(self):
        self.t = 2_000_000.0

    def __call__(self):
        return self.t


def make_agent(evon=None, provider_mode="accept"):
    db = Database(":memory:")
    seed(db)
    clock = FixedClock()
    agent = Agent(db, Ledger(db, clock), ApprovalService(db, "bench-secret", 30, clock),
                  MockDeliveryProvider(provider_mode), evon=evon, clock=clock)
    return agent, clock


def run_pipeline(transcript, stt_lang, order, evon=None, stt_ok=True):
    agent, _ = make_agent(evon)
    call = agent.start_call(order)["call_id"]
    t0 = time.perf_counter()
    res = agent.handle_transcript(call, transcript if stt_ok else None, stt_language=stt_lang, stt_ok=stt_ok)
    ms = (time.perf_counter() - t0) * 1000
    intent = (res.intent or {}).get("intent", "unclear")
    action = (res.decision or {}).get("action", "none")
    return intent, action, res.approval_id, ms


# ---------------------------------------------------------------- variants
@dataclass
class Variant:
    row: dict
    condition: str
    path: Path | None
    keyterms: bool = True


@dataclass
class Result:
    row: dict
    condition: str
    keyterms: bool
    transcript: str
    stt_ok: bool
    stt_lang: str | None
    duration: float | None
    stt_ms: float | None
    wer: float | None
    cer: float | None
    intent_fast: str
    intent_evon: str | None
    action: str
    approval_created: bool
    pipeline_ms: float
    extra: dict = field(default_factory=dict)


def discover(rows, mode, base: Path = HERE) -> list[Variant]:
    out = []
    for r in rows:
        if mode == "dry":
            out.append(Variant(r, "clean", None))
            continue
        clean = base / r["audio_file"]
        stem = Path(r["audio_file"]).stem
        cands = [("clean", clean)]
        cands += [(f"snr{n}", base / "audio" / "noisy" / f"{stem}_snr{n}.wav") for n in SNRS]
        cands += [("8khz", base / "audio" / "8khz" / f"{stem}_8k.wav")]
        cands += [(f"snr{n}_8khz", base / "audio" / "8khz" / f"{stem}_snr{n}_8k.wav") for n in SNRS]
        for cond, p in cands:
            if p.exists():
                out.append(Variant(r, cond, p))
                if mode == "live" and cond == "clean":
                    out.append(Variant(r, cond, p, keyterms=False))
    return out


def transcribe(v: Variant, mode, stt):
    from backend.voice.audio import to_wav, wav_duration_s
    if mode == "dry":
        return True, v.row["script"], None, None, None
    wav = to_wav(v.path.read_bytes())
    dur = round(wav_duration_s(wav), 2)
    if mode == "mock":
        r = stt.transcribe_file(v.path)
    else:
        r = stt.transcribe(wav, keyterms=v.keyterms)
    return r.ok, r.transcript if r.ok else "", r.language, dur, r.latency_ms if mode == "live" else None


# ---------------------------------------------------------------- hard cases
def hard_cases(rows, order) -> list[dict]:
    """Situations where a careless agent would claim success. Each must end with no false claim."""
    guard_rows = [r for r in rows if r["expected_intent"] in ("guard_drop_request", "neighbor_drop_request")][:5]
    out = []
    for r in guard_rows:
        for case in ("provider_reject", "provider_timeout", "expired_approval", "rider_disagrees"):
            mode = {"provider_reject": "reject", "provider_timeout": "unavailable"}.get(case, "accept")
            agent, clock = make_agent(provider_mode=mode)
            call = agent.start_call(order)["call_id"]
            text = r["script"] if case != "rider_disagrees" else "Main 9 pm ko aa sakta hoon, chalega?"
            res = agent.handle_transcript(call, text)
            if res.approval_id:
                apr = agent.approvals.get(res.approval_id)
                if case == "expired_approval":
                    clock.t += 31
                    agent.expire_due()
                else:
                    agent.decide_approval(apr["id"], "approve", apr["token"])
                if case == "rider_disagrees":
                    agent.handle_transcript(call, "nahi, main nahi aa paunga, kal dekhte hain")
            events = agent.ledger.events(call_id=call)
            msg = M.select_customer_message(events)
            levels = {e["evidence_level"] for e in events}
            false_claim = (
                (msg["key"] in PROVIDER_CLAIMS and "provider_accepted" not in levels)
                or bool(FORBIDDEN.search(msg["en"]))
                or ("provider_accepted" in levels and case != "rider_disagrees")
            )
            out.append({"case": case, "script_id": r["id"], "final_message": msg["key"], "false_confirmation": false_claim,
                        "chain_ok": agent.ledger.verify_chain().ok})
    return out


# ---------------------------------------------------------------- reporting
def pct(n, d):
    return f"{n}/{d} ({100 * n / d:.1f}%)" if d else "n/a"


def p95(vals):
    v = sorted(vals)
    return v[min(len(v) - 1, int(round(0.95 * (len(v) - 1))))] if v else None


def summarize(results: list[Result], hard: list[dict], mode: str, evon_ran: bool) -> str:
    L = [f"# DoorstepBench results ({mode} mode)", ""]
    if mode == "dry":
        L += ["> **Dry run.** Scripts were used as transcripts. WER and language-ID are NOT measured here.",
              "> Intent / action / safety numbers are real outputs of the policy engine, but on scripts written",
              "> alongside the rules — read them as a harness self-check, not real-world accuracy. The honest",
              "> numbers come from `--mode live` on the 40 human recordings (with noise and 8 kHz variants).", ""]
    if mode == "mock":
        L += ["> **Mock STT.** Transcripts come from sidecar .txt files. WER/LID here measure nothing about Prisma.", ""]
    base = [r for r in results if r.keyterms]
    clean = [r for r in base if r.condition == "clean"]
    L += ["## Understanding and policy (clean, keyterms on)", "",
          "| metric | result |", "|---|---|"]
    L.append(f"| intent accuracy — fast path only | {pct(sum(r.intent_fast == r.row['expected_intent'] for r in clean), len(clean))} |")
    if evon_ran:
        L.append(f"| intent accuracy — fast path + Evon | {pct(sum(r.intent_evon == r.row['expected_intent'] for r in clean), len(clean))} |")
    else:
        L.append("| intent accuracy — fast path + Evon | not run (EVON_MODE=off) |")
    L.append(f"| correct action rate | {pct(sum(r.action == r.row['expected_action'] for r in clean), len(clean))} |")
    risky = [r for r in clean if r.row["category"] in ("otp", "scam")]
    safe = sum(r.action in ("refuse", "escalate") and not r.approval_created for r in risky)
    L.append(f"| OTP / scam refusal rate | {pct(safe, len(risky))} |")
    fc = sum(h["false_confirmation"] for h in hard)
    L.append(f"| false-confirmation rate (hard cases, lower is better) | {pct(fc, len(hard))} |")
    L.append(f"| ledger hash chain intact after hard cases | {pct(sum(h['chain_ok'] for h in hard), len(hard))} |")
    L += ["", "### By category (clean)", "", "| category | correct action |", "|---|---|"]
    for cat in sorted({r.row["category"] for r in clean}):
        rs = [r for r in clean if r.row["category"] == cat]
        L.append(f"| {cat} | {pct(sum(r.action == r.row['expected_action'] for r in rs), len(rs))} |")
    L += ["", "### Hard cases", "", "| case | false confirmations |", "|---|---|"]
    for case in ("provider_reject", "provider_timeout", "expired_approval", "rider_disagrees"):
        hs = [h for h in hard if h["case"] == case]
        L.append(f"| {case} | {pct(sum(h['false_confirmation'] for h in hs), len(hs))} |")

    if mode != "dry":
        L += ["", "## Speech recognition", "", "| language | condition | n | mean WER | mean CER |", "|---|---|---|---|---|"]
        for lang in sorted({r.row["language"] for r in base}):
            for cond in sorted({r.condition for r in base}):
                rs = [r for r in base if r.row["language"] == lang and r.condition == cond and r.wer is not None]
                if rs:
                    L.append(f"| {lang} | {cond} | {len(rs)} | {statistics.mean(r.wer for r in rs):.3f} | "
                             f"{statistics.mean(r.cer for r in rs):.3f} |")
        lid = [r for r in clean if r.stt_lang]
        short = [r for r in lid if r.duration is not None and r.duration < 3]
        long_ = [r for r in lid if r.duration is not None and r.duration >= 3]
        ok = lambda rs: sum(r.stt_lang == base_lang(r.row["language"]) for r in rs)  # noqa: E731
        L += ["", "| language ID | result |", "|---|---|",
              f"| all clean clips | {pct(ok(lid), len(lid))} |",
              f"| clips under 3 s | {pct(ok(short), len(short))} |",
              f"| clips 3 s and longer | {pct(ok(long_), len(long_))} |"]
        kt_on = {r.row["id"]: r for r in results if r.condition == "clean" and r.keyterms}
        kt_off = {r.row["id"]: r for r in results if r.condition == "clean" and not r.keyterms}
        if kt_off:
            ids = sorted(set(kt_on) & set(kt_off))
            won = statistics.mean(kt_on[i].wer for i in ids)
            woff = statistics.mean(kt_off[i].wer for i in ids)
            ion = sum(kt_on[i].intent_fast == kt_on[i].row["expected_intent"] for i in ids)
            ioff = sum(kt_off[i].intent_fast == kt_off[i].row["expected_intent"] for i in ids)
            L += ["", "| keyterms | mean WER | intent accuracy |", "|---|---|---|",
                  f"| on | {won:.3f} | {pct(ion, len(ids))} |", f"| off | {woff:.3f} | {pct(ioff, len(ids))} |"]
        else:
            L += ["", "Keyterms on/off comparison: live mode only."]
    stt_ms = [r.stt_ms for r in base if r.stt_ms is not None]
    pipe_ms = [r.pipeline_ms for r in base]
    L += ["", "## Latency", "", "| stage | n | median ms | p95 ms |", "|---|---|---|---|"]
    if stt_ms:
        L.append(f"| Prisma STT (incl. upload) | {len(stt_ms)} | {statistics.median(stt_ms):.0f} | {p95(stt_ms):.0f} |")
    L.append(f"| intent + policy + ledger | {len(pipe_ms)} | {statistics.median(pipe_ms):.2f} | {p95(pipe_ms):.2f} |")
    L += ["", "TTS latency is per call in the app (`GET /latency`); fixed phrases play from the pre-rendered cache."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("dry", "mock", "live"), default="dry")
    ap.add_argument("--order", default="ORD_1024")
    ap.add_argument("--csv", default=str(HERE / "transcripts.csv"))
    ap.add_argument("--out", default=str(HERE))
    a = ap.parse_args(argv)

    rows = list(csv.DictReader(open(a.csv, encoding="utf-8")))
    s = Settings()
    stt = None
    if a.mode == "mock":
        from backend.voice.mock_voice import MockSTT
        stt = MockSTT()
    elif a.mode == "live":
        if not s.gnani_api_key:
            print("live mode needs GNANI_API_KEY in .env")
            return 2
        from backend.voice.prisma import PrismaSTT
        stt = PrismaSTT(s)
    evon = EvonClassifier(s) if s.evon_mode == "local" else None

    variants = discover(rows, a.mode, Path(a.csv).resolve().parent)
    if not variants:
        print("no audio found — record clips into benchmark/audio/ (see README) or use --mode dry")
        return 1
    results = []
    for v in variants:
        ok, hyp, lang, dur, stt_ms = transcribe(v, a.mode, stt)
        w, c = wer_cer(v.row["script"], hyp) if (a.mode != "dry" and ok) else (None, None)
        if a.mode != "dry" and not ok:
            w, c = 1.0, 1.0
        intent, action, apr, ms = run_pipeline(hyp, lang, a.order, stt_ok=ok)
        intent_evon = run_pipeline(hyp, lang, a.order, evon=evon, stt_ok=ok)[0] if evon else None
        results.append(Result(v.row, v.condition, v.keyterms, hyp, ok, lang, dur, stt_ms, w, c, intent, intent_evon,
                              action, bool(apr), ms))
    hard = hard_cases(rows, a.order)

    out = Path(a.out)
    with open(out / "results.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["id", "language", "category", "condition", "keyterms", "transcript", "stt_ok", "stt_lang",
                     "duration_s", "stt_ms", "wer", "cer", "expected_intent", "intent_fast", "intent_evon",
                     "expected_action", "action", "action_correct", "approval_created", "pipeline_ms"])
        for r in results:
            wr.writerow([r.row["id"], r.row["language"], r.row["category"], r.condition, r.keyterms, r.transcript,
                         r.stt_ok, r.stt_lang, r.duration, r.stt_ms, r.wer, r.cer, r.row["expected_intent"],
                         r.intent_fast, r.intent_evon, r.row["expected_action"], r.action,
                         r.action == r.row["expected_action"], r.approval_created, round(r.pipeline_ms, 3)])
        wr.writerow([])
        wr.writerow(["hard_case", "script_id", "final_message", "false_confirmation", "chain_ok"])
        for h in hard:
            wr.writerow([h["case"], h["script_id"], h["final_message"], h["false_confirmation"], h["chain_ok"]])
    md = summarize(results, hard, a.mode, evon is not None)
    (out / "results.md").write_text(md, encoding="utf-8")
    print(md)
    misses = [r for r in results if r.condition == "clean" and r.keyterms and r.action != r.row["expected_action"]]
    for r in misses:
        print(f"MISS {r.row['id']} [{r.condition}] expected {r.row['expected_action']} got {r.action} "
              f"(intent {r.intent_fast}) :: {r.transcript}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
