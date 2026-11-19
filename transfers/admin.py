from django.contrib import admin
from .models import StockTransfer, StockTransferLine, TransferReceipt, TransferReceiptLine


class LinesInline(admin.TabularInline):
    model = StockTransferLine
    extra = 0
    readonly_fields = ('product', 'quantity', 'received_qty')
    can_delete = False
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(StockTransfer)
class TransferAdmin(admin.ModelAdmin):
    list_display = ('reference', 'source_branch', 'destination_branch', 'status', 'created_at', 'dispatched_at')
    list_filter = ('status', 'source_branch', 'destination_branch')
    search_fields = ('reference', 'source_branch__name', 'destination_branch__name')
    readonly_fields = ('reference', 'source_branch', 'destination_branch', 'status', 'notes', 'created_by', 'created_at', 'dispatched_by', 'dispatched_at')
    inlines = (LinesInline,)
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False


class ReceiptLinesInline(admin.TabularInline):
    model = TransferReceiptLine
    extra = 0
    readonly_fields = ('transfer_line', 'quantity')
    can_delete = False
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(TransferReceipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ('reference', 'transfer', 'received_by', 'created_at')
    readonly_fields = ('reference', 'transfer', 'received_by', 'created_at')
    inlines = (ReceiptLinesInline,)
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
