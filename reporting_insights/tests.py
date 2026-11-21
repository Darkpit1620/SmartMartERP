"""Integration tests use Django's disposable test database only."""
import csv
import io
import unittest
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Branch, StaffProfile
from inventory.models import BranchStock, Category, Product
from finance_ops.models import Expense
from pos.models import Sale, SaleItem
from returns_ops.models import ReturnRequest
from .services import build_report, safe_csv_cell

ACTIVE = 'reporting_insights.apps.ReportingInsightsConfig' in settings.INSTALLED_APPS


@unittest.skipUnless(ACTIVE, 'Stage 13D is not yet registered in INSTALLED_APPS')
class ManagementReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Branch.objects.create(code='RPT-A', name='Reporting North', active=True)
        cls.b = Branch.objects.create(code='RPT-B', name='Reporting South', active=True)
        cat = Category.objects.create(name='Reporting sample category')
        cls.p = Product.objects.create(category=cat, name='Reporting rice', sku='RPT-RICE',
            cost_price=Decimal('60.00'), retail_price=Decimal('100.00'),
            wholesale_price=Decimal('90.00'), tax_rate=Decimal('0'))
        cls.p2 = Product.objects.create(category=cat, name='=FORMULA TEST', sku='RPT-TEST2',
            cost_price=Decimal('0.00'), retail_price=Decimal('80.00'),
            wholesale_price=Decimal('70.00'))
        BranchStock.objects.create(branch=cls.a, product=cls.p, quantity=Decimal('10.000'))
        BranchStock.objects.create(branch=cls.b, product=cls.p, quantity=Decimal('20.000'))
        User = get_user_model()
        cls.admin = User.objects.create_superuser('rpt_admin', 'admin@sample.invalid', 'test-only-password')
        cls.manager_a = User.objects.create_user('rpt_manager_a', password='test-only-password')
        cls.manager_b = User.objects.create_user('rpt_manager_b', password='test-only-password')
        cls.cashier = User.objects.create_user('rpt_cashier', password='test-only-password')
        cls.pending = User.objects.create_user('rpt_pending', password='test-only-password')
        cls.warehouse = User.objects.create_user('rpt_wh', password='test-only-password')
        for user, branch, role, approved in (
            (cls.manager_a, cls.a, 'MANAGER', True), (cls.manager_b, cls.b, 'MANAGER', True),
            (cls.cashier, cls.a, 'CASHIER', True), (cls.pending, cls.a, 'MANAGER', False),
            (cls.warehouse, cls.a, 'WAREHOUSE', True),
        ):
            StaffProfile.objects.create(user=user, branch=branch, role=role, is_approved=approved)
        cls.sale_a = cls.make_sale(cls.a, cls.cashier, 'CASH_RECEIVED', '100.00', 'RPT-CA')
        cls.make_sale(cls.a, cls.cashier, 'UNVERIFIED', '400.00', 'RPT-UN')
        cls.sale_b = cls.make_sale(cls.b, cls.cashier, 'VERIFIED', '200.00', 'RPT-VB')
        cls.make_sale(cls.b, cls.cashier, 'UNVERIFIED', '900.00', 'RPT-UB')
        SaleItem.objects.create(sale=cls.sale_a, product=cls.p, sku=cls.p.sku,
            description=cls.p.name, unit='EACH', quantity=Decimal('1.000'),
            unit_price=Decimal('100.00'), tax_rate=Decimal('0'),
            line_total=Decimal('100.00'), included_tax=Decimal('0.00'))
        SaleItem.objects.create(sale=cls.sale_b, product=cls.p, sku=cls.p.sku,
            description=cls.p.name, unit='EACH', quantity=Decimal('2.000'),
            unit_price=Decimal('100.00'), tax_rate=Decimal('0'),
            line_total=Decimal('200.00'), included_tax=Decimal('0.00'))
        cls.exp_a = Expense.objects.create(branch=cls.a, category='OTHER',
            amount=Decimal('15.00'), incurred_on=timezone.localdate(),
            description='Approved test expense', status='APPROVED', recorded_by=cls.admin)
        Expense.objects.create(branch=cls.a, category='OTHER', amount=Decimal('30.00'),
            incurred_on=timezone.localdate(), description='Pending sample', status='PENDING', recorded_by=cls.admin)
        Expense.objects.create(branch=cls.b, category='OTHER', amount=Decimal('40.00'),
            incurred_on=timezone.localdate(), description='Other branch', status='APPROVED', recorded_by=cls.admin)
        ReturnRequest.objects.create(sale=cls.sale_a, requested_by=cls.cashier,
            status='APPROVED', reason='Test returned', amount=Decimal('20.00'),
            refund_status='RECORDED', refunded_at=timezone.now(), refunded_by=cls.admin,
            refund_method='CASH', refund_reference='RPT-PAYOUT')
        ReturnRequest.objects.create(sale=cls.sale_a, requested_by=cls.cashier,
            status='APPROVED', reason='Unpaid', amount=Decimal('30.00'), refund_status='PENDING')

    @classmethod
    def make_sale(cls, branch, cashier, status, amount, token):
        return Sale.objects.create(branch=branch, cashier=cashier, sale_type='RETAIL',
            payment_method='CASH' if status == 'CASH_RECEIVED' else 'MPESA',
            payment_status=status, subtotal=Decimal(amount),
            included_tax=Decimal('0.00'), checkout_token=token,
            receipt_number=f'TEST-{token}')

    def test_anonymous_redirect_and_cashier_warehouse_pending_forbidden(self):
        self.assertEqual(self.client.get(reverse('reporting_insights:home')).status_code, 302)
        for user in (self.cashier, self.warehouse, self.pending):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('reporting_insights:home')).status_code, 403)
            self.assertEqual(self.client.get(reverse('reporting_insights:export_csv')).status_code, 403)

    def test_manager_cannot_switch_branch_by_query_parameter(self):
        self.client.force_login(self.manager_a)
        response = self.client.get(reverse('reporting_insights:home'), {'branch': self.b.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['branch'].pk, self.a.pk)
        self.assertEqual(response.context['report']['confirmed_sales'], Decimal('100.00'))
        self.assertEqual(response.context['report']['unverified_sales'], Decimal('400.00'))
        self.assertNotContains(response, 'Reporting South')

    def test_south_manager_sees_only_south_transactions(self):
        self.client.force_login(self.manager_b)
        response = self.client.get(reverse('reporting_insights:home'))
        self.assertEqual(response.context['report']['confirmed_sales'], Decimal('200.00'))
        self.assertEqual(response.context['report']['unverified_sales'], Decimal('900.00'))
        self.assertEqual(response.context['report']['approved_expenses'], Decimal('40.00'))
        self.assertEqual(response.context['report']['paid_refunds'], Decimal('0.00'))

    def test_superuser_all_branch_aggregate(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('reporting_insights:home'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['report']['confirmed_sales'], Decimal('300.00'))
        self.assertEqual(response.context['report']['unverified_sales'], Decimal('1300.00'))
        self.assertEqual(response.context['report']['approved_expenses'], Decimal('55.00'))
        self.assertEqual(response.context['report']['paid_refunds'], Decimal('20.00'))

    def test_margin_calculation_and_current_inventory_valuation(self):
        r = build_report(self.a, timezone.localdate(), timezone.localdate())
        self.assertEqual(r['estimated_cost'], Decimal('60.00'))
        self.assertEqual(r['estimated_merchandise_margin'], Decimal('40.00'))
        self.assertEqual(r['inventory_value'], Decimal('600.00'))
        self.assertEqual(r['paid_refunds'], Decimal('20.00'))
        self.assertEqual(r['pending_expenses'], Decimal('30.00'))

    def test_missing_cost_makes_margin_unavailable(self):
        SaleItem.objects.create(sale=self.sale_a, product=self.p2, sku=self.p2.sku,
            description=self.p2.name, unit='EACH', quantity=Decimal('1.000'),
            unit_price=Decimal('0.00'), tax_rate=Decimal('0'),
            line_total=Decimal('0.00'), included_tax=Decimal('0.00'))
        result = build_report(self.a, timezone.localdate(), timezone.localdate())
        self.assertEqual(result['missing_cost_lines'], 1)
        self.assertIsNone(result['estimated_merchandise_margin'])

    def test_missing_sale_items_makes_margin_unavailable(self):
        SaleItem.objects.filter(sale=self.sale_a).delete()
        report = build_report(self.a, timezone.localdate(), timezone.localdate())
        self.assertEqual(report['confirmed_sales_without_items'], 1)
        self.assertIsNone(report['estimated_merchandise_margin'])

    def test_date_validation_and_branch_validation(self):
        self.client.force_login(self.admin)
        url = reverse('reporting_insights:home')
        for query in ({'start': '2026-22-12'}, {'start': '2099-01-01'},
                      {'start': '2025-01-01', 'end': '2026-11-20'}, {'branch': 'bad'},
                      {'branch': '999999'}):
            self.assertEqual(self.client.get(url, query).status_code, 404)

    def test_csv_scoped_by_branch_and_formula_safe(self):
        self.client.force_login(self.manager_a)
        url = reverse('reporting_insights:export_csv')
        response = self.client.get(url, {'branch': str(self.b.pk)})
        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.content.decode('utf-8'))))
        self.assertIn(['Branch', self.a.name], rows)
        self.assertIn(['Confirmed sales (tax included)', '100.00'], rows)
        self.assertNotIn(['Branch', self.b.name], rows)
        self.assertEqual(safe_csv_cell('=2+2'), "'=2+2")

    def test_reads_do_not_change_business_data(self):
        self.client.force_login(self.admin)
        before = (Sale.objects.count(), Expense.objects.count(), ReturnRequest.objects.count(), BranchStock.objects.count())
        self.client.get(reverse('reporting_insights:home'))
        self.client.get(reverse('reporting_insights:export_csv'))
        self.assertEqual(before, (Sale.objects.count(), Expense.objects.count(), ReturnRequest.objects.count(), BranchStock.objects.count()))
