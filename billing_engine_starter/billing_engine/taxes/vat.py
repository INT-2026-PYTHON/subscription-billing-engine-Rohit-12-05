"""
VATCalculator — single-rate VAT (e.g. 19% in Germany).
"""

from decimal import Decimal
from billing_engine.money import Money
from billing_engine.taxes.base import TaxCalculator, TaxContext, TaxBreakdown


class VATCalculator(TaxCalculator):
    def __init__(self, rate: Decimal) -> None:
        """Initialize with a tax rate as a Decimal (e.g., 0.19 for 19%)."""
        # Day 1: Implementation & Validation
        if not isinstance(rate, Decimal):
            raise TypeError("Tax rate must be a Decimal, not a float.")
        if not (0 <= rate <= 1):
            raise ValueError("Tax rate must be between 0 and 1.")
        
        self.rate = rate

    def apply(self, taxable: Money, context: TaxContext) -> TaxBreakdown:
        """Applies the VAT rate to the taxable amount."""
        # Day 1: Algorithm
        # 1. Calculate the VAT amount: vat = taxable * self.rate
        vat_amount = taxable * self.rate
        
        # 2. Format percentage for the description (e.g., 0.19 -> 19%)
        percent_label = f"VAT {self.rate * 100:g}%"
        
        # 3. Return TaxBreakdown with the component and the total
        return TaxBreakdown(
            components=[(percent_label, vat_amount)],
            total=vat_amount
        )
    