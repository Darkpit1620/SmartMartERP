from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from core.models import StaffProfile
from .models import CashierShift
from .services import (
    allowed_shifts, open_shift, add_drawer_entry,
    close_shift, review_shift, cash_totals, cash_sales_for,
)


def _is_cashier(user):
    try:
        p = user.store_profile
        return bool(user.is_active and p.is_approved and p.branch_id and p.branch.active and p.role == StaffProfile.Role.CASHIER)
    except StaffProfile.DoesNotExist:
        return False


def _can_manage(user, shift):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    try:
        p = user.store_profile
        return bool(p.is_approved and p.branch_id == shift.branch_id
                    and p.branch.active and p.role == StaffProfile.Role.MANAGER)
    except StaffProfile.DoesNotExist:
        return False


def _report_errors(request, error):
    for item in error.messages[:4]:
        messages.error(request, item)


@login_required
@require_GET
def home(request):
    query = allowed_shifts(request.user).select_related('cashier', 'branch', 'reviewed_by')
    page = Paginator(query, 25).get_page(request.GET.get('page'))
    mine = query.filter(cashier=request.user, status=CashierShift.Status.OPEN).first() if _is_cashier(request.user) else None
    return render(request, 'shift_ops/home.html', {'page': page, 'my_open_shift': mine, 'can_open': _is_cashier(request.user)})


@login_required
@require_POST
def start(request):
    try:
        shift = open_shift(actor=request.user, opening_cash=request.POST.get('opening_cash'))
    except ValidationError as exc:
        _report_errors(request, exc)
        return redirect('shift_ops:home')
    messages.success(request, f'Shift #{shift.pk} opened. Opening float recorded in KES.')
    return redirect('shift_ops:detail', pk=shift.pk)


@login_required
@require_GET
def detail(request, pk):
    shift = get_object_or_404(allowed_shifts(request.user).select_related('cashier', 'branch', 'closed_by', 'reviewed_by'), pk=pk)
    totals = cash_totals(shift) if shift.status == CashierShift.Status.OPEN else {
        'cash_sales': shift.cash_sales, 'paid_in_total': shift.paid_in_total,
        'paid_out_total': shift.paid_out_total, 'expected_cash': shift.expected_cash,
    }
    at = shift.closed_at if shift.closed_at else totals.get('as_of')
    sales = cash_sales_for(shift, at).order_by('-created_at', '-pk')[:100]
    can_manage = _can_manage(request.user, shift)
    can_close = can_manage or (_is_cashier(request.user) and request.user.pk == shift.cashier_id)
    return render(request, 'shift_ops/detail.html', {
        'shift': shift, 'totals': totals, 'entries': shift.entries.select_related('recorded_by').all(),
        'sales': sales, 'can_manage': can_manage, 'can_close': can_close,
    })


@login_required
@require_POST
def entry(request, pk):
    shift = get_object_or_404(allowed_shifts(request.user), pk=pk)
    if not _can_manage(request.user, shift):
        raise PermissionDenied('Branch manager approval required.')
    try:
        add_drawer_entry(shift=shift, actor=request.user, kind=request.POST.get('kind'),
                         amount=request.POST.get('amount'), reference=request.POST.get('reference'),
                         note=request.POST.get('note'))
    except ValidationError as exc:
        _report_errors(request, exc)
    else:
        messages.success(request, 'Physical drawer movement recorded. No payment was made by SmartMart.')
    return redirect('shift_ops:detail', pk=pk)


@login_required
@require_POST
def finish(request, pk):
    shift = get_object_or_404(allowed_shifts(request.user), pk=pk)
    try:
        close_shift(shift=shift, actor=request.user, counted_cash=request.POST.get('closing_cash'),
                    note=request.POST.get('note', ''))
    except ValidationError as exc:
        _report_errors(request, exc)
    else:
        messages.success(request, 'Cashier shift closed. Expected cash and variance are now saved for manager review.')
    return redirect('shift_ops:detail', pk=pk)


@login_required
@require_POST
def review(request, pk):
    shift = get_object_or_404(allowed_shifts(request.user), pk=pk)
    if not _can_manage(request.user, shift):
        raise PermissionDenied('Only branch managers can review a closed shift.')
    try:
        review_shift(shift=shift, actor=request.user, note=request.POST.get('note', ''))
    except ValidationError as exc:
        _report_errors(request, exc)
    else:
        messages.success(request, 'Shift reviewed. Recorded totals and variance remain unchanged.')
    return redirect('shift_ops:detail', pk=pk)
