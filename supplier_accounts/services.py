"""Atomic, ledger-only invoice and recorded payout functions.

Supplier accounts are independent of goods receiving, finance expenses and any
payment gateway. Never infer payment success from an unverified reference.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from trading.models import PurchaseOrder
from .models import SupplierInvoice, SupplierPayment
from .permissions import actor_can_manage

CENT = Decimal('0.01')


def money(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError('Enter a valid amount.')
    if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
        raise ValidationError('Amount must be positive and have at most two decimal places.')
    if amount > Decimal('999999999999.99'):
        raise ValidationError('Amount is outside the supported range.')
    return amount.quantize(CENT)


def po_value(po):
    return sum((line.quantity * line.unit_cost for line in po.lines.all()), Decimal('0')).quantize(CENT, rounding=ROUND_HALF_UP)


@transaction.atomic
def record_invoice(*, purchase_order, actor, invoice_number, invoice_date, due_date, amount, note=''):
    po = PurchaseOrder.objects.select_for_update().select_related('supplier', 'branch').get(pk=purchase_order.pk)
    actor_can_manage(actor, po.branch)
    if po.status not in (PurchaseOrder.Status.ORDERED, PurchaseOrder.Status.PARTIAL, PurchaseOrder.Status.RECEIVED):
        raise ValidationError('Only submitted, non-cancelled purchase orders can have supplier invoices.')
    number = (invoice_number or '').strip().upper()
    if not (2 <= len(number) <= 80):
        raise ValidationError('Invoice number must be 2–80 characters.')
    if not invoice_date or not due_date or due_date < invoice_date:
        raise ValidationError('Due date must be on or after invoice date.')
    total = money(amount)
    billed = SupplierInvoice.objects.filter(purchase_order=po).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    if total > po_value(po) - billed:
        raise ValidationError('Total supplier invoices cannot exceed the committed purchase-order value.')
    if SupplierInvoice.objects.filter(supplier=po.supplier, invoice_number=number).exists():
        raise ValidationError('This supplier invoice number is already recorded.')
    try:
        with transaction.atomic():
            return SupplierInvoice.objects.create(
                purchase_order=po, supplier=po.supplier, invoice_number=number,
                invoice_date=invoice_date, due_date=due_date, amount=total,
                note=(note or '').strip()[:255], recorded_by=actor)
    except IntegrityError as exc:
        raise ValidationError('Supplier invoice number already exists.') from exc


@transaction.atomic
def record_payment(*, invoice, actor, amount, method, reference, paid_on, note=''):
    item = SupplierInvoice.objects.select_for_update().select_related('purchase_order__branch').get(pk=invoice.pk)
    actor_can_manage(actor, item.purchase_order.branch)
    paid = money(amount)
    if method not in SupplierPayment.Method.values:
        raise ValidationError('Choose a valid payment method.')
    ref = (reference or '').strip().upper()
    if not (3 <= len(ref) <= 100):
        raise ValidationError('An actual payment confirmation/reference is required (3–100 characters).')
    if not paid_on or paid_on > timezone.localdate():
        raise ValidationError('Only payments that have already happened can be recorded.')
    current = SupplierPayment.objects.filter(invoice=item).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    if current + paid > item.amount:
        raise ValidationError('Payment exceeds the outstanding invoice balance.')
    if SupplierPayment.objects.filter(invoice=item, reference=ref).exists():
        raise ValidationError('This payment reference is already recorded on the invoice.')
    try:
        with transaction.atomic():
            return SupplierPayment.objects.create(
                invoice=item, amount=paid, method=method, reference=ref,
                paid_on=paid_on, note=(note or '').strip()[:255], recorded_by=actor)
    except IntegrityError as exc:
        raise ValidationError('This payment reference is already recorded.') from exc
