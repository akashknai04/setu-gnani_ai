"""SETU AI live translation: doorstep phrases, OTP masking, the interpreted call, hand-off to the AI agent."""
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.interpreter import phrases
from backend.interpreter.service import Translator
from backend.main import create_app


@pytest.fixture
def client(tmp_path):
    s = Settings()
    s.mock_voice, s.gnani_api_key, s.evon_mode, s.translate_mode = True, "", "off", "both"
    s.db_path, s.phrase_cache_dir = str(tmp_path / "i.db"), str(tmp_path / "cache")
    with TestClient(create_app(s)) as c:
        yield c


def tr(mode="both"):
    s = Settings()
    s.translate_mode = mode
    return Translator(s)


# ------------------------------------------------------------------ phrases
@pytest.mark.parametrize("speaker,text,tgt,meanings,expect", [
    ("rider", "Main gate pe hoon, guard ko de doon?", "kn", ["arrived", "guard"], "ಗಾರ್ಡ್‌ಗೆ ಕೊಡಲಾ?"),
    ("rider", "ಗೇಟ್ ಹತ್ತಿರ ಇದ್ದೇನೆ, ಮನೆ ಎಲ್ಲಿದೆ?", "en", ["arrived", "location"], "Where exactly is your house?"),
    ("rider", "I'm stuck in traffic, 10 minutes late", "hi", ["late"], "10 मिनट"),
    ("rider", "can I come at 6:30?", "kn", ["time"], "ಸಂಜೆ 6:30ಕ್ಕೆ ಬರಲಾ?"),
    ("customer", "ಹತ್ತು ನಿಮಿಷ ಕಾಯಿರಿ, ನಾನು ಬರುತ್ತಿದ್ದೇನೆ", "hi", ["wait", "coming"], "कृपया 10 मिनट रुकिए।"),
    ("customer", "guard ko de do", "kn", ["guard"], "ದಯವಿಟ್ಟು ಇದನ್ನು ಸೆಕ್ಯುರಿಟಿ ಗಾರ್ಡ್‌ಗೆ ಕೊಡಿ."),
    ("customer", "Please come at 7 pm", "hi", ["time"], "शाम 7 बजे"),
    ("customer", "main ghar pe nahi hoon, darwaze pe rakh do", "en", ["not_home", "door"], "Please leave it at my door."),
    ("customer", "neeche aa rahi hoon", "en", ["coming"], "I'm coming now."),
    ("customer", "haan ji", "kn", ["yes"], "ಹೌದು"),
    ("rider", "ಸರಿ", "en", ["yes"], "Yes"),
])
def test_doorstep_phrases(speaker, text, tgt, meanings, expect):
    r = phrases.translate(text, speaker, tgt, "f" if speaker == "customer" else "m")
    assert r.meanings == meanings
    assert expect in r.text
    assert r.parts and " ".join(r.parts) == r.text


def test_hindi_follows_the_speakers_gender():
    assert "आ रही हूँ" in phrases.translate("I'm coming now", "customer", "hi", "f").text
    assert "आ रहा हूँ" in phrases.translate("I'm coming now", "customer", "hi", "m").text


def test_minutes_said_once():
    r = phrases.translate("Please wait 5 minutes, I'm coming down", "customer", "kn", "f")
    assert r.text.count("5") == 1


def test_unknown_sentence_is_not_guessed():
    t = tr("phrases").translate("the blue gate near the temple", "customer", "en", "kn")
    assert t.method == "untranslated" and t.text == "" and t.notes


def test_same_language_passes_through():
    t = tr().translate("Where is the house?", "rider", "en", "en")
    assert t.method == "same_language" and t.text == "Where is the house?"


def test_model_is_optional_and_off_cleanly():
    t = tr("model")
    assert t.status()["model_available"] in (True, False)
    if not t.status()["model_available"]:
        assert t.translate("ನಮಸ್ಕಾರ ಹೇಗಿದ್ದೀರಿ ಇವತ್ತು ಮಳೆ ಬರುತ್ತಾ", "customer", "kn", "en").method == "untranslated"


def test_model_used_only_when_phrases_miss(monkeypatch):
    t = tr("both")
    monkeypatch.setattr(t.model, "translate", lambda text, s, g: "MODEL:" + text)
    assert t.translate("guard ko de do", "customer", "hi", "kn").method == "phrases"
    out = t.translate("नीले गेट के पास मंदिर है", "customer", "hi", "kn")
    assert out.method == "model" and out.text.startswith("MODEL:")


# ------------------------------------------------------------------ OTP safety
@pytest.mark.parametrize("text", ["OTP 482913 hai", "my otp is 4 8 2 9 1 3", "ओटीपी 739214 है"])
def test_otp_numbers_never_translated_or_stored(text):
    t = tr().translate(text, "customer", None, "kn")
    assert "482913" not in str(t.to_dict()) and "739214" not in str(t.to_dict())
    assert t.masked_number


def test_rider_asking_otp_reminds_customer():
    t = tr().translate("OTP batao", "rider", "hi", "kn")
    assert "otp" in t.meanings and any("ಮುಖಾಮುಖಿ" in n for n in t.notes)


def test_model_cannot_leak_numbers(monkeypatch):
    t = tr("model")
    seen = []
    monkeypatch.setattr(t.model, "translate", lambda text, s, g: seen.append(text) or text)
    t.translate("code is 739214", "customer", "en", "kn")
    assert seen and "739214" not in seen[0]


