"""Read-only, branch-scoped reorder reporting.

Never creates purchase orders, stock records, supplier commitments, or payments.
Products with no verified retail OR wholesale selling price are excluded from
operational reorder suggestions. They remain visible in the setup-pending count.
A reorder threshold of zero disables the alert for that product.
"""
from decimal import Decimal
from django.db.models import DecimalField, Exists, F, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce

from inventory.models import BranchStock, Product

STOCK_FIELD = DecimalField(max_digits=12, decimal_places=3)
ZERO = Decimal('0.000')
TWO = Decimal('2')


def reorder_quantity(reorder_level, on_hand):
    """Suggest the top-up to double the configured reorder point, never negative.

    This is a *planning estimate*, not a confirmed supplier order quantity or
    lead-time/demand forecast. Managers can adjust the recommendation.
    """
    threshold = Decimal(str(reorder_level))
    current = Decimal(str(on_hand))
    return max(ZERO, threshold * TWO - current)


def low_stock_queryset(branch):
    """Database-side annotation and filtering; no per-product queries."""
    if branch is None:
        return Product.objects.none()
    entries = BranchStock.objects.filter(branch_id=branch.pk, product_id=OuterRef('pk')).order_by()
    products = Product.objects.select_related('category').filter(is_active=True, reorder_level__gt=0).filter(
        Q(retail_price__gt=0) | Q(wholesale_price__gt=0)
    )
    return products.annotate(
        on_hand=Coalesce(
            Subquery(entries.values('quantity')[:1], output_field=STOCK_FIELD),
            Value(ZERO, output_field=STOCK_FIELD),
            output_field=STOCK_FIELD,
        ),
        stock_recorded=Exists(entries),
    ).filter(on_hand__lte=F('reorder_level'))


def setup_pending_count():
    return Product.objects.filter(is_active=True, retail_price__lte=0, wholesale_price__lte=0).count()


def filtered_alerts(branch, query='', status='all'):
    if branch is None:
        return Product.objects.none().order_by('name', 'sku')
    qs = low_stock_queryset(branch)
    query = (query or '').strip()[:100]
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(sku__icontains=query) | Q(barcode__icontains=query))
    if status == 'out':
        qs = qs.filter(on_hand__lte=0)
    elif status == 'low':
        qs = qs.filter(on_hand__gt=0)
    return qs.order_by('on_hand', 'name', 'sku')


def safe_csv_cell(value):
    """Neutralize Excel/Sheets formulas in user-entered text cells."""
    value = str(value if value is not None else '')
    if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
        return "'" + value
    return value
