import pytest

from backend.engine.policy import (APPROVED, CONTACT_LATER, EXPIRED, REJECTED, Decision, Order, Prefs,
                                   evaluate, in_window)

PREFS = Prefs("18:00", "20:00", allow_guard=False, allow_neighbor=False)
OPEN = Order("ORD_1024", True, "out_for_delivery", requires_otp=False)
VERIFIED = Order("ORD_2048", True, "out_for_delivery", requires_otp=True)
CAPS = frozenset({"guard_drop_request", "neighbor_drop_request"})


def test_invalid_order_escalates_for_every_intent():
    for o in (Order("X", False, "unknown", False), Order("ORD_9", True, "delivered", False)):
        for intent in ("ask_availability", "guard_drop_request", "request_otp", "propose_time"):
            assert evaluate(intent, PREFS, o, time="18:30").action == "escalate"


def test_order_valid_is_not_requires_otp():
    assert VERIFIED.order_valid is True and VERIFIED.requires_otp is True
    assert Order("X", True, "delivered", False).order_valid is False


@pytest.mark.parametrize("approval", ["none", APPROVED, REJECTED, EXPIRED, CONTACT_LATER])
def test_otp_always_refused_even_if_approved(approval):
    for intent in ("request_otp", "share_otp"):
        d = evaluate(intent, PREFS, OPEN, approval)
        assert d.action == "refuse" and d.reason == "otp_protection"
        assert d.customer_approvable is False and d.provider_request is False


def test_ask_availability_instant():
    assert evaluate("ask_availability", PREFS, OPEN).action == "instant_action"


def test_propose_time_inside_window_is_rider_agreed_only():
    d = evaluate("propose_time", PREFS, OPEN, time="18:30")
    assert d.action == "record_rider_agreed" and not d.provider_request


def test_propose_time_window_edges():
    assert evaluate("propose_time", PREFS, OPEN, time="18:00").action == "record_rider_agreed"
    assert evaluate("propose_time", PREFS, OPEN, time="20:00").action == "record_rider_agreed"
    assert evaluate("propose_time", PREFS, OPEN, time="20:01").action == "request_approval"


def test_propose_time_outside_window_needs_approval_then_follows_it():
    assert evaluate("propose_time", PREFS, OPEN, time="21:00").action == "request_approval"
    assert evaluate("propose_time", PREFS, OPEN, APPROVED, time="21:00").action == "instant_action"
    assert evaluate("propose_time", PREFS, OPEN, REJECTED, time="21:00").action == "refuse"


def test_propose_time_without_time_is_unclear():
    assert evaluate("propose_time", PREFS, OPEN).reason == "ask_to_repeat_once"


def test_guard_needs_approval_on_open_order():
    d = evaluate("guard_drop_request", PREFS, OPEN)
    assert d.action == "request_approval" and d.customer_approvable


def test_guard_approved_permits_provider():
    d = evaluate("guard_drop_request", PREFS, OPEN, APPROVED, CAPS)
    assert d.action == "instant_action" and d.provider_request


@pytest.mark.parametrize("st", [REJECTED, EXPIRED, CONTACT_LATER])
def test_guard_rejected_or_expired_refuses(st):
    d = evaluate("guard_drop_request", PREFS, OPEN, st)
    assert d.action == "refuse" and not d.provider_request


@pytest.mark.parametrize("approval", ["none", APPROVED])
def test_verified_order_handover_refused_and_never_offered(approval):
    for intent in ("guard_drop_request", "neighbor_drop_request"):
        d = evaluate(intent, PREFS, VERIFIED, approval, CAPS)
        assert d.action == "refuse"
        assert d.reason == "handover_not_possible_for_verified_order"
        assert d.customer_approvable is False and d.provider_request is False


def test_verified_order_refused_even_if_pre_approved():
    p = Prefs("18:00", "20:00", allow_guard=True, allow_neighbor=True)
    assert evaluate("guard_drop_request", p, VERIFIED).action == "refuse"


def test_pre_approved_guard_is_instant():
    p = Prefs("18:00", "20:00", allow_guard=True)
    d = evaluate("guard_drop_request", p, OPEN)
    assert d.action == "instant_action" and d.provider_request


def test_change_address_flow():
    assert evaluate("change_address", PREFS, OPEN).action == "request_approval"
    assert evaluate("change_address", PREFS, OPEN, APPROVED, CAPS).action == "escalate"
    d = evaluate("change_address", PREFS, OPEN, APPROVED, CAPS | {"change_address"})
    assert d.action == "instant_action" and d.provider_request
    assert evaluate("change_address", PREFS, OPEN, REJECTED).action == "refuse"


def test_ask_address_instant_no_provider():
    d = evaluate("ask_address", PREFS, OPEN)
    assert d.action == "instant_action" and not d.provider_request


def test_unclear_asks_once_then_escalates():
    assert evaluate("unclear", PREFS, OPEN, clarify_attempts=0).reason == "ask_to_repeat_once"
    assert evaluate("unclear", PREFS, OPEN, clarify_attempts=1).action == "escalate"
    assert evaluate("something_made_up", PREFS, OPEN, clarify_attempts=1).action == "escalate"


def test_decision_cannot_request_provider_unless_instant():
    with pytest.raises(ValueError):
        Decision("refuse", "x", provider_request=True)
    with pytest.raises(ValueError):
        Decision("teleport", "x")


def test_in_window():
    assert in_window("19:59", "18:00", "20:00") and not in_window("17:59", "18:00", "20:00")
