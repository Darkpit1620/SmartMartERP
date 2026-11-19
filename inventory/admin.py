from django.contrib import admin
from .models import BranchStock, Category, Product, StockMovement


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "category", "retail_price", "wholesale_price", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("sku", "barcode", "name")
    autocomplete_fields = ("category",)


@admin.register(BranchStock)
class BranchStockAdmin(admin.ModelAdmin):
    list_display = ("branch", "product", "quantity", "updated_at")
    list_filter = ("branch",)
    search_fields = ("product__sku", "product__name", "branch__code")
    list_select_related = ("branch", "product")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("created_at", "branch", "product", "kind", "quantity", "balance_after", "reference", "recorded_by")
    list_filter = ("branch", "kind", "created_at")
    search_fields = ("product__sku", "reference")
    list_select_related = ("branch", "product", "recorded_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
