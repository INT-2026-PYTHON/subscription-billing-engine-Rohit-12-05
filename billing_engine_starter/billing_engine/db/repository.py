"""
Repositories — the ONLY place SQL lives.

Each repository wraps the Database connection and exposes methods that
take/return domain dataclasses (defined in billing_engine/models/).

⚠️ YOU IMPLEMENT every method body marked TODO.
   The signatures, docstrings, and the LedgerRepository's append-only
   guarantee are already in place — do not change them.

Beginner map (Day 2):
  1) CustomerRepository: add, get, find_by_email, list_all
  2) PlanRepository: add, get, list_all
  3) PlanTierRepository: add, list_for_plan
  4) DiscountRepository: add, get_by_code
  5) SubscriptionRepository: add, get, list_all, get_due_for_billing
  6) UsageRecordRepository: add, sum_for_period
  7) InvoiceRepository: add, get
  8) InvoiceLineItemRepository: add, list_for_invoice

Skip on Day 2 (read-only for now):
  - SubscriptionRepository.update_period / update_status / update_plan
  - InvoiceRepository.count_for_subscription / mark_paid / mark_failed / set_pdf_path
  - LedgerRepository and PaymentAttemptRepository

Conventions:
  - Always use parameterized queries (`?` placeholders) — NEVER f-string SQL.
  - Money values are persisted as TEXT using `money.to_storage()`.
  - Dates are persisted as ISO strings (`date.isoformat()`).

New layering (beginner-friendly):
  - Raw SQL lives in `billing_engine/db/queries.py`.
  - Repository methods call those query helpers.
  - Your Day 2 focus is:
      1) Convert domain -> storage values before helper call
      2) Convert rows -> domain dataclasses after helper call
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from billing_engine.db.database import Database
from billing_engine.db import queries as q
from billing_engine.money import Money
from billing_engine.models import (
    Customer,
    Plan, PricingType, BillingPeriod,
    Subscription, SubscriptionStatus,
    Invoice, InvoiceStatus, InvoiceLineItem, LineItemKind,
    LedgerEntry, LedgerDirection,
)


# ============================================================
# CUSTOMERS
# ============================================================
# Day 2: start here.
class CustomerRepository:
    """Persistence boundary for customers."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def _to_customer(self, row) -> Customer:
        """Helper to translate a database row back into a Customer object."""
        created_at = None
        if row["created_at"]:
            # SQLite timestamps might have a space instead of a 'T'; this ensures safe parsing
            created_at_str = row["created_at"].replace(" ", "T")
            created_at = datetime.fromisoformat(created_at_str)
            
        return Customer(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            country_code=row["country_code"],
            state_code=row["state_code"],
            created_at=created_at
        )

    def add(self, customer: Customer) -> Customer:
        with self.db.transaction() as conn:
            new_id = q.insert_customer(
                conn=conn,
                name=customer.name,
                email=customer.email,
                country_code=customer.country_code,
                state_code=customer.state_code,
            )
        # Fetch it right back from the database so it includes the newly generated ID
        return self.get(new_id)

    def get(self, customer_id: int) -> Optional[Customer]:
        with self.db.transaction() as conn:
            row = q.select_customer_by_id(conn, customer_id)
            
        if not row:
            return None
        return self._to_customer(row)

    def find_by_email(self, email: str) -> Optional[Customer]:
        with self.db.transaction() as conn:
            row = q.select_customer_by_email(conn, email)
            
        if not row:
            return None
        return self._to_customer(row)

    def list_all(self) -> list[Customer]:
        with self.db.transaction() as conn:
            rows = q.select_all_customers(conn)
            
        return [self._to_customer(row) for row in rows]


