from django.contrib import admin
from .models import Attendance, EmployeeDetail, LeaveRequest


@admin.register(EmployeeDetail)
class EmployeeDetailAdmin(admin.ModelAdmin):
    list_display = ('profile', 'department', 'job_title', 'contract_type', 'start_date')
    list_filter = ('department', 'contract_type')
    search_fields = ('profile__user__username', 'profile__employee_id', 'department', 'job_title')
    autocomplete_fields = ('profile',)


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('profile', 'work_date', 'checked_in_at', 'checked_out_at')
    list_filter = ('work_date', 'profile__branch')
    search_fields = ('profile__user__username', 'profile__employee_id')
    readonly_fields = ('profile', 'work_date', 'checked_in_at', 'checked_out_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('profile', 'leave_type', 'starts_on', 'ends_on', 'status', 'reviewed_by')
    list_filter = ('status', 'leave_type', 'profile__branch')
    search_fields = ('profile__user__username', 'profile__employee_id')
    readonly_fields = ('profile', 'leave_type', 'starts_on', 'ends_on', 'reason', 'status', 'created_at', 'reviewed_at', 'reviewed_by', 'review_note')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
