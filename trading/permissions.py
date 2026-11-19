"""Approved branch staff only. Purchase and wholesale permissions differ."""
from django.core.exceptions import PermissionDenied
from django.http import Http404
from core.models import Branch, StaffProfile


def trade_branch(request, *, operation='view'):
    if request.user.is_superuser:
        selected_id = request.POST.get('branch') if request.method == 'POST' else request.GET.get('branch')
        if selected_id:
            if not selected_id.isascii() or not selected_id.isdecimal():
                raise Http404('Invalid branch')
            branch = Branch.objects.filter(pk=int(selected_id), active=True).first()
            if not branch:
                raise Http404('Unknown branch')
            request.session['trading_branch_id'] = branch.pk
            return branch
        branch = Branch.objects.filter(pk=request.session.get('trading_branch_id'), active=True).first()
        return branch or Branch.objects.filter(active=True).order_by('name').first()
    try:
        profile = request.user.store_profile
    except StaffProfile.DoesNotExist:
        raise PermissionDenied('No store employee profile is assigned.')
    if not profile.is_approved or not profile.branch_id or not profile.branch.active:
        raise PermissionDenied('An approved account with an active branch is required.')
    roles = {
        'view': ('MANAGER', 'WAREHOUSE'),
        'receive': ('MANAGER', 'WAREHOUSE'),
        'purchasing': ('MANAGER',),
        'wholesale': ('MANAGER',),
    }
    if profile.role not in roles.get(operation, ()):
        raise PermissionDenied('Your store role cannot access this operation.')
    return profile.branch


def ensure_branch(obj, branch):
    if branch is None or obj.branch_id != branch.pk:
        raise Http404('Order not found at your assigned branch.')
