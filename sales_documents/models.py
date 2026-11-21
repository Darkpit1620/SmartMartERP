"""Receipt presentation preferences and optional invoice customer details.

Completed POS Sale and SaleItem records remain the sole transaction source.
This module never adjusts stock, prices, payment status or tax records.
"""
from django.conf import settings
from django.db import models

from core.models import Branch
from pos.models import Sale


class BranchPrintBrand(models.Model):
    branch = models.OneToOneField(Branch, on_delete=models.PROTECT, related_name='print_brand')
    trade_name = models.CharField(max_length=140)
    business_number = models.CharField(max_length=65, blank=True)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=45, blank=True)
    email = models.EmailField(blank=True)
    footer = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   null=True, blank=True, related_name='updated_receipt_brands')

    def __str__(self):
        return f'{self.trade_name} ({self.branch.code})'


class SaleCustomerDetails(models.Model):
    sale = models.OneToOneField(Sale, on_delete=models.PROTECT, related_name='invoice_customer')
    customer_name = models.CharField(max_length=140, blank=True)
    customer_phone = models.CharField(max_length=45, blank=True)
    customer_email = models.EmailField(blank=True)
    customer_address = models.CharField(max_length=255, blank=True)
    customer_reference = models.CharField(max_length=70, blank=True)
    note = models.CharField(max_length=240, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   null=True, blank=True, related_name='edited_invoice_customers')

    def __str__(self):
        return f'Customer details for {self.sale.receipt_number}'


class CustomerDetailsEdit(models.Model):
    """Non-sensitive audit trail: stores modified field names, not duplicated PII."""
    details = models.ForeignKey(SaleCustomerDetails, on_delete=models.PROTECT, related_name='edit_history')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    changed_fields = models.CharField(max_length=200)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-changed_at', '-pk')

    def __str__(self):
        return f'Invoice details edited at {self.changed_at}'


def invoice_number(sale):
    """Unique, deterministic business-document ID; never a fiscal/eTIMS number."""
    return f'SMI-{sale.pk:010d}'
