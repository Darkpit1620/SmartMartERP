from django.core.exceptions import PermissionDenied
from core.models import StaffProfile


def permitted_branch(request, *, manager=False):
    """Admin has global access; approved cashier/manager only own active branch."""
    if request.user.is_superuser and request.user.is_active:
        return None
    try:
        p = request.user.store_profile
    except StaffProfile.DoesNotExist:
        raise PermissionDenied('Approved supermarket staff account required.')
    allowed = (StaffProfile.Role.MANAGER,) if manager else (StaffProfile.Role.MANAGER, StaffProfile.Role.CASHIER)
    if not (request.user.is_active and p.is_approved and p.role in allowed and p.branch_id and p.branch.active):
        raise PermissionDenied('Approved branch cashier or manager required.')
    return p.branch
