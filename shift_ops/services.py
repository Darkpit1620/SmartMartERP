"""Shift reconciliation uses server-side receipts; never changes payments or POS rows.

Only CASH_RECEIVED sales are counted. Separate manager-attested entries represent
physical cash drawer movement; recording them does not transfer any funds.
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from core.models import StaffProfile
from pos.models import Sale
from .models import CashDrawerEntry, CashierShift

ZERO = Decimal('0.00')
LIMIT = Decimal('999999999999.99')


def parse_cash(value, *, allow_zero=True):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError('Enter a valid cash amount in KES.')
    if (not number.is_finite() or number < 0 or number > LIMIT
            or number.as_tuple().exponent < -2 or (not allow_zero and number == 0)):
        raise ValidationError('Enter a valid, nonnegative cash amount with at most two decimals.')
    return number.quantize(Decimal('0.01'))


def _profile(user):
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied('An active account is required.')
    try:
        profile = user.store_profile
    except StaffProfile.DoesNotExist:
        raise PermissionDenied('An approved employee profile is required.')
    if not profile.is_approved or not profile.branch_id or not profile.branch.active:
        raise PermissionDenied('An approved profile and active branch are required.')
    return profile


def allowed_shifts(user):
    """Superusers see all; managers their branch; cashiers only their shifts."""
    if user.is_authenticated and user.is_active and user.is_superuser:
        return CashierShift.objects.all()
    profile = _profile(user)
    if profile.role == StaffProfile.Role.MANAGER:
        return CashierShift.objects.filter(branch_id=profile.branch_id)
    if profile.role == StaffProfile.Role.CASHIER:
        return CashierShift.objects.filter(branch_id=profile.branch_id, cashier=user)
    raise PermissionDenied('Only cashiers and managers may view shifts.')


def _check_manager(user, shift):
    if user.is_authenticated and user.is_active and user.is_superuser:
        return
    profile = _profile(user)
    if profile.role != StaffProfile.Role.MANAGER or profile.branch_id != shift.branch_id:
        raise PermissionDenied('Only a manager assigned to this branch may approve cash movements.')


def _check_closer(user, shift, note):
    if user.pk == shift.cashier_id:
        profile = _profile(user)
        if profile.role != StaffProfile.Role.CASHIER or profile.branch_id != shift.branch_id:
            raise PermissionDenied('Cashier must still have an approved branch assignment.')
    else:
        _check_manager(user, shift)
        if len(note.strip()) < 8:
            raise ValidationError('Managers must give an emergency closing reason of at least eight characters.')


def cash_sales_for(shift, at_time):
    return Sale.objects.filter(
        cashier_id=shift.cashier_id, branch_id=shift.branch_id,
        created_at__gt=shift.opened_at, created_at__lte=at_time,
        payment_method=Sale.PaymentMethod.CASH,
        payment_status=Sale.PaymentStatus.CASH_RECEIVED,
    )


def cash_totals(shift, at_time=None):
    at_time = at_time or timezone.now()
    gross = cash_sales_for(shift, at_time).aggregate(v=Sum('subtotal'))['v'] or ZERO
    added = shift.entries.filter(kind=CashDrawerEntry.Kind.PAID_IN).aggregate(v=Sum('amount'))['v'] or ZERO
    removed = shift.entries.filter(kind=CashDrawerEntry.Kind.PAID_OUT).aggregate(v=Sum('amount'))['v'] or ZERO
    expected = shift.opening_cash + gross + added - removed
    return {'cash_sales': gross, 'paid_in_total': added, 'paid_out_total': removed,
            'expected_cash': expected, 'as_of': at_time}


def open_shift(*, actor, opening_cash):
    profile = _profile(actor)
    if profile.role != StaffProfile.Role.CASHIER:
        raise PermissionDenied('Only an approved cashier can open their own shift.')
    opening = parse_cash(opening_cash)
    try:
        with transaction.atomic():
            StaffProfile.objects.select_for_update().get(pk=profile.pk)
            if CashierShift.objects.filter(cashier=actor, status=CashierShift.Status.OPEN).exists():
                raise ValidationError('Close the existing open shift before opening another.')
            return CashierShift.objects.create(cashier=actor, branch=profile.branch, opening_cash=opening)
    except IntegrityError:
        raise ValidationError('An open shift already exists for this cashier.')


def add_drawer_entry(*, shift, actor, kind, amount, reference, note):
    if kind not in CashDrawerEntry.Kind.values:
        raise ValidationError('Select cash added or cash taken out.')
    value = parse_cash(amount, allow_zero=False)
    reference = (reference or '').strip()
    note = (note or '').strip()
    if not 3 <= len(reference) <= 100 or not 8 <= len(note) <= 300:
        raise ValidationError('Enter a reference (3–100 characters) and clear reason (8–300 characters).')
    try:
        with transaction.atomic():
            shift = CashierShift.objects.select_for_update().get(pk=shift.pk)
            _check_manager(actor, shift)
            if shift.status != CashierShift.Status.OPEN:
                raise ValidationError('Cash movement cannot be added after the shift is closed.')
            if CashDrawerEntry.objects.filter(shift=shift, reference=reference).exists():
                raise ValidationError('This cash-drawer reference was already recorded for the shift.')
            available = cash_totals(shift)['expected_cash']
            if kind == CashDrawerEntry.Kind.PAID_OUT and value > available:
                raise ValidationError('Cash taken out cannot exceed the expected drawer balance.')
            if kind == CashDrawerEntry.Kind.PAID_IN and available + value > LIMIT:
                raise ValidationError('Drawer balance exceeds the supported amount.')
            return CashDrawerEntry.objects.create(
                shift=shift, kind=kind, amount=value, reference=reference,
                note=note, recorded_by=actor,
            )
    except IntegrityError:
        raise ValidationError('This cash-drawer reference has already been used.')


def close_shift(*, shift, actor, counted_cash, note=''):
    count = parse_cash(counted_cash)
    note = (note or '').strip()
    if len(note) > 300:
        raise ValidationError('Closing note must be no longer than 300 characters.')
    with transaction.atomic():
        shift = CashierShift.objects.select_for_update().get(pk=shift.pk)
        _check_closer(actor, shift, note)
        if shift.status != CashierShift.Status.OPEN:
            raise ValidationError('This shift is already closed.')
        cutoff = timezone.now()
        totals = cash_totals(shift, cutoff)
        if totals['expected_cash'] < ZERO or totals['expected_cash'] > LIMIT:
            raise ValidationError('Expected cash is outside the supported range. Review cash-drawer entries.')
        variance = count - totals['expected_cash']
        shift.closed_at = cutoff
        shift.closed_by = actor
        shift.closing_cash = count
        shift.cash_sales = totals['cash_sales']
        shift.paid_in_total = totals['paid_in_total']
        shift.paid_out_total = totals['paid_out_total']
        shift.expected_cash = totals['expected_cash']
        shift.variance = variance
        shift.closing_note = note
        shift.status = CashierShift.Status.CLOSED
        shift.save(update_fields=[
            'closed_at', 'closed_by', 'closing_cash', 'cash_sales', 'paid_in_total',
            'paid_out_total', 'expected_cash', 'variance', 'closing_note', 'status',
        ])
        return shift


def review_shift(*, shift, actor, note=''):
    note = (note or '').strip()
    if len(note) > 300:
        raise ValidationError('Review note must be 300 characters or fewer.')
    with transaction.atomic():
        shift = CashierShift.objects.select_for_update().get(pk=shift.pk)
        _check_manager(actor, shift)
        if shift.status != CashierShift.Status.CLOSED:
            raise ValidationError('Only a closed, unreviewed shift can be approved.')
        if shift.variance != ZERO and len(note) < 8:
            raise ValidationError('Explain the difference between counted and expected cash (at least eight characters).')
        shift.status = CashierShift.Status.REVIEWED
        shift.reviewed_at = timezone.now()
        shift.reviewed_by = actor
        shift.review_note = note
        shift.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'review_note'])
        return shift
