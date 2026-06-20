"""
TieredPricing — different price per unit depending on the tier the quantity falls into.

This is the "cumulative" / "stacked" tier model, NOT the "volume" model:
    Tiers: [(0, 1000, ₹2.00), (1000, 5000, ₹1.50), (5000, None, ₹1.00)]
    Quantity = 6000:
        First 1000 units  @ ₹2.00 = ₹2000
        Next  4000 units  @ ₹1.50 = ₹6000
        Last  1000 units  @ ₹1.00 = ₹1000
        ------------------------------------
        Total                     = ₹9000

A tier with `to_units = None` is the open-ended top tier.

Tier boundaries are HALF-OPEN on the right: a tier (from, to, price)
covers units strictly less than `to` (i.e. [from, to)).
"""

"""
TieredPricing — different price per unit depending on the tier the quantity falls into.
"""

from dataclasses import dataclass
from typing import Optional

from billing_engine.money import Money
from billing_engine.pricing.base import PricingStrategy


@dataclass(frozen=True)
class Tier:
    from_units: int
    to_units: Optional[int]   # None means "unlimited" / open-ended
    unit_price: Money


class TieredPricing(PricingStrategy):
    """Charges across multiple price tiers based on cumulative quantity."""

    def __init__(self, tiers: list[Tier]) -> None:
        if not tiers:
            raise ValueError("Tiers list cannot be empty.")

        first_currency = tiers[0].unit_price.currency

        for i, tier in enumerate(tiers):
            # 1. Currency Check
            if tier.unit_price.currency != first_currency:
                raise ValueError("All tiers must use the same currency.")

            if i < len(tiers) - 1:
                # 2. Intermediate tiers cannot be open-ended
                if tier.to_units is None:
                    raise ValueError("Only the top tier can be open-ended.")
                # 3. Contiguous check (no gaps)
                if tier.to_units != tiers[i + 1].from_units:
                    raise ValueError("Tiers must be contiguous.")
            else:
                # 4. Top tier MUST be open-ended
                if tier.to_units is not None:
                    raise ValueError("The top tier must be open-ended (to_units=None).")

        self.tiers = tiers
        self.currency = first_currency

    def calculate(self, quantity: int) -> Money:
        if quantity < 0:
            raise ValueError("Quantity cannot be negative.")

        total = Money.zero(self.currency)
        if quantity == 0:
            return total

        for tier in self.tiers:
            # If the quantity hasn't even reached this tier's starting point, we are done
            if quantity <= tier.from_units:
                break

            # Calculate how many units fall specifically within this tier's bucket
            if tier.to_units is None:
                units_in_tier = quantity - tier.from_units
            else:
                upper_bound = min(quantity, tier.to_units)
                units_in_tier = upper_bound - tier.from_units

            if units_in_tier > 0:
                total += tier.unit_price * units_in_tier

        return total
    