"""Tests use Django's temporary test database, never live supermarket records."""
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import Client, TestCase
from django.urls import reverse

from core.models import Branch, StaffProfile
from inventory.models import BranchStock, Category, Product
from pos.models import Sale
from pos.services import complete_sale
from .models import CashDrawerEntry, CashierShift
from .services import add_drawer_entry, allowed_shifts, cash_totals, close_shift, open_shift, review_shift


class CashierShiftTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(code='S13B1', name='Shift Test Branch', active=True)
        cls.other_branch = Branch.objects.create(code='S13B2', name='Other Shift Branch', active=True)
        c = Category.objects.create(name='Shift test groceries')
        cls.product = Product.objects.create(
            category=c, name='Rice sample', sku='S13B-RICE',
            unit=Product.Unit.EACH, retail_price=Decimal('120.00'),
            wholesale_price=Decimal('90.00'), wholesale_min_qty=5,
            cost_price=Decimal('80.00'), tax_rate=Decimal('0'),
        )
        BranchStock.objects.create(branch=cls.branch, product=cls.product, quantity=Decimal('100.000'))
        User = get_user_model()
        cls.cashier = User.objects.create_user('s13b_cashier', password='sample-testing-only')
        cls.second_cashier = User.objects.create_user('s13b_other', password='sample-testing-only')
        cls.manager = User.objects.create_user('s13b_manager', password='sample-testing-only')
        cls.other_manager = User.objects.create_user('s13b_other_manager', password='sample-testing-only')
        cls.warehouse = User.objects.create_user('s13b_warehouse', password='sample-testing-only')
        cls.pending = User.objects.create_user('s13b_pending', password='sample-testing-only')
        cls.admin = User.objects.create_superuser('s13b_admin', email='test@example.invalid', password='sample-testing-only')
        for who, role, branch, approved in [
            (cls.cashier, 'CASHIER', cls.branch, True),
            (cls.second_cashier, 'CASHIER', cls.other_branch, True),
            (cls.manager, 'MANAGER', cls.branch, True),
            (cls.other_manager, 'MANAGER', cls.other_branch, True),
            (cls.warehouse, 'WAREHOUSE', cls.branch, True),
            (cls.pending, 'CASHIER', cls.branch, False),
        ]:
            StaffProfile.objects.create(user=who, role=role, branch=branch, is_approved=approved)

    def _sale(self, method='CASH', qty='1'):
        return complete_sale(
            branch=self.branch, cashier=self.cashier,
            cart={str(self.product.pk): qty}, mode=Sale.SaleType.RETAIL,
            method=method, token=uuid4().hex,
            tendered='500' if method == 'CASH' else '',
            reference='TEST-MPESA-REF-1' if method != 'CASH' else '',
        )

    def test_cashier_opens_own_shift_and_unique_open(self):
        sh = open_shift(actor=self.cashier, opening_cash='200.00')
        self.assertEqual(sh.cashier_id, self.cashier.pk)
        self.assertEqual(sh.branch_id, self.branch.pk)
        self.assertEqual(sh.status, CashierShift.Status.OPEN)
        with self.assertRaises(ValidationError):
            open_shift(actor=self.cashier, opening_cash='1')
        self.assertEqual(CashierShift.objects.count(), 1)

    def test_unapproved_and_other_roles_cannot_open(self):
        for who in (self.manager, self.warehouse, self.pending, self.admin):
            with self.assertRaises(PermissionDenied):
                open_shift(actor=who, opening_cash='100')

    def test_invalid_amounts_are_not_accepted(self):
        for amount in ('-1', 'NaN', 'Infinity', '0.001', '', 'text', '1000000000000'):
            with self.assertRaises(ValidationError):
                open_shift(actor=self.cashier, opening_cash=amount)
        self.assertFalse(CashierShift.objects.exists())

    def test_cash_sales_only_and_variance_snapshot(self):
        sh = open_shift(actor=self.cashier, opening_cash='100.00')
        self._sale('CASH')
        self._sale('MPESA')
        self.assertEqual(cash_totals(sh)['cash_sales'], Decimal('120.00'))
        add_drawer_entry(shift=sh, actor=self.manager, kind='IN', amount='50',
                         reference='FLOAT-001', note='Extra float physically received')
        add_drawer_entry(shift=sh, actor=self.manager, kind='OUT', amount='25',
                         reference='PAYOUT-001', note='Approved cash paid out manually')
        done = close_shift(shift=sh, actor=self.cashier, counted_cash='240.00')
        self.assertEqual(done.expected_cash, Decimal('245.00'))
        self.assertEqual(done.variance, Decimal('-5.00'))
        with self.assertRaises(ValidationError):
            review_shift(shift=done, actor=self.manager, note='short')
        reviewed = review_shift(shift=done, actor=self.manager, note='Five shillings shortage checked')
        self.assertEqual(reviewed.status, CashierShift.Status.REVIEWED)
        self.assertEqual(reviewed.variance, Decimal('-5.00'))
        self.assertEqual(CashDrawerEntry.objects.count(), 2)

    def test_duplicate_cash_out_and_excess_out_are_blocked(self):
        sh = open_shift(actor=self.cashier, opening_cash='25')
        with self.assertRaises(ValidationError):
            add_drawer_entry(shift=sh, actor=self.manager, kind='OUT', amount='30',
                             reference='OUT-AAA', note='More than expected in drawer')
        add_drawer_entry(shift=sh, actor=self.manager, kind='OUT', amount='10',
                         reference='OUT-AAA', note='Ten shillings paid out physically')
        with self.assertRaises(ValidationError):
            add_drawer_entry(shift=sh, actor=self.manager, kind='OUT', amount='10',
                             reference='OUT-AAA', note='Duplicate entry not allowed')
        self.assertEqual(sh.entries.count(), 1)

    def test_cashier_and_other_manager_cannot_create_entries(self):
        sh = open_shift(actor=self.cashier, opening_cash='80')
        for who in (self.cashier, self.other_manager, self.warehouse):
            with self.assertRaises(PermissionDenied):
                add_drawer_entry(shift=sh, actor=who, kind='OUT', amount='1',
                                 reference='TEST-001', note='Not permitted for this user')
        self.assertEqual(sh.entries.count(), 0)

    def test_closing_twice_or_entry_after_closing_rejected(self):
        sh = open_shift(actor=self.cashier, opening_cash='100')
        close_shift(shift=sh, actor=self.cashier, counted_cash='100')
        with self.assertRaises(ValidationError):
            close_shift(shift=sh, actor=self.cashier, counted_cash='100')
        with self.assertRaises(ValidationError):
            add_drawer_entry(shift=sh, actor=self.manager, kind='IN', amount='10',
                             reference='LATE-001', note='Attempted after closing shift')
        self.assertEqual(sh.entries.count(), 0)
        sh.refresh_from_db()
        self.assertEqual(sh.expected_cash, Decimal('100.00'))

    def test_manager_emergency_close_requires_reason(self):
        sh = open_shift(actor=self.cashier, opening_cash='30')
        with self.assertRaises(ValidationError):
            close_shift(shift=sh, actor=self.manager, counted_cash='30')
        done = close_shift(shift=sh, actor=self.manager, counted_cash='30',
                           note='Cashier left the premises unexpectedly')
        self.assertEqual(done.closed_by_id, self.manager.pk)

    def test_branch_permissions_and_warehouse_denied(self):
        sh = open_shift(actor=self.cashier, opening_cash='10')
        for who in (self.second_cashier, self.other_manager, self.warehouse, self.pending):
            self.client.force_login(who)
            self.assertEqual(self.client.get(reverse('shift_ops:detail', args=[sh.pk])).status_code,
                             403 if who in (self.warehouse, self.pending) else 404)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse('shift_ops:detail', args=[sh.pk])).status_code, 200)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('shift_ops:detail', args=[sh.pk])).status_code, 200)

    def test_real_pos_sale_is_visible_on_shift_page(self):
        sh = open_shift(actor=self.cashier, opening_cash='5')
        receipt = self._sale()
        self.client.force_login(self.cashier)
        response = self.client.get(reverse('shift_ops:detail', args=[sh.pk]))
        self.assertContains(response, receipt.receipt_number)
        self.assertContains(response, '125.00')

    def test_cross_branch_close_denied(self):
        sh = open_shift(actor=self.cashier, opening_cash='10')
        with self.assertRaises(PermissionDenied):
            close_shift(shift=sh, actor=self.other_manager, counted_cash='10',
                        note='Emergency closing at wrong branch')
        self.assertEqual(sh.status, CashierShift.Status.OPEN)

    def test_csrf_required_for_cash_movement(self):
        sh = open_shift(actor=self.cashier, opening_cash='10')
        web = Client(enforce_csrf_checks=True)
        web.force_login(self.manager)
        self.assertEqual(web.post(reverse('shift_ops:entry', args=[sh.pk]), {
            'kind': 'IN', 'amount': '5', 'reference': 'REF-001', 'note': 'Physical movement'}).status_code, 403)
        self.assertEqual(sh.entries.count(), 0)

    def test_snapshot_not_changed_by_later_sale(self):
        sh = open_shift(actor=self.cashier, opening_cash='10')
        self._sale()
        done = close_shift(shift=sh, actor=self.cashier, counted_cash='130')
        self._sale()
        done.refresh_from_db()
        self.assertEqual(done.expected_cash, Decimal('130.00'))
        self.assertEqual(done.variance, Decimal('0.00'))
        self.assertEqual(cash_totals(done, done.closed_at)['cash_sales'], Decimal('120.00'))

    def test_another_shift_after_close_allowed(self):
        sh = open_shift(actor=self.cashier, opening_cash='10')
        close_shift(shift=sh, actor=self.cashier, counted_cash='10')
        next_shift = open_shift(actor=self.cashier, opening_cash='25')
        self.assertNotEqual(sh.pk, next_shift.pk)
        self.assertEqual(next_shift.status, CashierShift.Status.OPEN)
