"""Permission boundary: only approved cashiers, branch managers and superusers can sell."""

from django.core.exceptions import PermissionDenied
from django.http import Http404
from core.models import Branch, StaffProfile


def pos_branch(request):
    if request.user.is_superuser:
        available = Branch.objects.filter(active=True)
        raw = request.GET.get('branch') if request.method == 'GET' else request.POST.get('branch')
        if raw:
            if not raw.isascii() or not raw.isdigit():
                raise Http404('Invalid branch')
            selected = available.filter(pk=int(raw)).first()
            if not selected:
                raise Http404('Invalid branch')
            request.session['pos_branch_id'] = selected.pk
        branch_id = request.session.get('pos_branch_id')
        branch = available.filter(pk=branch_id).first() if branch_id else None
        return branch or available.order_by('name').first()

    try:
        profile = request.user.store_profile
    except StaffProfile.DoesNotExist:
        raise PermissionDenied('Your store account has no approved profile.')
    if not profile.is_approved or profile.role not in (StaffProfile.Role.CASHIER, StaffProfile.Role.MANAGER):
        raise PermissionDenied('An approved cashier or manager account is required.')
    if not profile.branch_id or not profile.branch.active:
        raise PermissionDenied('An active branch must be assigned to your account.')
    return profile.branch


def visible_sales(request):
    from .models import Sale
    branch = pos_branch(request)
    if request.user.is_superuser:
        return Sale.objects.all()
    if request.user.store_profile.role == StaffProfile.Role.MANAGER:
        return Sale.objects.filter(branch=branch)
    return Sale.objects.filter(branch=branch, cashier=request.user)


def may_verify_payments(request, sale):
    if request.user.is_superuser:
        return True
    profile = request.user.store_profile
    return (profile.is_approved and profile.role == StaffProfile.Role.MANAGER
            and profile.branch_id == sale.branch_id)