# ============================================================
# PLANS  +  PLAN TIERS
# ============================================================
# Day 2
class PlanRepository:
    """Persistence boundary for subscription plans."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def _to_plan(self, row) -> Plan:
        """Helper to translate a database row back into a Plan object."""
        return Plan(
            id=row["id"],
            name=row["name"],
            # Convert string from DB back into the Enum
            pricing_type=PricingType(row["pricing_type"]),
            billing_period=BillingPeriod(row["billing_period"]),
            currency=row["currency"],
            config_json=row["config_json"],
        )

    def add(self, plan: Plan) -> Plan:
        with self.db.transaction() as conn:
            new_id = q.insert_plan(
                conn=conn,
                name=plan.name,
                # Enums must be converted to their string values for SQLite
                pricing_type=plan.pricing_type.value,
                billing_period=plan.billing_period.value,
                currency=plan.currency,
                config_json=plan.config_json,
            )
        return self.get(new_id)

    def get(self, plan_id: int) -> Optional[Plan]:
        with self.db.transaction() as conn:
            row = q.select_plan_by_id(conn, plan_id)
            
        if not row:
            return None
        return self._to_plan(row)

    def list_all(self) -> list[Plan]:
        with self.db.transaction() as conn:
            rows = q.select_all_plans(conn)
            
        return [self._to_plan(row) for row in rows]


class PlanTierRepository:
    """Persistence boundary for pricing tiers attached to a plan."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, plan_id: int, from_units: int, to_units: Optional[int], unit_price: Money) -> int:
        with self.db.transaction() as conn:
            return q.insert_plan_tier(
                conn=conn,
                plan_id=plan_id,
                from_units=from_units,
                to_units=to_units,
                # Money must be converted to a string before hitting the DB
                unit_price=unit_price.to_storage(),
            )

    def list_for_plan(self, plan_id: int, currency: str) -> list[tuple[int, Optional[int], Money]]:
        with self.db.transaction() as conn:
            rows = q.select_plan_tiers(conn, plan_id)
            
        # We construct the tuples precisely as the tests expect them
        return [
            (row["from_units"], row["to_units"], Money(row["unit_price"], currency))
            for row in rows
        ]


# ============================================================
# DISCOUNTS
# ============================================================
class DiscountRepository:
    """Persistence boundary for discount definitions."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, code: str, discount_type: str, value: str, currency: Optional[str] = None) -> int:
        with self.db.transaction() as conn:
            return q.insert_discount(conn, code, discount_type, value, currency)

    def get_by_code(self, code: str) -> Optional[dict]:
        with self.db.transaction() as conn:
            row = q.select_discount_by_code(conn, code)
            
        if not row:
            return None
        # Convert the SQLite Row into a standard Python dictionary
        return dict(row)


# ============================================================
# SUBSCRIPTIONS
# ============================================================
class SubscriptionRepository:
    """Persistence boundary for customer subscriptions."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def _to_subscription(self, row) -> Subscription:
        """Helper to safely parse strings back into Dates and Enums."""
        return Subscription(
            id=row["id"],
            customer_id=row["customer_id"],
            plan_id=row["plan_id"],
            status=SubscriptionStatus(row["status"]),
            current_period_start=date.fromisoformat(row["current_period_start"]),
            current_period_end=date.fromisoformat(row["current_period_end"]),
            trial_end=date.fromisoformat(row["trial_end"]) if row["trial_end"] else None,
            discount_id=row["discount_id"],
            past_due_since=date.fromisoformat(row["past_due_since"]) if row["past_due_since"] else None,
        )

    def add(self, subscription: Subscription) -> Subscription:
        with self.db.transaction() as conn:
            new_id = q.insert_subscription(
                conn=conn,
                customer_id=subscription.customer_id,
                plan_id=subscription.plan_id,
                status=subscription.status.value,
                # Convert Python dates to ISO strings for SQLite
                current_period_start=subscription.current_period_start.isoformat(),
                current_period_end=subscription.current_period_end.isoformat(),
                trial_end=subscription.trial_end.isoformat() if subscription.trial_end else None,
                discount_id=subscription.discount_id,
                past_due_since=subscription.past_due_since.isoformat() if subscription.past_due_since else None,
            )
        return self.get(new_id)

    def get(self, subscription_id: int) -> Optional[Subscription]:
        with self.db.transaction() as conn:
            row = q.select_subscription_by_id(conn, subscription_id)
            
        if not row:
            return None
        return self._to_subscription(row)

    def list_all(self) -> list[Subscription]:
        with self.db.transaction() as conn:
            rows = q.select_all_subscriptions(conn)
            
        return [self._to_subscription(row) for row in rows]

    def get_due_for_billing(self, as_of: date) -> list[Subscription]:
        with self.db.transaction() as conn:
            rows = q.select_due_subscriptions(conn, as_of.isoformat())
            
        return [self._to_subscription(row) for row in rows]

    def update_period(self, subscription_id: int, new_start: date, new_end: date) -> None:
        with self.db.transaction() as conn:
            q.update_subscription_period(
                conn, 
                subscription_id, 
                new_start.isoformat(), 
                new_end.isoformat()
            )

    def update_status(self, subscription_id: int, new_status: SubscriptionStatus, past_due_since: Optional[date] = None) -> None:
        with self.db.transaction() as conn:
            q.update_subscription_status(
                conn, 
                subscription_id, 
                new_status.value, 
                past_due_since.isoformat() if past_due_since else None
            )

    def update_plan(self, subscription_id: int, new_plan_id: int) -> None:
        # We will fully implement this on Day 4 for mid-cycle upgrades
        with self.db.transaction() as conn:
            q.update_subscription_plan(conn, subscription_id, new_plan_id)


