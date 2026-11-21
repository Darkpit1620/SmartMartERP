"""Supplier invoice ledger. Does not initiate or confirm external transfers."""
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from trading.models import PurchaseOrder, Supplier


class SupplierInvoice(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name='supplier_invoices')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='account_invoices')
    invoice_number = models.CharField(max_length=80)
    invoice_date = models.DateField()
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    note = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='supplier_invoices_entered')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-pk')
        constraints = [models.UniqueConstraint(fields=('supplier', 'invoice_number'), name='supplier_accounts_supplier_invoice_unique')]

    def __str__(self):
        return f'{self.supplier.name} · {self.invoice_number}'

    @property
    def paid_amount(self):
        return self.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    @property
    def balance(self):
        return max(self.amount - self.paid_amount, Decimal('0.00'))

    @property
    def state(self):
        if self.balance <= 0:
            return 'Paid'
        if self.due_date < timezone.localdate():
            return 'Overdue'
        if self.paid_amount:
            return 'Part paid'
        return 'Unpaid'


class SupplierPayment(models.Model):
    class Method(models.TextChoices):
        CASH = 'CASH', 'Cash'
        BANK = 'BANK', 'Bank transfer'
        MPESA = 'MPESA', 'M-Pesa'
        CARD = 'CARD', 'Card'
        OTHER = 'OTHER', 'Other'

    invoice = models.ForeignKey(SupplierInvoice, on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    method = models.CharField(max_length=12, choices=Method.choices)
    reference = models.CharField(max_length=100)
    paid_on = models.DateField()
    note = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='supplier_payments_entered')
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-recorded_at', '-pk')
        constraints = [models.UniqueConstraint(fields=('invoice', 'reference'), name='supplier_accounts_invoice_payment_ref_unique')]

    def __str__(self):
        return f'{self.invoice.invoice_number} · {self.amount} · {self.reference}'
