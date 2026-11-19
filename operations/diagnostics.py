"""Read-only operational indicators. Never expose data outside administrator access."""
from django.conf import settings
from django.db.models import Count
from core.models import Branch, StaffProfile
from inventory.models import Product, BranchStock, StockMovement
from pos.models import Sale, SaleItem
from trading.models import Supplier, PurchaseOrder, WholesaleOrder
from transfers.models import StockTransfer
from workforce.models import LeaveRequest
from finance_ops.models import Expense


def collect_snapshot():
    """Only aggregate counts. The audit never writes to stock, sales, or finance."""
    total_products = Product.objects.count()
    zero_retail = Product.objects.filter(is_active=True, retail_price__lte=0).count()
    zero_wholesale = Product.objects.filter(is_active=True, wholesale_price__lte=0).count()
    inconsistent_stock = BranchStock.objects.filter(quantity__lt=0).count()
    products_without_branch_stock = Product.objects.filter(
        is_active=True, branch_stock__isnull=True
    ).count()
    sale_with_no_items = Sale.objects.annotate(
        item_count=Count('items')
    ).filter(item_count=0).count()
    completed_wholesale_without_sale = WholesaleOrder.objects.filter(
        status=WholesaleOrder.Status.FULFILLED, sale__isnull=True
    ).count()
    return {
        'branches': Branch.objects.count(),
        'active_branches': Branch.objects.filter(active=True).count(),
        'products': total_products,
        'stock_lines': BranchStock.objects.count(),
        'stock_movements': StockMovement.objects.count(),
        'unpriced_retail': zero_retail,
        'unpriced_wholesale': zero_wholesale,
        'unstocked_products': products_without_branch_stock,
        'negative_stock_lines': inconsistent_stock,
        'staff_accounts': StaffProfile.objects.count(),
        'pending_staff': StaffProfile.objects.filter(is_approved=False).count(),
        'sales': Sale.objects.count(),
        'unverified_payments': Sale.objects.filter(payment_status=Sale.PaymentStatus.UNVERIFIED).count(),
        'sales_without_items': sale_with_no_items,
        'suppliers': Supplier.objects.count(),
        'purchase_orders': PurchaseOrder.objects.count(),
        'open_purchase_orders': PurchaseOrder.objects.filter(status__in=[PurchaseOrder.Status.ORDERED, PurchaseOrder.Status.PARTIAL]).count(),
        'wholesale_orders': WholesaleOrder.objects.count(),
        'wholesale_without_sale': completed_wholesale_without_sale,
        'in_transit_transfers': StockTransfer.objects.filter(status__in=[StockTransfer.Status.IN_TRANSIT, StockTransfer.Status.PARTIAL]).count(),
        'pending_expenses': Expense.objects.filter(status=Expense.Status.PENDING).count(),
        'pending_leave': LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDING).count(),
    }


def security_flags():
    """Read deployment-related switches without printing secrets or hosts."""
    return [
        {'label': 'Debug mode disabled', 'ok': not settings.DEBUG, 'detail': 'DEBUG is normally enabled only during local development.'},
        {'label': 'Allowed hosts configured', 'ok': bool(settings.ALLOWED_HOSTS) and '*' not in settings.ALLOWED_HOSTS, 'detail': 'Set exact hostnames for production.'},
        {'label': 'Secure session cookies', 'ok': bool(settings.SESSION_COOKIE_SECURE), 'detail': 'Requires HTTPS in production.'},
        {'label': 'Secure CSRF cookies', 'ok': bool(settings.CSRF_COOKIE_SECURE), 'detail': 'Requires HTTPS in production.'},
        {'label': 'HTTPS redirect configured', 'ok': bool(settings.SECURE_SSL_REDIRECT), 'detail': 'Or enforce HTTPS at a correctly configured reverse proxy.'},
        {'label': 'Static collection destination configured', 'ok': bool(getattr(settings, 'STATIC_ROOT', None)), 'detail': 'Required for collectstatic in normal production deployment.'},
    ]


def findings(data):
    """Actionable flags; pending operations are review items, not automatically errors."""
    alerts = []
    for count, label, severity in (
        (data['negative_stock_lines'], 'Negative stock balances need investigation', 'critical'),
        (data['sales_without_items'], 'Saved sales have no line items', 'critical'),
        (data['wholesale_without_sale'], 'Fulfilled wholesale orders are missing a sale', 'critical'),
        (data['unverified_payments'], 'Electronic payments are awaiting independent verification', 'review'),
        (data['pending_expenses'], 'Operating expenses need approval', 'review'),
        (data['in_transit_transfers'], 'Branch transfers have goods outstanding', 'review'),
        (data['open_purchase_orders'], 'Supplier purchase orders are still open', 'review'),
        (data['pending_staff'], 'Employee accounts await approval', 'review'),
        (data['unpriced_retail'], 'Active products do not yet have a verified retail price', 'review'),
    ):
        if count:
            alerts.append({'count': count, 'label': label, 'severity': severity})
    return alerts
