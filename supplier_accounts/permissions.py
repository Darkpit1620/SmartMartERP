"""Financial supplier documents: superusers and approved branch managers only."""
from django.core.exceptions import PermissionDenied
from django.http import Http404
from core.models import Branch, StaffProfile


def permitted_branch(request):
    if request.user.is_superuser:
        selected = request.POST.get('branch') if request.method == 'POST' else request.GET.get('branch')
        if selected:
            if not selected.isascii() or not selected.isdecimal():
                raise Http404('Unknown branch')
            branch = Branch.objects.filter(pk=int(selected), active=True).first()
            if not branch:
                raise Http404('Unknown branch')
            return branch
        return Branch.objects.filter(active=True).order_by('name').first()
    try:
        profile = request.user.store_profile
    except StaffProfile.DoesNotExist:
        raise PermissionDenied('Not an approved branch manager')
    if not (request.user.is_active and profile.is_approved and profile.role == 'MANAGER'
            and profile.branch_id and profile.branch.active):
        raise PermissionDenied('Not an approved branch manager')
    return profile.branch


def actor_can_manage(actor, branch):
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise PermissionDenied('An active manager account is required.')
    if actor.is_superuser:
        return
    try:
        profile = actor.store_profile
    except StaffProfile.DoesNotExist:
        raise PermissionDenied('No manager profile')
    if not (profile.is_approved and profile.role == 'MANAGER'
            and profile.branch_id == branch.pk and profile.branch.active):
        raise PermissionDenied('Cannot manage this branch supplier account')


def ensure_invoice_branch(invoice, branch):
    if branch is None or invoice.purchase_order.branch_id != branch.pk:
        raise Http404('Invoice not found at this branch')
