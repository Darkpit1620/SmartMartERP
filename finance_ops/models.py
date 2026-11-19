"""Branch expenses. Sales remain the single source of truth in pos.Sale."""

from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from core.models import Branch


class Expense(models.Model):
    class Category(models.TextChoices):
        RENT = 'RENT', 'Rent and premises'
        UTILITIES = 'UTILITIES', 'Utilities and electricity'
        TRANSPORT = 'TRANSPORT', 'Transport and fuel'
        MAINTENANCE = 'MAINTENANCE', 'Repairs and maintenance'
        PAYROLL = 'PAYROLL', 'Payroll and wages'
        MARKETING = 'MARKETING', 'Marketing and advertising'
        OFFICE = 'OFFICE', 'Office and administrative'
        OTHER = 'OTHER', 'Other approved operating expense'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Awaiting finance approval'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='operating_expenses')
    category = models.CharField(max_length=20, choices=Category.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2,
                                 validators=[MinValueValidator(Decimal('0.01'))])
    incurred_on = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=90, blank=True)
    description = models.CharField(max_length=350)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name='finance_expenses_recorded')
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.PROTECT, related_name='finance_expenses_reviewed')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=350, blank=True)

    class Meta:
        ordering = ('-incurred_on', '-pk')
        indexes = [models.Index(fields=('branch', 'incurred_on')),
                   models.Index(fields=('status', 'incurred_on'))]

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': 'Expense amount must be positive.'})
        if self.incurred_on and self.incurred_on > timezone.localdate():
            raise ValidationError({'incurred_on': 'Do not date an expense in the future.'})

    def __str__(self):
        return f'{self.branch.code} {self.category}: KES {self.amount} ({self.status})'
