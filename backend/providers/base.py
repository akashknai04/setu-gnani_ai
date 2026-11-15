from __future__ import annotations

from dataclasses import asdict, dataclass

from backend.engine.state_machine import PermitDenied, ProviderPermit

PROVIDER_STATUSES = ("accepted", "rejected", "unavailable", "invalid")


@dataclass
class ProviderResponse:
    status: str               # accepted = REQUEST accepted. Never means "delivered".
    request_id: str
    action: str
    order_id: str
    simulated: bool = True
    detail: str = ""

    @property
    def accepted(self) -> bool:
        return self.status == "accepted"

    def to_dict(self) -> dict:
        return asdict(self)


class DeliveryProvider:
    name = "base"
    capabilities: frozenset = frozenset()

    def request(self, permit: ProviderPermit, action: str) -> ProviderResponse:  # pragma: no cover
        raise NotImplementedError

    @staticmethod
    def _check_permit(permit) -> None:
        if not isinstance(permit, ProviderPermit):
            raise PermitDenied("provider call without a policy permit")
        if permit.used:
            raise PermitDenied("permit already used")
        permit.used = True
