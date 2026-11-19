from django.contrib import admin
from .models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('id', 'branch', 'incurred_on', 'category', 'amount', 'status', 'recorded_by', 'reviewed_by')
    list_filter = ('branch', 'category', 'status', 'incurred_on')
    search_fields = ('reference', 'description', 'branch__code', 'recorded_by__username')
    readonly_fields = ('branch', 'incurred_on', 'category', 'amount', 'reference', 'description',
                       'status', 'recorded_by', 'created_at', 'reviewed_by', 'reviewed_at', 'review_note')

    def has_add_permission(self, request):
        return False  # Record through the secured Finance form.

    def has_change_permission(self, request, obj=None):
        return False  # Approval must use the audited, transactional Finance workflow.

    def has_delete_permission(self, request, obj=None):
        return False  # Financial audit history is never deleted through Admin.
