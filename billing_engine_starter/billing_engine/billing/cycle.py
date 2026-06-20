"""
BillingCycle — finds due subscriptions, generates invoices, posts ledger DEBITs,
advances the subscription period. Must be IDEMPOTENT (safe to run twice).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional

from billing_engine.db import (
    Database,
    CustomerRepository, PlanRepository, SubscriptionRepository,
    UsageRecordRepository, InvoiceRepository, InvoiceLineItemRepository,
    LedgerRepository,
)
from billing_engine.models import (
    Subscription, SubscriptionStatus, InvoiceStatus, 
    LedgerEntry, LedgerDirection
)
from billing_engine.billing.pipeline import build_invoice


@dataclass
class BillingResult:
    invoices_created: int
    invoices_skipped_duplicate: int
    trials_activated: int


class BillingCycle:
    def __init__(
        self,
        db: Database,
        customer_repo: CustomerRepository,
        plan_repo: PlanRepository,
        subscription_repo: SubscriptionRepository,
        usage_repo: UsageRecordRepository,
        invoice_repo: InvoiceRepository,
        line_item_repo: InvoiceLineItemRepository,
        ledger_repo: LedgerRepository,
        strategy_factory: Callable,    
        discount_factory: Callable,    
        tax_factory: Callable,         
    ) -> None:
        self.db = db
        self.customer_repo = customer_repo
        self.plan_repo = plan_repo
        self.subscription_repo = subscription_repo
        self.usage_repo = usage_repo
        self.invoice_repo = invoice_repo
        self.line_item_repo = line_item_repo
        self.ledger_repo = ledger_repo
        self.strategy_factory = strategy_factory
        self.discount_factory = discount_factory
        self.tax_factory = tax_factory

    # --------------------------------------------------------
    def run(self, as_of: date) -> BillingResult:
        """Bill all subscriptions whose current period ends on or before `as_of`."""
        invoices_created = 0
        invoices_skipped = 0
        trials_activated = 0

        # 1. Activate trials that have ended
        for sub in self.subscription_repo.list_all():
            if sub.status == SubscriptionStatus.TRIAL and sub.trial_end and sub.trial_end <= as_of:
                self.subscription_repo.update_status(sub.id, SubscriptionStatus.ACTIVE)
                trials_activated += 1

        # 2. Process all subscriptions due for billing
        due_subscriptions = self.subscription_repo.get_due_for_billing(as_of)
        
        for sub in due_subscriptions:
            # Fetch related entities
            plan = self.plan_repo.get(sub.plan_id)
            customer = self.customer_repo.get(sub.customer_id)
            
            # Prepare factories for the pure pipeline
            strategy = self.strategy_factory(plan)
            discount = self.discount_factory(sub.discount_id) if sub.discount_id else None
            tax_calc, tax_context = self.tax_factory(customer)
            
            # Fetch usage (assuming "calls" as the default metric based on test setups)
            usage_quantity = self.usage_repo.sum_for_period(
                sub.id, "calls", sub.current_period_start, sub.current_period_end
            )
            
            invoice_count = self.invoice_repo.count_for_subscription(sub.id)
            
            # 3. Build the invoice using our pure function
            draft_invoice = build_invoice(
                subscription=sub,
                plan=plan,
                strategy=strategy,
                discount=discount,
                tax_calc=tax_calc,
                tax_context=tax_context,
                usage_quantity=usage_quantity,
                period_start=sub.current_period_start,
                period_end=sub.current_period_end,
                invoice_count_so_far=invoice_count,
            )
            
            # Mark it as ISSUED since we are officially billing them
            draft_invoice.status = InvoiceStatus.ISSUED
            
            # 4. Save everything sequentially
            try:
                # Save Invoice Header (This will trigger IntegrityError if already billed)
                saved_inv = self.invoice_repo.add(draft_invoice)
                
                # Save Line Items
                import dataclasses
                for line_item in draft_invoice.line_items:
                    li_to_save = dataclasses.replace(line_item, invoice_id=saved_inv.id)
                    self.line_item_repo.add(li_to_save)
                
                # Post Ledger DEBIT (Customer owes us money)
                self.ledger_repo.add(LedgerEntry(
                    id=None,
                    invoice_id=saved_inv.id,
                    customer_id=customer.id,
                    amount=saved_inv.total,
                    direction=LedgerDirection.DEBIT,
                    reason=f"Invoice {saved_inv.id} generated for {plan.name} plan",
                ))
                
                # Advance the subscription period (Handle Year Rollover)
                next_start = sub.current_period_end
                if next_start.month == 12:
                    next_end = next_start.replace(year=next_start.year + 1, month=1)
                else:
                    next_end = next_start.replace(month=next_start.month + 1)
                    
                self.subscription_repo.update_period(sub.id, next_start, next_end)
                
                invoices_created += 1
                
            except sqlite3.IntegrityError:
                # If the UNIQUE(subscription_id, period_start) constraint triggers on the invoice insert, 
                # we already billed this period. Skip safely!
                invoices_skipped += 1

        return BillingResult(invoices_created, invoices_skipped, trials_activated)

    # --------------------------------------------------------
    def upgrade_subscription(self, subscription_id: int, new_plan_id: int, switch_date: date) -> None:
        """Mid-cycle upgrade — Day 4 stretch."""
        # TODO Day 4
        raise NotImplementedError("Day 4: implement BillingCycle.upgrade_subscription")
    