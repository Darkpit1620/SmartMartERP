from django.core.exceptions import PermissionDenied
from core.models import Branch, StaffProfile


def finance_scope(user):
    """Return None for superuser (all branches) or a manager's single branch.

    Invalid/stale profiles are explicitly rejected, never treated as all-branch access.
    """
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied('Sign in to access financial reports.')
    if user.is_superuser:
        return None
    try:
        profile = user.store_profile
    except StaffProfile.DoesNotExist:
        raise PermissionDenied('An approved branch manager account is required.')
    if not profile.is_approved or profile.role != StaffProfile.Role.MANAGER:
        raise PermissionDenied('Only approved branch managers and administrators can view finances.')
    if not profile.branch_id or not profile.branch.active:
        raise PermissionDenied('An active assigned branch is required.')
    return profile.branch


def allowed_branches(user):
    selected = finance_scope(user)
    return Branch.objects.filter(active=True) if selected is None else Branch.objects.filter(pk=selected.pk)
