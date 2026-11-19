"""Permanent sale and receipt records. Never delete completed sales in production."""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.models import Branch
from inventory.models import Product


class Sale(models.Model):
    class SaleType(models.TextChoices):
        RETAIL = 'RETAIL', 'Retail'
        WHOLESALE = 'WHOLESALE', 'Wholesale'

    class PaymentMethod(models.TextChoices):
        CASH = 'CASH', 'Cash'
        MPESA = 'MPESA', 'M-Pesa (manual reference)'
        CARD = 'CARD', 'Card (manual reference)'
        BANK = 'BANK', 'Bank transfer (manual reference)'

    class PaymentStatus(models.TextChoices):
        CASH_RECEIVED = 'CASH_RECEIVED', 'Cash received'
        UNVERIFIED = 'UNVERIFIED', 'Awaiting independent payment verification'
        VERIFIED = 'VERIFIED', 'Verified by manager'

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='pos_sales')
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='pos_sales')
    sale_type = models.CharField(max_length=10, choices=SaleType.choices)
    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices)
    payment_reference = models.CharField(max_length=100, blank=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    included_tax = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tendered_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    change_due = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    checkout_token = models.CharField(max_length=64, unique=True)
    receipt_number = models.CharField(max_length=32, unique=True, null=True, blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='verified_pos_sales')
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-pk')
        indexes = [models.Index(fields=['branch', 'created_at']), models.Index(fields=['cashier', 'created_at'])]

    def __str__(self):
        return self.receipt_number or f'Sale #{self.pk or "new"}'


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='pos_sale_items')
    sku = models.CharField(max_length=48)
    description = models.CharField(max_length=170)
    unit = models.CharField(max_length=10)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
    included_tax = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ('pk',)

    def __str__(self):
        return f'{self.sku} x {self.quantity}'
