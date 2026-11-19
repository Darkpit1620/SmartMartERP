from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import StaffProfile


class EmployeeDetail(models.Model):
    """Optional, admin-managed employment details; identity and access remain in core.StaffProfile."""
    class Contract(models.TextChoices):
        FULL_TIME = 'FULL_TIME', 'Full-time'
        PART_TIME = 'PART_TIME', 'Part-time'
        TEMPORARY = 'TEMPORARY', 'Temporary'
        CONTRACT = 'CONTRACT', 'Fixed-term contract'

    profile = models.OneToOneField(StaffProfile, related_name='hr_detail', on_delete=models.PROTECT)
    department = models.CharField(max_length=100, blank=True)
    job_title = models.CharField(max_length=120, blank=True)
    contract_type = models.CharField(max_length=15, choices=Contract.choices, default=Contract.FULL_TIME)
    start_date = models.DateField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'HR details: {self.profile.user.username}'


class Attendance(models.Model):
    profile = models.ForeignKey(StaffProfile, on_delete=models.PROTECT, related_name='attendance_entries')
    work_date = models.DateField(default=timezone.localdate)
    checked_in_at = models.DateTimeField()
    checked_out_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ('-work_date', '-checked_in_at')
        constraints = [models.UniqueConstraint(fields=('profile', 'work_date'), name='workforce_one_attendance_day')]
        indexes = [models.Index(fields=('work_date', 'profile'))]

    def clean(self):
        if self.checked_out_at and self.checked_out_at < self.checked_in_at:
            raise ValidationError('Check-out cannot be earlier than check-in.')

    def __str__(self):
        return f'{self.profile.user.username}: {self.work_date}'


class LeaveRequest(models.Model):
    class Type(models.TextChoices):
        ANNUAL = 'ANNUAL', 'Annual leave'
        SICK = 'SICK', 'Sick leave'
        UNPAID = 'UNPAID', 'Unpaid leave'
        COMPASSIONATE = 'COMPASSIONATE', 'Compassionate leave'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending review'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        CANCELLED = 'CANCELLED', 'Cancelled by employee'

    profile = models.ForeignKey(StaffProfile, on_delete=models.PROTECT, related_name='leave_requests')
    leave_type = models.CharField(max_length=16, choices=Type.choices)
    starts_on = models.DateField()
    ends_on = models.DateField()
    reason = models.TextField(max_length=1200, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.PROTECT, related_name='workforce_leave_reviews')
    review_note = models.TextField(max_length=1200, blank=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [models.Index(fields=('status', 'starts_on'))]

    def clean(self):
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError('The leave end date must not be before the start date.')

    def __str__(self):
        return f'{self.profile.user.username}: {self.starts_on} to {self.ends_on} ({self.status})'
