"""Gate 3: voice adapters. All offline (httpx MockTransport / mock voice / local ffmpeg)."""
import json
import os
import subprocess

import httpx
import pytest

from backend.config import Settings
from backend.intent.evon_intent import EvonClassifier
from backend.intent.schema import IntentResult, SchemaError, validate_evon_output
from backend.voice.audio import concat_wavs, read_wav, silent_wav, to_wav, wav_duration_s
from backend.voice.mock_voice import MockSTT, MockTTS
from backend.voice.phrase_cache import PhraseCache
from backend.voice.prisma import PrismaSTT
from backend.voice.timbre import TimbreTTS


def _settings(**kw):
    s = Settings()
    s.gnani_api_key = "test-key"
    for k, v in kw.items():
        setattr(s, k, v)
    return s


# ---------------------------------------------------------------- audio
def _webm_tone(tmp_path):
    out = tmp_path / "tone.webm"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-c:a", "libopus", str(out)], check=True)
    return out.read_bytes()


def test_webm_to_wav_16k_mono(tmp_path):
    wav = to_wav(_webm_tone(tmp_path))
    x, rate = read_wav(wav)
    assert rate == 16000 and 0.9 < wav_duration_s(wav) < 1.2 and x.ndim == 1


def test_telephony_8k(tmp_path):
    _, rate = read_wav(to_wav(_webm_tone(tmp_path), telephony=True))
    assert rate == 8000


def test_concat_and_silence():
    w = concat_wavs([silent_wav(200), silent_wav(200)], gap_ms=100)
    assert abs(wav_duration_s(w) - 0.5) < 0.01


# ---------------------------------------------------------------- Prisma
def test_prisma_sends_confirmed_fields_and_parses():
    seen = {}

    def handler(req: httpx.Request):
        seen["path"] = req.url.path
        seen["key"] = req.headers.get("X-API-Key-ID")
        seen["body"] = req.content
        return httpx.Response(200, json={"success": True, "request_id": "r1", "transcript": "गार्ड को दे दूँ",
                                         "model": "prisma-v3.0", "detected_language_code": "hi-IN",
                                         "processing_time": 0.4, "end_to_end_latency": 0.5})

    stt = PrismaSTT(_settings(), transport=httpx.MockTransport(handler))
    r = stt.transcribe(silent_wav(500))
    assert r.ok and r.language == "hi" and r.transcript.startswith("गार्ड")
    assert seen["path"] == "/stt/v3" and seen["key"] == "test-key"
    body = seen["body"]
    for field in (b'name="audio_file"', b'name="model"', b"prisma-v3.0", b'name="language_code"',
                  b'name="format"', b'name="keyterms"'):
        assert field in body


def test_prisma_keyterms_off():
    seen = {}

    def handler(req):
        seen["body"] = req.content
        return httpx.Response(200, json={"success": True, "transcript": "", "model": "prisma-v3.0"})

    PrismaSTT(_settings(), transport=httpx.MockTransport(handler)).transcribe(silent_wav(), keyterms=False)
    assert b'name="keyterms"' not in seen["body"]


@pytest.mark.parametrize("status,body,code", [
    (400, {"success": False, "error": {"type": "MAX_AUDIO_DURATION_EXCEEDED", "message": "x"}}, "MAX_AUDIO_DURATION_EXCEEDED"),
    (401, {"detail": {"error_code": "INVALID_API_KEY", "message": "Unauthorized", "status_code": 401}}, "INVALID_API_KEY"),
    (504, {"error": "Gateway Timeout", "code": "UPSTREAM_TIMEOUT", "message": "x"}, "UPSTREAM_TIMEOUT"),
    (422, {"detail": [{"type": "missing"}]}, "VALIDATION_ERROR"),
])
def test_prisma_error_shapes(status, body, code):
    r = PrismaSTT.parse(status, json.dumps(body))
    assert not r.ok and code in r.error


def test_prisma_without_key_fails_cleanly():
    s = _settings()
    s.gnani_api_key = ""
    assert not PrismaSTT(s).transcribe(silent_wav()).ok


def test_prisma_network_error():
    def boom(req):
        raise httpx.ConnectError("down")
    r = PrismaSTT(_settings(), transport=httpx.MockTransport(boom)).transcribe(silent_wav())
    assert not r.ok and "network" in r.error


# ---------------------------------------------------------------- Timbre
def test_timbre_body_and_audio():
    seen = {}

    def handler(req):
        seen["json"] = json.loads(req.content)
        seen["path"] = req.url.path
        return httpx.Response(200, content=silent_wav(), headers={"content-type": "audio/wav"})

    r = TimbreTTS(_settings(), transport=httpx.MockTransport(handler)).synthesize("ನಮಸ್ಕಾರ", "kn")
    assert r.ok and r.audio[:4] == b"RIFF"
    assert seen["path"] == "/api/v1/tts/inference"
    j = seen["json"]
    assert j["voice"] == "Saanvi" and j["language"] == "kn-IN" and j["model"] == "timbre-v2.5"
    assert j["audio_config"]["container"] == "wav"


