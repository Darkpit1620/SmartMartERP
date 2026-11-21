"""Supplier ledger: amount ceilings, duplicate protection, role isolation, CSV safety."""
import csv
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from core.models import Branch, StaffProfile
from inventory.models import Category, Product, BranchStock
from trading.models import PurchaseOrder, PurchaseOrderLine, Supplier
from .models import SupplierInvoice, SupplierPayment
from .services import record_invoice, record_payment


class SupplierAccountsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(code='ACCOUNT-1', name='Supplier Accounts North')
        cls.other = Branch.objects.create(code='ACCOUNT-2', name='Supplier Accounts South')
        cls.supplier = Supplier.objects.create(name='Sample Supplier Ledger')
        cls.cat = Category.objects.create(name='Supplier accounts products')
        cls.product = Product.objects.create(category=cls.cat, sku='SUP-ACC-001', name='Supplier Ledger Flour',
                                             retail_price=Decimal('150.00'), wholesale_price=Decimal('130.00'), cost_price=Decimal('100.00'))
        cls.stock = BranchStock.objects.create(branch=cls.branch, product=cls.product, quantity=Decimal('17.000'))
        User = get_user_model()
        cls.admin = User.objects.create_superuser('supp_admin', 'supp_admin@example.test', 'test-password-1')
        cls.manager = User.objects.create_user('supp_mgr', password='test-password-1')
        cls.other_manager = User.objects.create_user('supp_other_mgr', password='test-password-1')
        cls.cashier = User.objects.create_user('supp_cashier', password='test-password-1')
        cls.warehouse = User.objects.create_user('supp_warehouse', password='test-password-1')
        cls.pending = User.objects.create_user('supp_pending', password='test-password-1')
        for user, role, branch, approved in (
            (cls.manager, 'MANAGER', cls.branch, True),
            (cls.other_manager, 'MANAGER', cls.other, True),
            (cls.cashier, 'CASHIER', cls.branch, True),
            (cls.warehouse, 'WAREHOUSE', cls.branch, True),
            (cls.pending, 'MANAGER', cls.branch, False),
        ):
            StaffProfile.objects.create(user=user, role=role, branch=branch, is_approved=approved)
        cls.po = PurchaseOrder.objects.create(branch=cls.branch, supplier=cls.supplier,
                                              created_by=cls.manager, status=PurchaseOrder.Status.ORDERED)
        PurchaseOrderLine.objects.create(order=cls.po, product=cls.product,
                                         quantity=Decimal('2.000'), unit_cost=Decimal('100.00'))
        cls.other_po = PurchaseOrder.objects.create(branch=cls.other, supplier=cls.supplier,
                                                    created_by=cls.other_manager, status=PurchaseOrder.Status.ORDERED)
        PurchaseOrderLine.objects.create(order=cls.other_po, product=cls.product,
                                         quantity=Decimal('2.000'), unit_cost=Decimal('100.00'))

    def new_invoice(self, *, po=None, actor=None, amount='150.00', number='BILL-100'):
        day = timezone.localdate()
        return record_invoice(purchase_order=po or self.po, actor=actor or self.manager,
                              invoice_number=number, invoice_date=day, due_date=day+timedelta(days=10),
                              amount=amount)

    def new_payment(self, inv, *, amount='50.00', reference='PAY-001', actor=None):
        return record_payment(invoice=inv, actor=actor or self.manager, amount=amount,
                              method='BANK', reference=reference, paid_on=timezone.localdate())

    def test_invoice_multiple_partial_payments_and_exact_balance(self):
        i = self.new_invoice()
        self.assertEqual(i.amount, Decimal('150.00'))
        self.assertEqual(i.balance, Decimal('150.00'))
        self.new_payment(i)
        self.assertEqual(i.paid_amount, Decimal('50.00'))
        self.assertEqual(i.balance, Decimal('100.00'))
        self.new_payment(i, amount='100.00', reference='PAY-002')
        self.assertEqual(i.balance, Decimal('0.00'))
        self.assertEqual(i.state, 'Paid')
        self.assertEqual(SupplierPayment.objects.count(), 2)

    def test_prevent_excess_invoicing_and_supplier_duplicate(self):
        self.new_invoice(amount='150', number='BILL-100')
        self.new_invoice(amount='50', number='BILL-101')
        with self.assertRaises(ValidationError):
            self.new_invoice(amount='1', number='BILL-102')
        with self.assertRaises(ValidationError):
            self.new_invoice(po=self.other_po, actor=self.other_manager, amount='50', number='bill-100')
        self.assertEqual(SupplierInvoice.objects.count(), 2)

    def test_reject_draft_and_invalid_invoice(self):
        PurchaseOrder.objects.filter(pk=self.po.pk).update(status=PurchaseOrder.Status.DRAFT)
        with self.assertRaises(ValidationError):
            self.new_invoice()
        PurchaseOrder.objects.filter(pk=self.po.pk).update(status=PurchaseOrder.Status.ORDERED)
        for amount in ('0', '-12', '10.001', 'NaN', 'Infinity'):
            with self.subTest(amount=amount):
                with self.assertRaises(ValidationError):
                    self.new_invoice(amount=amount)
        self.assertFalse(SupplierInvoice.objects.exists())

    def test_reject_overpay_duplicate_ref_and_future_payment(self):
        inv = self.new_invoice(amount='100')
        self.new_payment(inv, amount='60', reference='PAY-001')
        with self.assertRaises(ValidationError):
            self.new_payment(inv, amount='41', reference='PAY-002')
        with self.assertRaises(ValidationError):
            self.new_payment(inv, amount='10', reference='pay-001')
        with self.assertRaises(ValidationError):
            record_payment(invoice=inv, actor=self.manager, amount='10', method='BANK', reference='PAY-NEW',
                           paid_on=timezone.localdate()+timedelta(days=1))
        self.assertEqual(inv.balance, Decimal('40.00'))
        self.assertEqual(SupplierPayment.objects.count(), 1)

    def test_services_enforce_branch_and_approval(self):
        with self.assertRaises(PermissionDenied):
            self.new_invoice(actor=self.cashier)
        with self.assertRaises(PermissionDenied):
            self.new_invoice(actor=self.pending)
        with self.assertRaises(PermissionDenied):
            self.new_invoice(actor=self.other_manager)
        inv = self.new_invoice()
        with self.assertRaises(PermissionDenied):
            self.new_payment(inv, actor=self.other_manager)
        self.new_payment(inv, actor=self.admin)

    def test_no_stock_or_purchase_receipt_changes(self):
        original = BranchStock.objects.get(pk=self.stock.pk).quantity
        invoice = self.new_invoice()
        self.new_payment(invoice)
        self.assertEqual(BranchStock.objects.get(pk=self.stock.pk).quantity, original)
        self.assertEqual(self.po.receipts.count(), 0)
        self.assertEqual(PurchaseOrder.objects.get(pk=self.po.pk).status, PurchaseOrder.Status.ORDERED)

    def test_no_anonymous_or_warehouse_access(self):
        self.assertEqual(self.client.get(reverse('supplier_accounts:home')).status_code, 302)
        for actor in (self.cashier, self.warehouse, self.pending):
            self.client.force_login(actor)
            self.assertEqual(self.client.get(reverse('supplier_accounts:home')).status_code, 403)
            self.assertEqual(self.client.post(reverse('supplier_accounts:invoice_new'), {}).status_code, 403)
        self.assertFalse(SupplierInvoice.objects.exists())

    def test_branch_scoping_on_invoice_detail_post_and_csv(self):
        invoice = self.new_invoice()
        self.client.force_login(self.other_manager)
        self.assertEqual(self.client.get(reverse('supplier_accounts:detail', args=[invoice.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('supplier_accounts:payment_new', args=[invoice.pk]),
                                          {'amount':'10', 'method':'CASH', 'reference':'NOT-MINE',
                                           'paid_on':str(timezone.localdate())}).status_code, 404)
        self.assertNotIn('BILL-100', self.client.get(reverse('supplier_accounts:export')).content.decode())
        self.client.force_login(self.manager)
        self.assertContains(self.client.get(reverse('supplier_accounts:home')), 'BILL-100')
        self.assertContains(self.client.get(reverse('supplier_accounts:detail', args=[invoice.pk])), 'BILL-100')

    def test_csv_escapes_supplier_formula_and_money_is_two_decimals(self):
        bad = Supplier.objects.create(name='=CMD(1)')
        po = PurchaseOrder.objects.create(branch=self.branch, supplier=bad,
                                          created_by=self.manager, status=PurchaseOrder.Status.ORDERED)
        PurchaseOrderLine.objects.create(order=po, product=self.product, quantity=Decimal('1'), unit_cost=Decimal('100'))
        self.new_invoice(po=po, number='=EVIL', amount='100')
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('supplier_accounts:export'))
        self.assertEqual(resp.status_code, 200)
        data = list(csv.reader(StringIO(resp.content.decode('utf-8'))))
        self.assertTrue(any(row[0] == "'=CMD(1)" and row[1] == "'=EVIL" and row[5] == '100.00' for row in data))

    def test_http_record_invoice_and_payment_nonmutating_get(self):
        self.client.force_login(self.manager)
        url = reverse('supplier_accounts:invoice_new')
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(SupplierInvoice.objects.count(), 0)
        day = timezone.localdate()
        resp = self.client.post(url, {'purchase_order':self.po.pk, 'invoice_number':'REAL-PO-100',
                 'invoice_date':str(day), 'due_date':str(day+timedelta(days=5)), 'amount':'100.00'})
        self.assertEqual(resp.status_code, 302)
        inv = SupplierInvoice.objects.get()
        pay_url = reverse('supplier_accounts:payment_new', args=[inv.pk])
        self.assertEqual(self.client.get(pay_url).status_code, 200)
        self.assertEqual(SupplierPayment.objects.count(), 0)
        resp = self.client.post(pay_url, {'amount':'100', 'method':'MPESA',
                                         'reference':'PAID-EXT-1', 'paid_on':str(day)})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(inv.balance, Decimal('0.00'))
