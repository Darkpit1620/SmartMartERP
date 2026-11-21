"""Read-only analytics computed from existing SmartMart business records.

IMPORTANT: Product cost_price is a *current* catalogue cost, not a cost-of-sale
snapshot. Merchandise margin is therefore an estimate, not accounting profit.
Refunds are separated by actual recorded payout date. Inventory is a current
snapshot and is deliberately NOT filtered by the chosen historical date range.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from finance_ops.models import Expense
from inventory.models import BranchStock
from pos.models import Sale, SaleItem
from returns_ops.models import ReturnRequest

ZERO = Decimal('0.00')
MONEY = DecimalField(max_digits=22, decimal_places=2)
CONFIRMED = (Sale.PaymentStatus.CASH_RECEIVED, Sale.PaymentStatus.VERIFIED)


def money_sum(qs, column):
    return qs.aggregate(value=Coalesce(Sum(column), Value(ZERO), output_field=MONEY))['value']


def build_report(branch, start, end):
    """Return a branch-scoped snapshot without inserting or updating anything."""
    sales = Sale.objects.filter(created_at__date__range=(start, end))
    expenses = Expense.objects.filter(incurred_on__range=(start, end))
    refunds = ReturnRequest.objects.filter(
        status=ReturnRequest.Status.APPROVED,
        refund_status=ReturnRequest.RefundStatus.RECORDED,
        refunded_at__date__range=(start, end),
    )
    stock = BranchStock.objects.filter(quantity__gt=0)
    if branch is not None:
        sales = sales.filter(branch=branch)
        expenses = expenses.filter(branch=branch)
        refunds = refunds.filter(sale__branch=branch)
        stock = stock.filter(branch=branch)

    confirmed = sales.filter(payment_status__in=CONFIRMED)
    pending = sales.filter(payment_status=Sale.PaymentStatus.UNVERIFIED)
    lines = SaleItem.objects.filter(sale__in=confirmed)

    # Sum on actual sale items for current-cost estimate, not original/snapshot COGS.
    unit_cost = ExpressionWrapper(F('quantity') * F('product__cost_price'), output_field=MONEY)
    cost_coverage = lines.aggregate(
        known_cost_estimate=Coalesce(Sum(unit_cost), Value(ZERO), output_field=MONEY),
        missing_cost_lines=Count('pk', filter=Q(product__cost_price__lte=0)),
        line_count=Count('pk'),
    )
    sales_without_items = confirmed.filter(items__isnull=True).count()
    confirmed_amount = money_sum(confirmed, 'subtotal')
    included_tax = money_sum(confirmed, 'included_tax')
    recorded_refunds = money_sum(refunds, 'amount')
    approved_expenses = money_sum(expenses.filter(status=Expense.Status.APPROVED), 'amount')
    estimated_margin = (
        confirmed_amount - included_tax - cost_coverage['known_cost_estimate']
        if cost_coverage['missing_cost_lines'] == 0 and sales_without_items == 0 else None
    )

    stock_cost = ExpressionWrapper(F('quantity') * F('product__cost_price'), output_field=MONEY)
    inventory = stock.aggregate(
        value=Coalesce(Sum(stock_cost), Value(ZERO), output_field=MONEY),
        missing_cost_rows=Count('pk', filter=Q(product__cost_price__lte=0)),
        stocked_rows=Count('pk'),
    )

    start_daily = max(start, end - timedelta(days=13))
    day_amounts = {
        x['day']: x['amount']
        for x in confirmed.filter(created_at__date__gte=start_daily)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(amount=Coalesce(Sum('subtotal'), Value(ZERO), output_field=MONEY))
        .order_by('day')
    }
    daily = [
        {'date': start_daily + timedelta(days=i),
         'amount': day_amounts.get(start_daily + timedelta(days=i), ZERO)}
        for i in range((end - start_daily).days + 1)
    ]
    highest = max((d['amount'] for d in daily), default=ZERO)
    for d in daily:
        d['width'] = round(d['amount'] * 100 / highest) if highest > 0 else 0

    top_products = list(
        lines.values('product__sku', 'product__name')
        .annotate(qty=Sum('quantity'), gross=Sum('line_total'))
        .order_by('-gross', 'product__sku')[:10]
    )

    return {
        'confirmed_sales': confirmed_amount,
        'confirmed_count': confirmed.count(),
        'unverified_sales': money_sum(pending, 'subtotal'),
        'unverified_count': pending.count(),
        'included_tax': included_tax,
        'retail_sales': money_sum(confirmed.filter(sale_type=Sale.SaleType.RETAIL), 'subtotal'),
        'wholesale_sales': money_sum(confirmed.filter(sale_type=Sale.SaleType.WHOLESALE), 'subtotal'),
        'paid_refunds': recorded_refunds,
        'paid_refund_count': refunds.count(),
        'approved_expenses': approved_expenses,
        'pending_expenses': money_sum(expenses.filter(status=Expense.Status.PENDING), 'amount'),
        'estimated_cost': cost_coverage['known_cost_estimate'],
        'missing_cost_lines': cost_coverage['missing_cost_lines'],
        'confirmed_sales_without_items': sales_without_items,
        'sale_line_count': cost_coverage['line_count'],
        'estimated_merchandise_margin': estimated_margin,
        'inventory_value': inventory['value'],
        'inventory_missing_cost_rows': inventory['missing_cost_rows'],
        'inventory_stocked_rows': inventory['stocked_rows'],
        'daily': daily,
        'top_products': top_products,
        'generated_at': timezone.now(),
    }


def safe_csv_cell(value):
    """Prevent cells from being interpreted as formulas by common spreadsheet apps."""
    text = str(value if value is not None else '')
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else text
