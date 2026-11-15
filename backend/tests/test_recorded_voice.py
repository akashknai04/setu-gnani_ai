"""Recorded voice (no Gnani key): every fixed line has a real, non-silent recording."""
import json

import numpy as np

from backend.engine import messages as M
from backend.voice.audio import read_wav
from backend.voice.phrase_cache import PhraseCache
from backend.voice.recorded import VOICE_DIR, RecordedVoice, clip_key

MAN = json.loads((VOICE_DIR / "manifest.json").read_text(encoding="utf-8"))
WINDOW = M.fmt_window("18:00", "20:00")


def test_manifest_files_exist_and_keys_match():
    assert len(MAN) >= 150
    for k, v in MAN.items():
        assert clip_key(v["role"], v["lang"], v["text"]) == k
        assert (VOICE_DIR / v["file"]).stat().st_size > 2000


def test_every_fixed_reply_has_a_recording_in_all_three_languages():
    rv = RecordedVoice("ai")
    for key, lang, text in M.all_fixed_rider_phrases(WINDOW, "Demo Layout, Block 4 (mock)", "opposite the blue water tank (mock)"):
        assert rv.has(text, lang), (key, lang, text)


def test_recordings_are_audible_speech():
    rv = RecordedVoice("ai")
    for lang in ("hi", "kn", "en"):
        r = rv.synthesize(M.rider_reply("greeting", lang), lang)
        assert r.ok
        x, rate = read_wav(r.audio)
        assert len(x) / rate > 2.0                      # a real sentence, not a click
        assert float(np.sqrt(np.mean(x ** 2))) > 0.02   # not silence


def test_scenario_rider_lines_have_recordings():
    scen = json.loads((VOICE_DIR.parent / "scenarios.json").read_text(encoding="utf-8"))
    rider = RecordedVoice("rider")
    for sc in scen["scenarios"]:
        for st in sc["steps"]:
            for lang, text in st.get("say", {}).items():
                assert rider.has(text, lang), (sc["id"], lang, text)


def test_missing_line_does_not_fall_back_to_another_language(tmp_path):
    c = PhraseCache(str(tmp_path), RecordedVoice("ai"))
    s = c.speak("time_approved", "kn", {"time": "03:17"})   # an odd time nobody recorded
    assert not s.ok and s.error == "no_recording" and s.lang == "kn"
