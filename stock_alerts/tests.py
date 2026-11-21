"""All tests use Django's temporary test database and leave live stock untouched."""
import csv
import io
import unittest
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Branch, StaffProfile
from inventory.models import BranchStock, Category, Product, StockMovement
from .services import reorder_quantity, safe_csv_cell

ACTIVE = 'stock_alerts.apps.StockAlertsConfig' in settings.INSTALLED_APPS


@unittest.skipUnless(ACTIVE, 'Stage 13C is not registered in INSTALLED_APPS yet')
class StockAlertsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Branch.objects.create(name='Branch A', code='ALERT-A', active=True)
        cls.b = Branch.objects.create(name='Branch B', code='ALERT-B', active=True)
        cls.cat = Category.objects.create(name='Alert test groceries')
        def product(name, sku, threshold='5.000', retail='120.00', wholesale='90.00', active=True):
            return Product.objects.create(category=cls.cat, name=name, sku=sku,
                cost_price=Decimal('40.00'), retail_price=Decimal(retail),
                wholesale_price=Decimal(wholesale), reorder_level=Decimal(threshold), is_active=active)
        cls.low = product('Test low bread', 'ALERT-LOW')
        cls.out = product('Test out rice', 'ALERT-OUT')
        cls.safe = product('Test plentiful milk', 'ALERT-SAFE')
        cls.unpriced = product('Test unpriced tea', 'ALERT-UNPRICED', retail='0', wholesale='0')
        cls.no_threshold = product('Test no reorder', 'ALERT-OFF', threshold='0')
        cls.inactive = product('Test inactive', 'ALERT-INACTIVE', active=False)
        cls.formula = product('=2+2', 'ALERT-FORMULA')
        BranchStock.objects.create(branch=cls.a, product=cls.low, quantity=Decimal('3.000'))
        BranchStock.objects.create(branch=cls.a, product=cls.safe, quantity=Decimal('20.000'))
        BranchStock.objects.create(branch=cls.a, product=cls.formula, quantity=Decimal('3.000'))
        BranchStock.objects.create(branch=cls.b, product=cls.low, quantity=Decimal('30.000'))
        User = get_user_model()
        cls.admin = User.objects.create_superuser('alerts_admin', 'admin@example.invalid', 'test-only-password')
        cls.manager = User.objects.create_user('alerts_manager', password='test-only-password')
        cls.warehouse = User.objects.create_user('alerts_warehouse', password='test-only-password')
        cls.cashier = User.objects.create_user('alerts_cashier', password='test-only-password')
        cls.pending = User.objects.create_user('alerts_pending', password='test-only-password')
        cls.unassigned = User.objects.create_user('alerts_unassigned', password='test-only-password')
        for u, role, branch, approved in [
            (cls.manager, 'MANAGER', cls.a, True), (cls.warehouse, 'WAREHOUSE', cls.a, True),
            (cls.cashier, 'CASHIER', cls.a, True), (cls.pending, 'MANAGER', cls.a, False),
            (cls.unassigned, 'MANAGER', None, True),
        ]:
            StaffProfile.objects.create(user=u, role=role, branch=branch, is_approved=approved)

    def test_anonymous_redirects(self):
        for path in (reverse('stock_alerts:home'), reverse('stock_alerts:export_csv')):
            self.assertEqual(self.client.get(path).status_code, 302)

    def test_cashier_pending_and_branchless_forbidden(self):
        for user in (self.cashier, self.pending, self.unassigned):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('stock_alerts:home')).status_code, 403)
            self.assertEqual(self.client.get(reverse('stock_alerts:export_csv')).status_code, 403)

    def test_manager_sees_only_own_branch_even_if_branch_parameter_spoofed(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse('stock_alerts:home'), {'branch': self.b.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['branch'], self.a)
        self.assertEqual(response.context['total_low'], 3)
        self.assertEqual(response.context['out_of_stock'], 1)
        self.assertEqual(response.context['setup_pending'], 1)
        self.assertContains(response, 'Test low bread')
        self.assertContains(response, 'Test out rice')
        self.assertNotContains(response, 'Test plentiful milk')
        self.assertNotContains(response, 'Test unpriced tea')
        self.assertNotContains(response, 'Test no reorder')

    def test_warehouse_access_and_search_filter(self):
        self.client.force_login(self.warehouse)
        response = self.client.get(reverse('stock_alerts:home'), {'q': 'ALERT-LOW'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['filtered_count'], 1)
        self.assertEqual(response.context['rows'][0]['suggested'], Decimal('7.000'))

    def test_stock_unrecorded_is_zero_and_labelled(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse('stock_alerts:home'), {'status': 'out'})
        self.assertEqual(response.context['filtered_count'], 1)
        self.assertEqual(response.context['rows'][0]['product'], self.out)
        self.assertFalse(response.context['rows'][0]['recorded'])
        self.assertEqual(response.context['rows'][0]['suggested'], Decimal('10.000'))

    def test_admin_can_select_branch_and_invalid_branch_is_404(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('stock_alerts:home'), {'branch': self.b.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_low'], 3)  # out, safe and formula have no branch-B balance
        self.assertEqual(self.client.get(reverse('stock_alerts:home'), {'branch': 'invalid'}).status_code, 404)
        self.assertEqual(self.client.get(reverse('stock_alerts:home'), {'branch': '999999'}).status_code, 404)

    def test_no_active_branch_shows_setup_message_without_error(self):
        Branch.objects.update(active=False)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('stock_alerts:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No active branches')
        self.assertEqual(self.client.get(reverse('stock_alerts:export_csv')).status_code, 404)

    def test_filter_status_only_low_with_stock(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse('stock_alerts:home'), {'status': 'low'})
        self.assertEqual(response.context['filtered_count'], 2)
        self.assertEqual(response.context['out_of_stock'], 1)  # headline remains branch total

    def test_csv_is_branch_scoped_and_formula_safe(self):
        self.client.force_login(self.warehouse)
        response = self.client.get(reverse('stock_alerts:export_csv'), {'branch': self.b.pk})
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment;', response['Content-Disposition'])
        records = list(csv.reader(io.StringIO(response.content.decode('utf-8'))))
        self.assertEqual(len(records), 4)  # header + 3 alert records at staff's own branch
        self.assertTrue(any(row[2] == "'=2+2" for row in records[1:]))
        self.assertTrue(all(row[0] == self.a.code for row in records[1:]))
        self.assertEqual(len([row for row in records[1:] if row[1] == 'ALERT-UNPRICED']), 0)

    def test_no_inventory_changes_on_read_and_export(self):
        self.client.force_login(self.manager)
        before = (Product.objects.count(), BranchStock.objects.count(), StockMovement.objects.count())
        self.client.get(reverse('stock_alerts:home'))
        self.client.get(reverse('stock_alerts:export_csv'))
        after = (Product.objects.count(), BranchStock.objects.count(), StockMovement.objects.count())
        self.assertEqual(before, after)

    def test_helper_stops_negative_suggestions(self):
        self.assertEqual(reorder_quantity('5', '3'), Decimal('7'))
        self.assertEqual(reorder_quantity('5', '12'), Decimal('0.000'))
        self.assertEqual(safe_csv_cell('=HYPERLINK("x")'), "'=HYPERLINK(\"x\")")
        self.assertEqual(safe_csv_cell('Rice'), 'Rice')
