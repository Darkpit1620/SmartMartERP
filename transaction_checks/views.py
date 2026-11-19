"""Read-only administration checklist. Test scenarios run only via manage.py test."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_GET
from django.shortcuts import render

from core.models import Branch, StaffProfile
from inventory.models import Product, BranchStock
from pos.models import Sale
from trading.models import PurchaseOrder, GoodsReceipt, WholesaleOrder
from transfers.models import StockTransfer
from finance_ops.models import Expense


@login_required
@require_GET
def overview(request):
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied("Head-office administrators only.")
    snapshot = {
        "branches": Branch.objects.filter(active=True).count(),
        "catalogue_products": Product.objects.count(),
        "priced_products": Product.objects.filter(retail_price__gt=0).count(),
        "stock_lines": BranchStock.objects.count(),
        "approved_staff": StaffProfile.objects.filter(is_approved=True).count(),
        "sales": Sale.objects.count(),
        "unverified_payments": Sale.objects.filter(payment_status=Sale.PaymentStatus.UNVERIFIED).count(),
        "purchase_orders": PurchaseOrder.objects.count(),
        "goods_receipts": GoodsReceipt.objects.count(),
        "wholesale_orders": WholesaleOrder.objects.count(),
        "open_transfers": StockTransfer.objects.filter(status__in=["IN_TRANSIT", "PARTIAL"]).count(),
        "pending_expenses": Expense.objects.filter(status=Expense.Status.PENDING).count(),
    }
    return render(request, "transaction_checks/overview.html", {"snapshot": snapshot})
