from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth import get_user_model
from .models import Branch, StaffProfile


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "active")
    list_filter = ("active",)
    search_fields = ("name", "code")


@admin.action(description="Approve selected employee accounts")
def approve_profiles(modeladmin, request, queryset):
    approved = queryset.update(is_approved=True)
    modeladmin.message_user(request, f"Approved {approved} employee profile(s).")


@admin.action(description="Suspend selected employee accounts")
def suspend_profiles(modeladmin, request, queryset):
    suspended = queryset.update(is_approved=False)
    modeladmin.message_user(request, f"Suspended {suspended} employee profile(s).")


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "branch", "employee_id", "is_approved")
    list_filter = ("role", "branch", "is_approved")
    search_fields = ("user__username", "user__email", "employee_id")
    actions = (approve_profiles, suspend_profiles)
    autocomplete_fields = ("user", "branch")


class StaffProfileInline(admin.StackedInline):
    model = StaffProfile
    extra = 1
    max_num = 1
    can_delete = False
    fields = ("role", "branch", "employee_id", "is_approved")


User = get_user_model()
if User in admin.site._registry:
    admin.site.unregister(User)


@admin.register(User)
class SmartMartUserAdmin(DjangoUserAdmin):
    inlines = (StaffProfileInline,)
    search_fields = ("username", "first_name", "last_name", "email")
