from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models import Branch, StaffProfile
from inventory.models import Category, Product, BranchStock, StockMovement
from pos.models import Sale
from .models import (GoodsReceipt, PurchaseOrder, PurchaseOrderLine, Supplier,
                     WholesaleCustomer, WholesaleOrder, WholesaleOrderLine)
from .services import (fulfill_wholesale_order, prepare_wholesale_order,
                       receive_delivery, submit_purchase_order)


class TradingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(name='Main', code='MAINTR')
        cls.other_branch = Branch.objects.create(name='Riverside', code='RIVTR')
        cls.category = Category.objects.create(name='Trade Test Groceries')
        cls.product = Product.objects.create(
            category=cls.category, name='Test Rice 1 kg', sku='TEST-TR-001',
            cost_price=Decimal('70.00'), retail_price=Decimal('120.00'),
            wholesale_price=Decimal('100.00'), wholesale_min_qty=5,
            unit=Product.Unit.EACH, tax_rate=Decimal('0'),
        )
        cls.weight = Product.objects.create(
            category=cls.category, name='Test Loose Beans', sku='TEST-TR-002',
            cost_price=Decimal('50'), retail_price=Decimal('100'),
            wholesale_price=Decimal('85'), wholesale_min_qty=2,
            unit=Product.Unit.KG,
        )
        BranchStock.objects.create(branch=cls.branch, product=cls.product, quantity=Decimal('25.000'))
        BranchStock.objects.create(branch=cls.other_branch, product=cls.product, quantity=Decimal('10.000'))
        cls.supplier = Supplier.objects.create(name='Trading Test Supplier')
        cls.customer = WholesaleCustomer.objects.create(name='Trading Test Buyer')
        User = get_user_model()
        cls.manager = User.objects.create_user(username='trade_manager', password='test-password')
        cls.other_manager = User.objects.create_user(username='trade_other_manager', password='test-password')
        cls.warehouse = User.objects.create_user(username='trade_warehouse', password='test-password')
        cls.cashier = User.objects.create_user(username='trade_cashier', password='test-password')
        cls.pending = User.objects.create_user(username='trade_pending', password='test-password')
        cls.admin = User.objects.create_superuser('trade_root', 'root@example.test', 'test-password')
        for user, role, branch, approved in (
            (cls.manager, 'MANAGER', cls.branch, True),
            (cls.other_manager, 'MANAGER', cls.other_branch, True),
            (cls.warehouse, 'WAREHOUSE', cls.branch, True),
            (cls.cashier, 'CASHIER', cls.branch, True),
            (cls.pending, 'MANAGER', cls.branch, False),
        ):
            StaffProfile.objects.create(user=user, role=role, branch=branch, is_approved=approved)

    def po(self, qty='10'):
        order = PurchaseOrder.objects.create(branch=self.branch, supplier=self.supplier, created_by=self.manager)
        line = PurchaseOrderLine.objects.create(order=order, product=self.product, quantity=Decimal(qty), unit_cost=Decimal('70.00'))
        return order, line

    def wo(self, qty='5'):
        order = WholesaleOrder.objects.create(branch=self.branch, customer=self.customer, created_by=self.manager)
        WholesaleOrderLine.objects.create(order=order, product=self.product, quantity=Decimal(qty), quoted_unit_price=Decimal('100.00'))
        return order

    def test_goods_receipt_partial_then_full_and_audited(self):
        po, line = self.po()
        submit_purchase_order(po)
        grn1 = receive_delivery(order=po, actor=self.warehouse, delivery_note='TEST-DN-001', quantities={line.pk: '7'})
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.PARTIAL)
        self.assertEqual(grn1.lines.count(), 1)
        self.assertEqual(BranchStock.objects.get(branch=self.branch, product=self.product).quantity, Decimal('32.000'))
        grn2 = receive_delivery(order=po, actor=self.warehouse, delivery_note='TEST-DN-002', quantities={line.pk: '3'})
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.RECEIVED)
        self.assertEqual(BranchStock.objects.get(branch=self.branch, product=self.product).quantity, Decimal('35.000'))
        self.assertEqual(StockMovement.objects.filter(branch=self.branch, product=self.product, kind='RECEIPT').count(), 2)
        self.assertEqual(GoodsReceipt.objects.filter(order=po).count(), 2)

    def test_duplicate_delivery_reference_rejected_and_stock_unchanged(self):
        po, line = self.po()
        submit_purchase_order(po)
        receive_delivery(order=po, actor=self.warehouse, delivery_note='TEST-DN-003', quantities={line.pk: '3'})
        with self.assertRaises(ValidationError):
            receive_delivery(order=po, actor=self.warehouse, delivery_note='TEST-DN-003', quantities={line.pk: '2'})
        self.assertEqual(BranchStock.objects.get(branch=self.branch, product=self.product).quantity, Decimal('28.000'))

    def test_receipt_cannot_exceed_order_or_allow_fractional_packs(self):
        po, line = self.po()
        submit_purchase_order(po)
        for invalid in ('11', '1.5', 'NaN'):
            with self.assertRaises(ValidationError):
                receive_delivery(order=po, actor=self.warehouse,
                                 delivery_note='TEST-DN-004', quantities={line.pk: invalid})
        self.assertEqual(GoodsReceipt.objects.count(), 0)
        self.assertEqual(BranchStock.objects.get(branch=self.branch, product=self.product).quantity, Decimal('25.000'))

    def test_wholesale_uses_pos_receipt_and_decrements_once(self):
        order = self.wo()
        prepare_wholesale_order(order)
        done = fulfill_wholesale_order(order=order, actor=self.manager,
                                       method=Sale.PaymentMethod.CASH, tendered='700.00')
        self.assertEqual(done.sale.subtotal, Decimal('500.00'))
        self.assertEqual(done.sale.change_due, Decimal('200.00'))
        self.assertEqual(done.sale.sale_type, Sale.SaleType.WHOLESALE)
        self.assertEqual(done.sale.payment_status, Sale.PaymentStatus.CASH_RECEIVED)
        self.assertTrue(done.sale.receipt_number)
        self.assertEqual(BranchStock.objects.get(branch=self.branch, product=self.product).quantity, Decimal('20.000'))
        retried = fulfill_wholesale_order(order=order, actor=self.manager,
                                          method=Sale.PaymentMethod.CASH, tendered='700.00')
        self.assertEqual(retried.sale_id, done.sale_id)
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(BranchStock.objects.get(branch=self.branch, product=self.product).quantity, Decimal('20.000'))

    def test_wholesale_requires_stock_and_minimum(self):
        too_small = self.wo('4')
        prepare_wholesale_order(too_small)
        with self.assertRaises(ValidationError):
            fulfill_wholesale_order(order=too_small, actor=self.manager, method='CASH', tendered='1000')
        self.assertEqual(Sale.objects.count(), 0)
        huge = self.wo('30')
        prepare_wholesale_order(huge)
        with self.assertRaises(ValidationError):
            fulfill_wholesale_order(order=huge, actor=self.manager, method='CASH', tendered='3000')
        self.assertEqual(Sale.objects.count(), 0)

    def test_manual_mpesa_reference_is_unverified(self):
        order = self.wo()
        prepare_wholesale_order(order)
        done = fulfill_wholesale_order(order=order, actor=self.manager, method='MPESA', reference='FAKE-TEST-ONLY-88')
        self.assertEqual(done.sale.payment_status, Sale.PaymentStatus.UNVERIFIED)
        self.assertEqual(done.sale.subtotal, Decimal('500.00'))

    def test_portal_access_and_branch_isolation(self):
        po, line = self.po()
        wo = self.wo()
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse('trading:home')).status_code, 403)
        self.client.force_login(self.pending)
        self.assertEqual(self.client.get(reverse('trading:home')).status_code, 403)
        self.client.force_login(self.warehouse)
        self.assertEqual(self.client.get(reverse('trading:home')).status_code, 200)
        self.assertEqual(self.client.get(reverse('trading:purchase_detail', args=[po.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('trading:wholesale_detail', args=[wo.pk])).status_code, 403)
        self.client.force_login(self.other_manager)
        self.assertEqual(self.client.get(reverse('trading:purchase_detail', args=[po.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('trading:wholesale_detail', args=[wo.pk])).status_code, 404)

    def test_http_workflow_create_order_and_receive(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse('trading:purchase_new'), {'supplier': self.supplier.pk, 'notes': 'Test PO'})
        self.assertEqual(response.status_code, 302)
        po = PurchaseOrder.objects.get()
        self.client.post(reverse('trading:purchase_add_line', args=[po.pk]), {
            'product_code': self.product.sku, 'quantity': '10', 'unit_cost': '70.00',
        })
        self.assertEqual(po.lines.count(), 1)
        self.client.post(reverse('trading:purchase_place', args=[po.pk]))
        po.refresh_from_db()
        self.assertEqual(po.status, 'ORDERED')
        self.client.force_login(self.warehouse)
        line = po.lines.get()
        response = self.client.post(reverse('trading:purchase_receive', args=[po.pk]), {
            'delivery_note': 'TEST-DN-005', f'qty_{line.pk}': '10',
        })
        self.assertEqual(response.status_code, 302)
        po.refresh_from_db()
        self.assertEqual(po.status, 'RECEIVED')
        self.assertEqual(BranchStock.objects.get(branch=self.branch, product=self.product).quantity, Decimal('35.000'))

    def test_wholesale_form_uses_product_sku(self):
        self.client.force_login(self.manager)
        resp = self.client.post(reverse('trading:wholesale_new'), {'customer': self.customer.pk})
        self.assertEqual(resp.status_code, 302)
        wo = WholesaleOrder.objects.get()
        self.client.post(reverse('trading:wholesale_add_line', args=[wo.pk]), {
            'product_code': self.product.sku, 'quantity': '5',
        })
        self.assertEqual(wo.lines.count(), 1)
        self.client.post(reverse('trading:wholesale_prepare', args=[wo.pk]))
        wo.refresh_from_db()
        self.assertEqual(wo.status, 'READY')
        self.client.post(reverse('trading:wholesale_fulfill', args=[wo.pk]), {
            'payment_method': 'CASH', 'cash_tendered': '600.00',
        })
        wo.refresh_from_db()
        self.assertEqual(wo.status, 'FULFILLED')
        self.assertEqual(wo.sale.subtotal, Decimal('500.00'))
