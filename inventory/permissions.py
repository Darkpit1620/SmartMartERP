from django.core.exceptions import PermissionDenied
from core.models import StaffProfile


def allowed_store_profile(request):
    if request.user.is_superuser:
        return None
    try:
        profile = request.user.store_profile
    except StaffProfile.DoesNotExist:
        raise PermissionDenied("This account has no store access profile.")
    if not profile.is_approved:
        raise PermissionDenied("Store access has not yet been approved.")
    return profile


def require_stock_staff(request):
    profile = allowed_store_profile(request)
    if profile and profile.role not in (StaffProfile.Role.MANAGER, StaffProfile.Role.WAREHOUSE):
        raise PermissionDenied("Stock changes require warehouse or manager permissions.")
    if profile and not profile.branch_id:
        raise PermissionDenied("Your account must have an assigned branch.")
    return profile
