"""Read-only admin audit views. Financial records are entered through secured workflows."""
from django.contrib import admin
from .models import SupplierInvoice, SupplierPayment


class ReadOnlyAuditAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_superuser)


@admin.register(SupplierInvoice)
class SupplierInvoiceAdmin(ReadOnlyAuditAdmin):
    list_display = ('invoice_number', 'supplier', 'purchase_order', 'invoice_date', 'due_date', 'amount', 'recorded_by')
    search_fields = ('invoice_number', 'supplier__name')


@admin.register(SupplierPayment)
class SupplierPaymentAdmin(ReadOnlyAuditAdmin):
    list_display = ('invoice', 'amount', 'method', 'reference', 'paid_on', 'recorded_by')
    search_fields = ('reference', 'invoice__invoice_number')
