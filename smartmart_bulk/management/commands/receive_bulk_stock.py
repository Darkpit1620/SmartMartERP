"""Receive genuine delivered stock into a branch with a movement audit record."""
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Branch
from inventory.models import Product, StockMovement
from inventory.services import record_stock_movement


class Command(BaseCommand):
    help = "Receive actual supplier quantities using CSV: sku,quantity,reference. Idempotent per branch/SKU/reference."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument("--branch", required=True, help="Existing store branch code, such as MAIN")
        parser.add_argument("--actor", required=True, help="Existing active superuser username")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        path = Path(opts["file"]).expanduser().resolve()
        if not path.is_file():
            raise CommandError(f"File not found: {path}")
        branch = Branch.objects.filter(code__iexact=opts["branch"], active=True).first()
        if not branch:
            raise CommandError("Active branch code not found")
        actor = get_user_model().objects.filter(username=opts["actor"], is_superuser=True, is_active=True).first()
        if not actor:
            raise CommandError("Actor must be an existing active superuser")
        entries=[]
        try:
            with path.open(encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                if not {"sku", "quantity", "reference"}.issubset(reader.fieldnames or []):
                    raise CommandError("CSV must contain sku, quantity and reference")
                seen=set()
                for line,row in enumerate(reader,2):
                    sku=(row.get("sku") or "").strip().upper()
                    qty=(row.get("quantity") or "").strip()
                    reference=(row.get("reference") or "").strip()
                    if not sku and not qty and not reference:
                        continue
                    if not qty and not reference:  # Blank template row; not a delivery.
                        continue
                    if not sku or not qty or not reference or len(reference)>120:
                        raise CommandError(f"Line {line}: SKU, quantity and delivery reference are required")
                    key=(sku,reference)
                    if key in seen:
                        raise CommandError(f"Line {line}: duplicate SKU and reference")
                    seen.add(key)
                    try:
                        quantity=Decimal(qty)
                    except InvalidOperation:
                        raise CommandError(f"Line {line}: invalid quantity")
                    if not quantity.is_finite() or quantity<Decimal('0.001') or quantity>Decimal('999999999.999') or -quantity.as_tuple().exponent>3:
                        raise CommandError(f"Line {line}: invalid quantity")
                    entries.append((sku,quantity,reference))
        except (OSError, UnicodeError) as exc:
            raise CommandError(str(exc)) from exc
        product_map=Product.objects.in_bulk([sku for sku,_,_ in entries],field_name='sku')
        missing=[sku for sku,_,_ in entries if sku not in product_map]
        if missing:
            raise CommandError(f"Unknown product SKU(s), no stock changed: {', '.join(missing[:10])}")
        for sku, quantity, _ in entries:
            if product_map[sku].unit not in ("KG", "LITRE") and quantity != quantity.to_integral_value():
                raise CommandError(f"Product {sku} is packaged and requires a whole-number quantity")
        existing=set(StockMovement.objects.filter(branch=branch,kind=StockMovement.Kind.RECEIPT,
            product_id__in=[p.pk for p in product_map.values()]).values_list('product__sku','reference'))
        fresh=[r for r in entries if (r[0],r[2]) not in existing]
        self.stdout.write(f"Actual receipts to add: {len(fresh)}. Already recorded: {len(entries)-len(fresh)}.")
        if opts['dry_run']:
            self.stdout.write(self.style.SUCCESS("Dry run: inventory unchanged."))
            return
        with transaction.atomic():
            for sku, quantity, reference in fresh:
                record_stock_movement(branch=branch,product=product_map[sku],actor=actor,
                    kind=StockMovement.Kind.RECEIPT,quantity=quantity,reference=reference,
                    note="Recorded from verified bulk supplier delivery CSV")
        self.stdout.write(self.style.SUCCESS(f"Received {len(fresh)} stock lines into {branch.name} with audit records."))
