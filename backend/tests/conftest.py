import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MOCK_VOICE", "1")
os.environ.setdefault("EVON_MODE", "off")

from backend.db import Database  # noqa: E402
from backend.engine.approvals import ApprovalService  # noqa: E402
from backend.engine.ledger import Ledger  # noqa: E402
from backend.engine.orchestrator import Agent  # noqa: E402
from backend.providers.mock_delivery import MockDeliveryProvider  # noqa: E402
from backend.seed import seed  # noqa: E402


class FakeClock:
    def __init__(self, t: float = 1_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def db():
    d = Database(":memory:")
    seed(d)
    yield d
    d.close()


@pytest.fixture
def ledger(db, clock):
    return Ledger(db, clock)


@pytest.fixture
def approvals(db, clock):
    return ApprovalService(db, "test-secret", ttl_s=30, clock=clock)


@pytest.fixture
def provider():
    return MockDeliveryProvider("accept")


@pytest.fixture
def agent(db, ledger, approvals, provider, clock):
    return Agent(db, ledger, approvals, provider, clock=clock)
