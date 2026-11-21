from django.contrib import admin
from .models import LoyaltyMember, LoyaltyPurchase, LoyaltyReward, LoyaltyRedemption


@admin.register(LoyaltyMember)
class MemberAdmin(admin.ModelAdmin):
    list_display = ('member_code', 'full_name', 'branch', 'active', 'created_at')
    list_filter = ('branch', 'active')
    search_fields = ('member_code', 'full_name')
    readonly_fields = ('branch', 'member_code', 'full_name', 'phone', 'consent_recorded', 'created_by', 'created_at')
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(LoyaltyPurchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ('sale', 'member', 'points_awarded', 'linked_at')
    readonly_fields = ('sale', 'member', 'points_awarded', 'linked_by', 'linked_at')
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(LoyaltyReward)
class RewardAdmin(admin.ModelAdmin):
    list_display = ('title', 'branch', 'points_cost', 'active')
    readonly_fields = ('branch', 'title', 'details', 'points_cost', 'created_by', 'created_at')
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(LoyaltyRedemption)
class RedemptionAdmin(admin.ModelAdmin):
    list_display = ('member', 'reward', 'state', 'points_spent', 'created_at')
    readonly_fields = ('member', 'reward', 'state', 'points_spent', 'requested_by', 'reviewed_by', 'reviewed_at', 'review_reference', 'created_at')
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
