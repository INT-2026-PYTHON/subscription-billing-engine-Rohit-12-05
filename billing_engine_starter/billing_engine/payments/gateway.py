"""
PaymentGateway — abstract + two mock implementations.

In real life this would talk to Stripe / Razorpay / Adyen. For the project
we use mocks so tests are deterministic and the demo never hits the network.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from billing_engine.models import Invoice


@dataclass(frozen=True)
class PaymentResult:
    success: bool
    failure_reason: Optional[str] = None


class PaymentGateway(ABC):
    @abstractmethod
    def charge(self, invoice: Invoice) -> PaymentResult:
        raise NotImplementedError


# ----------------------------------------------------------------
# Scripted — for deterministic tests
# ----------------------------------------------------------------
class ScriptedGateway(PaymentGateway):
    """Returns pre-set results from a queue. Used in tests."""

    def __init__(self, results: list[PaymentResult]) -> None:
        # Copy the list so we don't accidentally mutate the test's original list
        self.results = results.copy()

    def charge(self, invoice: Invoice) -> PaymentResult:
        if not self.results:
            # Fallback if the test forgets to provide enough mock results
            return PaymentResult(success=False, failure_reason="OUT_OF_MOCKS")
            
        # Pop the first result off the front of the list
        return self.results.pop(0)


# ----------------------------------------------------------------
# Fake-random — for the CLI demo
# ----------------------------------------------------------------
class FakeRandomGateway(PaymentGateway):
    """Succeeds at a configurable rate; seeded for reproducibility."""

    def __init__(self, success_rate: float = 0.7, seed: Optional[int] = None) -> None:
        self.success_rate = success_rate
        # Use an isolated Random instance so we don't mess with global random state
        self.rng = random.Random(seed)

    def charge(self, invoice: Invoice) -> PaymentResult:
        # random.random() returns a float between 0.0 and 1.0
        if self.rng.random() < self.success_rate:
            return PaymentResult(success=True)
            
        # If it randomly fails, pick a random reason just for realism in the demo
        reasons = ["INSUFFICIENT_FUNDS", "CARD_EXPIRED", "DO_NOT_HONOR", "NETWORK_ERROR"]
        return PaymentResult(success=False, failure_reason=self.rng.choice(reasons))