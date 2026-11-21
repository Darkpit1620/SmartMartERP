from decimal import Decimal
import hashlib
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import Client, TestCase
from django.urls import reverse
from core.models import Branch, StaffProfile
from inventory.models import BranchStock, Category, Product, StockMovement
from pos.models import Sale
from pos.services import complete_sale
from .models import ReturnLine, ReturnRequest
from .services import request_return, review_return, record_paid_refund


class ReturnTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(name='Stage13 Training', code='STAGE13', active=True)
        cls.other = Branch.objects.create(name='Other branch', code='STAGE13X', active=True)
        cat = Category.objects.create(name='Stage13 test groceries')
        cls.item = Product.objects.create(name='Training Rice', category=cat, sku='STAGE13-RICE',
            unit=Product.Unit.EACH, cost_price=60, retail_price=100, wholesale_price=90)
        BranchStock.objects.create(branch=cls.branch, product=cls.item, quantity=Decimal('10.000'))
        U = get_user_model()
        cls.cashier = U.objects.create_user(username='stage13cashier', password='test')
        cls.manager = U.objects.create_user(username='stage13manager', password='test')
        cls.other_manager = U.objects.create_user(username='stage13other', password='test')
        cls.warehouse = U.objects.create_user(username='stage13warehouse', password='test')
        cls.admin = U.objects.create_superuser(username='stage13admin', email='admin@example.invalid', password='test')
        for user, role, branch in ((cls.cashier, 'CASHIER', cls.branch), (cls.manager, 'MANAGER', cls.branch),
            (cls.other_manager, 'MANAGER', cls.other), (cls.warehouse, 'WAREHOUSE', cls.branch)):
            StaffProfile.objects.create(user=user, role=role, branch=branch, is_approved=True)

    def setUp(self):
        self.sale = complete_sale(branch=self.branch, cashier=self.cashier,
            cart={str(self.item.pk): '4'}, mode=Sale.SaleType.RETAIL,
            method=Sale.PaymentMethod.CASH, token='stage13-' + hashlib.sha256(self._testMethodName.encode('utf-8')).hexdigest()[:32], tendered='500')
        self.line = self.sale.items.first()

    def create_request(self, qty='2'):
        return request_return(sale=self.sale, sale_item=self.line, actor=self.cashier,
            quantity=qty, reason='Product packet damaged')

    def stock(self):
        return BranchStock.objects.get(branch=self.branch, product=self.item).quantity

    def test_approve_and_restock_preserves_receipt_and_audits_stock(self):
        case = self.create_request()
        self.assertEqual(self.stock(), Decimal('6.000'))
        review_return(case=case, actor=self.manager, approve=True, restock=True, note='Sealed item')
        self.assertEqual(self.stock(), Decimal('8.000'))
        self.assertEqual(StockMovement.objects.filter(reference=f'RETURN-{case.pk}').count(), 1)
        self.assertEqual(case.amount, Decimal('200.00'))
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.subtotal, Decimal('400.00'))
        self.assertEqual(self.sale.items.count(), 1)

    def test_repeated_return_not_over_quantity_and_no_duplicate_review(self):
        c = self.create_request('3')
        with self.assertRaises(ValidationError):
            self.create_request('2')
        review_return(case=c, actor=self.manager, approve=True, restock=True)
        with self.assertRaises(ValidationError):
            review_return(case=c, actor=self.manager, approve=True, restock=True)
        self.assertEqual(self.stock(), Decimal('9.000'))

    def test_reject_frees_quantity_and_no_stock_changes(self):
        c = self.create_request('4')
        review_return(case=c, actor=self.manager, approve=False, note='No proof of return')
        self.assertEqual(self.stock(), Decimal('6.000'))
        self.assertEqual(self.create_request('4').amount, Decimal('400.00'))

    def test_refund_record_requires_confirmation_and_is_not_double_paid(self):
        case = self.create_request()
        with self.assertRaises(ValidationError):
            record_paid_refund(case=case, actor=self.manager, method='CASH', reference='', confirmed=True)
        review_return(case=case, actor=self.manager, approve=True)
        with self.assertRaises(ValidationError):
            record_paid_refund(case=case, actor=self.manager, method='MPESA', reference='', confirmed=True)
        with self.assertRaises(ValidationError):
            record_paid_refund(case=case, actor=self.manager, method='CASH', reference='', confirmed=False)
        record_paid_refund(case=case, actor=self.manager, method='MPESA', reference='OFFLINE-TEST-1234', confirmed=True)
        with self.assertRaises(ValidationError):
            record_paid_refund(case=case, actor=self.manager, method='MPESA', reference='OFFLINE-TEST-1234', confirmed=True)
        case.refresh_from_db()
        self.assertEqual(case.refund_status, ReturnRequest.RefundStatus.RECORDED)
        self.assertEqual(self.stock(), Decimal('6.000'))

    def test_cross_branch_and_cashier_cannot_approve(self):
        c = self.create_request()
        for user in (self.cashier, self.other_manager, self.warehouse):
            with self.assertRaises(PermissionDenied):
                review_return(case=c, actor=user, approve=True, restock=True)
        self.assertEqual(c.status, ReturnRequest.Status.REQUESTED)

    def test_http_permissions_csrf_and_manager_workflow(self):
        self.client.force_login(self.cashier)
        url = reverse('returns_ops:new', args=[self.sale.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        res = self.client.post(url, {'sale_item_id': self.line.pk, 'quantity': '2', 'reason': 'Damaged packet on arrival'})
        self.assertEqual(res.status_code, 302)
        case = ReturnRequest.objects.get()
        self.assertEqual(self.client.post(reverse('returns_ops:review', args=[case.pk]),
            {'decision': 'approve'}).status_code, 403)
        self.client.force_login(self.other_manager)
        self.assertEqual(self.client.get(reverse('returns_ops:detail', args=[case.pk])).status_code, 404)
        self.client.force_login(self.warehouse)
        self.assertEqual(self.client.get(reverse('returns_ops:home')).status_code, 403)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.post(reverse('returns_ops:review', args=[case.pk]),
            {'decision': 'approve', 'restock': 'yes'}).status_code, 302)
        case.refresh_from_db()
        self.assertEqual(case.status, ReturnRequest.Status.APPROVED)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.manager)
        self.assertEqual(csrf_client.post(reverse('returns_ops:record_refund', args=[case.pk]),
            {'confirmed': 'yes', 'refund_method': 'CASH'}).status_code, 403)

    def test_no_return_on_unverified_payment(self):
        Sale.objects.filter(pk=self.sale.pk).update(payment_status=Sale.PaymentStatus.UNVERIFIED)
        self.sale.refresh_from_db()
        with self.assertRaises(ValidationError):
            self.create_request()

    def test_packaged_product_fractional_returns_rejected(self):
        with self.assertRaises(ValidationError):
            self.create_request('0.5')
        self.assertEqual(ReturnRequest.objects.count(), 0)
