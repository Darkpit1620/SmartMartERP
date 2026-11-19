from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models import Branch, StaffProfile
from .models import BranchStock, Category, Product, StockMovement
from .services import record_stock_movement


class SmartMartInventoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_superuser("stockadmin", "stockadmin@example.test", "TestPassword321!")
        cls.warehouse = User.objects.create_user("storekeeper", password="TestPassword321!")
        cls.cashier = User.objects.create_user("stockcashier", password="TestPassword321!")
        cls.other_warehouse = User.objects.create_user("otherkeeper", password="TestPassword321!")
        cls.pending = User.objects.create_user("pendingkeeper", password="TestPassword321!")
        cls.branch1 = Branch.objects.create(name="Nairobi Central", code="NAI")
        cls.branch2 = Branch.objects.create(name="Mombasa Central", code="MBA")
        StaffProfile.objects.create(user=cls.warehouse, role=StaffProfile.Role.WAREHOUSE, branch=cls.branch1, is_approved=True)
        StaffProfile.objects.create(user=cls.cashier, role=StaffProfile.Role.CASHIER, branch=cls.branch1, is_approved=True)
        StaffProfile.objects.create(user=cls.other_warehouse, role=StaffProfile.Role.WAREHOUSE, branch=cls.branch2, is_approved=True)
        StaffProfile.objects.create(user=cls.pending, role=StaffProfile.Role.WAREHOUSE, branch=cls.branch1, is_approved=False)
        cls.cat = Category.objects.create(name="Test Groceries")
        cls.product = Product.objects.create(category=cls.cat, name="Sample Rice 2 kg", sku="RICE-2KG", barcode="7771234567",
            cost_price=Decimal("180"), retail_price=Decimal("250"), wholesale_price=Decimal("220"))

    def test_catalogue_needs_login(self):
        result = self.client.get(reverse("inventory:product_list"))
        self.assertEqual(result.status_code, 302)

    def test_cashier_can_read_catalogue_but_not_change_stock(self):
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse("inventory:product_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("inventory:stock_list")).status_code, 403)
        self.assertEqual(self.client.post(reverse("inventory:stock_change", args=[self.product.id]), {
            "kind": "RECEIPT", "quantity": 10, "reference": "NO-ACCESS",
        }).status_code, 403)

    def test_pending_account_cannot_read_catalogue(self):
        self.client.force_login(self.pending)
        self.assertEqual(self.client.get(reverse("inventory:product_list")).status_code, 403)

    def test_new_product_has_zero_stock(self):
        self.assertFalse(BranchStock.objects.filter(product=self.product).exists())
        self.client.force_login(self.warehouse)
        response = self.client.get(reverse("inventory:stock_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Low stock")
        self.assertFalse(BranchStock.objects.filter(product=self.product).exists())

    def test_movement_receipt_and_adjustment_preserves_ledger(self):
        self.client.force_login(self.warehouse)
        url = reverse("inventory:stock_change", args=[self.product.id])
        response = self.client.post(url, {"kind": "RECEIPT", "quantity": 20, "reference": "DN-102"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(BranchStock.objects.get(branch=self.branch1, product=self.product).quantity, 20)
        self.client.post(url, {"kind": "CORRECTION_OUT", "quantity": 3, "reference": "COUNT-102"})
        self.assertEqual(BranchStock.objects.get(branch=self.branch1, product=self.product).quantity, 17)
        self.assertEqual(StockMovement.objects.filter(branch=self.branch1).count(), 2)
        self.assertEqual(StockMovement.objects.latest("pk").balance_after, 17)

    def test_cannot_make_branch_stock_negative(self):
        self.client.force_login(self.warehouse)
        url = reverse("inventory:stock_change", args=[self.product.id])
        result = self.client.post(url, {"kind": "CORRECTION_OUT", "quantity": 2, "reference": "COUNT-1"})
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "Not enough stock")
        self.assertEqual(StockMovement.objects.count(), 0)
        self.assertFalse(BranchStock.objects.filter(branch=self.branch1, product=self.product).exists())

    def test_warehouse_cannot_view_or_change_other_branch_stock(self):
        record_stock_movement(branch=self.branch2, product=self.product, actor=self.owner,
            kind="RECEIPT", quantity=40, reference="OTHER-BRANCH")
        self.client.force_login(self.warehouse)
        result = self.client.get(reverse("inventory:stock_list") + f"?branch={self.branch2.pk}")
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "Nairobi Central")
        self.assertNotContains(result, "Mombasa Central")
        self.assertNotContains(result, "40")
        self.client.post(reverse("inventory:stock_change", args=[self.product.pk]) + f"?branch={self.branch2.pk}", {
            "kind": "RECEIPT", "quantity": 2, "reference": "LOCAL",
        })
        self.assertEqual(BranchStock.objects.get(branch=self.branch2, product=self.product).quantity, 40)
        self.assertEqual(BranchStock.objects.get(branch=self.branch1, product=self.product).quantity, 2)

    def test_only_admin_can_create_products(self):
        self.client.force_login(self.warehouse)
        self.assertEqual(self.client.get(reverse("inventory:product_create")).status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("inventory:product_create")).status_code, 200)

    def test_admin_can_select_branch(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("inventory:stock_list") + f"?branch={self.branch2.pk}").status_code, 200)

    def test_barcode_optional_and_unique(self):
        alt = Product.objects.create(category=self.cat, name="No barcode", sku="NO-BARCODE",
            cost_price=0, retail_price=0, wholesale_price=0)
        self.assertIsNone(alt.barcode)
        self.assertEqual(Product.objects.filter(barcode__isnull=True).count(), 1)

    def test_cashier_cannot_see_stock_balances_or_cost_price(self):
        record_stock_movement(branch=self.branch1, product=self.product, actor=self.owner,
            kind="RECEIPT", quantity=77, reference="SECRET-BAL")
        self.client.force_login(self.cashier)
        result = self.client.get(reverse("inventory:product_detail", args=[self.product.pk]))
        self.assertEqual(result.status_code, 200)
        self.assertNotContains(result, "KSh 180.00")
        self.assertNotContains(result, "77 units")
        self.assertContains(result, "Stock balances are visible")

    def test_fractional_quantity_allowed_only_for_weighed_products(self):
        self.product.unit = Product.Unit.KG
        self.product.save()
        movement = record_stock_movement(branch=self.branch1, product=self.product, actor=self.owner,
            kind="RECEIPT", quantity=Decimal("1.250"), reference="WEIGH-1")
        self.assertEqual(movement.balance_after, Decimal("1.250"))
        self.product.unit = Product.Unit.EACH
        self.product.save()
        with self.assertRaises(ValidationError):
            record_stock_movement(branch=self.branch1, product=self.product, actor=self.owner,
                kind="RECEIPT", quantity=Decimal("0.500"), reference="INVALID-HALF-PIECE")
