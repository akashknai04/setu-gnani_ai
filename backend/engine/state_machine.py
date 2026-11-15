"""Per-call state machine (6 states) and the provider permit gate.

GREETING -> LISTENING -> POLICY_CHECK -> {INSTANT_ACTION | WAITING_APPROVAL | ESCALATED}
         -> REPLY_AND_RECORD -> LISTENING (next turn)
WAITING_APPROVAL -> POLICY_CHECK when the customer answers (approval re-enters policy).

A ProviderPermit can only be minted by CallSession.authorize_provider(), which
requires state INSTANT_ACTION, a Decision with provider_request=True, and a valid
order. The mock provider refuses to run without a permit.
"""
from __future__ import annotations

from enum import Enum

from backend.engine.policy import Decision, Order


class State(str, Enum):
    GREETING = "GREETING"
    LISTENING = "LISTENING"
    POLICY_CHECK = "POLICY_CHECK"
    INSTANT_ACTION = "INSTANT_ACTION"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    ESCALATED = "ESCALATED"
    REPLY_AND_RECORD = "REPLY_AND_RECORD"


TRANSITIONS: dict[State, set[State]] = {
    State.GREETING: {State.LISTENING},
    State.LISTENING: {State.POLICY_CHECK},
    State.POLICY_CHECK: {State.INSTANT_ACTION, State.WAITING_APPROVAL, State.ESCALATED},
    State.INSTANT_ACTION: {State.REPLY_AND_RECORD},
    State.WAITING_APPROVAL: {State.POLICY_CHECK, State.REPLY_AND_RECORD},
    State.ESCALATED: {State.REPLY_AND_RECORD},
    State.REPLY_AND_RECORD: {State.LISTENING},
}

ACTION_TO_STATE = {
    "instant_action": State.INSTANT_ACTION,
    "record_rider_agreed": State.INSTANT_ACTION,
    "refuse": State.INSTANT_ACTION,      # refusing is an immediate, safe reply
    "request_approval": State.WAITING_APPROVAL,
    "escalate": State.ESCALATED,
}


class InvalidTransition(RuntimeError):
    pass


class PermitDenied(RuntimeError):
    pass


_PERMIT_KEY = object()


class ProviderPermit:
    """Proof that policy allowed a provider request. Cannot be built from outside."""

    def __init__(self, key, *, call_id: str, order_id: str, reason: str):
        if key is not _PERMIT_KEY:
            raise PermitDenied("ProviderPermit can only be issued by CallSession.authorize_provider")
        self.call_id, self.order_id, self.reason = call_id, order_id, reason
        self.used = False


class CallSession:
    def __init__(self, call_id: str, order_id: str, state: State | str = State.GREETING):
        self.call_id = call_id
        self.order_id = order_id
        self.state = State(state)
        self.last_decision: Decision | None = None

    def transition(self, to: State | str) -> None:
        to = State(to)
        if to not in TRANSITIONS[self.state]:
            raise InvalidTransition(f"{self.state.value} -> {to.value} not allowed")
        self.state = to

    def apply_decision(self, decision: Decision) -> State:
        if self.state != State.POLICY_CHECK:
            raise InvalidTransition(f"decision applied outside POLICY_CHECK (state={self.state.value})")
        self.last_decision = decision
        self.transition(ACTION_TO_STATE[decision.action])
        return self.state

    def authorize_provider(self, decision: Decision, order: Order) -> ProviderPermit:
        if self.state != State.INSTANT_ACTION:
            raise PermitDenied(f"not in INSTANT_ACTION (state={self.state.value})")
        if decision is not self.last_decision:
            raise PermitDenied("decision did not come from this call's policy check")
        if not (decision.action == "instant_action" and decision.provider_request):
            raise PermitDenied(f"policy did not permit a provider request ({decision.reason})")
        if not order.order_valid or order.id != self.order_id:
            raise PermitDenied("order not valid for this call")
        return ProviderPermit(_PERMIT_KEY, call_id=self.call_id, order_id=order.id, reason=decision.reason)
