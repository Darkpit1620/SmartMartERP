"""Careful, validated CSV pricing updates; no inventory changes.

The upload is always validated completely before any row is written. Blank
price fields mean "leave the database value alone". Validation never uses
floating-point arithmetic for money.
"""

import csv
import io
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from inventory.models import Product

MAX_CSV_BYTES = 8 * 1024 * 1024
MAX_PRODUCTS = 20000
PRICE_FIELDS = ("retail_price", "wholesale_price", "cost_price")
UPDATE_FIELDS = (*PRICE_FIELDS, "wholesale_min_qty", "tax_rate")
EXPORT_FIELDS = ("sku", "product_name", "department", *UPDATE_FIELDS)


class PricingValidationError(Exception):
    pass


@dataclass
class PricingPlan:
    records: list
    seen: int
    changed: int
    cells: int
    examples: list


def _decimal(value, field, line):
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError):
        raise PricingValidationError(f"Line {line}: invalid {field} ({value!r}).")
    if not number.is_finite() or number < 0:
        raise PricingValidationError(f"Line {line}: {field} cannot be negative, NaN, or infinite.")
    if not value.replace(".", "", 1).isdigit():
        raise PricingValidationError(f"Line {line}: {field} must be an ordinary decimal number without currency symbols or scientific notation.")
    if number.as_tuple().exponent < -2:
        raise PricingValidationError(f"Line {line}: {field} must have at most 2 decimal places.")
    if field in ("retail_price", "wholesale_price") and number <= 0:
        raise PricingValidationError(f"Line {line}: {field} must be greater than zero; leave it blank to keep the current value.")
    if field == "tax_rate":
        if number > 100:
            raise PricingValidationError(f"Line {line}: tax_rate cannot exceed 100.")
    elif number > Decimal("9999999999.99"):
        raise PricingValidationError(f"Line {line}: {field} is too large.")
    return number


def read_csv(upload):
    """Decode an uploaded CSV (or a byte stream) into a fully validated plan."""
    if getattr(upload, "size", None) is not None and upload.size > MAX_CSV_BYTES:
        raise PricingValidationError("CSV exceeds the 8 MB upload limit.")
    blob = upload.read(MAX_CSV_BYTES + 1)
    if len(blob) > MAX_CSV_BYTES:
        raise PricingValidationError("CSV exceeds the 8 MB upload limit.")
    try:
        text = blob.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise PricingValidationError("Upload a UTF-8 CSV file. Use Save As > CSV UTF-8 in Excel.")
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = [name.strip() for name in (reader.fieldnames or []) if name is not None]
        if len(headers) != len(set(headers)):
            raise PricingValidationError("The CSV contains duplicate column headings.")
        if "sku" not in headers or not any(key in headers for key in UPDATE_FIELDS):
            raise PricingValidationError("CSV must contain sku and at least one pricing column.")
        # Remove surrounding header whitespace without changing the user's file.
        reader.fieldnames = headers
        results = []
        sku_set = set()
        for i, row in enumerate(reader, 2):
            if i > MAX_PRODUCTS + 1:
                raise PricingValidationError(f"CSV exceeds {MAX_PRODUCTS:,} product lines.")
            if None in row:
                raise PricingValidationError(f"Line {i}: extra comma or too many values.")
            if not any(str(value or "").strip() for value in row.values()):
                continue
            sku = str(row.get("sku") or "").strip().upper()
            if not sku:
                raise PricingValidationError(f"Line {i}: SKU is required.")
            if sku in sku_set:
                raise PricingValidationError(f"Line {i}: duplicate SKU {sku}.")
            sku_set.add(sku)
            changes = {}
            for field in UPDATE_FIELDS:
                value = str(row.get(field) or "").strip()
                if not value:
                    continue
                if field == "wholesale_min_qty":
                    if not value.isdecimal() or not (1 <= int(value) <= 1000000):
                        raise PricingValidationError(f"Line {i}: wholesale_min_qty must be an integer between 1 and 1,000,000.")
                    changes[field] = int(value)
                else:
                    changes[field] = _decimal(value, field, i)
            if changes:
                results.append((sku, changes))
    except (csv.Error, UnicodeError) as exc:
        raise PricingValidationError(f"CSV formatting error: {exc}")
    if not results:
        raise PricingValidationError("No prices entered. Fill a price column on at least one product row.")
    return results


def plan_updates(records):
    """Compare against the current database without saving anything."""
    products = Product.objects.in_bulk([sku for sku, _ in records], field_name="sku")
    unknown = [sku for sku, _ in records if sku not in products]
    if unknown:
        preview = ", ".join(unknown[:8])
        raise PricingValidationError(f"Unknown SKU(s): {preview}. No products were updated.")
    instructions = []
    examples = []
    changed_cells = 0
    for sku, incoming in records:
        product = products[sku]
        changed = {field: val for field, val in incoming.items()
                   if getattr(product, field) != val}
        if changed:
            instructions.append((product, changed))
            changed_cells += len(changed)
            if len(examples) < 10:
                fields = ", ".join(changed.keys())
                examples.append((sku, product.name, fields))
    return PricingPlan(records=instructions, seen=len(records),
                       changed=len(instructions), cells=changed_cells,
                       examples=examples)


@transaction.atomic
def commit_updates(records):
    """Re-read and lock product rows, then apply the fully validated changes."""
    # Ensure all SKU values still exist at write time; atomic rollback on error.
    skus = [sku for sku, _ in records]
    products = {
        p.sku: p for p in Product.objects.select_for_update().filter(sku__in=skus)
    }
    unknown = [sku for sku in skus if sku not in products]
    if unknown:
        raise PricingValidationError("Product catalogue changed during upload. No prices were saved. Please retry.")
    changed_count = 0
    for sku, incoming in records:
        product = products[sku]
        updates = {field: value for field, value in incoming.items()
                   if getattr(product, field) != value}
        if updates:
            updates["updated_at"] = timezone.now()
            Product.objects.filter(pk=product.pk).update(**updates)
            changed_count += 1
    return changed_count


def safe_excel_cell(value):
    """Protect descriptive CSV fields from spreadsheet formula execution."""
    output = str(value or "")
    if output.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + output
    return output
