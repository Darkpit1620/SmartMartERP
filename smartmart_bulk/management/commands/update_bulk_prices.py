"""Import verified business prices for existing products, without affecting stock."""
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from inventory.models import Product


class Command(BaseCommand):
    help = "Update verified retail/wholesale/cost prices from CSV. Blank fields are ignored."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="CSV with sku and one or more of retail_price, wholesale_price, cost_price, tax_rate")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        path = Path(opts["file"]).expanduser().resolve()
        if not path.is_file():
            raise CommandError(f"File not found: {path}")
        changes = []
        try:
            with path.open(encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                columns = reader.fieldnames or []
                allowed = ("retail_price", "wholesale_price", "cost_price", "tax_rate")
                if "sku" not in columns or not set(allowed).intersection(columns):
                    raise CommandError("CSV requires SKU and at least one price/tax column")
                seen = set()
                for row_no, row in enumerate(reader, 2):
                    sku = (row.get("sku") or "").strip().upper()
                    if not sku:
                        continue
                    if sku in seen:
                        raise CommandError(f"Duplicate SKU on CSV line {row_no}: {sku}")
                    seen.add(sku)
                    updates = {}
                    for field in allowed:
                        value = (row.get(field) or "").strip()
                        if not value:
                            continue
                        try:
                            number = Decimal(value)
                        except InvalidOperation:
                            raise CommandError(f"Invalid {field} on CSV line {row_no}")
                        if not number.is_finite() or number < 0 or (field == "tax_rate" and number > 100):
                            raise CommandError(f"Invalid {field} on CSV line {row_no}")
                        if field in ("retail_price", "wholesale_price") and number == 0:
                            raise CommandError(f"{field} must be positive on CSV line {row_no}")
                        if -number.as_tuple().exponent > 2:
                            raise CommandError(f"{field} may have at most two decimal places (line {row_no})")
                        updates[field] = number
                    if updates:
                        changes.append((sku, updates))
        except (OSError, UnicodeError) as exc:
            raise CommandError(str(exc)) from exc
        existing = Product.objects.in_bulk([sku for sku, _ in changes], field_name="sku")
        missing = [sku for sku, _ in changes if sku not in existing]
        if missing:
            raise CommandError(f"Unknown SKU(s), no changes made: {', '.join(missing[:12])}")
        self.stdout.write(f"Validated verified pricing for {len(changes)} products.")
        if opts["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Dry run succeeded; database unchanged."))
            return
        with transaction.atomic():
            for sku, updates in changes:
                Product.objects.filter(pk=existing[sku].pk).update(**updates)
        self.stdout.write(self.style.SUCCESS(f"Updated {len(changes)} products. Stock quantities unchanged."))
