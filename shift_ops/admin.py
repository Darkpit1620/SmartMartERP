from django.contrib import admin
from .models import CashDrawerEntry, CashierShift


class CashDrawerEntryInline(admin.TabularInline):
    model = CashDrawerEntry
    extra = 0
    can_delete = False
    fields = ('kind', 'amount', 'reference', 'note', 'recorded_by', 'created_at')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CashierShift)
class CashierShiftAdmin(admin.ModelAdmin):
    list_display = ('id', 'branch', 'cashier', 'status', 'opened_at', 'closed_at', 'expected_cash', 'variance')
    list_filter = ('status', 'branch')
    search_fields = ('cashier__username', 'branch__code')
    readonly_fields = [f.name for f in CashierShift._meta.fields]
    inlines = [CashDrawerEntryInline]
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_active and request.user.is_superuser)
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CashDrawerEntry)
class CashDrawerEntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'shift', 'kind', 'amount', 'reference', 'recorded_by', 'created_at')
    readonly_fields = [f.name for f in CashDrawerEntry._meta.fields]
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_active and request.user.is_superuser)
    def has_delete_permission(self, request, obj=None):
        return False
