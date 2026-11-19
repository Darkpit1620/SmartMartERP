import csv
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from inventory.models import Category, Product, BranchStock
from core.models import Branch

FIELDS = [
    "category", "name", "sku", "unit", "barcode", "cost_price",
    "retail_price", "wholesale_price", "wholesale_min_qty",
    "reorder_level", "tax_rate", "is_active",
]


class BulkCatalogueTests(TestCase):
    def _make_csv(self, path):
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerow(dict(category="Staples Test", name="Maize Flour 2 kg", sku="SM-TEST-00001", unit="PACK", barcode="", cost_price="0.00", retail_price="0.00", wholesale_price="0.00", wholesale_min_qty="6", reorder_level="5.000", tax_rate="0.00", is_active="True"))
            writer.writerow(dict(category="Electronics Test", name="Smartphone 8GB RAM 128GB", sku="SM-TEST-00002", unit="EACH", barcode="", cost_price="0.00", retail_price="0.00", wholesale_price="0.00", wholesale_min_qty="2", reorder_level="2.000", tax_rate="0.00", is_active="True"))

    def test_dry_run_import_and_repeat_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.csv"
            self._make_csv(path)
            call_command("import_bulk_catalogue", file=str(path), dry_run=True, verbosity=0)
            self.assertEqual(Product.objects.count(), 0)
            call_command("import_bulk_catalogue", file=str(path), verbosity=0)
            self.assertEqual(Product.objects.count(), 2)
            product = Product.objects.get(sku="SM-TEST-00001")
            product.retail_price = "123.00"
            product.save()
            call_command("import_bulk_catalogue", file=str(path), verbosity=0)
            self.assertEqual(Product.objects.count(), 2)
            product.refresh_from_db()
            self.assertEqual(str(product.retail_price), "123.00")
            self.assertFalse(BranchStock.objects.exists())

    def test_browse_requires_login_and_shows_departments(self):
        c = Category.objects.create(name="Staples Test")
        Product.objects.create(category=c, name="Maize Flour 2 kg", sku="SM-TEST-00001", unit="PACK", cost_price=0, retail_price=0, wholesale_price=0)
        url = reverse("smartmart_bulk:browse")
        anonymous = self.client.get(url)
        self.assertEqual(anonymous.status_code, 302)
        user = get_user_model().objects.create_superuser(username="storeadmin", email="admin@example.com", password="TestOnlyChange_12345!")
        self.client.force_login(user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Maize Flour 2 kg")
        self.assertContains(response, "Price pending")
        self.assertContains(response, "Not stocked") if Branch.objects.exists() else self.assertContains(response, "Branch not selected")
        response = self.client.get(url, {"q": "missing laptop"})
        self.assertEqual(response.context["page"].paginator.count, 0)
