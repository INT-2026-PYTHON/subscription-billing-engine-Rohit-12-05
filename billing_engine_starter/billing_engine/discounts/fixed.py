"""
FixedAmountDiscount — e.g., flat ₹500 off.

CAPPING RULE: if the fixed amount exceeds the subtotal, return subtotal
(so the discounted total never goes below zero).
"""

"""
FixedAmountDiscount — e.g., flat ₹500 off.
"""

from billing_engine.money import Money
from billing_engine.discounts.base import Discount, DiscountContext


class FixedAmountDiscount(Discount):
    def __init__(self, amount: Money) -> None:
        if not isinstance(amount, Money):
            raise TypeError("Fixed discount amount must be a Money instance.")
        if amount.is_negative():
            raise ValueError("Discount amount cannot be negative.")
            
        self.amount = amount

    def apply(self, subtotal: Money, context: DiscountContext) -> Money:
        # min() will use Money's comparison logic, automatically raising a ValueError
        # if the currencies don't match, while also enforcing the capping rule!
        return min(self.amount, subtotal)
    