"""Stage 10C: multi-module synthetic transactions, created ONLY in Django's test DB."""
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models import Branch, StaffProfile
from inventory.models import BranchStock, Category, Product, StockMovement
from pos.models import Sale, SaleItem
from pos.services import complete_sale
from trading.models import (
    GoodsReceipt, PurchaseOrder, PurchaseOrderLine, Supplier,
    WholesaleCustomer, WholesaleOrder, WholesaleOrderLine,
)
from trading.services import (
    receive_delivery, submit_purchase_order, prepare_wholesale_order,
    fulfill_wholesale_order,
)
from transfers.models import StockTransfer, TransferReceipt
from transfers.services import (
    create_transfer, add_transfer_line, dispatch_transfer, receive_transfer,
)
from finance_ops.models import Expense
from finance_ops.services import review_expense


class SmartMartFullTransactionTests(TestCase):
    """All objects below are test fixtures, never production sales or stock."""

    @classmethod
    def setUpTestData(cls):
        cls.main = Branch.objects.create(name="10C Testing Main", code="TEST10CMAIN")
        cls.remote = Branch.objects.create(name="10C Testing Second", code="TEST10CSEC")
        cls.category = Category.objects.create(name="10C Test Groceries")
        cls.product = Product.objects.create(
            category=cls.category, name="Stage 10C test maize flour", sku="SM10C-MAIZE-2KG",
            unit=Product.Unit.EACH, cost_price=Decimal("90.00"),
            retail_price=Decimal("150.00"), wholesale_price=Decimal("120.00"),
            wholesale_min_qty=5, tax_rate=Decimal("0"),
        )
        cls.unpriced = Product.objects.create(
            category=cls.category, name="Stage 10C not priced", sku="SM10C-UNPRICED",
            unit=Product.Unit.EACH, cost_price=Decimal("0.00"),
            retail_price=Decimal("0.00"), wholesale_price=Decimal("0.00"),
        )
        BranchStock.objects.create(branch=cls.main, product=cls.product, quantity=Decimal("0.000"))
        BranchStock.objects.create(branch=cls.remote, product=cls.product, quantity=Decimal("0.000"))
        cls.supplier = Supplier.objects.create(name="10C Testing Supplier")
        cls.customer = WholesaleCustomer.objects.create(name="10C Testing Buyer")
        User = get_user_model()
        cls.admin = User.objects.create_superuser("sm10c_admin", "test-admin@example.test", "test-password")
        cls.manager = User.objects.create_user("sm10c_manager", password="test-password")
        cls.cashier = User.objects.create_user("sm10c_cashier", password="test-password")
        cls.sender = User.objects.create_user("sm10c_sender", password="test-password")
        cls.receiver = User.objects.create_user("sm10c_receiver", password="test-password")
        cls.other_cashier = User.objects.create_user("sm10c_other_cashier", password="test-password")
        cls.pending = User.objects.create_user("sm10c_pending", password="test-password")
        for user, role, branch, approval in (
            (cls.manager, "MANAGER", cls.main, True),
            (cls.cashier, "CASHIER", cls.main, True),
            (cls.sender, "WAREHOUSE", cls.main, True),
            (cls.receiver, "WAREHOUSE", cls.remote, True),
            (cls.other_cashier, "CASHIER", cls.remote, True),
            (cls.pending, "CASHIER", cls.main, False),
        ):
            StaffProfile.objects.create(user=user, role=role, branch=branch, is_approved=approval)

    def balance(self, branch):
        return BranchStock.objects.get(branch=branch, product=self.product).quantity

    def purchase_and_receive(self, quantity="30"):
        po = PurchaseOrder.objects.create(branch=self.main, supplier=self.supplier,
                                          created_by=self.manager)
        line = PurchaseOrderLine.objects.create(
            order=po, product=self.product, quantity=Decimal(quantity), unit_cost=Decimal("90.00"))
        submit_purchase_order(po)
        return po, line

    def test_full_flow_purchase_retail_wholesale_transfer_and_finance(self):
        """One end-to-end sequence checks accounting and branch stock invariants."""
        po, line = self.purchase_and_receive("30")
        self.assertEqual(self.balance(self.main), Decimal("0.000"))
        receive_delivery(order=po, actor=self.sender, delivery_note="10C-DN-001",
                         quantities={line.pk: "20"})
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.PARTIAL)
        self.assertEqual(self.balance(self.main), Decimal("20.000"))
        receive_delivery(order=po, actor=self.sender, delivery_note="10C-DN-002",
                         quantities={line.pk: "10"})
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.RECEIVED)
        self.assertEqual(self.balance(self.main), Decimal("30.000"))
        self.assertEqual(GoodsReceipt.objects.filter(order=po).count(), 2)

        retail = complete_sale(
            branch=self.main, cashier=self.cashier,
            cart={str(self.product.pk): "2"}, mode=Sale.SaleType.RETAIL,
            method=Sale.PaymentMethod.CASH, token=uuid4().hex, tendered="500.00")
        self.assertEqual(retail.subtotal, Decimal("300.00"))
        self.assertEqual(retail.change_due, Decimal("200.00"))
        self.assertTrue(retail.receipt_number.startswith("SM-"))
        self.assertEqual(SaleItem.objects.filter(sale=retail).count(), 1)
        self.assertEqual(self.balance(self.main), Decimal("28.000"))
        self.assertEqual(complete_sale(
            branch=self.main, cashier=self.cashier,
            cart={str(self.product.pk): "2"}, mode=Sale.SaleType.RETAIL,
            method=Sale.PaymentMethod.CASH, token=retail.checkout_token,
            tendered="500.00").pk, retail.pk)
        self.assertEqual(self.balance(self.main), Decimal("28.000"))

        wo = WholesaleOrder.objects.create(
            branch=self.main, customer=self.customer, created_by=self.manager)
        WholesaleOrderLine.objects.create(
            order=wo, product=self.product, quantity=Decimal("6.000"),
            quoted_unit_price=Decimal("120.00"))
        prepare_wholesale_order(wo)
        fulfill_wholesale_order(order=wo, actor=self.manager,
                                method=Sale.PaymentMethod.CASH, tendered="720.00")
        wo.refresh_from_db()
        self.assertEqual(wo.status, WholesaleOrder.Status.FULFILLED)
        self.assertEqual(wo.sale.sale_type, Sale.SaleType.WHOLESALE)
        self.assertEqual(wo.sale.subtotal, Decimal("720.00"))
        self.assertEqual(self.balance(self.main), Decimal("22.000"))
        again = fulfill_wholesale_order(order=wo, actor=self.manager,
                                        method=Sale.PaymentMethod.CASH, tendered="720.00")
        self.assertEqual(again.sale_id, wo.sale_id)
        self.assertEqual(Sale.objects.count(), 2)

        move = create_transfer(source=self.main, destination=self.remote,
                               actor=self.manager, notes="Testing shipment")
        line = add_transfer_line(transfer=move, product=self.product, quantity="5")
        self.assertEqual(self.balance(self.main), Decimal("22.000"))
        dispatch_transfer(transfer=move, actor=self.sender)
        self.assertEqual(self.balance(self.main), Decimal("17.000"))
        self.assertEqual(self.balance(self.remote), Decimal("0.000"))
        receive_transfer(transfer=move, actor=self.receiver,
                         receipt_reference="10C-TR-001", quantities={line.pk: "2"})
        move.refresh_from_db()
        self.assertEqual(move.status, StockTransfer.Status.PARTIAL)
        self.assertEqual(self.balance(self.remote), Decimal("2.000"))
        receive_transfer(transfer=move, actor=self.receiver,
                         receipt_reference="10C-TR-002", quantities={line.pk: "3"})
        move.refresh_from_db()
        self.assertEqual(move.status, StockTransfer.Status.RECEIVED)
        self.assertEqual(self.balance(self.main), Decimal("17.000"))
        self.assertEqual(self.balance(self.remote), Decimal("5.000"))
        self.assertEqual(TransferReceipt.objects.filter(transfer=move).count(), 2)
        self.assertEqual(StockMovement.objects.filter(kind="TRANSFER_OUT").count(), 1)
        self.assertEqual(StockMovement.objects.filter(kind="TRANSFER_IN").count(), 2)

        expense = Expense.objects.create(
            branch=self.main, category=Expense.Category.OFFICE,
            amount=Decimal("50.00"), description="Test office supplies",
            recorded_by=self.manager)
        self.client.force_login(self.admin)
        before = self.client.get(reverse("finance_ops:overview"))
        self.assertEqual(before.status_code, 200)
        self.assertEqual(before.context["summary"]["recorded_sales"], Decimal("1020.00"))
        self.assertEqual(before.context["summary"]["confirmed_receipts"], Decimal("1020.00"))
        self.assertEqual(before.context["summary"]["approved_expenses"], Decimal("0.00"))
        self.assertEqual(before.context["summary"]["pending_expenses"], Decimal("50.00"))
        review_expense(pk=expense.pk, actor=self.admin, approve=True)
        after = self.client.get(reverse("finance_ops:overview"))
        self.assertEqual(after.context["summary"]["approved_expenses"], Decimal("50.00"))

    def test_failed_checkout_does_not_create_sale_or_negative_stock(self):
        po, line = self.purchase_and_receive("4")
        receive_delivery(order=po, actor=self.sender, delivery_note="10C-FOUR",
                         quantities={line.pk: "4"})
        with self.assertRaises(ValidationError):
            complete_sale(branch=self.main, cashier=self.cashier,
                          cart={str(self.product.pk): "5"},
                          mode=Sale.SaleType.RETAIL, method=Sale.PaymentMethod.CASH,
                          token=uuid4().hex, tendered="10000")
        self.assertEqual(self.balance(self.main), Decimal("4.000"))
        self.assertEqual(Sale.objects.count(), 0)

    def test_unverified_mpesa_is_not_confirmed_cash(self):
        po, line = self.purchase_and_receive("3")
        receive_delivery(order=po, actor=self.sender, delivery_note="10C-MPESA-GRN",
                         quantities={line.pk: "3"})
        sale = complete_sale(
            branch=self.main, cashier=self.cashier,
            cart={str(self.product.pk): "1"}, mode=Sale.SaleType.RETAIL,
            method=Sale.PaymentMethod.MPESA, token=uuid4().hex,
            reference="TEST-MPESA-REFERENCE")
        self.assertEqual(sale.payment_status, Sale.PaymentStatus.UNVERIFIED)
        self.assertEqual(self.balance(self.main), Decimal("2.000"))
        self.client.force_login(self.admin)
        report = self.client.get(reverse("finance_ops:overview"))
        self.assertEqual(report.context["summary"]["recorded_sales"], Decimal("150.00"))
        self.assertEqual(report.context["summary"]["unverified_receipts"], Decimal("150.00"))
        self.assertEqual(report.context["summary"]["confirmed_receipts"], Decimal("0.00"))

    def test_duplicate_delivery_reference_does_not_double_count(self):
        po, line = self.purchase_and_receive("10")
        receive_delivery(order=po, actor=self.sender, delivery_note="10C-ONLY-ONCE",
                         quantities={line.pk: "4"})
        with self.assertRaises(ValidationError):
            receive_delivery(order=po, actor=self.sender, delivery_note="10C-ONLY-ONCE",
                             quantities={line.pk: "3"})
        self.assertEqual(self.balance(self.main), Decimal("4.000"))
        self.assertEqual(GoodsReceipt.objects.count(), 1)

    def test_unpriced_products_are_not_sold(self):
        BranchStock.objects.create(branch=self.main, product=self.unpriced,
                                   quantity=Decimal("9.000"))
        with self.assertRaises(ValidationError):
            complete_sale(branch=self.main, cashier=self.cashier,
                          cart={str(self.unpriced.pk): "1"},
                          mode=Sale.SaleType.RETAIL, method=Sale.PaymentMethod.CASH,
                          token=uuid4().hex, tendered="2000")
        self.assertEqual(Sale.objects.count(), 0)

    def test_admin_hub_and_cashier_permissions(self):
        self.client.force_login(self.admin)
        page = self.client.get(reverse("transaction_checks:overview"))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["snapshot"]["catalogue_products"], 2)
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse("transaction_checks:overview")).status_code, 403)
        self.assertEqual(self.client.get(reverse("finance_ops:overview")).status_code, 403)
        self.assertEqual(self.client.get(reverse("transfers:list")).status_code, 403)
        self.client.force_login(self.pending)
        self.assertEqual(self.client.get(reverse("pos:index")).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("transaction_checks:overview")).status_code, 302)

    def test_manager_branch_finance_is_isolated(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("finance_ops:overview"), {"branch": self.remote.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["branch_rows"]), 1)
        self.assertEqual(response.context["branch_rows"][0]["branch"], self.main)
