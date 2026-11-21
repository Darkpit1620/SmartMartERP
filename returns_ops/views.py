from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from pos.models import Sale, SaleItem
from pos.permissions import visible_sales
from .models import ReturnRequest
from .services import can_review, record_paid_refund, request_return, review_return


def _allowed(request):
    # Shared existing POS permission boundary: cashier sees own sales; manager
    # sees branch sales; superuser sees all; unapproved / warehouse get 403.
    return ReturnRequest.objects.filter(sale__in=visible_sales(request))


def _errors(request, exc):
    for m in (exc.messages if isinstance(exc, ValidationError) else [str(exc)]):
        messages.error(request, m)


@login_required
@require_GET
def home(request):
    qs = _allowed(request).select_related('sale__branch', 'sale__cashier', 'requested_by')
    page = Paginator(qs, 30).get_page(request.GET.get('page'))
    return render(request, 'returns_ops/home.html', {'page': page})


@login_required
@require_http_methods(['GET', 'POST'])
def new_return(request, pk):
    sale = get_object_or_404(visible_sales(request).select_related('branch'), pk=pk)
    items = sale.items.all()
    if request.method == 'POST':
        raw_id = request.POST.get('sale_item_id', '')
        if not raw_id.isascii() or not raw_id.isdigit():
            raise Http404('Invalid receipt item.')
        item = get_object_or_404(SaleItem, sale=sale, pk=int(raw_id))
        try:
            case = request_return(sale=sale, sale_item=item, actor=request.user,
                                  quantity=request.POST.get('quantity'), reason=request.POST.get('reason'))
        except ValidationError as exc:
            _errors(request, exc)
        else:
            messages.success(request, f'Return #{case.pk} submitted for manager review. No cash was paid.')
            return redirect('returns_ops:detail', pk=case.pk)
    return render(request, 'returns_ops/new.html', {'sale': sale, 'items': items})


@login_required
@require_GET
def detail(request, pk):
    case = get_object_or_404(_allowed(request).select_related('sale__branch', 'reviewed_by', 'requested_by', 'refunded_by'), pk=pk)
    return render(request, 'returns_ops/detail.html', {'case': case,
        'lines': case.lines.select_related('sale_item'), 'can_review': can_review(request.user, case.sale)})


@login_required
@require_POST
def review(request, pk):
    case = get_object_or_404(_allowed(request).select_related('sale'), pk=pk)
    if not can_review(request.user, case.sale):
        raise PermissionDenied('Manager approval required.')
    action = request.POST.get('decision')
    if action not in ('approve', 'reject'):
        messages.error(request, 'Choose approve or reject.')
        return redirect('returns_ops:detail', pk=pk)
    try:
        review_return(case=case, actor=request.user, approve=action == 'approve',
                      restock=request.POST.get('restock') == 'yes', note=request.POST.get('note', ''))
    except ValidationError as exc:
        _errors(request, exc)
    else:
        messages.success(request, 'Return reviewed. Any refund still requires a separate verified payout record.')
    return redirect('returns_ops:detail', pk=pk)


@login_required
@require_POST
def record_refund(request, pk):
    case = get_object_or_404(_allowed(request).select_related('sale'), pk=pk)
    if not can_review(request.user, case.sale):
        raise PermissionDenied('Manager approval required.')
    try:
        record_paid_refund(case=case, actor=request.user,
                           method=request.POST.get('refund_method'),
                           reference=request.POST.get('refund_reference', ''),
                           confirmed=request.POST.get('confirmed') == 'yes')
    except ValidationError as exc:
        _errors(request, exc)
    else:
        messages.success(request, 'Refund manually recorded as paid. No payment was sent by SmartMart.')
    return redirect('returns_ops:detail', pk=pk)
