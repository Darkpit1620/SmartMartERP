from django.core.exceptions import PermissionDenied
from django.http import Http404
from core.models import Branch, StaffProfile


def employee_branch(request, *, manager_only=False):
    """Never allow arbitrary branch IDs to broaden a staff member's access."""
    if request.user.is_superuser:
        return None
    try:
        p = request.user.store_profile
    except StaffProfile.DoesNotExist:
        raise PermissionDenied('No approved employee profile exists.')
    roles = (StaffProfile.Role.MANAGER,) if manager_only else (StaffProfile.Role.MANAGER, StaffProfile.Role.WAREHOUSE)
    if not p.is_approved or p.role not in roles or not p.branch_id or not p.branch.active:
        raise PermissionDenied('Only approved branch managers or warehouse staff may use transfers.')
    return p.branch


def scoped_transfer(request, transfer, *, operation='view'):
    branch = employee_branch(request, manager_only=(operation in ('create', 'edit')))
    if branch is None:
        return
    allowed = {
        'view': (transfer.source_branch_id, transfer.destination_branch_id),
        'edit': (transfer.source_branch_id,),
        'dispatch': (transfer.source_branch_id,),
        'receive': (transfer.destination_branch_id,),
    }
    if branch.pk not in allowed.get(operation, ()):
        # Hide transfers from unrelated branches.
        raise Http404('Transfer not found for this branch.')
