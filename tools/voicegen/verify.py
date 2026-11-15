"""Transcribe every clip with Whisper small and compare to the intended spoken text (character error rate)."""
import json, subprocess, sys, unicodedata, re
import numpy as np, sherpa_onnx, jiwer
V, M, manifest = sys.argv[1], sys.argv[2], sys.argv[3]
W = f"{M}/sherpa-onnx-whisper-small"
rec = {}
def recognizer(lang):
    if lang not in rec:
        rec[lang] = sherpa_onnx.OfflineRecognizer.from_whisper(encoder=f"{W}/small-encoder.int8.onnx", decoder=f"{W}/small-decoder.int8.onnx",
                                                               tokens=f"{W}/hex-tokens.txt", language=lang, task="transcribe", num_threads=2)
    return rec[lang]
def load(path):
    pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
_V = {"अ":"a","आ":"aa","इ":"i","ई":"ee","उ":"u","ऊ":"oo","ए":"e","ऐ":"ai","ओ":"o","औ":"au"}
_M = {"ा":"a","ि":"i","ी":"i","ु":"u","ू":"u","े":"e","ै":"ai","ो":"o","ौ":"au","ं":"n","ँ":"n","ः":"h","ृ":"ri"}
_C = dict(zip("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह", "k kh g gh n ch chh j jh n t th d dh n t th d dh n p ph b bh m y r l v sh sh s h".split()))
def roman(t):
    out, i = [], 0
    t = t.replace("़", "")
    for j, ch in enumerate(t):
        if ch in _C:
            nxt = t[j + 1] if j + 1 < len(t) else ""
            end = (not nxt) or not ("\u0900" <= nxt <= "\u097f")
            out.append(_C[ch] + ("" if nxt in _M or nxt == "्" or end else "a"))
        elif ch in _M: out.append(_M[ch])
        elif ch in _V: out.append(_V[ch])
        elif ch == "्": continue
        else: out.append(ch)
    return "".join(out)
def unhex(t):
    # join runs of §hex§ byte pieces, then decode them as UTF-8 (sherpa drops partial characters otherwise)
    t = re.sub(r"(?:§[0-9a-f]+§)+", lambda m: bytes.fromhex(re.sub(r"§", "", m.group(0))).decode("utf-8", "replace"), t)
    return t.replace("§", "")
def norm(t):
    t = unicodedata.normalize("NFC", t.lower()).replace("‌", "").replace("‍", "")
    t = re.sub(r"[^\w\s]", " ", t); return re.sub(r"\s+", " ", t).strip()
man = json.load(open(manifest, encoding="utf-8")); rows = []
only = sys.argv[4] if len(sys.argv) > 4 else None
if only: man = {k: v for k, v in man.items() if v["lang"] == only}
for k, v in man.items():
    x = load(f"{V}/clips/{v['file']}"); dur = len(x) / 16000
    r = recognizer(v["lang"]); s = r.create_stream(); s.accept_waveform(16000, x); r.decode_stream(s)
    hyp = unhex(s.result.text).strip(); cer = jiwer.cer(norm(v["spoken"]), norm(hyp)) if norm(hyp) else 1.0
    if v["lang"] == "hi" and re.search(r"[a-zA-Z]", hyp) and not re.search(r"[\u0900-\u097f]", hyp):
        cer = jiwer.cer(norm(roman(v["spoken"])), norm(hyp))
    rms = float(np.sqrt(np.mean(x ** 2))); rows.append((cer, v["lang"], v["role"], round(dur, 1), round(rms, 3), v["spoken"][:70], hyp[:70]))
rows.sort(reverse=True)
by = {}
for r in rows: by.setdefault(r[1], []).append(r[0])
print({l: f"median CER {np.median(c):.2f}, worst {max(c):.2f}, n={len(c)}" for l, c in by.items()})
print("silent clips (rms<0.01):", sum(1 for r in rows if r[4] < 0.01))
for r in rows[:8]: print(f"{r[0]:.2f} {r[1]} {r[2]} {r[3]}s | {r[5]} || {r[6]}")
json.dump(rows, open(manifest + ".verify.json", "w", encoding="utf-8"), ensure_ascii=False)
