"""Every scenario on the call screen, played through the HTTP API in Hindi, Kannada and English.

The scenario list lives in frontend/scenarios.json so the UI and the tests can never drift apart.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app

SCEN = json.loads((Path(__file__).resolve().parents[2] / "frontend" / "scenarios.json").read_text(encoding="utf-8"))
CASES = [(sc, lang) for sc in SCEN["scenarios"] for lang in ("hi", "kn", "en")]


@pytest.fixture(scope="module")
def app_client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("scen")
    s = Settings()
    s.mock_voice, s.gnani_api_key, s.evon_mode = True, "", "off"
    s.db_path, s.phrase_cache_dir = str(tmp / "s.db"), str(tmp / "cache")
    app = create_app(s)
    with TestClient(app) as c:
        yield c, app


def test_every_group_has_scenarios():
    groups = {sc["group"] for sc in SCEN["scenarios"]}
    assert groups == set(SCEN["groups"])
    assert len(SCEN["scenarios"]) >= 20


@pytest.mark.parametrize("sc,lang", CASES, ids=[f"{sc['id']}-{lang}" for sc, lang in CASES])
def test_scenario(app_client, sc, lang):
    c, app = app_client
    c.put("/customers/CUST_001/preferences", json={"allow_guard": False, "allow_neighbor": False,
                                                    **sc.get("rules", {})})
    c.post("/mock-provider/mode", json={"mode": sc.get("provider_mode", "accept")})
    start = c.post("/calls/start", json={"order_id": sc["order"], "language": lang}).json()
    call = start["call_id"]
    assert start["greeting_langs"] == [lang] and start["audio_url"]
    out = None
    for step in sc["steps"]:
        exp = step["expect"]
        if "say" in step:
            text = step["say"][lang]
            r = c.post(f"/calls/{call}/audio", files={"audio": ("clip.webm", b"x", "audio/webm")},
                       data={"mock_transcript": text})
            assert r.status_code == 200, r.text
            out = r.json()
            assert out["language"] == lang, (text, out["language"])
            if exp.get("redacted"):
                assert "739214" not in json.dumps(out, ensure_ascii=False) and "[REDACTED]" in out["transcript"]
        elif "customer" in step:
            apr = [a for a in c.get("/approvals/pending").json() if a["call_id"] == call]
            assert len(apr) == 1
            if step["customer"] == "no_answer":
                agent = app.state.agent
                agent.approvals.clock = lambda: 9e12   # jump past the expiry
                try:
                    res = agent.expire_due()
                finally:
                    agent.approvals.clock = __import__("time").time
                out = next(x for x in res if x.call_id == call).to_dict()
            else:
                r = c.post(f"/approvals/{apr[0]['id']}/decide", json={"decision": step["customer"], "token": apr[0]["token"]})
                assert r.status_code == 200, r.text
                out = r.json()
        elif step.get("hangup"):
            out = c.post(f"/calls/{call}/end").json()
            assert c.get("/approvals/pending").json() == [] or all(
                a["call_id"] != call for a in c.get("/approvals/pending").json())
        if "action" in exp:
            assert out["decision"]["action"] == exp["action"], (sc["id"], lang, out.get("transcript"), out["decision"])
        if "reply" in exp:
            assert out["reply_key"] == exp["reply"], (sc["id"], lang, out.get("transcript"), out["reply_key"])
            assert out["reply_text"] and out.get("spoken_lang", lang) in ("hi", "kn", "en")
        if exp.get("ended"):
            assert out["ended"] is True
            assert c.post(f"/calls/{call}/text", json={"text": "hello"}).status_code == 409
        if "customer_message" in exp:
            assert c.get(f"/calls/{call}").json()["customer_message"]["key"] == exp["customer_message"]
    info = c.get(f"/calls/{call}").json()
    assert info["chain_ok"] and info["simulated"]
    assert info["highest_evidence"] != "provider_accepted" or any(
        s.get("expect", {}).get("customer_message") == "handover_provider_accepted" for s in sc["steps"])


def test_hangup_then_late_approval_does_nothing(app_client):
    c, _ = app_client
    c.post("/mock-provider/mode", json={"mode": "accept"})
    c.put("/customers/CUST_001/preferences", json={"allow_guard": False, "allow_neighbor": False})
    call = c.post("/calls/start", json={"order_id": "ORD_1024"}).json()["call_id"]
    c.post(f"/calls/{call}/text", json={"text": "guard ko de doon?"})
    apr = [a for a in c.get("/approvals/pending").json() if a["call_id"] == call][0]
    c.post(f"/calls/{call}/end")
    late = c.post(f"/approvals/{apr['id']}/decide", json={"decision": "approve", "token": apr["token"]})
    assert late.status_code == 409
    levels = {e["evidence_level"] for e in c.get("/orders/ORD_1024/ledger").json()["events"] if e["call_id"] == call}
    assert "provider_accepted" not in levels and "customer_approved" not in levels


def test_bye_while_waiting_ends_and_closes_approval(app_client):
    c, _ = app_client
    c.post("/mock-provider/mode", json={"mode": "accept"})
    call = c.post("/calls/start", json={"order_id": "ORD_1024", "language": "hi"}).json()["call_id"]
    c.post(f"/calls/{call}/text", json={"text": "padosi ko de doon?"})
    out = c.post(f"/calls/{call}/text", json={"text": "theek hai, thank you"}).json()
    assert out["ended"] and out["reply_key"] == "goodbye"
    assert c.get(f"/calls/{call}").json()["customer_message"]["key"] == "call_ended_unresolved"


def test_speaking_while_waiting_gets_holding_line(app_client):
    c, _ = app_client
    call = c.post("/calls/start", json={"order_id": "ORD_1024"}).json()["call_id"]
    c.post(f"/calls/{call}/text", json={"text": "guard ko de doon?"})
    out = c.post(f"/calls/{call}/text", json={"text": "hello? kitna time lagega?"}).json()
    assert out["reply_key"] == "holding"
    c.post(f"/calls/{call}/end")


def test_noise_only_clip_is_not_a_turn(app_client):
    c, _ = app_client
    call = c.post("/calls/start", json={"order_id": "ORD_1024"}).json()["call_id"]
    r = c.post(f"/calls/{call}/audio", files={"audio": ("clip.webm", b"x", "audio/webm")},
               data={"mock_transcript": "#lang=hi\n "}).json()
    assert r.get("heard_nothing") is True
    events = [e["event_type"] for e in c.get("/orders/ORD_1024/ledger").json()["events"] if e["call_id"] == call]
    assert "rider_utterance" not in events and "stt_failed" not in events
