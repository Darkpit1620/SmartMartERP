"""Persisted, non-destructive cashier shift and cash-drawer audit trail."""
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.core.validators import MinValueValidator

from core.models import Branch


class CashierShift(models.Model):
    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        CLOSED = 'CLOSED', 'Awaiting review'
        REVIEWED = 'REVIEWED', 'Reviewed'

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='cashier_shifts')
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='cashier_shifts')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    opening_cash = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='closed_cashier_shifts')
    closing_cash = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cash_sales = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    paid_in_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    paid_out_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    expected_cash = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    variance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    closing_note = models.CharField(max_length=300, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='reviewed_cashier_shifts')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ('-opened_at', '-pk')
        constraints = [models.UniqueConstraint(fields=['cashier'], condition=Q(status='OPEN'), name='shiftops_one_open_per_cashier')]
        indexes = [models.Index(fields=['branch', 'opened_at'], name='shiftops_branch_open_idx')]

    def __str__(self):
        return f'Shift #{self.pk} · {self.cashier.username}'


class CashDrawerEntry(models.Model):
    class Kind(models.TextChoices):
        PAID_IN = 'IN', 'Cash added to drawer'
        PAID_OUT = 'OUT', 'Cash taken from drawer'

    shift = models.ForeignKey(CashierShift, on_delete=models.PROTECT, related_name='entries')
    kind = models.CharField(max_length=3, choices=Kind.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    reference = models.CharField(max_length=100)
    note = models.CharField(max_length=300)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='cash_drawer_entries')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('created_at', 'pk')
        constraints = [models.UniqueConstraint(fields=['shift', 'reference'], name='shiftops_unique_entry_reference')]

    def __str__(self):
        return f'{self.get_kind_display()} · KES {self.amount}'
