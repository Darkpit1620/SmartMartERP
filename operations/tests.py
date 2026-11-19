"""Permission and data-safety tests. Never use live sales in tests."""
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from core.models import Branch, StaffProfile
from inventory.models import Category, Product, BranchStock
from pos.models import Sale
from .diagnostics import collect_snapshot, security_flags


class OperationsAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser(
            username='ops_admin', email='ops_admin@example.test', password='Test-Only-12345!')
        cls.manager = User.objects.create_user(username='ops_mgr', password='Test-Only-12345!')
        cls.cashier = User.objects.create_user(username='ops_cash', password='Test-Only-12345!')
        cls.branch = Branch.objects.create(name='Ops Branch', code='OPS-TEST')
        StaffProfile.objects.create(user=cls.manager, branch=cls.branch, role='MANAGER', is_approved=True)
        StaffProfile.objects.create(user=cls.cashier, branch=cls.branch, role='CASHIER', is_approved=True)
        category = Category.objects.create(name='Ops Test Goods')
        cls.product = Product.objects.create(
            category=category, name='Test Item', sku='OPS-TEST-0001',
            cost_price=Decimal('10.00'), retail_price=Decimal('15.00'),
            wholesale_price=Decimal('12.00'), wholesale_min_qty=2)
        BranchStock.objects.create(branch=cls.branch, product=cls.product, quantity=Decimal('10.000'))
        cls.sale = Sale.objects.create(
            branch=cls.branch, cashier=cls.cashier,
            sale_type=Sale.SaleType.RETAIL, payment_method=Sale.PaymentMethod.CASH,
            payment_status=Sale.PaymentStatus.CASH_RECEIVED,
            subtotal=Decimal('15.00'), checkout_token='ops-test-checkout')

    def test_unauthenticated_is_redirected(self):
        response = self.client.get(reverse('operations:overview'))
        self.assertEqual(response.status_code, 302)

    def test_manager_and_cashier_cannot_access_readiness_dashboard(self):
        for account in (self.manager, self.cashier):
            self.client.force_login(account)
            self.assertEqual(self.client.get(reverse('operations:overview')).status_code, 403)

    def test_admin_sees_read_only_counts(self):
        self.client.force_login(self.admin)
        before = list(BranchStock.objects.values_list('pk', 'quantity'))
        response = self.client.get(reverse('operations:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'System readiness')
        self.assertEqual(response.context['data']['products'], 1)
        self.assertEqual(response.context['data']['sales'], 1)
        self.assertEqual(list(BranchStock.objects.values_list('pk', 'quantity')), before)

    def test_no_post_or_state_change(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('operations:overview'))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(BranchStock.objects.get(pk=self.product.branch_stock.first().pk).quantity,
                         Decimal('10.000'))

    def test_command_collects_only_aggregates(self):
        report = collect_snapshot()
        self.assertEqual(report['negative_stock_lines'], 0)
        self.assertEqual(report['products'], 1)
        self.assertEqual(report['sales_without_items'], 1)
        self.assertTrue(isinstance(security_flags(), list))
