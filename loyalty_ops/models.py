"""Customer-consented, branch-scoped loyalty with immutable sale links and reward records."""
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from core.models import Branch
from pos.models import Sale


class LoyaltyMember(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='loyalty_members')
    member_code = models.CharField(max_length=22, unique=True)
    full_name = models.CharField(max_length=140)
    phone = models.CharField(max_length=35, blank=True)
    consent_recorded = models.BooleanField(default=False, help_text='Customer has agreed to enrollment and purchase history linkage.')
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='loyalty_members_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-pk')
        indexes = [models.Index(fields=['branch', 'member_code'], name='loyalty_ops_branch_code_idx')]

    def __str__(self):
        return f'{self.member_code} · {self.full_name}'


class LoyaltyPurchase(models.Model):
    """Exactly one membership link for each paid receipt, with a snapshot of initial points."""
    sale = models.OneToOneField(Sale, on_delete=models.PROTECT, related_name='loyalty_purchase')
    member = models.ForeignKey(LoyaltyMember, on_delete=models.PROTECT, related_name='loyalty_purchases')
    points_awarded = models.PositiveIntegerField()
    linked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='loyalty_sales_linked')
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-linked_at', '-pk')


class LoyaltyReward(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='loyalty_rewards')
    title = models.CharField(max_length=120)
    details = models.CharField(max_length=250, blank=True)
    points_cost = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='loyalty_rewards_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('title', 'pk')


class LoyaltyRedemption(models.Model):
    class State(models.TextChoices):
        RESERVED = 'RESERVED', 'Points reserved, awaiting handover'
        FULFILLED = 'FULFILLED', 'Reward handed to customer'
        CANCELLED = 'CANCELLED', 'Cancelled, points released'

    member = models.ForeignKey(LoyaltyMember, on_delete=models.PROTECT, related_name='loyalty_redemptions')
    reward = models.ForeignKey(LoyaltyReward, on_delete=models.PROTECT, related_name='loyalty_redemptions')
    points_spent = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    state = models.CharField(max_length=12, choices=State.choices, default=State.RESERVED)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='loyalty_redemptions_requested')
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='loyalty_redemptions_reviewed')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_reference = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-pk')
        indexes = [models.Index(fields=['member', 'state'], name='loyalty_ops_member_state_idx')]
