"""SIMULATED delivery provider. Nothing here talks to a real delivery platform."""
from __future__ import annotations

import uuid

from backend.providers.base import DeliveryProvider, ProviderResponse

MODES = ("accept", "reject", "unavailable", "invalid")


class MockDeliveryProvider(DeliveryProvider):
    name = "mock_delivery_provider"
    # The simulated provider can record handovers. It cannot change addresses, so an
    # approved address change escalates (exercises the "no capability" path).
    capabilities = frozenset({"guard_drop_request", "neighbor_drop_request"})

    def __init__(self, mode: str = "accept"):
        self.set_mode(mode)

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        self.mode = mode

    def raw_request(self, action: str, order_id: str) -> dict:
        """What the 'wire' returns. 'invalid' returns a malformed payload on purpose."""
        rid = f"sim_{uuid.uuid4().hex[:10]}"
        if self.mode == "accept":
            return {"status": "accepted", "request_id": rid, "simulated": True}
        if self.mode == "reject":
            return {"status": "rejected", "request_id": rid, "simulated": True, "detail": "simulated reject"}
        if self.mode == "unavailable":
            raise TimeoutError("simulated provider unavailable")
        return {"garbage": True}  # invalid

    def request(self, permit, action: str) -> ProviderResponse:
        self._check_permit(permit)
        order_id = permit.order_id
        try:
            raw = self.raw_request(action, order_id)
        except TimeoutError as e:
            return ProviderResponse("unavailable", "-", action, order_id, True, str(e))
        status = raw.get("status") if isinstance(raw, dict) else None
        if status not in ("accepted", "rejected") or raw.get("simulated") is not True:
            return ProviderResponse("invalid", "-", action, order_id, True, "malformed provider response")
        return ProviderResponse(status, raw["request_id"], action, order_id, True, raw.get("detail", ""))
