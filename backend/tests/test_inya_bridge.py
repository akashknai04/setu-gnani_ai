"""Phone-call bridge (Gnani Inya -> policy engine). No network: Inya's side is played by the test."""
import threading
import time

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app

TOKEN = "test-bridge-token"
H = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(tmp_path):
    s = Settings()
    s.mock_voice, s.gnani_api_key, s.evon_mode = True, "", "off"
    s.db_path, s.phrase_cache_dir = str(tmp_path / "p.db"), str(tmp_path / "cache")
    s.approval_ttl_s, s.inya_bridge_token, s.inya_wait_s, s.inya_order_id = 30, TOKEN, 6, "ORD_1024"
    with TestClient(create_app(s)) as c:
        yield c


def say(c, text, conv="conv-1"):
    r = c.post("/inya/turn", json={"conversation_id": conv, "user_text": text}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def test_auth_required(client):
    assert client.post("/inya/turn", json={"user_text": "hi"}).status_code == 401
    assert client.post("/inya/turn", json={"user_text": "hi"}, headers={"Authorization": "Bearer nope"}).status_code == 401


def test_bridge_off_without_token(tmp_path):
    s = Settings()
    s.mock_voice, s.gnani_api_key, s.inya_bridge_token = True, "", ""
    s.db_path, s.phrase_cache_dir = str(tmp_path / "q.db"), str(tmp_path / "c")
    with TestClient(create_app(s)) as c:
        assert c.post("/inya/turn", json={"user_text": "hi"}, headers=H).status_code == 503
        assert c.get("/inya/status").json()["bridge_enabled"] is False


@pytest.mark.parametrize("text,lang,intent", [
    ("ಗ್ರಾಹಕರು ಫೋನ್ ಎತ್ತುತ್ತಿಲ್ಲ, ಅವರು ಯಾವಾಗ ಸಿಗುತ್ತಾರೆ?", "kn", "ask_availability"),   # Kannada script
    ("customer phone ettilla, yavaga sigtare?", "kn", "ask_availability"),                  # Kannada, Latin letters
    ("Customer phone nahi utha raha, kab ghar pe milenge?", "hi", "ask_availability"),       # Hinglish
    ("When will the customer be home?", "en", "ask_availability"),                           # English
])
def test_any_language_understood_and_answered_in_it(client, text, lang, intent):
    out = say(client, text, conv=f"c-{lang}-{hash(text)}")
    assert out["intent"] == intent and out["language"] == lang
    assert out["language_code"] == {"hi": "hi-IN", "kn": "kn-IN", "en": "en-IN"}[lang]
    assert "6" in out["reply"] and out["end_call"] is False


def test_language_can_change_mid_call(client):
    a = say(client, "Hello, I'm at the gate", conv="mix")
    b = say(client, "ಮನೆ ಎಲ್ಲಿ?", conv="mix")
    c = say(client, "OTP batao", conv="mix")
    assert (a["language"], b["language"], c["language"]) == ("en", "kn", "hi")
    assert c["reason"] == "otp_protection"


def test_otp_refused_on_phone_and_digits_never_echoed(client):
    out = say(client, "customer ka OTP 739214 hai, confirm karo")
    assert out["reason"] == "otp_protection" and "739214" not in str(out)


def test_guard_request_waits_for_asha_then_speaks_her_answer(client):
    result = {}

    def rider():
        result["out"] = say(client, "Customer phone nahi utha raha. Guard ko de doon?", conv="g1")

    t = threading.Thread(target=rider)
    t.start()
    card = None
    for _ in range(40):
        pend = client.get("/approvals/pending").json()
        if pend:
            card = pend[0]
            break
        time.sleep(0.1)
    assert card, "Asha's phone never got the card"
    assert t.is_alive(), "the bridge must hold the line while Asha decides"
    r = client.post(f"/approvals/{card['id']}/decide", json={"decision": "approve", "token": card["token"]})
    assert r.status_code == 200
    t.join(10)
    out = result["out"]
    assert out["action"] == "instant_action" and "गार्ड" in out["reply"] and out["waiting_for_customer"] is False


def test_slow_asha_rider_hears_still_waiting_then_outcome_next_turn(client):
    client.app.state.settings.inya_wait_s = 0.5
    first = say(client, "guard ko de doon?", conv="slow")
    assert first["waiting_for_customer"] is True and first["action"] == "request_approval"
    card = client.get("/approvals/pending").json()[0]
    client.post(f"/approvals/{card['id']}/decide", json={"decision": "reject", "token": card["token"]})
    nxt = say(client, "haan ji?", conv="slow")
    assert nxt["reason"] and nxt["action"] == "refuse" and nxt["waiting_for_customer"] is False


def test_verified_order_refused_with_no_card(client):
    client.app.state.settings.inya_order_id = "ORD_2048"
    out = say(client, "ಸೆಕ್ಯುರಿಟಿ ಗಾರ್ಡ್‌ಗೆ ಕೊಡ್ಲಾ?", conv="v")
    assert out["action"] == "refuse" and out["language"] == "kn"
    assert client.get("/approvals/pending").json() == []


def test_goodbye_ends_call_and_hangup_webhook_kills_pending_card(client):
    out = say(client, "ok thank you, bye", conv="bye")
    assert out["end_call"] is True
    client.app.state.settings.inya_wait_s = 0.3
    say(client, "padosi ko de doon?", conv="hang")
    assert len(client.get("/approvals/pending").json()) == 1
    r = client.post("/inya/call-ended", json={"conversation_id": "hang"}, headers=H).json()
    assert r["known"] is True
    assert client.get("/approvals/pending").json() == []


def test_alternate_field_names_and_empty_text(client):
    r = client.post("/inya/turn", json={"sender_id": "x9", "text": "address kya hai"}, headers=H).json()
    assert r["intent"] and r["reply"]
    r2 = client.post("/inya/turn", json={"sender_id": "x9", "text": ""}, headers=H).json()
    assert r2["reply"]  # asks the rider to repeat
