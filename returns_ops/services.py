"""Atomic returns, controlled restocking and offline refund recording.

No network payouts are attempted here. Payment confirmation is an attestation
by a manager who independently executed / checked the actual refund.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.models import StaffProfile
from inventory.models import StockMovement
from inventory.services import record_stock_movement
from pos.models import Sale
from .models import ReturnLine, ReturnRequest

CENT = Decimal('0.01')


def can_review(user, sale):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    try:
        profile = user.store_profile
    except StaffProfile.DoesNotExist:
        return False
    return bool(profile.is_approved and profile.role == StaffProfile.Role.MANAGER
                and profile.branch_id == sale.branch_id and profile.branch.active)


def _ensure_requester(user, sale):
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied('An active account is required.')
    if user.is_superuser:
        return
    try:
        profile = user.store_profile
    except StaffProfile.DoesNotExist:
        raise PermissionDenied('Approved store account required.')
    if not profile.is_approved or not profile.branch_id or not profile.branch.active:
        raise PermissionDenied('Approved branch account required.')
    if profile.branch_id != sale.branch_id:
        raise PermissionDenied('Cannot process another branch sale.')
    if profile.role == StaffProfile.Role.MANAGER:
        return
    if profile.role != StaffProfile.Role.CASHIER or sale.cashier_id != user.pk:
        raise PermissionDenied('Cashiers can request returns only on their own receipts.')


def _parse_quantity(raw, sale_item):
    try:
        qty = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError('Enter a valid quantity.')
    if not qty.is_finite() or not Decimal('0') < qty <= Decimal('9999999.999'):
        raise ValidationError('Enter a positive quantity.')
    if qty.as_tuple().exponent < -3:
        raise ValidationError('Use no more than three decimal places.')
    if sale_item.unit not in ('KG', 'LITRE') and qty != qty.to_integral_value():
        raise ValidationError('Packaged products require whole units.')
    return qty.quantize(Decimal('0.001'))


def _money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@transaction.atomic
def request_return(*, sale, sale_item, actor, quantity, reason):
    # Lock the parent sale to serialize competing returns across individual line items.
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    _ensure_requester(actor, sale)
    if not sale_item or sale_item.sale_id != sale.pk:
        raise ValidationError('Choose an item from this exact receipt.')
    reason = (reason or '').strip()
    if len(reason) < 8 or len(reason) > 500:
        raise ValidationError('Explain the reason for return (8–500 characters).')
    if sale.payment_status == Sale.PaymentStatus.UNVERIFIED:
        raise ValidationError('Payment is unverified. A manager must verify it before a return is requested.')
    qty = _parse_quantity(quantity, sale_item)
    claimed = ReturnLine.objects.filter(
        sale_item=sale_item,
        request__status__in=(ReturnRequest.Status.REQUESTED, ReturnRequest.Status.APPROVED),
    ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
    if qty > sale_item.quantity - claimed:
        raise ValidationError('Requested quantity exceeds the unreturned units on this receipt.')
    # Derive returns from the ORIGINAL receipt, never the current catalogue price.
    previous = ReturnLine.objects.filter(
        sale_item=sale_item,
        request__status__in=(ReturnRequest.Status.REQUESTED, ReturnRequest.Status.APPROVED),
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    amount = min(_money(sale_item.line_total * qty / sale_item.quantity), sale_item.line_total - previous)
    if amount <= 0:
        raise ValidationError('This amount has already been returned or is too small to refund.')
    case = ReturnRequest.objects.create(sale=sale, requested_by=actor, reason=reason, amount=amount)
    ReturnLine.objects.create(request=case, sale_item=sale_item, quantity=qty, amount=amount)
    return case


@transaction.atomic
def review_return(*, case, actor, approve, restock=False, note=''):
    # Sale lock matches request_return lock order, helping avoid competing approvals.
    sale = Sale.objects.select_for_update().get(pk=case.sale_id)
    if not can_review(actor, sale):
        raise PermissionDenied('Manager or administrator permission required.')
    case = ReturnRequest.objects.select_for_update().get(pk=case.pk)
    if case.status != ReturnRequest.Status.REQUESTED:
        raise ValidationError('This return has already been reviewed.')
    if approve and sale.payment_status == Sale.PaymentStatus.UNVERIFIED:
        raise ValidationError('An unverified original payment cannot be refunded.')
    note = (note or '').strip()
    if len(note) > 300:
        raise ValidationError('Review note is too long (300 character maximum).')
    if not approve and len(note) < 5:
        raise ValidationError('Explain why this return is rejected (at least 5 characters).')
    if approve and restock:
        for line in case.lines.select_related('sale_item__product'):
            record_stock_movement(
                branch=sale.branch, product=line.sale_item.product, actor=actor,
                kind=StockMovement.Kind.CORRECTION_IN, quantity=line.quantity,
                reference=f'RETURN-{case.pk}', note='Inspected resaleable return; ' + note,
            )
    case.status = ReturnRequest.Status.APPROVED if approve else ReturnRequest.Status.REJECTED
    case.restocked = bool(approve and restock)
    case.reviewed_by = actor
    case.reviewed_at = timezone.now()
    case.review_note = note
    case.save(update_fields=['status', 'restocked', 'reviewed_by', 'reviewed_at', 'review_note'])
    return case


@transaction.atomic
def record_paid_refund(*, case, actor, method, reference, confirmed):
    sale = Sale.objects.select_for_update().get(pk=case.sale_id)
    if not can_review(actor, sale):
        raise PermissionDenied('Manager or administrator permission required.')
    case = ReturnRequest.objects.select_for_update().get(pk=case.pk)
    if case.status != ReturnRequest.Status.APPROVED:
        raise ValidationError('Approve the return before recording a refund payout.')
    if case.refund_status == ReturnRequest.RefundStatus.RECORDED:
        raise ValidationError('The refund has already been recorded as paid.')
    if confirmed is not True:
        raise ValidationError('Confirm that the refund was actually completed outside SmartMart.')
    if method not in Sale.PaymentMethod.values:
        raise ValidationError('Select a supported refund payment method.')
    reference = (reference or '').strip()
    if method != Sale.PaymentMethod.CASH and not (4 <= len(reference) <= 120):
        raise ValidationError('Record the provider transaction reference (4–120 characters).')
    if method == Sale.PaymentMethod.CASH and len(reference) > 120:
        raise ValidationError('Reference is too long.')
    case.refund_status = ReturnRequest.RefundStatus.RECORDED
    case.refund_method = method
    case.refund_reference = reference
    case.refunded_by = actor
    case.refunded_at = timezone.now()
    case.save(update_fields=['refund_status', 'refund_method', 'refund_reference', 'refunded_by', 'refunded_at'])
    return case