# ============================================================
# USAGE
# ============================================================
class UsageRecordRepository:
    """Persistence boundary for metered usage."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, subscription_id: int, metric: str, quantity: int) -> int:
        with self.db.transaction() as conn:
            return q.insert_usage_record(conn, subscription_id, metric, quantity)

    def sum_for_period(self, subscription_id: int, metric: str, period_start: date, period_end: date) -> int:
        with self.db.transaction() as conn:
            return q.sum_usage_for_subscription_metric(conn, subscription_id, metric)

# ============================================================
# INVOICES + LINE ITEMS
# ============================================================
class InvoiceRepository:
    """Persistence boundary for invoice headers."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def _to_invoice(self, row) -> Invoice:
        return Invoice(
            id=row["id"],
            subscription_id=row["subscription_id"],
            period_start=date.fromisoformat(row["period_start"]),
            period_end=date.fromisoformat(row["period_end"]),
            subtotal=Money(row["subtotal"], row["currency"]),
            discount_total=Money(row["discount_total"], row["currency"]),
            tax_total=Money(row["tax_total"], row["currency"]),
            total=Money(row["total"], row["currency"]),
            status=InvoiceStatus(row["status"]),
            issued_at=datetime.fromisoformat(row["issued_at"].replace(" ", "T")) if row["issued_at"] else None,
            pdf_path=row["pdf_path"],
        )

    def add(self, invoice: Invoice) -> Invoice:
        with self.db.transaction() as conn:
            new_id = q.insert_invoice(
                conn=conn,
                subscription_id=invoice.subscription_id,
                period_start=invoice.period_start.isoformat(),
                period_end=invoice.period_end.isoformat(),
                currency=invoice.total.currency,
                subtotal=invoice.subtotal.to_storage(),
                discount_total=invoice.discount_total.to_storage(),
                tax_total=invoice.tax_total.to_storage(),
                total=invoice.total.to_storage(),
                status=invoice.status.value,
                issued_at=invoice.issued_at.isoformat() if invoice.issued_at else None,
                pdf_path=invoice.pdf_path,
            )
        return self.get(new_id)

    def get(self, invoice_id: int) -> Optional[Invoice]:
        with self.db.transaction() as conn:
            row = q.select_invoice_by_id(conn, invoice_id)
            
        if not row:
            return None
        return self._to_invoice(row)

    # ------------------------------------------------------------------
    # DAY 3/4 STUBS - DO NOT IMPLEMENT YET
    # ------------------------------------------------------------------
    def count_for_subscription(self, subscription_id: int) -> int:
        with self.db.transaction() as conn:
            return q.count_invoices_for_subscription(conn, subscription_id)

    def mark_paid(self, invoice_id: int) -> None:
        with self.db.transaction() as conn:
            q.update_invoice_status(conn, invoice_id, "PAID")

    def mark_failed(self, invoice_id: int) -> None:
        with self.db.transaction() as conn:
            q.update_invoice_status(conn, invoice_id, "FAILED")

    def set_pdf_path(self, invoice_id: int, path: str) -> None:
        with self.db.transaction() as conn:
            q.update_invoice_pdf_path(conn, invoice_id, path)


