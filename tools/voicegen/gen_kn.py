"""Render Kannada lines with AI4Bharat Indic-TTS (FastPitch + HiFi-GAN): female = assistant, male = rider."""
import hashlib, json, os, subprocess, sys
import numpy as np, soundfile as sf
from speakable import speakable
from kn_load import load
V = sys.argv[1]
syn = load()
lines = [l for l in json.load(open(f"{V}/lines.json", encoding="utf-8")) if l["lang"] == "kn"]
man = {}
for i, l in enumerate(lines):
    k = hashlib.sha1(f"{l['role']}|{l['lang']}|{l['text']}".encode()).hexdigest()[:12]
    dst = f"{V}/clips/{k}.mp3"; spoken = speakable(l["text"], "kn")
    if not os.path.exists(dst):
        wav = np.array(syn.tts(spoken, speaker_name="female" if l["role"] == "ai" else "male"), dtype=np.float32)
        rate = syn.output_sample_rate
        x = np.concatenate([np.zeros(int(rate * 0.08)), wav, np.zeros(int(rate * 0.15))])
        x = x / (float(np.max(np.abs(x))) or 1.0) * 0.89
        tmp = dst + ".wav"; sf.write(tmp, x, rate, subtype="PCM_16")
        tempo = "1.08" if l["role"] == "ai" else "1.12"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-af", f"atempo={tempo}", "-ac", "1", "-ar", "22050",
                        "-c:a", "libmp3lame", "-b:a", "40k", dst], check=True)
        os.remove(tmp)
    man[k] = {**l, "spoken": spoken, "file": f"{k}.mp3"}
    print(i + 1, "/", len(lines), flush=True)
json.dump(man, open(f"{V}/manifest_kn.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print("done", len(man))