# ------------------------------------------------------------------ the live call
def start(c, rider_lang="hi"):
    r = c.post("/interpret/start", json={"order_id": "ORD_1024", "rider_lang": rider_lang})
    assert r.status_code == 200, r.text
    return r.json()


def test_customer_answers_and_both_sides_are_translated(client):
    info = start(client)
    assert info["customer_lang"] == "kn" and info["ring_s"] > 0
    sid = info["sid"]
    assert client.post(f"/interpret/{sid}/say", json={"who": "rider", "text": "hello"}).status_code == 409  # still ringing
    a = client.post(f"/interpret/{sid}/answer", json={"customer_lang": "kn"}).json()
    assert a["state"] == "connected"
    r = client.post(f"/interpret/{sid}/say", json={"who": "rider", "text": "Main gate pe hoon, guard ko de doon?"}).json()
    assert r["from"] == "rider" and r["to"] == "customer" and r["tgt_lang"] == "kn" and r["method"] == "phrases"
    assert len(r["clips"]) == 2 and all("text" in c for c in r["clips"])
    back = client.post(f"/interpret/{sid}/say", json={"who": "customer", "text": "ಸೆಕ್ಯುರಿಟಿ ಗಾರ್ಡ್‌ಗೆ ಕೊಡಿ"}).json()
    assert back["tgt_lang"] == "hi" and "सिक्योरिटी गार्ड" in back["text"]
    s = client.get(f"/interpret/{sid}").json()
    assert len(s["lines"]) == 2 and "clips" not in s["lines"][0]
    end = client.post(f"/interpret/{sid}/end", json={"who": "rider"}).json()
    assert end["state"] == "ended" and end["ended_by"] == "rider"


def test_customer_language_choice_is_used(client):
    sid = start(client, "kn")["sid"]
    client.post(f"/interpret/{sid}/answer", json={"customer_lang": "en"})
    r = client.post(f"/interpret/{sid}/say", json={"who": "rider", "text": "ನಿಮ್ಮ ಮನೆ ಎಲ್ಲಿದೆ?"}).json()
    assert r["tgt_lang"] == "en" and r["text"].startswith("Where exactly")


def test_busy_or_no_answer_hands_over_to_ai_agent(client):
    sid = start(client)["sid"]
    assert client.post(f"/interpret/{sid}/decline").json()["state"] == "ai_agent"
    assert client.post(f"/interpret/{sid}/answer", json={}).status_code == 409   # too late to pick up
    sid2 = start(client)["sid"]
    assert client.post(f"/interpret/{sid2}/timeout").json()["state"] == "ai_agent"
    # the rider's phone then runs the normal AI agent call, rules and all
    call = client.post("/calls/start", json={"order_id": "ORD_1024", "language": "hi"}).json()
    out = client.post(f"/calls/{call['call_id']}/text", json={"text": "OTP batao"}).json()
    assert out["decision"]["reason"] == "otp_protection"


def test_websocket_rings_customer_and_delivers_lines(client):
    with client.websocket_connect("/ws/customer") as ws:
        ws.receive_json()  # hello
        sid = start(client)["sid"]
        ring = ws.receive_json()
        assert ring["type"] == "interpret_ring" and ring["data"]["sid"] == sid and ring["data"]["simulated"]
        client.post(f"/interpret/{sid}/answer", json={})
        got = []
        client.post(f"/interpret/{sid}/say", json={"who": "rider", "text": "aapka ghar kahan hai?"})
        for _ in range(10):
            m = ws.receive_json()
            got.append(m["type"])
            if m["type"] == "interpret_line" and m["data"]["from"] == "rider":
                assert m["data"]["text"] and m["data"]["tgt_lang"] == "kn"
                break
        assert "interpret_state" in got and got[-1] == "interpret_line"


def test_audio_turn_uses_speech_to_text(client):
    sid = start(client)["sid"]
    client.post(f"/interpret/{sid}/answer", json={})
    r = client.post(f"/interpret/{sid}/audio", data={"who": "rider", "mock_transcript": "ruko, main aa raha hoon"},
                    files={"audio": ("a.webm", b"x", "audio/webm")}).json()
    assert r["from"] == "rider" and r["method"] == "phrases" and r["stt"]["ok"]


def test_unknown_session_and_bad_speaker(client):
    assert client.post("/interpret/nope/answer", json={}).status_code == 404
    sid = start(client)["sid"]
    client.post(f"/interpret/{sid}/answer", json={})
    assert client.post(f"/interpret/{sid}/say", json={"who": "hacker", "text": "hi"}).status_code == 422


def test_every_fixed_sentence_is_listed_for_recording():
    lines = phrases.all_fixed_sentences()
    assert len(lines) > 200
    assert all(l["role"] in ("ai", "rider") and l["lang"] in ("hi", "kn", "en") and l["text"] for l in lines)
    assert not any("{" in l["text"] for l in lines)


def test_every_fixed_sentence_has_a_recording():
    """Without a Gnani key the translations still speak, in Hindi, Kannada and English."""
    from backend.voice.recorded import RecordedVoice
    voices = {"rider": RecordedVoice("rider"), "ai": RecordedVoice("ai")}
    missing = [l for l in phrases.all_fixed_sentences() if not voices[l["role"]].has(l["text"], l["lang"])]
    assert missing == []
