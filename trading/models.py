"""Supplier purchases and wholesale trade, linked to existing branch inventory/POS."""
from decimal import Decimal
from uuid import uuid4


def new_trade_token():
    return uuid4().hex

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from core.models import Branch
from inventory.models import Product
from pos.models import Sale


class Supplier(models.Model):
    name = models.CharField(max_length=160, unique=True)
    contact_person = models.CharField(max_length=140, blank=True)
    phone = models.CharField(max_length=35, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        ORDERED = 'ORDERED', 'Sent / Ordered'
        PARTIAL = 'PARTIAL', 'Partially received'
        RECEIVED = 'RECEIVED', 'Fully received'
        CANCELLED = 'CANCELLED', 'Cancelled'

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='purchase_orders')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_purchase_orders')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True)
    ordered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-pk')

    @property
    def reference(self):
        return f'PO-{self.pk:07d}' if self.pk else 'Draft'

    def __str__(self):
        return f'{self.reference} · {self.supplier.name}'


class PurchaseOrderLine(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name='lines')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))])
    received_qty = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal('0.000'))
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])

    class Meta:
        constraints = [models.UniqueConstraint(fields=['order', 'product'], name='trading_unique_purchase_product')]
        ordering = ('pk',)

    @property
    def remaining(self):
        return max(self.quantity - self.received_qty, Decimal('0.000'))

    @property
    def line_total(self):
        return self.quantity * self.unit_cost


class GoodsReceipt(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name='receipts')
    delivery_note = models.CharField(max_length=100)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-pk')
        constraints = [models.UniqueConstraint(fields=['order', 'delivery_note'], name='trading_unique_delivery_note_per_po')]

    def __str__(self):
        return f'{self.order.reference} / {self.delivery_note}'


class GoodsReceiptLine(models.Model):
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.PROTECT, related_name='lines')
    purchase_line = models.ForeignKey(PurchaseOrderLine, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    stock_movement = models.OneToOneField('inventory.StockMovement', on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['receipt', 'purchase_line'], name='trading_unique_grn_line')]


class WholesaleCustomer(models.Model):
    name = models.CharField(max_length=160)
    business_name = models.CharField(max_length=160, blank=True)
    phone = models.CharField(max_length=35, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('name', 'pk')

    def __str__(self):
        return self.business_name or self.name


class WholesaleOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        READY = 'READY', 'Ready for checkout'
        FULFILLED = 'FULFILLED', 'Fulfilled / Sale completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='wholesale_orders')
    customer = models.ForeignKey(WholesaleCustomer, on_delete=models.PROTECT, related_name='orders')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_wholesale_orders')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True)
    checkout_token = models.CharField(max_length=64, unique=True, default=new_trade_token, editable=False)
    sale = models.OneToOneField(Sale, on_delete=models.PROTECT, null=True, blank=True, related_name='wholesale_order')
    created_at = models.DateTimeField(auto_now_add=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at', '-pk')

    @property
    def reference(self):
        return f'WO-{self.pk:07d}' if self.pk else 'Draft'

    def __str__(self):
        return f'{self.reference} · {self.customer}'


class WholesaleOrderLine(models.Model):
    order = models.ForeignKey(WholesaleOrder, on_delete=models.PROTECT, related_name='lines')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    quoted_unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['order', 'product'], name='trading_unique_wholesale_product')]
        ordering = ('pk',)

    @property
    def quoted_total(self):
        return self.quantity * self.quoted_unit_price
