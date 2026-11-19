import logging

from django.contrib import messages
from django.contrib.admin.models import CHANGE, ADDITION, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from core.models import Branch, StaffProfile
from .forms import BranchCreateForm, EmployeeCreateForm

logger = logging.getLogger(__name__)


def require_superuser(request):
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied("Only an active head-office administrator may manage employee accounts.")


def log_admin_change(request, instance, change_message, action_flag=CHANGE):
    LogEntry.objects.log_actions(
        user_id=request.user.pk,
        queryset=type(instance).objects.filter(pk=instance.pk),
        action_flag=action_flag,
        change_message=change_message,
        single_object=True,
    )


@login_required
@require_GET
def home(request):
    require_superuser(request)
    branch_filter = request.GET.get("branch", "")
    role_filter = request.GET.get("role", "")
    approval_filter = request.GET.get("status", "")
    profiles = StaffProfile.objects.select_related("user", "branch").order_by("user__username")
    if branch_filter.isdigit():
        profiles = profiles.filter(branch_id=int(branch_filter))
    if role_filter in StaffProfile.Role.values:
        profiles = profiles.filter(role=role_filter)
    if approval_filter == "approved":
        profiles = profiles.filter(is_approved=True)
    elif approval_filter == "pending":
        profiles = profiles.filter(is_approved=False)
    return render(request, "staff_activation/home.html", {
        "profiles": profiles,
        "branches": Branch.objects.order_by("name"),
        "branch_count": Branch.objects.count(),
        "active_branches": Branch.objects.filter(active=True).count(),
        "employee_count": StaffProfile.objects.count(),
        "approved_count": StaffProfile.objects.filter(is_approved=True).count(),
        "pending_count": StaffProfile.objects.filter(is_approved=False).count(),
        "role_options": StaffProfile.Role.choices,
        "selected_branch": branch_filter,
        "selected_role": role_filter,
        "selected_status": approval_filter,
    })


@login_required
def create_employee(request):
    require_superuser(request)
    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])
    form = EmployeeCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                data = form.cleaned_data
                user = get_user_model().objects.create_user(
                    username=data["username"],
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                    email=data["email"],
                    password=data["password1"],
                    is_staff=False,
                    is_superuser=False,
                )
                profile = StaffProfile.objects.create(
                    user=user, role=data["role"], branch=data["branch"],
                    is_approved=False,
                )
                # Unique, stable company ID. Never overwrite an existing number.
                candidate = f"SME-{profile.pk:07d}"
                if not StaffProfile.objects.filter(employee_id=candidate).exists():
                    profile.employee_id = candidate
                    profile.save(update_fields=["employee_id"])
                log_admin_change(request, profile, "Employee account created, pending approval", ADDITION)
        except IntegrityError:
            form.add_error(None, "Username, email or employee identifier conflicts with an existing account. Check and retry.")
        else:
            messages.success(request, f"Created {user.username}. Approve the account to enable login. Share the initial password securely; it is never emailed or stored in plain text.")
            return redirect("staff_activation:home")
    return render(request, "staff_activation/form.html", {
        "form": form,
        "heading": "Create employee account",
        "summary": "Select a role and an active branch. New employees remain pending until you approve them.",
        "password_controls": True,
    })


@login_required
def create_branch(request):
    require_superuser(request)
    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])
    form = BranchCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        branch = form.save()
        log_admin_change(request, branch, "Created branch", ADDITION)
        messages.success(request, f"Branch {branch.name} created successfully.")
        return redirect("staff_activation:home")
    return render(request, "staff_activation/form.html", {
        "form": form,
        "heading": "Add supermarket branch",
        "summary": "Create a real branch with its own code. Staff can only be assigned to active branches.",
    })


@login_required
@require_POST
def review_employee(request, pk):
    require_superuser(request)
    action = request.POST.get("action")
    if action not in ("approve", "suspend"):
        messages.error(request, "Choose a valid approval action.")
        return redirect("staff_activation:home")
    with transaction.atomic():
        profile = get_object_or_404(
            StaffProfile.objects.select_for_update().select_related("user", "branch"), pk=pk
        )
        if profile.user.is_superuser or profile.user.is_staff:
            raise PermissionDenied("Superusers and Django administration users cannot be managed as employees here.")
        if action == "approve":
            if not profile.branch_id or not profile.branch.active:
                messages.error(request, "Assign an active branch before approving this employee.")
                return redirect("staff_activation:home")
            if not profile.user.is_active:
                messages.error(request, "This user is inactive. Reactivate it through Django Admin before approval.")
                return redirect("staff_activation:home")
        new_value = action == "approve"
        if profile.is_approved != new_value:
            profile.is_approved = new_value
            profile.save(update_fields=["is_approved"])
            log_admin_change(request, profile, f"Employee access {'approved' if new_value else 'suspended'} by head-office admin")
            logger.info("employee access %s: profile=%s admin=%s", action, profile.pk, request.user.pk)
        messages.success(request, f"{profile.user.username}: access {'approved' if new_value else 'suspended'}.")
    return redirect("staff_activation:home")
