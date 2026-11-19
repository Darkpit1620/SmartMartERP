"""Warehouse dispatches and inter-branch receipts.

BranchStock continues to represent the sole verified stock quantity per branch.
Goods in transit are deliberately not counted as stock in either branch.
"""
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from core.models import Branch
from inventory.models import Product


class StockTransfer(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        IN_TRANSIT = 'IN_TRANSIT', 'In transit'
        PARTIAL = 'PARTIAL', 'Partially received'
        RECEIVED = 'RECEIVED', 'Fully received'
        CANCELLED = 'CANCELLED', 'Cancelled draft'

    reference = models.CharField(max_length=36, unique=True, null=True, blank=True, editable=False)
    source_branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='sent_transfers')
    destination_branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='incoming_transfers')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_stock_transfers')
    created_at = models.DateTimeField(auto_now_add=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    dispatched_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='dispatched_stock_transfers')

    class Meta:
        ordering = ('-created_at', '-pk')
        indexes = [models.Index(fields=['status', 'created_at'])]

    def __str__(self):
        return self.reference or f'Transfer #{self.pk}'


class StockTransferLine(models.Model):
    transfer = models.ForeignKey(StockTransfer, on_delete=models.PROTECT, related_name='lines')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))])
    received_qty = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal('0.000'), validators=[MinValueValidator(Decimal('0.000'))])

    class Meta:
        ordering = ('pk',)
        constraints = [models.UniqueConstraint(fields=['transfer', 'product'], name='transfer_unique_sku_per_transfer')]

    @property
    def remaining(self):
        return self.quantity - self.received_qty

    def __str__(self):
        return f'{self.product.sku} × {self.quantity}'


class TransferReceipt(models.Model):
    transfer = models.ForeignKey(StockTransfer, on_delete=models.PROTECT, related_name='receipts')
    reference = models.CharField(max_length=100)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-pk')
        constraints = [models.UniqueConstraint(fields=['transfer', 'reference'], name='unique_transfer_receipt_reference')]

    def __str__(self):
        return f'{self.transfer} / {self.reference}'


class TransferReceiptLine(models.Model):
    receipt = models.ForeignKey(TransferReceipt, on_delete=models.PROTECT, related_name='lines')
    transfer_line = models.ForeignKey(StockTransferLine, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))])

    class Meta:
        constraints = [models.UniqueConstraint(fields=['receipt', 'transfer_line'], name='unique_transfer_receipt_line')]
