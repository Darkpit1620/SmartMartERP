"""Strict branch-scoped, GET-only reporting for administrators and managers."""
import csv
from decimal import Decimal
from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from core.models import Branch, StaffProfile
from .services import build_report, safe_csv_cell


def _csv_money(value):
    """Export KES monetary values with exactly two decimal places."""
    return format(Decimal(str(value)), '.2f')


def permitted_filters(request):
    user = request.user
    if not user.is_active:
        raise PermissionDenied('An active account is required for management reporting.')
    if user.is_superuser:
        branches = Branch.objects.order_by('name', 'pk')
        value = request.GET.get('branch', '').strip()
        if value:
            if not value.isascii() or not value.isdecimal():
                raise Http404('Invalid branch.')
            branch = get_object_or_404(Branch, pk=int(value))
        else:
            branch = None  # Only the superuser may report across all branches.
    else:
        try:
            profile = user.store_profile
        except StaffProfile.DoesNotExist:
            raise PermissionDenied('This account has no approved manager profile.')
        if not profile.is_approved or profile.role != StaffProfile.Role.MANAGER:
            raise PermissionDenied('Only approved branch managers can view management reports.')
        if not profile.branch_id or not profile.branch.active:
            raise PermissionDenied('Assign an active branch before viewing reports.')
        branch = profile.branch  # Ignore any user-supplied branch value.
        branches = None

    today = timezone.localdate()
    try:
        start = date.fromisoformat(request.GET.get('start', today.replace(day=1).isoformat()))
        end = date.fromisoformat(request.GET.get('end', today.isoformat()))
    except (ValueError, TypeError):
        raise Http404('Dates must be YYYY-MM-DD.')
    if start > end or end > today or (end - start).days > 366:
        raise Http404('Choose a valid reporting range no longer than 367 days, ending today or earlier.')
    return branch, branches, start, end


@login_required
@require_GET
def home(request):
    branch, branches, start, end = permitted_filters(request)
    report = build_report(branch, start, end)
    return render(request, 'reporting_insights/home.html', {
        'report': report, 'branch': branch, 'branches': branches,
        'start': start, 'end': end,
    })


@login_required
@require_GET
def export_csv(request):
    branch, _branches, start, end = permitted_filters(request)
    report = build_report(branch, start, end)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="smartmart-insights-{start}-{end}.csv"'
    writer = csv.writer(response)
    writer.writerow(['SmartMart ERP — management insights (KES)', ''])
    writer.writerow(['Branch', safe_csv_cell(branch.name if branch else 'All branches')])
    writer.writerow(['Period', f'{start} through {end}'])
    writer.writerow(['Confirmed sales (tax included)', _csv_money(report['confirmed_sales'])])
    writer.writerow(['Unverified sales excluded from confirmed total', _csv_money(report['unverified_sales'])])
    writer.writerow(['Included tax in confirmed sales', _csv_money(report['included_tax'])])
    writer.writerow(['Retail sales (confirmed)', _csv_money(report['retail_sales'])])
    writer.writerow(['Wholesale sales (confirmed)', _csv_money(report['wholesale_sales'])])
    writer.writerow(['Refunds manually recorded as paid in period', _csv_money(report['paid_refunds'])])
    writer.writerow(['Approved operating expenses in period', _csv_money(report['approved_expenses'])])
    writer.writerow(['Pending operating expenses in period', _csv_money(report['pending_expenses'])])
    writer.writerow(['Estimated goods cost using CURRENT product costs', _csv_money(report['estimated_cost'])])
    writer.writerow(['Confirmed sale lines with missing/zero current cost', report['missing_cost_lines']])
    writer.writerow(['Confirmed sales missing receipt lines', report['confirmed_sales_without_items']])
    writer.writerow(['Indicative merchandise margin BEFORE returns and expenses (not accounting profit)',
                    _csv_money(report['estimated_merchandise_margin']) if report['estimated_merchandise_margin'] is not None else 'Unavailable: missing cost data'])
    writer.writerow(['CURRENT inventory value using CURRENT costs (not a historical total)', _csv_money(report['inventory_value'])])
    writer.writerow(['Current stocked rows with missing/zero product cost', report['inventory_missing_cost_rows']])
    writer.writerow([])
    writer.writerow(['Top products by confirmed line total', 'SKU', 'Units sold', 'Gross line total KES'])
    for item in report['top_products']:
        writer.writerow([safe_csv_cell(item['product__name']), safe_csv_cell(item['product__sku']),
                         item['qty'], _csv_money(item['gross'])])
    writer.writerow([])
    writer.writerow(['Notes', 'Amounts are management estimates, not audited financial statements.'])
    writer.writerow(['Notes', 'Historical item costs and return cost reversal are not stored on receipts.'])
    writer.writerow(['Notes', 'Refunds use actual recorded payout date; expenses use incurred date.'])
    return response
