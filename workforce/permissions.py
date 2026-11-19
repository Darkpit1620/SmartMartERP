from django.core.exceptions import PermissionDenied
from core.models import StaffProfile


def employee_profile(user):
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied('An active employee account is required.')
    try:
        profile = user.store_profile
    except StaffProfile.DoesNotExist:
        raise PermissionDenied('Your account has no store employee profile.')
    if not profile.is_approved or not profile.branch_id or not profile.branch.active:
        raise PermissionDenied('Your employee profile needs an approved, active branch.')
    return profile


def manager_profile(user):
    if user.is_superuser and user.is_active:
        return None
    profile = employee_profile(user)
    if profile.role != StaffProfile.Role.MANAGER:
        raise PermissionDenied('Only authorized managers can review employee records.')
    return profile
