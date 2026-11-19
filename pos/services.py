"""Server-side pricing, controlled checkout and transactional stock decrement."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from inventory.models import BranchStock, Product
from .models import Sale, SaleItem

CENT = Decimal('0.01')
THOUSANDTH = Decimal('0.001')


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def quantity_from_text(raw, product):
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError('Enter a valid quantity.')
    if not value.is_finite() or value <= 0 or value > Decimal('9999999.999'):
        raise ValidationError('Enter a positive, reasonable quantity.')
    if value.as_tuple().exponent < -3:
        raise ValidationError('Quantities allow at most three decimal places.')
    if product.unit not in (Product.Unit.KG, Product.Unit.LITRE) and value != value.to_integral_value():
        raise ValidationError('Packaged products are sold in whole units.')
    return value.quantize(THOUSANDTH)


def parse_tender(raw):
    try:
        value = Decimal(str(raw))
    except (TypeError, InvalidOperation, ValueError):
        raise ValidationError('Enter a valid cash amount.')
    if not value.is_finite() or value < 0 or value.as_tuple().exponent < -2 or value > Decimal('999999999999.99'):
        raise ValidationError('Enter a valid cash amount with up to two decimal places.')
    return money(value)


def line_for(product, qty, mode):
    qty = quantity_from_text(qty, product)
    if not product.is_active:
        raise ValidationError(f'{product.sku}: this product is inactive.')
    if mode == Sale.SaleType.WHOLESALE and qty < product.wholesale_min_qty:
        raise ValidationError(f'{product.sku}: wholesale requires at least {product.wholesale_min_qty} units.')
    price = product.wholesale_price if mode == Sale.SaleType.WHOLESALE else product.retail_price
    if price <= 0:
        raise ValidationError(f'{product.sku}: price is pending. Ask the administrator to set a verified price.')
    total = money(price * qty)
    if total > Decimal('999999999999.99'):
        raise ValidationError('Line value exceeds the supported receipt limit.')
    if not total:
        raise ValidationError('The line total cannot be zero.')
    tax = money(total - (total / (Decimal('1') + product.tax_rate / Decimal('100'))))
    return {'product': product, 'quantity': qty, 'price': price, 'total': total,
            'tax': tax, 'tax_rate': product.tax_rate}


def build_cart(cart, mode, branch):
    """Always fetch current prices and stock from the DB, never from the session."""
    ids = [int(k) for k in cart if str(k).isdigit()]
    products = {p.pk: p for p in Product.objects.filter(pk__in=ids).select_related('category')}
    on_hand = {row.product_id: row.quantity for row in BranchStock.objects.filter(branch=branch, product_id__in=ids)}
    rows, errors = [], []
    subtotal = Decimal('0.00')
    tax_total = Decimal('0.00')
    for key, raw_qty in cart.items():
        product = products.get(int(key)) if str(key).isdigit() else None
        if product is None:
            errors.append(f'Product {key} is unavailable.')
            continue
        try:
            row = line_for(product, raw_qty, mode)
        except ValidationError as exc:
            errors.extend(exc.messages)
            continue
        row['available'] = on_hand.get(product.pk, Decimal('0.000'))
        if row['quantity'] > row['available']:
            errors.append(f'{product.sku}: only {row["available"]} available at this branch.')
        rows.append(row)
        subtotal += row['total']
        tax_total += row['tax']
    return rows, money(subtotal), money(tax_total), errors


def complete_sale(*, branch, cashier, cart, mode, method, token, tendered='', reference=''):
    """Create an immutable receipt and reduce stock in one database transaction.

    Stock decrements use a conditional F() update: no sale can result in negative stock.
    A unique checkout token protects against refresh/repeat submissions.
    Prices, stock and totals are checked again *inside* the transaction.
    """
    if mode not in Sale.SaleType.values or method not in Sale.PaymentMethod.values:
        raise ValidationError('Select a valid sale type and payment method.')
    if not cart or not token or len(token) > 64:
        raise ValidationError('A nonempty cart and checkout token are required.')
    if not branch or not branch.active:
        raise ValidationError('Select an active branch.')

    # Avoid huge bulk checkouts and prevent crafted sessions from exhausting resources.
    if len(cart) > 120:
        raise ValidationError('Only 120 different products may be checked out at once.')
    reference = (reference or '').strip()
    if method != Sale.PaymentMethod.CASH and (len(reference) < 4 or len(reference) > 100):
        raise ValidationError('Enter the provider payment reference (4–100 characters). It will require verification.')
    if method == Sale.PaymentMethod.CASH:
        reference = ''

    with transaction.atomic():
        if Sale.objects.filter(checkout_token=token).exists():
            return Sale.objects.get(checkout_token=token)
        rows, total, included_tax, errors = build_cart(cart, mode, branch)
        if errors:
            raise ValidationError(errors)
        if total > Decimal('999999999999.99'):
            raise ValidationError('The transaction total exceeds the supported receipt limit.')
        if not rows or len(rows) != len(cart):
            raise ValidationError('Your cart contains unavailable products.')
        amount = parse_tender(tendered) if method == Sale.PaymentMethod.CASH else Decimal('0.00')
        if method == Sale.PaymentMethod.CASH and amount < total:
            raise ValidationError(f'Cash tendered must be at least {total}.')
        status = (Sale.PaymentStatus.CASH_RECEIVED if method == Sale.PaymentMethod.CASH
                  else Sale.PaymentStatus.UNVERIFIED)
        sale = Sale.objects.create(
            branch=branch, cashier=cashier, sale_type=mode, payment_method=method,
            payment_status=status, payment_reference=reference,
            subtotal=total, included_tax=included_tax,
            tendered_amount=amount, change_due=money(amount - total) if method == Sale.PaymentMethod.CASH else 0,
            checkout_token=token,
        )
        for row in rows:
            affected = BranchStock.objects.filter(
                branch=branch, product=row['product'], quantity__gte=row['quantity']
            ).update(quantity=F('quantity') - row['quantity'], updated_at=timezone.now())
            if affected != 1:
                raise ValidationError(f'{row["product"].sku}: stock changed during checkout. Refresh the cart.')
            SaleItem.objects.create(
                sale=sale, product=row['product'], sku=row['product'].sku,
                description=row['product'].name, unit=row['product'].unit,
                quantity=row['quantity'], unit_price=row['price'], tax_rate=row['tax_rate'],
                line_total=row['total'], included_tax=row['tax'],
            )
        sale.receipt_number = f'SM-{timezone.localtime(sale.created_at):%Y}-{sale.pk:07d}'
        sale.save(update_fields=['receipt_number'])
        return sale
