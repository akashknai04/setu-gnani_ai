"""Deterministic policy engine. Pure Python. No model calls, no I/O.

evaluate() is the ONLY place that decides what the agent may do. A language model
can at most suggest an intent label; it never decides a permission.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.intent.schema import HANDOVER_INTENTS, OTP_INTENTS

ACTIONS = ("instant_action", "request_approval", "record_rider_agreed", "refuse", "escalate")

# approval states passed into evaluate()
NO_APPROVAL, APPROVED, REJECTED, EXPIRED, CONTACT_LATER = "none", "approved", "rejected", "expired", "contact_later"


@dataclass(frozen=True)
class Prefs:
    window_start: str          # "HH:MM"
    window_end: str            # "HH:MM"
    allow_guard: bool = False
    allow_neighbor: bool = False
    language: str = "kn"
    meeting_mode: bool = True
    area: str = ""
    landmark: str = ""

    @staticmethod
    def from_row(row: dict) -> "Prefs":
        return Prefs(row["window_start"], row["window_end"], bool(row["allow_guard"]),
                     bool(row["allow_neighbor"]), row["language"], bool(row["meeting_mode"]),
                     row["area"], row["landmark"])


@dataclass(frozen=True)
class Order:
    id: str
    exists: bool
    status: str
    requires_otp: bool

    @property
    def order_valid(self) -> bool:
        """order exists and is out for delivery (NOT the same as requires_otp)."""
        return self.exists and self.status == "out_for_delivery"


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    provider_request: bool = False   # True only when a provider call is permitted
    customer_approvable: bool = False

    def __post_init__(self):
        if self.action not in ACTIONS:
            raise ValueError(f"unknown action {self.action}")
        if self.provider_request and self.action != "instant_action":
            raise ValueError("provider requests are only allowed for instant_action")

    def to_dict(self) -> dict:
        return {"action": self.action, "reason": self.reason,
                "provider_request": self.provider_request, "customer_approvable": self.customer_approvable}


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def in_window(t: str, start: str, end: str) -> bool:
    return _minutes(start) <= _minutes(t) <= _minutes(end)


def evaluate(intent: str, prefs: Prefs, order: Order, approval: str = NO_APPROVAL,
             provider_caps: frozenset | set = frozenset(), *, time: str | None = None,
             clarify_attempts: int = 0) -> Decision:
    # 1. an invalid order is never acted on
    if not order.order_valid:
        return Decision("escalate", "order_not_valid")

    # 2. OTP: always refused, never customer-approvable, approval state ignored
    if intent in OTP_INTENTS:
        return Decision("refuse", "otp_protection")

    if intent == "greeting":
        return Decision("instant_action", "greet_back")

    if intent == "end_call":
        return Decision("instant_action", "end_call")

    if intent == "customer_unavailable":
        return Decision("instant_action", "agent_answering_for_customer")

    if intent == "ask_availability":
        return Decision("instant_action", "share_preferred_window")

    if intent == "propose_time":
        if not time:
            return _unclear(clarify_attempts)
        if in_window(time, prefs.window_start, prefs.window_end):
            return Decision("record_rider_agreed", "inside_customer_window")
        if approval == APPROVED:
            return Decision("instant_action", "customer_approved_time")
        if approval in (REJECTED, EXPIRED, CONTACT_LATER):
            return Decision("refuse", f"time_outside_window_{approval}")
        return Decision("request_approval", "time_outside_window", customer_approvable=True)

    if intent in HANDOVER_INTENTS:
        kind = "guard" if intent == "guard_drop_request" else "neighbor"
        pre = prefs.allow_guard if kind == "guard" else prefs.allow_neighbor
        if order.requires_otp:
            # Verified handover cannot go to a third party. Not offered to the customer.
            return Decision("refuse", "handover_not_possible_for_verified_order")
        if pre:
            return Decision("instant_action", f"{kind}_pre_approved", provider_request=True)
        if approval == APPROVED:
            return Decision("instant_action", f"{kind}_customer_approved", provider_request=True)
        if approval in (REJECTED, EXPIRED, CONTACT_LATER):
            return Decision("refuse", f"{kind}_handover_{approval}")
        return Decision("request_approval", f"{kind}_handover_needs_approval", customer_approvable=True)

    if intent == "change_address":
        if approval == APPROVED:
            if "change_address" in provider_caps:
                return Decision("instant_action", "address_change_customer_approved", provider_request=True)
            return Decision("escalate", "provider_cannot_change_address")
        if approval in (REJECTED, EXPIRED, CONTACT_LATER):
            return Decision("refuse", f"address_change_{approval}")
        return Decision("request_approval", "address_change_needs_approval", customer_approvable=True)

    if intent == "ask_address":
        return Decision("instant_action", "share_area_and_landmark_only")

    return _unclear(clarify_attempts)


def _unclear(clarify_attempts: int) -> Decision:
    if clarify_attempts < 1:
        return Decision("instant_action", "ask_to_repeat_once")
    return Decision("escalate", "still_unclear_after_one_retry")