def test_timbre_json_error_is_failure():
    t = TimbreTTS(_settings(), transport=httpx.MockTransport(
        lambda r: httpx.Response(400, json={"error": "bad voice"})))
    assert not t.synthesize("hi", "hi").ok


# ---------------------------------------------------------------- mock voice + cache
def test_mock_stt_reads_sidecar(tmp_path):
    a = tmp_path / "clip.webm"
    a.write_bytes(b"x")
    (tmp_path / "clip.txt").write_text("ಗಾರ್ಡ್ ಗೆ ಕೊಡ್ಲಾ?", encoding="utf-8")
    r = MockSTT().transcribe_file(a)
    assert r.ok and r.language == "kn"
    (tmp_path / "clip.txt").write_text("#stt_fail\n", encoding="utf-8")
    assert not MockSTT().transcribe_file(a).ok


def test_phrase_cache_hits_second_time(tmp_path):
    c = PhraseCache(str(tmp_path), MockTTS())
    first = c.speak("holding", "hi")
    second = c.speak("holding", "hi")
    assert first.ok and not first.cached and second.cached
    assert c.stats["hits"] == 1


def test_kannada_tts_failure_falls_back_to_english(tmp_path):
    c = PhraseCache(str(tmp_path), MockTTS(fail_langs={"kn"}))
    s = c.speak("otp_refused", "kn")
    assert s.ok and s.lang == "en" and s.fallback_from == "kn" and "OTP" in s.text


def test_total_tts_failure_reports_not_ok(tmp_path):
    c = PhraseCache(str(tmp_path), MockTTS(fail_langs={"kn", "en", "hi"}))
    s = c.speak("holding", "kn")
    assert not s.ok and s.audio == b""


def test_prerender_all_fixed_phrases(tmp_path):
    from backend.engine.messages import all_fixed_rider_phrases
    c = PhraseCache(str(tmp_path), MockTTS())
    phrases = all_fixed_rider_phrases("6 PM – 8 PM", "A", "L")
    rep = c.prerender(phrases)
    assert rep["failed"] == 0 and rep["rendered"] == len(phrases)


# ---------------------------------------------------------------- Evon
FAST_UNCLEAR = IntentResult("unclear", None, "hi", "fast_path", [])


def _evon(content=None, exc=None):
    def handler(req):
        if exc:
            raise exc
        body = json.loads(req.content)
        assert "4821" not in json.dumps(body, ensure_ascii=False)  # redacted before prompt
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
    return EvonClassifier(_settings(evon_mode="local"), transport=httpx.MockTransport(handler))


def test_evon_off_returns_fast_path():
    e = EvonClassifier(_settings(evon_mode="off"))
    assert e.classify("x", FAST_UNCLEAR) is FAST_UNCLEAR


def test_evon_api_mode_refused_clearly():
    with pytest.raises(ValueError):
        EvonClassifier(_settings(evon_mode="api"))


def test_evon_valid_json():
    r = _evon('{"intent": "propose_time", "time": "18:45"}').classify("pone saat ke aas paas", FAST_UNCLEAR)
    assert r.intent == "propose_time" and r.time == "18:45" and r.source == "evon"


@pytest.mark.parametrize("content", [
    "sure! guard drop", '{"intent": "approve_everything"}', '{"intent": "guard_drop_request", "confidence": 0.99}',
    '{"intent": "propose_time", "time": "25:99"}', '{"intent": "ask_address", "time": "18:00"}',
])
def test_evon_malformed_becomes_unclear(content):
    r = _evon(content).classify("blah", FAST_UNCLEAR)
    assert r.intent == "unclear" and r.source == "fallback"


def test_evon_timeout_uses_fast_path():
    r = _evon(exc=httpx.ReadTimeout("slow")).classify("blah", FAST_UNCLEAR)
    assert r.intent == "unclear" and "evon_timeout" in r.matched


def test_evon_cannot_override_otp_match():
    r = _evon('{"intent": "guard_drop_request", "time": null}').classify(
        "otp 4821", IntentResult("request_otp", None, "hi"), {"otp_rule": True})
    assert r.intent == "request_otp"


def test_schema_rejects_confidence_key():
    with pytest.raises(SchemaError):
        validate_evon_output({"intent": "ask_address", "time": None, "confidence": 1.0})


# ---------------------------------------------------------------- optional live check
@pytest.mark.skipif(not os.environ.get("GNANI_API_KEY") or os.environ.get("MOCK_VOICE", "1") == "1",
                    reason="live Gnani check needs GNANI_API_KEY and MOCK_VOICE=0")
def test_live_hindi_and_kannada_tts():
    s = Settings()
    tts = TimbreTTS(s)
    assert tts.synthesize("नमस्ते, कृपया थोड़ा रुकिए।", "hi").ok
    assert tts.synthesize("ನಮಸ್ಕಾರ, ದಯವಿಟ್ಟು ಸ್ವಲ್ಪ ಕಾಯಿರಿ.", "kn").ok
