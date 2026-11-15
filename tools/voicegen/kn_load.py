import json, time
fp="/tmp/claude-0/-home-claude/0d25b0a4-19ba-5918-93c3-e30a79dfe072/scratchpad/models/kn/kn/fastpitch"; hg="/tmp/claude-0/-home-claude/0d25b0a4-19ba-5918-93c3-e30a79dfe072/scratchpad/models/kn/kn/hifigan"
c=json.load(open(f"{fp}/config.json")); c["speakers_file"]=f"{fp}/speakers.pth"
if "model_args" in c: c["model_args"]["speakers_file"]=f"{fp}/speakers.pth"
json.dump(c, open(f"{fp}/config_local.json","w"))
from TTS.utils.synthesizer import Synthesizer
def load():
    return Synthesizer(tts_checkpoint=f"{fp}/best_model.pth", tts_config_path=f"{fp}/config_local.json",
                       vocoder_checkpoint=f"{hg}/best_model.pth", vocoder_config=f"{hg}/config.json", use_cuda=False)
