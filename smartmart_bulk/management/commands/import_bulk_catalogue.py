"""Safe, repeatable import of a generic supermarket product master catalogue."""
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from inventory.models import Category, Product

DEFAULT_CSV = Path(__file__).resolve().parents[2] / "data" / "smartmart_bulk_catalogue.csv"
REQUIRED = {
    "category", "name", "sku", "unit", "barcode", "cost_price",
    "retail_price", "wholesale_price", "wholesale_min_qty", "reorder_level", "tax_rate", "is_active"
}


class Command(BaseCommand):
    help = "Load the SmartMart bulk product catalogue without changing existing products, stock, or pricing."

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str, help="Optional alternative CSV to import")
        parser.add_argument("--dry-run", action="store_true", help="Validate the file without changing the database")

    def handle(self, *args, **options):
        path = Path(options["file"]).expanduser().resolve() if options["file"] else DEFAULT_CSV
        if not path.is_file():
            raise CommandError(f"Product CSV missing: {path}")
        self.stdout.write(f"Reading catalogue: {path}")
        valid_units = set(Product.Unit.values)
        records = []
        seen = set()
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames or not REQUIRED.issubset(reader.fieldnames):
                    raise CommandError("The CSV is missing required fields: " + ", ".join(sorted(REQUIRED - set(reader.fieldnames or []))))
                for line_no, row in enumerate(reader, start=2):
                    sku = (row["sku"] or "").strip().upper()
                    name = (row["name"] or "").strip()
                    category = (row["category"] or "").strip()
                    unit = (row["unit"] or "").strip().upper()
                    if not sku or len(sku) > 48 or not name or len(name) > 170 or not category or len(category) > 100:
                        raise CommandError(f"Line {line_no}: missing or oversized SKU, name, or category")
                    if sku in seen:
                        raise CommandError(f"Line {line_no}: duplicate SKU {sku} inside the file")
                    seen.add(sku)
                    if unit not in valid_units:
                        raise CommandError(f"Line {line_no}: invalid unit {unit}")
                    barcode = (row["barcode"] or "").strip() or None
                    if barcode and len(barcode) > 64:
                        raise CommandError(f"Line {line_no}: barcode too long")
                    try:
                        cost = Decimal(row["cost_price"])
                        retail = Decimal(row["retail_price"])
                        wholesale = Decimal(row["wholesale_price"])
                        minimum = int(row["wholesale_min_qty"])
                        reorder = Decimal(row["reorder_level"])
                        tax = Decimal(row["tax_rate"])
                    except (ValueError, InvalidOperation, TypeError) as exc:
                        raise CommandError(f"Line {line_no}: invalid number: {exc}") from exc
                    if min(cost, retail, wholesale, reorder, tax) < 0 or tax > 100 or minimum < 1:
                        raise CommandError(f"Line {line_no}: prices, reorder levels, quantities or tax rates out of bounds")
                    if row["is_active"].strip().casefold() not in {"true", "false"}:
                        raise CommandError(f"Line {line_no}: is_active must be True or False")
                    records.append({
                        "category_name": category, "sku": sku, "name": name, "unit": unit,
                        "barcode": barcode, "cost_price": cost, "retail_price": retail,
                        "wholesale_price": wholesale, "wholesale_min_qty": minimum,
                        "reorder_level": reorder, "tax_rate": tax,
                        "is_active": row["is_active"].strip().casefold() == "true",
                    })
        except (OSError, UnicodeError) as exc:
            raise CommandError(f"Cannot read CSV: {exc}") from exc

        # Validate every line before writing anything. Existing rows are never overwritten.
        existing = set(Product.objects.values_list("sku", flat=True))
        needed = [record for record in records if record["sku"] not in existing]
        self.stdout.write(f"File: {len(records)} products. Already present: {len(records) - len(needed)}. To add: {len(needed)}")
        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Dry run passed: database unchanged."))
            return

        with transaction.atomic():
            category_cache = {}
            for category_name in sorted(set(r["category_name"] for r in needed)):
                category_cache[category_name], _ = Category.objects.get_or_create(name=category_name)
            new_products = [
                Product(
                    category=category_cache[record["category_name"]],
                    **{key: value for key, value in record.items() if key != "category_name"}
                ) for record in needed
            ]
            Product.objects.bulk_create(new_products, batch_size=250, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(
            f"Catalogue imported. {len(needed)} candidate products added; existing records preserved."
        ))
        self.stdout.write("New products have no barcodes, prices or stock until your team enters verified business data.")
