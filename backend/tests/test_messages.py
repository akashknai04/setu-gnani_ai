import re

import pytest

from backend.engine import messages as M

FORBIDDEN = re.compile(r"arriving|will arrive|has been delivered|was delivered|is delivered|on its way|confirmed for",
                       re.IGNORECASE)


def test_every_rider_template_has_three_languages():
    for key, by_lang in M.RIDER.items():
        assert set(by_lang) == {"hi", "kn", "en"}, key


def test_every_customer_template_has_en_and_kn():
    for key, by_lang in M.CUSTOMER.items():
        assert set(by_lang) == {"en", "kn"}, key


def test_no_template_makes_unproven_delivery_claims():
    for table in (M.RIDER, M.CUSTOMER):
        for key, by_lang in table.items():
            assert not FORBIDDEN.search(by_lang["en"]), key


def test_spec_example_claims_render():
    assert M.customer_message("rider_agreed_time", time="18:00")["en"] == (
        "The rider agreed to attempt delivery at 6 PM. The delivery platform has not confirmed a new slot.")
    assert M.customer_message("handover_provider_accepted", who="guard")["en"] == (
        "Your security guard handover was approved. The simulated delivery provider accepted the request. "
        "Delivery completion has not yet been recorded.")
    assert M.customer_message("otp_refused")["en"] == (
        "The rider asked for an OTP. The agent refused. Nothing was shared or confirmed.")


def _ev(level, key=None, slots=None):
    d = {}
    if key:
        d = {"customer_message": key, "slots": slots or {}}
    return {"evidence_level": level, "detail": d}


def test_provider_claim_downgraded_without_provider_evidence():
    events = [_ev("customer_approved"), _ev("info", "handover_provider_accepted", {"who": "guard"})]
    out = M.select_customer_message(events)
    assert out["key"] == M.SAFE_FALLBACK and out["downgraded"]


def test_provider_claim_allowed_with_evidence():
    events = [_ev("customer_approved"), _ev("provider_accepted"),
              _ev("info", "handover_provider_accepted", {"who": "guard"})]
    out = M.select_customer_message(events)
    assert out["key"] == "handover_provider_accepted" and "accepted the request" in out["en"]


@pytest.mark.parametrize("key,need", list(M.CUSTOMER_REQUIRES.items()))
def test_each_evidence_gated_template_is_gated(key, need):
    out = M.select_customer_message([_ev("info", key, {"time": "18:30", "who": "guard"})])
    assert out["downgraded"]
    out = M.select_customer_message([_ev(need), _ev("info", key, {"time": "18:30", "who": "guard"})])
    assert out["key"] == key


def test_time_formatting():
    assert M.fmt_time("18:30") == "6:30 PM" and M.fmt_time("09:00") == "9 AM" and M.fmt_time("00:15") == "12:15 AM"
    assert M.fmt_window("18:00", "20:00") == "6 PM – 8 PM"


def test_rider_reply_localizes_who():
    assert "गार्ड" in M.rider_reply("handover_ok", "hi", who="guard")
    assert "ಸೆಕ್ಯುರಿಟಿ" in M.rider_reply("handover_ok", "kn", who="guard")


def test_fixed_phrases_for_cache_have_no_unfilled_slots():
    phrases = M.all_fixed_rider_phrases("6 PM – 8 PM", "Area", "Landmark")
    assert phrases and all("{" not in text for _, _, text in phrases)


def test_approval_request_label_is_localized():
    m = M.customer_message("approval_requested", request_intent="guard_drop_request", time=None)
    assert "security guard" in m["en"] and "ಸೆಕ್ಯುರಿಟಿ ಗಾರ್ಡ್" in m["kn"] and "leave the order" not in m["kn"]
    m = M.customer_message("approval_requested", request_intent="propose_time", time="21:00")
    assert "9 PM" in m["en"] and "9 PM" in m["kn"]
