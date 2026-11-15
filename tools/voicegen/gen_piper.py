"""Render Hindi and English lines with Piper (sherpa-onnx) -> mp3. Kannada is rendered by gen_kn.py."""
import hashlib, json, os, subprocess, sys
import numpy as np, sherpa_onnx, soundfile as sf
from speakable import speakable
V, M = sys.argv[1], sys.argv[2]
VOICE = {("ai", "hi"): "vits-piper-hi_IN-priyamvada-medium", ("rider", "hi"): "vits-piper-hi_IN-pratham-medium",
         ("ai", "en"): "vits-piper-en_US-lessac-medium", ("rider", "en"): "vits-piper-en_US-ryan-medium"}
engines = {}
def eng(d):
    if d not in engines:
        p = f"{M}/{d}"; onnx = [f for f in os.listdir(p) if f.endswith(".onnx")][0]
        engines[d] = sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=f"{p}/{onnx}", tokens=f"{p}/tokens.txt", data_dir=f"{p}/espeak-ng-data"), num_threads=2)))
    return engines[d]
def key(l): return hashlib.sha1(f"{l['role']}|{l['lang']}|{l['text']}".encode()).hexdigest()[:12]
def to_mp3(samples, rate, dst):
    x = np.concatenate([np.zeros(int(rate * 0.08)), samples, np.zeros(int(rate * 0.15))]).astype(np.float32)
    peak = float(np.max(np.abs(x))) or 1.0
    x = x / peak * 0.89                                   # consistent loudness, no clipping
    tmp = dst + ".wav"; sf.write(tmp, x, rate, subtype="PCM_16")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-ac", "1", "-ar", "22050", "-c:a", "libmp3lame", "-b:a", "40k", dst], check=True)
    os.remove(tmp)
os.makedirs(f"{V}/clips", exist_ok=True)
lines = json.load(open(f"{V}/lines.json", encoding="utf-8")); man = {}
for l in lines:
    if l["lang"] == "kn": continue
    spoken = speakable(l["text"], l["lang"]); k = key(l); dst = f"{V}/clips/{k}.mp3"
    if not os.path.exists(dst):
        a = eng(VOICE[(l["role"], l["lang"])]).generate(spoken, sid=0, speed=1.0 if l["role"] == "ai" else 1.05)
        to_mp3(np.array(a.samples), a.sample_rate, dst)
    man[k] = {**l, "spoken": spoken, "file": f"{k}.mp3"}
json.dump(man, open(f"{V}/manifest_hi_en.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(man), "clips", sum(os.path.getsize(f"{V}/clips/{v['file']}") for v in man.values()) // 1024, "KB")
