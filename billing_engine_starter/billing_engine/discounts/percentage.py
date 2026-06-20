"""
PercentageDiscount — e.g., 20% off the subtotal.

Examples:
    PercentageDiscount(Decimal("0.20")).apply(Money(1000, "INR"), ctx)  ->  Money(200, "INR")
    PercentageDiscount(Decimal("1.00")).apply(Money(500, "INR"), ctx)   ->  Money(500, "INR")  # 100% off
"""

"""
PercentageDiscount — e.g., 20% off the subtotal.
"""

from decimal import Decimal

from billing_engine.money import Money
from billing_engine.discounts.base import Discount, DiscountContext


class PercentageDiscount(Discount):
    def __init__(self, percentage: Decimal) -> None:
        if isinstance(percentage, float):
            raise TypeError("Percentage must be a Decimal, not a float.")
        if percentage < Decimal("0") or percentage > Decimal("1"):
            raise ValueError("Percentage must be between 0.0 and 1.0 inclusive.")
            
        self.percentage = percentage

    def apply(self, subtotal: Money, context: DiscountContext) -> Money:
        # Multiplication handles the math and preserves the currency automatically
        return subtotal * self.percentage
    