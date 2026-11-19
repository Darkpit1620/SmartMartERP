from django.contrib import admin
from .models import Sale, SaleItem


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    can_delete = False
    readonly_fields = ('product', 'sku', 'description', 'unit', 'quantity', 'unit_price', 'tax_rate', 'line_total', 'included_tax')
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('receipt_number', 'branch', 'cashier', 'sale_type', 'subtotal', 'payment_method', 'payment_status', 'created_at')
    list_filter = ('branch', 'payment_method', 'payment_status', 'sale_type')
    search_fields = ('receipt_number', 'cashier__username', 'payment_reference')
    readonly_fields = [f.name for f in Sale._meta.fields]
    inlines = [SaleItemInline]
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ('sale', 'sku', 'quantity', 'unit_price', 'line_total')
    search_fields = ('sale__receipt_number', 'sku')
    readonly_fields = [f.name for f in SaleItem._meta.fields]
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser
    def has_delete_permission(self, request, obj=None):
        return False