class InvoiceLineItemRepository:
    """Persistence boundary for invoice detail rows."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, line_item: InvoiceLineItem) -> InvoiceLineItem:
        with self.db.transaction() as conn:
            new_id = q.insert_invoice_line_item(
                conn=conn,
                invoice_id=line_item.invoice_id,
                description=line_item.description,
                amount=line_item.amount.to_storage(),
                kind=line_item.kind.value,
            )
        
        # Return a new dataclass instance with the generated ID
        return InvoiceLineItem(
            id=new_id,
            invoice_id=line_item.invoice_id,
            description=line_item.description,
            amount=line_item.amount,
            kind=line_item.kind
        )

    def list_for_invoice(self, invoice_id: int) -> list[InvoiceLineItem]:
        with self.db.transaction() as conn:
            # We must fetch the parent invoice first to know what currency to use for the line items
            inv_row = q.select_invoice_by_id(conn, invoice_id)
            currency = inv_row["currency"] if inv_row else "INR"
            
            rows = q.select_line_items_for_invoice(conn, invoice_id)
            
        return [
            InvoiceLineItem(
                id=row["id"],
                invoice_id=row["invoice_id"],
                description=row["description"],
                amount=Money(row["amount"], currency),
                kind=LineItemKind(row["kind"])
            )
            for row in rows
        ]


# ============================================================
# LEDGER — APPEND-ONLY
# ============================================================
class LedgerRepository:
    """Persistence boundary for the append-only accounting ledger."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, entry: LedgerEntry) -> LedgerEntry:
        with self.db.transaction() as conn:
            new_id = q.insert_ledger_entry(
                conn=conn,
                invoice_id=entry.invoice_id,
                customer_id=entry.customer_id,
                amount=entry.amount.to_storage(),
                currency=entry.amount.currency,
                direction=entry.direction.value,
                reason=entry.reason
            )
        
        return LedgerEntry(
            id=new_id,
            invoice_id=entry.invoice_id,
            customer_id=entry.customer_id,
            amount=entry.amount,
            direction=entry.direction,
            reason=entry.reason,
            created_at=entry.created_at
        )

    def list_for_customer(self, customer_id: int) -> list[LedgerEntry]:
        with self.db.transaction() as conn:
            rows = q.select_ledger_for_customer(conn, customer_id)
            
        return [
            LedgerEntry(
                id=row["id"],
                invoice_id=row["invoice_id"],
                customer_id=row["customer_id"],
                amount=Money(row["amount"], row["currency"]),
                direction=LedgerDirection(row["direction"]),
                reason=row["reason"],
                created_at=datetime.fromisoformat(row["created_at"].replace(" ", "T")) if row["created_at"] else None
            )
            for row in rows
        ]

    # These two methods are intentionally implemented to REJECT — do not override.
    def update(self, *args, **kwargs):
        raise NotImplementedError("Ledger is append-only. Post a reversing entry instead.")

    def delete(self, *args, **kwargs):
        raise NotImplementedError("Ledger is append-only. Post a reversing entry instead.")
# ============================================================
# PAYMENT ATTEMPTS
# ============================================================
class PaymentAttemptRepository:
    """Persistence boundary for payment retry history."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def add(
        self,
        invoice_id: int,
        attempt_no: int,
        status: str,
        failure_reason: Optional[str],
        next_retry_at: Optional[datetime],
    ) -> int:
        with self.db.transaction() as conn:
            return q.insert_payment_attempt(
                conn=conn,
                invoice_id=invoice_id,
                attempt_no=attempt_no,
                status=status,
                failure_reason=failure_reason,
                # Convert the datetime object to an ISO string for SQLite
                next_retry_at=next_retry_at.isoformat() if next_retry_at else None,
            )

    def list_for_invoice(self, invoice_id: int) -> list[dict]:
        with self.db.transaction() as conn:
            rows = q.select_attempts_for_invoice(conn, invoice_id)
        return [dict(row) for row in rows]

    def count_for_invoice(self, invoice_id: int) -> int:
        with self.db.transaction() as conn:
            return q.count_attempts_for_invoice(conn, invoice_id)
        