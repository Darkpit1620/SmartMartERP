"""Security and data-integrity checks for the head-office pricing importer."""
import csv
import io
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import Branch, StaffProfile
from inventory.models import BranchStock, Category, Product


class PricingPortalTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="admin_prices", email="admin@example.com", password="TestOnly!ChangeMe12345"
        )
        self.manager = get_user_model().objects.create_user(
            username="manager_prices", password="TestOnly!ChangeMe12345"
        )
        branch = Branch.objects.create(code="TEST", name="Test Branch")
        StaffProfile.objects.create(user=self.manager, role="MANAGER", branch=branch, is_approved=True)
        cat = Category.objects.create(name="Bulk Pricing Test")
        self.product = Product.objects.create(
            category=cat, name="Maize Flour 2 kg", sku="PRICING-001", unit="PACK",
            cost_price=Decimal("65.00"), retail_price=Decimal("0.00"),
            wholesale_price=Decimal("0.00"), wholesale_min_qty=6,
        )
        BranchStock.objects.create(product=self.product, branch=branch, quantity=Decimal("20.000"))

    def upload(self, text, action="preview"):
        return self.client.post(
            reverse("pricing_portal:home"),
            {"action": action, "csv_file": SimpleUploadedFile(
                "prices.csv", text.encode("utf-8"), content_type="text/csv"
            )},
        )

    def test_requires_login_and_superuser(self):
        self.assertEqual(self.client.get(reverse("pricing_portal:home")).status_code, 302)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("pricing_portal:home")).status_code, 403)
        self.assertEqual(self.client.get(reverse("pricing_portal:export")).status_code, 403)
        self.assertEqual(self.upload("sku,retail_price\nPRICING-001,120\n", "import").status_code, 403)
        self.product.refresh_from_db()
        self.assertEqual(self.product.retail_price, 0)

    def test_preview_is_read_only_and_import_preserves_stock(self):
        self.client.force_login(self.admin)
        contents = "sku,name,retail_price,wholesale_price,cost_price,tax_rate,wholesale_min_qty\nPRICING-001,Test,120.00,100.00,,16.00,8\n"
        response = self.upload(contents, "preview")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Preview passed")
        self.product.refresh_from_db()
        self.assertEqual(self.product.retail_price, 0)
        response = self.upload(contents, "import")
        self.assertContains(response, "Prices updated:")
        self.product.refresh_from_db()
        self.assertEqual(self.product.retail_price, Decimal("120.00"))
        self.assertEqual(self.product.wholesale_price, Decimal("100.00"))
        self.assertEqual(self.product.cost_price, Decimal("65.00"))
        self.assertEqual(self.product.tax_rate, Decimal("16.00"))
        self.assertEqual(self.product.wholesale_min_qty, 8)
        self.assertEqual(BranchStock.objects.get(product=self.product).quantity, Decimal("20.000"))
        response = self.upload(contents, "import")
        self.assertContains(response, "Prices updated:")
        self.assertEqual(response.context["imported_count"], 0)

    def test_invalid_or_missing_sku_leaves_everything_intact(self):
        self.client.force_login(self.admin)
        csv_text = "sku,retail_price\nPRICING-001,150.00\nNOT-REAL,999.00\n"
        response = self.upload(csv_text, "import")
        self.assertContains(response, "No changes made")
        self.product.refresh_from_db()
        self.assertEqual(self.product.retail_price, 0)

    def test_duplicate_and_negative_values_rejected(self):
        self.client.force_login(self.admin)
        duplicates = "sku,retail_price\nPRICING-001,150\nPRICING-001,155\n"
        self.assertContains(self.upload(duplicates, "import"), "duplicate SKU")
        self.assertContains(self.upload("sku,retail_price\nPRICING-001,-100\n", "import"), "cannot be negative")
        self.assertContains(self.upload("sku,retail_price\nPRICING-001,0\n", "import"), "greater than zero")
        self.assertContains(self.upload("sku,tax_rate\nPRICING-001,101\n", "import"), "cannot exceed 100")
        self.product.refresh_from_db()
        self.assertEqual(self.product.retail_price, 0)

    def test_export_contains_skus_and_blank_pending_prices(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("pricing_portal:export"))
        self.assertEqual(response.status_code, 200)
        csv_text = response.content.decode("utf-8-sig")
        parsed = list(csv.DictReader(io.StringIO(csv_text)))
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["sku"], "PRICING-001")
        self.assertEqual(parsed[0]["retail_price"], "")
        self.assertEqual(parsed[0]["wholesale_price"], "")
        self.assertEqual(parsed[0]["cost_price"], "65.00")
