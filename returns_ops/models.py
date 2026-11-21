"""Append-only sale return history. Original receipts are never edited."""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator

from pos.models import Sale, SaleItem


class ReturnRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = 'REQUESTED', 'Awaiting manager review'
        APPROVED = 'APPROVED', 'Return approved'
        REJECTED = 'REJECTED', 'Rejected'

    class RefundStatus(models.TextChoices):
        PENDING = 'PENDING', 'Refund not yet recorded as paid'
        RECORDED = 'RECORDED', 'Refund manually recorded as paid'

    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='return_requests')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='return_requests_created')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REQUESTED)
    reason = models.TextField(max_length=500)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='returns_reviewed')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=300, blank=True)
    restocked = models.BooleanField(default=False)
    refund_status = models.CharField(max_length=12, choices=RefundStatus.choices, default=RefundStatus.PENDING)
    refund_method = models.CharField(max_length=10, choices=Sale.PaymentMethod.choices, blank=True)
    refund_reference = models.CharField(max_length=120, blank=True)
    refunded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='refunds_recorded')
    refunded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-pk')
        indexes = [models.Index(fields=['status', 'created_at'], name='returns_ops_status_44ab9f_idx')]

    def __str__(self):
        return f'Return #{self.pk} · {self.sale.receipt_number}'


class ReturnLine(models.Model):
    request = models.ForeignKey(ReturnRequest, on_delete=models.PROTECT, related_name='lines')
    sale_item = models.ForeignKey(SaleItem, on_delete=models.PROTECT, related_name='return_lines')
    quantity = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))])
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])

    class Meta:
        constraints = [models.UniqueConstraint(fields=['request', 'sale_item'], name='returns_one_line_per_request')]

    def __str__(self):
        return f'{self.sale_item.sku} × {self.quantity}'
