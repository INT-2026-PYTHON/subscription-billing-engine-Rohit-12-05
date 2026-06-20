"""
build_invoice — PURE function that turns inputs into an Invoice dataclass.

⚠️ NO database calls here. No `datetime.now()`. No PDF. Just math.

The order is FIXED:
    1. base       = strategy.calculate(usage)
    2. discount   = discount.apply(base) if discount else 0
    3. taxable    = base - discount
    4. tax        = tax_calc.apply(taxable)
    5. total      = taxable + tax.total
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from billing_engine.money import Money
from billing_engine.models import (
    Invoice, InvoiceStatus, InvoiceLineItem, LineItemKind, Subscription, Plan,
)
from billing_engine.pricing.base import PricingStrategy
from billing_engine.discounts.base import Discount, DiscountContext
from billing_engine.taxes.base import TaxCalculator, TaxContext


def build_invoice(
    subscription: Subscription,
    plan: Plan,
    strategy: PricingStrategy,
    discount: Optional[Discount],
    tax_calc: TaxCalculator,
    tax_context: TaxContext,
    usage_quantity: int,
    period_start: date,
    period_end: date,
    invoice_count_so_far: int,
) -> Invoice:
    """Pure function. Returns an Invoice (id=None, status=DRAFT) ready to be persisted."""
    
    line_items = []
    
    # 1. Compute base charge
    base_charge = strategy.calculate(usage_quantity)
    line_items.append(
        InvoiceLineItem(id=None, invoice_id=None, description="Base Charge", amount=base_charge, kind=LineItemKind.BASE)
    )

    # 2. Apply discount if present
    discount_amount = Money.zero(base_charge.currency)
    if discount is not None:
        discount_ctx = DiscountContext(invoice_count_so_far=invoice_count_so_far)
        discount_amount = discount.apply(base_charge, discount_ctx)
        
        # Only add a line item if the discount is actually greater than zero
        if discount_amount > Money.zero(base_charge.currency):
            line_items.append(
                InvoiceLineItem(id=None, invoice_id=None, description="Discount", amount=-discount_amount, kind=LineItemKind.DISCOUNT)
            )

    # 3. Compute taxable amount
    taxable_amount = base_charge - discount_amount

    # 4. Apply tax
    tax_breakdown = tax_calc.apply(taxable_amount, tax_context)
    for label, amount in tax_breakdown.components:
        line_items.append(
            InvoiceLineItem(id=None, invoice_id=None, description=label, amount=amount, kind=LineItemKind.TAX)
        )

    # 5. Calculate Final Total
    total = taxable_amount + tax_breakdown.total

    # 6. Return the draft Invoice
    return Invoice(
        id=None,
        subscription_id=subscription.id,
        period_start=period_start,
        period_end=period_end,
        subtotal=base_charge,
        discount_total=discount_amount,
        tax_total=tax_breakdown.total,
        total=total,
        status=InvoiceStatus.DRAFT,
        issued_at=None,
        pdf_path=None,
        line_items=line_items,
    )
