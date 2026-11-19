"""Transactional service functions. Keep attendance and leave decisions out of templates."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Attendance, LeaveRequest


@transaction.atomic
def clock_in(profile):
    if Attendance.objects.filter(profile=profile, work_date=timezone.localdate()).exists():
        raise ValidationError('You have already checked in today.')
    return Attendance.objects.create(profile=profile, work_date=timezone.localdate(), checked_in_at=timezone.now())


@transaction.atomic
def clock_out(profile):
    attendance = Attendance.objects.select_for_update().filter(
        profile=profile, work_date=timezone.localdate()
    ).first()
    if attendance is None:
        raise ValidationError('Check in before checking out.')
    if attendance.checked_out_at is not None:
        raise ValidationError('You have already checked out today.')
    attendance.checked_out_at = timezone.now()
    attendance.full_clean()
    attendance.save(update_fields=['checked_out_at'])
    return attendance


@transaction.atomic
def create_leave(profile, *, leave_type, starts_on, ends_on, reason=''):
    request = LeaveRequest(profile=profile, leave_type=leave_type,
                           starts_on=starts_on, ends_on=ends_on, reason=reason)
    request.full_clean()
    overlapping = LeaveRequest.objects.filter(
        profile=profile,
        status__in=(LeaveRequest.Status.PENDING, LeaveRequest.Status.APPROVED),
        starts_on__lte=ends_on, ends_on__gte=starts_on,
    ).exists()
    if overlapping:
        raise ValidationError('You already have a pending or approved leave request for these dates.')
    request.save()
    return request


@transaction.atomic
def decide_leave(leave_request, *, actor, approve, note=''):
    locked = LeaveRequest.objects.select_for_update().select_related('profile__user', 'profile__branch').get(pk=leave_request.pk)
    if locked.status != LeaveRequest.Status.PENDING:
        raise ValidationError('This leave request has already been processed.')
    if locked.profile.user_id == actor.pk:
        raise ValidationError('You cannot approve your own leave.')
    locked.status = LeaveRequest.Status.APPROVED if approve else LeaveRequest.Status.REJECTED
    locked.reviewed_by = actor
    locked.reviewed_at = timezone.now()
    locked.review_note = (note or '').strip()[:1200]
    if not approve and not locked.review_note:
        raise ValidationError('Provide a reason for rejecting leave.')
    locked.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_note'])
    return locked


@transaction.atomic
def cancel_leave(leave_request, *, actor):
    locked = LeaveRequest.objects.select_for_update().get(pk=leave_request.pk)
    if locked.profile.user_id != actor.pk or locked.status != LeaveRequest.Status.PENDING:
        raise ValidationError('Only your own pending leave requests may be cancelled.')
    locked.status = LeaveRequest.Status.CANCELLED
    locked.save(update_fields=['status'])
    return locked
