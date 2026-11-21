from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models import Branch, StaffProfile
from inventory.models import Category, Product, BranchStock
from .barcodes import PATTERNS, encoded_values, choose_scan_code, svg_for
from .services import make_labels, sku_input


class BarcodeEncodingTests(TestCase):
    def test_spec_pattern_lengths(self):
        self.assertEqual(len(PATTERNS), 107)
        self.assertTrue(all(sum(map(int, item)) == 11 for item in PATTERNS[:106]))
        self.assertEqual(sum(map(int, PATTERNS[106])), 13)

    def test_code128b_start_checksum_stop(self):
        self.assertEqual(encoded_values('AB'), [104, 33, 34, 102, 106])
        svg = svg_for('AB')
        self.assertIn('viewBox="0 0 77 56"', svg)  # 20 quiet + 5 * 11 + 2 stop modules
        self.assertIn('Code 128 barcode', svg)

    def test_rejects_out_of_range_and_injection_text(self):
        for text in ('', 'À', '\x00', 'x' * 49):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    encoded_values(text)


class LabelPrintingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(name='North Branch', code='LABELN')
        cls.inactive_branch = Branch.objects.create(name='Closed Branch', code='LABELX', active=False)
        cls.category = Category.objects.create(name='Labelling Category')
        cls.product = Product.objects.create(
            category=cls.category, sku='LABEL-001', barcode='0098765432101',
            name='<b>Printed Rice</b>', cost_price=Decimal('60.00'),
            retail_price=Decimal('100.00'), wholesale_price=Decimal('90.00'),
        )
        cls.other = Product.objects.create(
            category=cls.category, sku='LABEL-002', name='Cooking oil',
            cost_price=Decimal('25.00'), retail_price=Decimal('70.00'),
            wholesale_price=Decimal('60.00'),
        )
        cls.unpriced = Product.objects.create(
            category=cls.category, sku='LABEL-003', name='Not priced',
            cost_price=Decimal('0'), retail_price=Decimal('0'), wholesale_price=Decimal('0'),
        )
        cls.inactive = Product.objects.create(
            category=cls.category, sku='LABEL-004', name='Inactive', is_active=False,
            cost_price=Decimal('20'), retail_price=Decimal('30'), wholesale_price=Decimal('25'),
        )
        BranchStock.objects.create(branch=cls.branch, product=cls.product, quantity=Decimal('4'))
        User = get_user_model()
        cls.admin = User.objects.create_superuser('label_admin', 'admin@example.test', 'test-secret-for-local-only')
        cls.manager = User.objects.create_user('label_manager', password='test-secret-for-local-only')
        StaffProfile.objects.create(user=cls.manager, branch=cls.branch, role='MANAGER', is_approved=True)
        cls.warehouse = User.objects.create_user('label_warehouse', password='test-secret-for-local-only')
        StaffProfile.objects.create(user=cls.warehouse, branch=cls.branch, role='WAREHOUSE', is_approved=True)
        cls.cashier = User.objects.create_user('label_cashier', password='test-secret-for-local-only')
        StaffProfile.objects.create(user=cls.cashier, branch=cls.branch, role='CASHIER', is_approved=True)
        cls.pending = User.objects.create_user('label_pending', password='test-secret-for-local-only')
        StaffProfile.objects.create(user=cls.pending, branch=cls.branch, role='WAREHOUSE', is_approved=False)
        cls.closed = User.objects.create_user('label_closed', password='test-secret-for-local-only')
        StaffProfile.objects.create(user=cls.closed, branch=cls.inactive_branch, role='MANAGER', is_approved=True)

    def test_authentication_and_roles(self):
        home = reverse('label_printing:home')
        self.assertEqual(self.client.get(home).status_code, 302)
        for user in (self.cashier, self.pending, self.closed):
            self.client.force_login(user)
            self.assertEqual(self.client.get(home).status_code, 403)
        for user in (self.admin, self.manager, self.warehouse):
            self.client.force_login(user)
            self.assertEqual(self.client.get(home).status_code, 200)

    def test_only_post_can_preview_and_permissions_apply(self):
        url = reverse('label_printing:preview')
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.post(url, {'skus': self.product.sku}).status_code, 403)

    def test_prints_real_code128_without_modifying_stock(self):
        self.client.force_login(self.warehouse)
        old_balance = BranchStock.objects.get(branch=self.branch, product=self.product).quantity
        r = self.client.post(reverse('label_printing:preview'), {
            'selected_skus': ['LABEL-001', 'LABEL-002'], 'copies': '2', 'mode': 'shelf',
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['count'], 4)
        self.assertContains(r, '0098765432101')
        self.assertContains(r, 'LABEL-002')
        self.assertContains(r, '100.00')
        self.assertContains(r, '&lt;b&gt;Printed Rice&lt;/b&gt;', html=False)
        self.assertNotContains(r, '<b>Printed Rice</b>', html=False)
        self.assertEqual(BranchStock.objects.get(branch=self.branch, product=self.product).quantity, old_balance)

    def test_unknown_inactive_and_unpriced_skipped(self):
        self.client.force_login(self.admin)
        result = self.client.post(reverse('label_printing:preview'), {'skus': 'LABEL-001, LABEL-003, LABEL-004, NOTREAL'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.context['count'], 1)
        self.assertEqual(len(result.context['skipped']), 3)

    def test_all_unpriced_fails_closed(self):
        self.client.force_login(self.manager)
        result = self.client.post(reverse('label_printing:preview'), {'skus': 'LABEL-003'})
        self.assertEqual(result.status_code, 400)

    def test_invalid_quantity_and_mass_input_rejected(self):
        self.client.force_login(self.admin)
        url = reverse('label_printing:preview')
        self.assertEqual(self.client.post(url, {'skus': 'LABEL-001', 'copies': '9'}).status_code, 400)
        self.assertEqual(self.client.post(url, {'skus': 'LABEL-001', 'mode': 'bad'}).status_code, 400)
        self.assertEqual(self.client.post(url, {'skus': ','.join(f'ITEM-{n}' for n in range(25))}).status_code, 400)
        self.assertEqual(self.client.post(url, {}).status_code, 400)

    def test_checkbox_and_typed_sku_deduplication(self):
        self.assertEqual(sku_input('label-001, LABEL-002', ['LABEL-001']), ['LABEL-001', 'LABEL-002'])

    def test_barcode_falls_back_to_sku_if_invalid(self):
        self.product.barcode = 'a' * 64
        self.assertEqual(choose_scan_code(self.product), 'LABEL-001')
        self.assertEqual(choose_scan_code(self.other), 'LABEL-002')

    def test_search_is_read_only(self):
        self.client.force_login(self.manager)
        r = self.client.get(reverse('label_printing:home'), {'q': 'LABEL-002'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'LABEL-002')
        self.assertNotContains(r, 'LABEL-001')
