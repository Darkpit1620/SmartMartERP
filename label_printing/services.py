"""Read-only preparation of price tags.  No writes, no price defaults."""
import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe

from inventory.models import Product
from .barcodes import choose_scan_code, svg_for

MAX_PRODUCTS = 24
MAX_COPIES = 8
MAX_TOTAL = 192


def sku_input(text, selected=None):
    if not isinstance(text, str) or len(text) > 2500:
        raise ValidationError('The SKU list is too long.')
    supplied = re.split(r'[\s,;]+', text.strip()) if text.strip() else []
    supplied += list(selected or ())
    ordered = []
    seen = set()
    for raw in supplied:
        sku = str(raw).strip().upper()
        if not sku or sku in seen:
            continue
        if len(sku) > 48:
            raise ValidationError('Each SKU must be at most 48 characters.')
        seen.add(sku)
        ordered.append(sku)
        if len(ordered) > MAX_PRODUCTS:
            raise ValidationError(f'Maximum {MAX_PRODUCTS} distinct products per print job.')
    if not ordered:
        raise ValidationError('Enter or select at least one SKU.')
    return ordered


def make_labels(skus, copies=1, mode='shelf'):
    """Return (labels, skipped) with no database mutations."""
    try:
        copies = int(copies)
    except (TypeError, ValueError):
        raise ValidationError('Copies must be a whole number.')
    if copies < 1 or copies > MAX_COPIES or mode not in ('shelf', 'barcode'):
        raise ValidationError('Choose 1–8 copies and an available label format.')
    if not skus or len(skus) > MAX_PRODUCTS or len(set(skus)) != len(skus):
        raise ValidationError('Select 1–24 unique products.')
    if len(skus) * copies > MAX_TOTAL:
        raise ValidationError('Too many labels requested.')
    products = {p.sku: p for p in Product.objects.filter(sku__in=skus, is_active=True)}
    labels = []
    skipped = []
    for sku in skus:
        product = products.get(sku)
        if product is None:
            skipped.append(f'{sku}: not an active product')
            continue
        if product.retail_price is None or product.retail_price <= Decimal('0.00'):
            skipped.append(f'{sku}: retail price not verified')
            continue
        scan_code = choose_scan_code(product)
        row = {
            'product': product,
            'price': f'{product.retail_price:.2f}',
            'code': scan_code,
            # Geometry generated using strictly numeric constants; never inject product text.
            'svg': mark_safe(svg_for(scan_code)) if scan_code else '',
        }
        labels.extend([row] * copies)
    return labels, skipped
