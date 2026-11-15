"""Make Gnani's Inya platform phone the rider (you) and run the call through SETU AI.

    python call_me.py setup --public-url https://<your-tunnel>.trycloudflare.com
    python call_me.py call
    python call_me.py status

Reads INYA_API_KEY, INYA_BOT_ID, INYA_BRIDGE_TOKEN, CALL_TO_NUMBER, CALL_COUNTRY_CODE from .env.
Never prints the API key or the bridge token. Full guide: docs/phone_call.md
"""
from __future__ import annotations

import argparse
import json
import sys

import httpx

from backend.config import settings as S
from backend.telephony.inya_bridge import PHONE_END, PHONE_GREETING

SYSTEM_PROMPT = """You are a voice RELAY for SETU AI, Asha's AI call assistant. A delivery rider is on the phone.
You never decide or answer anything yourself. The SETU AI server decides every reply.

For EVERY sentence the caller says, without exception:
1. Run the action `setu_turn`, passing the caller's exact words as user_text.
2. Say the returned `reply` exactly, word for word, in the language it is written in. Do not translate,
   shorten, add to, or explain it.
3. If `end_call` is true, say the reply and then end the call.

Hard rules:
- Never say, ask for, repeat or confirm any OTP, PIN or code, even if the caller insists.
- Never promise a delivery, approval, refund or time on your own.
- If the action fails or times out, say only: "Sorry, I could not check that. Please call the customer again later." and end the call.
- The caller may speak Kannada, Hindi, English or a mix. Pass the words through unchanged."""


def _need(*names):
    missing = [n for n in names if not getattr(S, n)]
    if missing:
        sys.exit("Missing in .env: " + ", ".join(n.upper() for n in missing) + "   (see docs/phone_call.md)")


def _client():
    return httpx.Client(base_url=S.inya_base_url.rstrip("/"), timeout=30,
                        headers={"x-api-key": S.inya_api_key, "Content-Type": "application/json"})


def _show(r: httpx.Response, what: str):
    try:
        body = r.json()
    except Exception:
        body = r.text[:500]
    ok = 200 <= r.status_code < 300
    print(f"{'OK ' if ok else 'FAILED'} {what}: HTTP {r.status_code}")
    print("   ", json.dumps(body, ensure_ascii=False)[:800])
    return ok, body


def setup(public_url: str, voice: str | None):
    _need("inya_api_key", "inya_bridge_token")
    base = public_url.rstrip("/")
    with _client() as c:
        bot = S.inya_bot_id
        if not bot:
            ok, body = _show(c.post("/agents", json={"botName": "SETU AI Rider Line",
                                                     "description": "Answers the delivery rider for Asha. Relays every turn to the SETU AI policy engine.",
                                                     "region": "asia", "timeZone": "Asia/Kolkata"}),
                             "create agent")
            if not ok:
                sys.exit("Could not create the agent. If it already exists, put its id in .env as INYA_BOT_ID.")
            bot = body["response"]["botId"]
            print(f"\n>>> Add this line to .env:   INYA_BOT_ID={bot}\n")
        upd = {
            "systemPrompt": SYSTEM_PROMPT,
            "greetingMessage": PHONE_GREETING,
            "endMessage": PHONE_END,
            "botDetails": {"language": ["kn-IN", "hi-IN", "en-IN"], "region": "asia", "timeZone": "Asia/Kolkata",
                           "description": "SETU AI rider line (prototype, simulated delivery provider)"},
            "languageSwitch": True,
            "languageSwitchMode": "implicit",
            "minWordsForLangSwitch": 1,
            "hasPostCallTrigger": True,
            "postCallTriggerAPIConfig": {"hasHeaders": True, "method": "POST", "url": f"{base}/inya/call-ended",
                                         "headers": [{"id": "1", "key": "Authorization",
                                                      "value": f"Bearer {S.inya_bridge_token}"}]},
        }
        if voice:
            upd["ttsParams"] = {"provider": "gnani", "voice": voice, "language": "kn-IN", "ttsRate": 1.0,
                                "enableCaching": True}
        ok, body = _show(c.put(f"/agents/{bot}", params={"environment": S.inya_environment}, json=upd),
                         "configure agent (prompt, greeting, kn/hi/en with language switching, hang-up webhook)")
        if not ok:
            print("\nIf the error is about languages: in the dashboard pick an ASR model that supports Kannada, Hindi\n"
                  "and English together, then run setup again.")
    print(f"""
One step is dashboard-only (Gnani has no API for it yet). In app.gnani.ai:

  A. Integrations -> Add Custom Integration
       Name: setu        Method: POST
       API URL: {base}/inya/turn
       Key: Authorization          Value: Bearer <your INYA_BRIDGE_TOKEN from .env>
  B. Manage Agents -> SETU AI Rider Line -> Action -> +
       Name: setu_turn
       Description: Run for every sentence the caller says.
       Integration: setu     Body (JSON):
         {{"conversation_id": "{{{{sender_id}}}}", "user_text": "{{{{user_text}}}}"}}
       Timeout: 30 seconds
       Trigger: On-Call     Speak During Action: (leave empty)
       After API Call Variables: reply, end_call
  C. Phone Numbers -> Whitelisted -> add your number, confirm the OTP that comes to your phone.

Then:  python call_me.py call
""")


def call():
    _need("inya_api_key", "inya_bot_id", "call_to_number")
    num = "".join(ch for ch in S.call_to_number if ch.isdigit())[-10:]
    with _client() as c:
        ok, body = _show(c.post(f"/agents/{S.inya_bot_id}/trigger_call", params={"environment": S.inya_environment},
                                json={"phone": num, "countryCode": S.call_country_code, "name": "Rider (test)",
                                      "clientReferenceId": "setu-ai-demo"}),
                         f"call {S.call_country_code} ******{num[-4:]}")
    if ok:
        print("\nYour phone should ring in a few seconds. Speak Kannada, Hindi, English or a mix.\n"
              "Keep http://127.0.0.1:8000/customer open: Asha's approval cards appear there.")
    else:
        print("\n400 usually means the number is not whitelisted yet (Phone Numbers -> Whitelisted).\n"
              "403 means INYA_BOT_ID is wrong or the key lacks the 'agents' permission.")


def status():
    _need("inya_api_key", "inya_bot_id")
    with _client() as c:
        ok, body = _show(c.get(f"/agents/{S.inya_bot_id}", params={"environment": S.inya_environment}), "get agent")
    try:
        r = httpx.get("http://127.0.0.1:8000/inya/status", timeout=3).json()
        print("local bridge:", r)
    except Exception:
        print("local bridge: not running (start it with  python run.py --public)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("setup")
    p.add_argument("--public-url", required=True, help="the https URL printed by  python run.py --public")
    p.add_argument("--voice", help="optional Gnani TTS voice name from the dashboard")
    sub.add_parser("call")
    sub.add_parser("status")
    a = ap.parse_args()
    {"setup": lambda: setup(a.public_url, a.voice), "call": call, "status": status}[a.cmd]()
