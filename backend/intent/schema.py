"""Intent vocabulary shared by the fast path, Evon and the policy engine."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

INTENTS = (
    "customer_unavailable",
    "ask_availability",
    "propose_time",
    "guard_drop_request",
    "neighbor_drop_request",
    "request_otp",
    "change_address",
    "ask_address",
    "greeting",
    "end_call",
    "unclear",
)
OTP_INTENTS = {"request_otp", "share_otp"}
HANDOVER_INTENTS = {"guard_drop_request", "neighbor_drop_request"}
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@dataclass
class IntentResult:
    intent: str
    time: str | None = None          # "HH:MM" 24h, only for propose_time
    language: str = "hi"             # hi | kn | en
    source: str = "fast_path"        # fast_path | evon | fallback
    matched: list[str] = field(default_factory=list)  # which rules fired (debug only)

    def to_dict(self) -> dict:
        return asdict(self)


class SchemaError(ValueError):
    pass


def validate_evon_output(obj) -> IntentResult:
    """Strict validation for model output. Anything off-schema raises SchemaError.

    Allowed shape: {"intent": <one of INTENTS>, "time": "HH:MM" | null}
    Extra keys (including any 'confidence') are rejected: we never gate on them.
    """
    if not isinstance(obj, dict):
        raise SchemaError("not an object")
    allowed = {"intent", "time"}
    extra = set(obj) - allowed
    if extra:
        raise SchemaError(f"unexpected keys {sorted(extra)}")
    intent = obj.get("intent")
    if intent not in INTENTS:
        raise SchemaError(f"bad intent {intent!r}")
    t = obj.get("time")
    if t is not None and (not isinstance(t, str) or not _TIME_RE.match(t)):
        raise SchemaError("bad time")
    if intent == "propose_time" and t is None:
        raise SchemaError("propose_time without time")
    if intent != "propose_time" and t is not None:
        raise SchemaError("time given for non-time intent")
    return IntentResult(intent=intent, time=t, source="evon")
