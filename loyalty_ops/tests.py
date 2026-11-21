"""Smoke and security tests for opt-in membership, paid receipts, returns and rewards."""

# SMARTMART_STAGE13I_OPTIONAL_LOYALTY_TEST_GUARD
# During a failed Stage 13H installation, settings are rolled back but the
# source folder can remain. Skip its tests only while the app is not installed.
import unittest as _smartmart_unittest
from django.conf import settings as _smartmart_settings
if not any(entry == 'loyalty_ops' or entry.startswith('loyalty_ops.')
           for entry in _smartmart_settings.INSTALLED_APPS):
    raise _smartmart_unittest.SkipTest(
        'Optional Stage 13H loyalty app is inactive; its tests require installation.')


from decimal import Decimal
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models import Branch, StaffProfile
from inventory.models import Category, Product, BranchStock
from pos.models import Sale
from pos.services import complete_sale
from returns_ops.models import ReturnRequest
from returns_ops.services import request_return, review_return
from .models import LoyaltyMember, LoyaltyPurchase, LoyaltyReward, LoyaltyRedemption
from .services import balance_for, enroll_member, earned_points, link_paid_sale, reserve_reward, review_redemption


class LoyaltyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(name='Loyalty North', code='LOY-NORTH')
        cls.other = Branch.objects.create(name='Loyalty South', code='LOY-SOUTH')
        cat = Category.objects.create(name='Loyalty test groceries')
        cls.product = Product.objects.create(category=cat, name='Loyalty test rice', sku='LOY-RICE',
            retail_price=Decimal('100.00'), wholesale_price=Decimal('90.00'), cost_price=Decimal('60.00'), tax_rate=Decimal('0'))
        for b in (cls.branch, cls.other):
            BranchStock.objects.create(branch=b, product=cls.product, quantity=Decimal('100.000'))
        User = get_user_model()
        cls.admin = User.objects.create_superuser('loy_admin', 'loy-admin@example.test', 'safe-test-password')
        cls.manager = User.objects.create_user('loy_manager', password='safe-test-password')
        cls.other_manager = User.objects.create_user('loy_other', password='safe-test-password')
        cls.cashier = User.objects.create_user('loy_cashier', password='safe-test-password')
        cls.other_cashier = User.objects.create_user('loy_other_cashier', password='safe-test-password')
        cls.warehouse = User.objects.create_user('loy_warehouse', password='safe-test-password')
        cls.unapproved = User.objects.create_user('loy_pending', password='safe-test-password')
        for user, role, branch, approved in (
            (cls.manager, 'MANAGER', cls.branch, True),
            (cls.other_manager, 'MANAGER', cls.other, True),
            (cls.cashier, 'CASHIER', cls.branch, True),
            (cls.other_cashier, 'CASHIER', cls.other, True),
            (cls.warehouse, 'WAREHOUSE', cls.branch, True),
            (cls.unapproved, 'CASHIER', cls.branch, False),
        ):
            StaffProfile.objects.create(user=user, role=role, branch=branch, is_approved=approved)

    def setUp(self):
        self.member = enroll_member(branch=self.branch, full_name='Test Customer', phone='',
                                    consent=True, actor=self.cashier)

    def sale(self, *, branch=None, cashier=None, method='CASH', cart=None, promotion_code=''):
        return complete_sale(branch=branch or self.branch, cashier=cashier or self.cashier,
            cart=cart or {str(self.product.pk): '5'}, mode=Sale.SaleType.RETAIL,
            method=method, token=uuid4().hex, tendered='1000', reference='EXTERNAL-REF-123' if method != 'CASH' else '',
            promotion_code=promotion_code)

    def reward(self, points=2, branch=None):
        return LoyaltyReward.objects.create(branch=branch or self.branch, title='Gift voucher (manual handover)',
                                            points_cost=points, created_by=self.manager)

    def test_consent_required_and_no_phone_mandatory(self):
        with self.assertRaises(ValidationError):
            enroll_member(branch=self.branch, full_name='A Customer', phone='', consent=False, actor=self.cashier)
        self.assertTrue(self.member.consent_recorded)
        self.assertTrue(self.member.member_code.startswith('LM-'))

    def test_paid_receipt_credits_once_and_no_stock_change_from_link(self):
        sale = self.sale()
        stock = BranchStock.objects.get(branch=self.branch, product=self.product).quantity
        p = link_paid_sale(member=self.member, sale=sale, actor=self.cashier)
        self.assertEqual(p.points_awarded, 5)
        self.assertEqual(balance_for(self.member)['balance'], 5)
        with self.assertRaises(ValidationError):
            link_paid_sale(member=self.member, sale=sale, actor=self.cashier)
        self.assertEqual(BranchStock.objects.get(branch=self.branch, product=self.product).quantity, stock)
        self.assertEqual(LoyaltyPurchase.objects.count(), 1)

    def test_unverified_electronic_payment_never_credits(self):
        sale = self.sale(method='MPESA')
        with self.assertRaises(ValidationError):
            link_paid_sale(member=self.member, sale=sale, actor=self.cashier)
        self.assertEqual(LoyaltyPurchase.objects.count(), 0)
        Sale.objects.filter(pk=sale.pk).update(payment_status=Sale.PaymentStatus.VERIFIED)
        link_paid_sale(member=self.member, sale=sale, actor=self.cashier)
        self.assertEqual(balance_for(self.member)['balance'], 5)

    def test_branch_separation(self):
        sale = self.sale(branch=self.other, cashier=self.other_cashier)
        with self.assertRaises(ValidationError):
            link_paid_sale(member=self.member, sale=sale, actor=self.manager)
        self.assertFalse(LoyaltyPurchase.objects.exists())

    def test_approved_returns_reduce_points_automatically(self):
        sale = self.sale()
        link_paid_sale(member=self.member, sale=sale, actor=self.cashier)
        self.assertEqual(balance_for(self.member)['balance'], 5)
        case = request_return(sale=sale, sale_item=sale.items.first(), actor=self.cashier,
                              quantity='2', reason='Test return')
        self.assertEqual(balance_for(self.member)['balance'], 5)  # Pending is not counted
        review_return(case=case, actor=self.manager, approve=True, restock=False, note='Approved for loyalty test')
        self.assertEqual(balance_for(self.member)['balance'], 3)
        self.assertEqual(balance_for(self.member)['return_adjustment'], 2)
        sale.refresh_from_db()
        self.assertEqual(sale.subtotal, Decimal('500.00'))

    def test_reward_reserve_cancel_release_and_double_review_blocked(self):
        sale = self.sale()
        link_paid_sale(member=self.member, sale=sale, actor=self.cashier)
        reward = self.reward(points=3)
        reservation = reserve_reward(member=self.member, reward=reward, actor=self.cashier)
        self.assertEqual(balance_for(self.member)['balance'], 2)
        with self.assertRaises(ValidationError):
            reserve_reward(member=self.member, reward=self.reward(points=3), actor=self.cashier)
        review_redemption(redemption=reservation, actor=self.manager, state='CANCELLED', reference='Customer changed mind')
        self.assertEqual(balance_for(self.member)['balance'], 5)
        with self.assertRaises(ValidationError):
            review_redemption(redemption=reservation, actor=self.manager, state='FULFILLED', reference='Handover')

    def test_fulfilled_reward_points_not_reused(self):
        sale = self.sale()
        link_paid_sale(member=self.member, sale=sale, actor=self.cashier)
        reward = self.reward(points=5)
        reservation = reserve_reward(member=self.member, reward=reward, actor=self.manager)
        review_redemption(redemption=reservation, actor=self.manager, state='FULFILLED', reference='Gift card delivered')
        self.assertEqual(balance_for(self.member)['balance'], 0)
        with self.assertRaises(ValidationError):
            reserve_reward(member=self.member, reward=reward, actor=self.manager)

    def test_post_redemption_return_creates_debt_and_blocks_more(self):
        sale = self.sale()
        link_paid_sale(member=self.member, sale=sale, actor=self.cashier)
        reward = self.reward(points=4)
        reserve_reward(member=self.member, reward=reward, actor=self.cashier)
        case = request_return(sale=sale, sale_item=sale.items.first(), actor=self.cashier,
                              quantity='3', reason='Return after reward reserved')
        review_return(case=case, actor=self.manager, approve=True, restock=False)
        self.assertEqual(balance_for(self.member)['balance'], -2)
        with self.assertRaises(ValidationError):
            reserve_reward(member=self.member, reward=self.reward(points=1), actor=self.cashier)

    def test_role_permissions_and_cross_branch_http(self):
        self.client.force_login(self.warehouse)
        self.assertEqual(self.client.get(reverse('loyalty_ops:home')).status_code, 403)
        self.client.force_login(self.unapproved)
        self.assertEqual(self.client.get(reverse('loyalty_ops:home')).status_code, 403)
        self.client.force_login(self.other_manager)
        self.assertEqual(self.client.get(reverse('loyalty_ops:member', args=[self.member.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('loyalty_ops:link_receipt', args=[self.member.pk]),
                                         {'receipt_number': 'X'}).status_code, 404)
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse('loyalty_ops:rewards')).status_code, 403)
        self.assertEqual(self.client.get(reverse('loyalty_ops:member', args=[self.member.pk])).status_code, 200)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('loyalty_ops:member', args=[self.member.pk])).status_code, 200)

    def test_cashier_only_links_their_own_receipts(self):
        sale = self.sale(cashier=self.manager)
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.post(reverse('loyalty_ops:link_receipt', args=[self.member.pk]),
                        {'receipt_number': sale.receipt_number}).status_code, 404)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.post(reverse('loyalty_ops:link_receipt', args=[self.member.pk]),
                        {'receipt_number': sale.receipt_number}).status_code, 302)
        self.assertEqual(LoyaltyPurchase.objects.get(sale=sale).member_id, self.member.pk)

    def test_redeem_branch_guard_and_manager_review(self):
        sale = self.sale()
        link_paid_sale(member=self.member, sale=sale, actor=self.cashier)
        other_reward = self.reward(points=2, branch=self.other)
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.post(reverse('loyalty_ops:redeem', args=[self.member.pk]),
                        {'reward_id': other_reward.pk}).status_code, 404)
        reward = self.reward(points=3)
        self.assertEqual(self.client.post(reverse('loyalty_ops:redeem', args=[self.member.pk]),
                        {'reward_id': reward.pk}).status_code, 302)
        redemption = LoyaltyRedemption.objects.get()
        self.assertEqual(self.client.post(reverse('loyalty_ops:review', args=[redemption.pk]),
                        {'action': 'fulfill', 'reference': 'Handed over'}).status_code, 403)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.post(reverse('loyalty_ops:review', args=[redemption.pk]),
                        {'action': 'fulfill', 'reference': 'Handed over'}).status_code, 302)
        self.assertEqual(balance_for(self.member)['balance'], 2)

    def test_suspended_member_cannot_redeem(self):
        sale = self.sale()
        link_paid_sale(member=self.member, sale=sale, actor=self.cashier)
        reward = self.reward(points=2)
        LoyaltyMember.objects.filter(pk=self.member.pk).update(active=False)
        with self.assertRaises(ValidationError):
            reserve_reward(member=self.member, reward=reward, actor=self.manager)

    def test_points_round_down(self):
        self.assertEqual(earned_points(Decimal('299.99')), 2)
        self.assertEqual(earned_points(Decimal('0.00')), 0)
        self.assertEqual(earned_points(Decimal('100.00')), 1)

    def test_rewards_pages_require_manager(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse('loyalty_ops:rewards'),
            {'branch': self.branch.pk, 'title': 'Training notebook', 'details': 'Test only', 'points_cost': '2'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LoyaltyReward.objects.count(), 1)
        self.client.force_login(self.other_manager)
        response = self.client.post(reverse('loyalty_ops:rewards'),
            {'branch': self.branch.pk, 'title': 'Forbidden reward', 'points_cost': '2'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LoyaltyReward.objects.count(), 1)
