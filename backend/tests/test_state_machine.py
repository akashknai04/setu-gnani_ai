import pytest

from backend.engine.policy import Decision, Order, Prefs, evaluate
from backend.engine.state_machine import CallSession, InvalidTransition, PermitDenied, ProviderPermit, State
from backend.providers.mock_delivery import MockDeliveryProvider

OPEN = Order("ORD_1024", True, "out_for_delivery", False)
PREFS = Prefs("18:00", "20:00")


def _to_policy(s):
    s.transition(State.LISTENING)
    s.transition(State.POLICY_CHECK)
    return s


def test_happy_path():
    s = _to_policy(CallSession("c1", "ORD_1024"))
    s.apply_decision(evaluate("ask_availability", PREFS, OPEN))
    assert s.state == State.INSTANT_ACTION
    s.transition(State.REPLY_AND_RECORD)
    s.transition(State.LISTENING)


@pytest.mark.parametrize("frm,to", [
    (State.GREETING, State.POLICY_CHECK),
    (State.LISTENING, State.INSTANT_ACTION),
    (State.LISTENING, State.REPLY_AND_RECORD),
    (State.ESCALATED, State.INSTANT_ACTION),
    (State.REPLY_AND_RECORD, State.POLICY_CHECK),
    (State.INSTANT_ACTION, State.WAITING_APPROVAL),
])
def test_invalid_transitions_raise(frm, to):
    with pytest.raises(InvalidTransition):
        CallSession("c", "o", frm).transition(to)


def test_decision_only_applies_in_policy_check():
    s = CallSession("c", "ORD_1024", State.LISTENING)
    with pytest.raises(InvalidTransition):
        s.apply_decision(Decision("instant_action", "x"))


def test_approval_reenters_policy_check():
    s = _to_policy(CallSession("c", "ORD_1024"))
    s.apply_decision(evaluate("guard_drop_request", PREFS, OPEN))
    assert s.state == State.WAITING_APPROVAL
    s.transition(State.POLICY_CHECK)
    s.apply_decision(evaluate("guard_drop_request", PREFS, OPEN, "approved", {"guard_drop_request"}))
    assert s.state == State.INSTANT_ACTION


# ---- "provider request impossible without policy permission" -------------

def test_provider_rejects_call_without_permit():
    p = MockDeliveryProvider("accept")
    with pytest.raises(PermitDenied):
        p.request(None, "guard_drop_request")
    with pytest.raises(PermitDenied):
        p.request("forged", "guard_drop_request")


def test_permit_cannot_be_constructed_directly():
    with pytest.raises(PermitDenied):
        ProviderPermit(object(), call_id="c", order_id="o", reason="x")


def test_no_permit_when_policy_waits_for_approval():
    s = _to_policy(CallSession("c", "ORD_1024"))
    d = evaluate("guard_drop_request", PREFS, OPEN)
    s.apply_decision(d)
    with pytest.raises(PermitDenied):
        s.authorize_provider(d, OPEN)


def test_no_permit_for_non_provider_instant_action():
    s = _to_policy(CallSession("c", "ORD_1024"))
    d = evaluate("ask_address", PREFS, OPEN)
    s.apply_decision(d)
    with pytest.raises(PermitDenied):
        s.authorize_provider(d, OPEN)


def test_no_permit_for_decision_not_from_this_policy_check():
    s = _to_policy(CallSession("c", "ORD_1024"))
    s.apply_decision(evaluate("ask_address", PREFS, OPEN))
    forged = Decision("instant_action", "guard_customer_approved", provider_request=True)
    with pytest.raises(PermitDenied):
        s.authorize_provider(forged, OPEN)


def test_no_permit_for_invalid_or_other_order():
    s = _to_policy(CallSession("c", "ORD_1024"))
    d = evaluate("guard_drop_request", PREFS, OPEN, "approved")
    s.apply_decision(d)
    with pytest.raises(PermitDenied):
        s.authorize_provider(d, Order("ORD_1024", True, "delivered", False))
    with pytest.raises(PermitDenied):
        s.authorize_provider(d, Order("ORD_7777", True, "out_for_delivery", False))


def test_permit_is_single_use():
    s = _to_policy(CallSession("c", "ORD_1024"))
    d = evaluate("guard_drop_request", PREFS, OPEN, "approved")
    s.apply_decision(d)
    permit = s.authorize_provider(d, OPEN)
    p = MockDeliveryProvider("accept")
    assert p.request(permit, "guard_drop_request").accepted
    with pytest.raises(PermitDenied):
        p.request(permit, "guard_drop_request")


@pytest.mark.parametrize("mode,status", [("accept", "accepted"), ("reject", "rejected"),
                                         ("unavailable", "unavailable"), ("invalid", "invalid")])
def test_provider_modes_always_simulated(mode, status):
    s = _to_policy(CallSession("c", "ORD_1024"))
    d = evaluate("guard_drop_request", PREFS, OPEN, "approved")
    s.apply_decision(d)
    r = MockDeliveryProvider(mode).request(s.authorize_provider(d, OPEN), "guard_drop_request")
    assert r.status == status and r.simulated is True
