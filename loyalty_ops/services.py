"""Validated, concurrency-aware loyalty ledger; never creates money or stock movements."""
from decimal import Decimal
from secrets import token_hex

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from pos.models import Sale
from .models import LoyaltyMember, LoyaltyPurchase, LoyaltyReward, LoyaltyRedemption

POINTS_PER_KES = Decimal('100.00')  # One point per complete KES 100 of eligible net paid spend.


def earned_points(amount):
    return max(0, int(max(Decimal('0.00'), Decimal(amount)) // POINTS_PER_KES))


def _approved_returns(sale_ids):
    """Exclude rejected/pending return requests; net credit declines after approved returns."""
    if not sale_ids:
        return {}
    from returns_ops.models import ReturnRequest
    rows = (ReturnRequest.objects.filter(sale_id__in=sale_ids, status=ReturnRequest.Status.APPROVED)
            .values('sale_id').annotate(value=Sum('amount')))
    return {row['sale_id']: row['value'] or Decimal('0.00') for row in rows}


def balance_for(member):
    """Derive balance from immutable paid sale links, approved returns, and reserved/fulfilled rewards.

    A return after redemption can create a negative balance. Preserve the debt in reports and
    block additional redemptions until subsequent eligible purchases cover it.
    """
    purchases = list(LoyaltyPurchase.objects.filter(member=member).select_related('sale'))
    refunds = _approved_returns([p.sale_id for p in purchases])
    effective_earned = sum(min(p.points_awarded, earned_points(
        max(Decimal('0.00'), p.sale.subtotal - refunds.get(p.sale_id, Decimal('0.00')))
    )) for p in purchases)
    spent = LoyaltyRedemption.objects.filter(member=member).exclude(
        state=LoyaltyRedemption.State.CANCELLED).aggregate(total=Sum('points_spent'))['total'] or 0
    return {
        'earned': effective_earned,
        'spent': spent,
        'balance': effective_earned - spent,
        'purchase_count': len(purchases),
        'return_adjustment': sum(p.points_awarded for p in purchases) - effective_earned,
    }


def enroll_member(*, branch, full_name, phone, consent, actor):
    name = (full_name or '').strip()
    if not branch or not branch.active or len(name) < 2 or len(name) > 140:
        raise ValidationError('Select an active branch and enter a customer name (2–140 characters).')
    if not consent:
        raise ValidationError('Customer consent is required before enrollment.')
    if len((phone or '').strip()) > 35:
        raise ValidationError('Phone must be 35 characters or fewer.')
    for attempt in range(5):
        try:
            with transaction.atomic():
                return LoyaltyMember.objects.create(
                    branch=branch, member_code='LM-' + token_hex(7).upper(),
                    full_name=name, phone=(phone or '').strip(),
                    consent_recorded=True, created_by=actor,
                )
        except IntegrityError:
            if attempt == 4:
                raise


def link_paid_sale(*, member, sale, actor):
    if not member.active or not member.consent_recorded:
        raise ValidationError('This member is inactive or has not consented.')
    with transaction.atomic():
        member = LoyaltyMember.objects.select_for_update().get(pk=member.pk)
        if not member.active or not member.consent_recorded:
            raise ValidationError('This member is inactive or has not consented.')
        sale = Sale.objects.select_for_update().get(pk=sale.pk)
        if sale.branch_id != member.branch_id:
            raise ValidationError('Sale and customer membership must belong to the same branch.')
        if sale.payment_status not in (Sale.PaymentStatus.CASH_RECEIVED, Sale.PaymentStatus.VERIFIED):
            raise ValidationError('Points are awarded only for cash-received or manager-verified sales.')
        if LoyaltyPurchase.objects.filter(sale=sale).exists():
            raise ValidationError('This receipt has already been linked to a loyalty member.')
        approved = _approved_returns([sale.pk]).get(sale.pk, Decimal('0.00'))
        net = max(Decimal('0.00'), sale.subtotal - approved)
        return LoyaltyPurchase.objects.create(
            member=member, sale=sale, points_awarded=earned_points(net), linked_by=actor,
        )


def reserve_reward(*, member, reward, actor):
    with transaction.atomic():
        member = LoyaltyMember.objects.select_for_update().get(pk=member.pk)
        reward = LoyaltyReward.objects.select_for_update().get(pk=reward.pk)
        if not member.active or not member.consent_recorded:
            raise ValidationError('Loyalty account is inactive.')
        if not reward.active or reward.branch_id != member.branch_id or reward.points_cost < 1:
            raise ValidationError('Reward is unavailable for this member or branch.')
        if balance_for(member)['balance'] < reward.points_cost:
            raise ValidationError('Not enough available points for this reward.')
        return LoyaltyRedemption.objects.create(
            member=member, reward=reward, points_spent=reward.points_cost, requested_by=actor,
        )


def review_redemption(*, redemption, actor, state, reference):
    if state not in (LoyaltyRedemption.State.FULFILLED, LoyaltyRedemption.State.CANCELLED):
        raise ValidationError('Select fulfilled or cancelled.')
    reference = (reference or '').strip()
    if len(reference) < 3 or len(reference) > 100:
        raise ValidationError('Record a handover reference or cancellation reason (3–100 characters).')
    with transaction.atomic():
        redemption = LoyaltyRedemption.objects.select_for_update().get(pk=redemption.pk)
        if redemption.state != LoyaltyRedemption.State.RESERVED:
            raise ValidationError('This reward has already been reviewed.')
        redemption.state = state
        redemption.reviewed_by = actor
        redemption.reviewed_at = timezone.now()
        redemption.review_reference = reference
        redemption.save(update_fields=['state', 'reviewed_by', 'reviewed_at', 'review_reference'])
        return redemption
