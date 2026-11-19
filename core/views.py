from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect
from .models import StaffProfile


ROLE_PORTALS = {
    "MANAGER": {
        "name": "Branch Manager",
        "slug": "manager_portal",
        "tagline": "Keep your branch organised, informed and ready for customers.",
        "modules": [
            ("Sales overview", "Branch sales and shifts will appear when POS is enabled.", "chart-no-axes-combined"),
            ("Team operations", "Track cashiers and scheduled store staff.", "users"),
            ("Stock health", "Monitor replenishment and stock movement.", "boxes"),
        ],
    },
    "CASHIER": {
        "name": "Cashier",
        "slug": "cashier_portal",
        "tagline": "A simple workspace for quick, accurate customer service.",
        "modules": [
            ("Checkout / POS", "Barcode sales and receipts arrive in Stage 3.", "scan-line"),
            ("My shift", "Cash drawer and end-of-shift reconciliation.", "clock-4"),
            ("Returns", "Verified returns and refunds workflow.", "receipt"),
        ],
    },
    "WAREHOUSE": {
        "name": "Warehouse",
        "slug": "warehouse_portal",
        "tagline": "Keep shelves stocked and every movement accounted for.",
        "modules": [
            ("Inventory", "Stock on hand and barcode records arrive next.", "package"),
            ("Goods received", "Record supplier deliveries and discrepancies.", "truck"),
            ("Transfers", "Move products between branches with approvals.", "warehouse"),
        ],
    },
    "STAFF": {
        "name": "Store Staff",
        "slug": "staff_portal",
        "tagline": "Your assigned duties, branch updates and store information.",
        "modules": [
            ("My tasks", "Assigned work will appear here in a later stage.", "list-todo"),
            ("Branch noticeboard", "Store updates and announcements.", "megaphone"),
            ("My profile", "Your assigned branch and employee role.", "badge-check"),
        ],
    },
}


def home(request):
    return render(request, "core/home.html")


@login_required
def dashboard(request):
    if request.user.is_superuser:
        return redirect("core:admin_portal")
    try:
        profile = request.user.store_profile
    except StaffProfile.DoesNotExist:
        raise PermissionDenied("No store role is assigned to this account.")
    if not profile.is_approved:
        raise PermissionDenied("Your store account has not been approved.")
    return redirect(f"core:{ROLE_PORTALS[profile.role]['slug']}")


@login_required
def _portal(request, role):
    if role == "ADMIN":
        if not request.user.is_superuser:
            raise PermissionDenied("This area requires a superuser account.")
        return render(request, "core/admin_portal.html")
    if request.user.is_superuser:
        raise PermissionDenied("Use the administrator portal instead.")
    try:
        profile = request.user.store_profile
    except StaffProfile.DoesNotExist:
        raise PermissionDenied("No store role is assigned to this account.")
    if not profile.is_approved or profile.role != role:
        raise PermissionDenied("You do not have access to this workspace.")
    return render(
        request,
        "core/staff_portal.html",
        {"profile": profile, "workspace": ROLE_PORTALS[role]},
    )


def admin_portal(request):
    return _portal(request, "ADMIN")


def manager_portal(request):
    return _portal(request, "MANAGER")


def cashier_portal(request):
    return _portal(request, "CASHIER")


def warehouse_portal(request):
    return _portal(request, "WAREHOUSE")


def staff_portal(request):
    return _portal(request, "STAFF")
