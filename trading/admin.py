from django.contrib import admin
from .models import (Supplier, WholesaleCustomer, PurchaseOrder, PurchaseOrderLine,
                     GoodsReceipt, GoodsReceiptLine, WholesaleOrder, WholesaleOrderLine)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_person', 'phone', 'email', 'is_active')
    search_fields = ('name', 'contact_person', 'phone')
    list_filter = ('is_active',)


@admin.register(WholesaleCustomer)
class WholesaleCustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'business_name', 'phone', 'is_active')
    search_fields = ('name', 'business_name', 'phone')
    list_filter = ('is_active',)


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0
    readonly_fields = ('product', 'quantity', 'received_qty', 'unit_cost')
    can_delete = False
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'supplier', 'branch', 'status', 'created_at')
    list_filter = ('status', 'branch')
    search_fields = ('supplier__name',)
    readonly_fields = ('branch', 'supplier', 'created_by', 'status', 'notes', 'ordered_at')
    inlines = [PurchaseItemInline]
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GoodsReceipt)
class GoodsReceiptAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'delivery_note', 'recorded_by', 'created_at')
    readonly_fields = ('order', 'delivery_note', 'recorded_by', 'created_at')
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WholesaleOrder)
class WholesaleOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'branch', 'status', 'sale', 'created_at')
    list_filter = ('status', 'branch')
    readonly_fields = ('branch', 'customer', 'created_by', 'status', 'notes', 'checkout_token', 'sale', 'fulfilled_at')
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
