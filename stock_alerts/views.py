"""Read-only inventory alerts, strictly scoped to an approved employee's branch."""
import csv
import re
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from core.models import Branch, StaffProfile
from inventory.permissions import require_stock_staff
from .services import filtered_alerts, low_stock_queryset, reorder_quantity, safe_csv_cell, setup_pending_count


def _branch_for_user(request):
    # Checks approval and roles before examining user-supplied branch values.
    profile = require_stock_staff(request)
    if profile is not None:
        if not profile.branch_id:
            raise PermissionDenied('Assign this employee to a branch before viewing stock alerts.')
        if not profile.branch.active:
            raise PermissionDenied('Assigned branch is inactive.')
        return profile.branch, None

    choices = Branch.objects.filter(active=True).order_by('name', 'pk')
    requested = request.GET.get('branch', '')
    if requested:
        if not requested.isascii() or not requested.isdecimal():
            raise Http404('Branch not found.')
        branch = choices.filter(pk=int(requested)).first()
        if branch is None:
            raise Http404('Branch not found.')
    else:
        branch = choices.first()
    return branch, choices


def _filters(request):
    query = request.GET.get('q', '').strip()[:100]
    status = request.GET.get('status', 'all')
    if status not in {'all', 'out', 'low'}:
        status = 'all'
    return query, status


@login_required
@require_GET
def home(request):
    branch, branches = _branch_for_user(request)
    query, status = _filters(request)
    low = low_stock_queryset(branch)
    total_low = low.count() if branch else 0
    out = low.filter(on_hand__lte=0).count() if branch else 0
    rows = filtered_alerts(branch, query, status)
    page = Paginator(rows, 30).get_page(request.GET.get('page'))
    recommendations = [
        {'product': p, 'quantity': p.on_hand,
         'recorded': p.stock_recorded, 'suggested': reorder_quantity(p.reorder_level, p.on_hand)}
        for p in page.object_list
    ]
    return render(request, 'stock_alerts/home.html', {
        'branch': branch, 'branches': branches,
        'query': query, 'status': status, 'page': page, 'rows': recommendations,
        'total_low': total_low, 'out_of_stock': out,
        'setup_pending': setup_pending_count(),
        'filtered_count': page.paginator.count,
    })


@login_required
@require_GET
def export_csv(request):
    branch, _ = _branch_for_user(request)
    if branch is None:
        raise Http404('No active branch has been configured.')
    query, status = _filters(request)
    items = filtered_alerts(branch, query, status)
    code = re.sub(r'[^A-Za-z0-9_-]', '_', branch.code)[:45] or 'BRANCH'
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="smartmart_reorder_{code}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Branch', 'SKU', 'Product', 'Category', 'Unit', 'On hand',
                     'Reorder threshold', 'Suggested top-up to 2x threshold',
                     'Stock balance recorded', 'Planning status'])
    for p in items.iterator(chunk_size=300):
        writer.writerow([
            safe_csv_cell(branch.code), safe_csv_cell(p.sku),
            safe_csv_cell(p.name), safe_csv_cell(p.category.name), safe_csv_cell(p.unit),
            str(p.on_hand), str(p.reorder_level), str(reorder_quantity(p.reorder_level, p.on_hand)),
            'Yes' if p.stock_recorded else 'No',
            'Out of stock' if p.on_hand <= 0 else 'Below reorder threshold',
        ])
    return response
