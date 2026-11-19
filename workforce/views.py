from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone

from core.models import StaffProfile
from .forms import LeaveRequestForm
from .models import Attendance, EmployeeDetail, LeaveRequest
from .permissions import employee_profile, manager_profile
from .services import cancel_leave, clock_in, clock_out, create_leave, decide_leave


@login_required
@require_GET
def home(request):
    if request.user.is_superuser:
        return redirect('workforce:team')
    profile = employee_profile(request.user)
    today = Attendance.objects.filter(profile=profile, work_date=timezone.localdate()).first()
    history = Attendance.objects.filter(profile=profile).order_by('-work_date')[:12]
    leaves = LeaveRequest.objects.filter(profile=profile)[:8]
    detail = EmployeeDetail.objects.filter(profile=profile).first()
    return render(request, 'workforce/home.html', {
        'profile': profile, 'today': today, 'history': history, 'leaves': leaves,
        'detail': detail, 'is_manager': profile.role == StaffProfile.Role.MANAGER,
    })


@login_required
@require_POST
def attendance_action(request, action):
    profile = employee_profile(request.user)
    try:
        if action == 'in':
            clock_in(profile)
            messages.success(request, 'Checked in successfully.')
        elif action == 'out':
            clock_out(profile)
            messages.success(request, 'Checked out successfully.')
        else:
            raise Http404('Unknown attendance action.')
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    return redirect('workforce:home')


@login_required
@require_GET
def my_leaves(request):
    profile = employee_profile(request.user)
    return render(request, 'workforce/my_leaves.html', {
        'requests': LeaveRequest.objects.filter(profile=profile),
    })


@login_required
def request_leave(request):
    profile = employee_profile(request.user)
    form = LeaveRequestForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            create_leave(profile=profile, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Your leave request has been sent for approval.')
            return redirect('workforce:my_leaves')
    return render(request, 'workforce/request_leave.html', {'form': form})


@login_required
@require_POST
def cancel_my_leave(request, pk):
    profile = employee_profile(request.user)
    record = get_object_or_404(LeaveRequest, pk=pk, profile=profile)
    try:
        cancel_leave(record, actor=request.user)
        messages.success(request, 'Your pending leave request was cancelled.')
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    return redirect('workforce:my_leaves')


def team_scope(user):
    manager = manager_profile(user)
    if manager is None:
        return StaffProfile.objects.select_related('user', 'branch').all()
    return StaffProfile.objects.select_related('user', 'branch').filter(branch_id=manager.branch_id)


@login_required
@require_GET
def team(request):
    profiles = team_scope(request.user).order_by('branch__name', 'user__username')
    return render(request, 'workforce/team.html', {'profiles': profiles})


@login_required
@require_GET
def team_attendance(request):
    qs = Attendance.objects.select_related('profile__user', 'profile__branch')
    manager = manager_profile(request.user)
    if manager is not None:
        qs = qs.filter(profile__branch_id=manager.branch_id)
    day = request.GET.get('date', '')
    if day:
        try:
            from datetime import date
            date.fromisoformat(day)
        except ValueError:
            messages.error(request, 'Invalid date filter.')
            day = ''
    if day:
        qs = qs.filter(work_date=day)
    else:
        qs = qs.filter(work_date=timezone.localdate())
    return render(request, 'workforce/team_attendance.html', {
        'entries': qs.order_by('profile__user__username')[:200], 'selected_date': day or str(timezone.localdate()),
    })


@login_required
@require_GET
def team_leaves(request):
    manager = manager_profile(request.user)
    qs = LeaveRequest.objects.select_related('profile__user', 'profile__branch', 'reviewed_by')
    if manager is not None:
        qs = qs.filter(profile__branch_id=manager.branch_id)
    status = request.GET.get('status', 'PENDING').upper()
    if status not in {'PENDING', 'APPROVED', 'REJECTED', 'CANCELLED', 'ALL'}:
        status = 'PENDING'
    if status != 'ALL':
        qs = qs.filter(status=status)
    requests = list(qs[:150])
    for item in requests:
        item.can_review = (
            item.status == LeaveRequest.Status.PENDING
            and item.profile.user_id != request.user.pk
            and (manager is None or item.profile.role != StaffProfile.Role.MANAGER)
        )
    return render(request, 'workforce/team_leaves.html', {
        'requests': requests, 'selected_status': status,
    })


@login_required
@require_POST
def review_leave(request, pk):
    manager = manager_profile(request.user)
    qs = LeaveRequest.objects.select_related('profile__user', 'profile__branch')
    if manager is not None:
        qs = qs.filter(profile__branch_id=manager.branch_id)
    record = get_object_or_404(qs, pk=pk)
    if manager is not None and record.profile.role == StaffProfile.Role.MANAGER:
        raise PermissionDenied('Manager leave requires an administrator to approve it.')
    action = request.POST.get('action')
    if action not in ('approve', 'reject'):
        raise Http404('Unknown review action.')
    try:
        decide_leave(record, actor=request.user, approve=(action == 'approve'),
                     note=request.POST.get('note', ''))
        messages.success(request, 'Leave request reviewed successfully.')
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    return redirect('workforce:team_leaves')
