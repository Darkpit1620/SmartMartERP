from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from core.models import Branch
from inventory.models import Product
from .forms import StockTransferForm, TransferLineForm
from .models import StockTransfer
from .permissions import employee_branch, scoped_transfer
from .services import (create_transfer, add_transfer_line, remove_transfer_line,
                       dispatch_transfer, receive_transfer)


def flash_exception(request, exc):
    if isinstance(exc, ValidationError):
        for msg in exc.messages[:5]:
            messages.error(request, msg)
    else:
        messages.error(request, 'The action could not be completed. Please review the transfer.')


@login_required
@require_GET
def transfer_list(request):
    branch = employee_branch(request)
    orders = StockTransfer.objects.select_related('source_branch', 'destination_branch', 'created_by')
    if branch:
        orders = orders.filter(Q(source_branch=branch) | Q(destination_branch=branch))
    status = request.GET.get('status', '')
    if status in StockTransfer.Status.values:
        orders = orders.filter(status=status)
    can_create = request.user.is_superuser or request.user.store_profile.role == 'MANAGER'
    incoming = orders.exclude(status__in=['DRAFT', 'CANCELLED']).count() if branch is None else orders.filter(destination_branch=branch).exclude(status__in=['DRAFT', 'CANCELLED']).count()
    return render(request, 'transfers/list.html', {'orders': orders[:150], 'branch': branch,
                  'can_create': can_create, 'incoming': incoming, 'status_filter': status, 'status_choices': StockTransfer.Status.choices})


@login_required
@require_http_methods(['GET', 'POST'])
def transfer_new(request):
    branch = employee_branch(request, manager_only=True)
    form = StockTransferForm(request.POST or None, assigned_branch=branch)
    if request.method == 'POST' and form.is_valid():
        source = branch or form.cleaned_data['source_branch']
        try:
            transfer = create_transfer(source=source, destination=form.cleaned_data['destination_branch'],
                                       actor=request.user, notes=form.cleaned_data['notes'])
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Draft transfer created. Add products, then dispatch from the source warehouse.')
            return redirect('transfers:detail', pk=transfer.pk)
    return render(request, 'transfers/new.html', {'form': form, 'branch': branch})


@login_required
@require_GET
def transfer_detail(request, pk):
    employee_branch(request)
    transfer = get_object_or_404(StockTransfer.objects.select_related('source_branch', 'destination_branch', 'created_by', 'dispatched_by'), pk=pk)
    scoped_transfer(request, transfer)
    branch = employee_branch(request)
    can_edit = transfer.status == 'DRAFT' and (request.user.is_superuser or (branch and branch.pk == transfer.source_branch_id and request.user.store_profile.role == 'MANAGER'))
    can_dispatch = transfer.status == 'DRAFT' and (request.user.is_superuser or (branch and branch.pk == transfer.source_branch_id))
    can_receive = transfer.status in ('IN_TRANSIT', 'PARTIAL') and (request.user.is_superuser or (branch and branch.pk == transfer.destination_branch_id))
    lines = list(transfer.lines.select_related('product'))
    search = request.GET.get('q', '').strip()[:70]
    matches = []
    if can_edit and len(search) >= 2:
        matches = list(Product.objects.filter(is_active=True).filter(
            Q(sku__icontains=search) | Q(name__icontains=search) | Q(barcode__icontains=search))[:15])
    receipts = transfer.receipts.select_related('received_by').prefetch_related('lines__transfer_line__product')
    return render(request, 'transfers/detail.html', {
        'transfer': transfer, 'lines': lines, 'can_edit': can_edit,
        'can_dispatch': can_dispatch, 'can_receive': can_receive,
        'line_form': TransferLineForm(initial={'product_code': request.GET.get('sku', '')[:64]}),
        'matches': matches, 'search': search, 'receipts': receipts,
    })


@login_required
@require_POST
def transfer_add(request, pk):
    employee_branch(request, manager_only=True)
    transfer = get_object_or_404(StockTransfer, pk=pk)
    scoped_transfer(request, transfer, operation='edit')
    form = TransferLineForm(request.POST)
    if form.is_valid():
        code = form.cleaned_data['product_code'].strip()
        product = Product.objects.filter(is_active=True).filter(Q(sku__iexact=code) | Q(barcode__iexact=code)).first()
        if not product:
            messages.error(request, 'No active product matches that SKU or barcode.')
        else:
            try:
                add_transfer_line(transfer=transfer, product=product, quantity=form.cleaned_data['quantity'])
                messages.success(request, f'Added {product.sku} to the draft transfer.')
            except (ValidationError, IntegrityError) as exc:
                flash_exception(request, exc)
    else:
        messages.error(request, 'Enter a valid product code and quantity.')
    return redirect('transfers:detail', pk=pk)


@login_required
@require_POST
def transfer_remove(request, pk, line_id):
    employee_branch(request, manager_only=True)
    transfer = get_object_or_404(StockTransfer, pk=pk)
    scoped_transfer(request, transfer, operation='edit')
    try:
        remove_transfer_line(transfer=transfer, line_id=line_id)
        messages.success(request, 'Product removed from draft.')
    except ValidationError as exc:
        flash_exception(request, exc)
    return redirect('transfers:detail', pk=pk)


@login_required
@require_POST
def transfer_dispatch(request, pk):
    employee_branch(request)
    transfer = get_object_or_404(StockTransfer, pk=pk)
    scoped_transfer(request, transfer, operation='dispatch')
    try:
        dispatch_transfer(transfer=transfer, actor=request.user)
        messages.success(request, 'Transfer dispatched. Origin stock was deducted and goods are now in transit.')
    except ValidationError as exc:
        flash_exception(request, exc)
    return redirect('transfers:detail', pk=pk)


@login_required
@require_POST
def transfer_receive(request, pk):
    employee_branch(request)
    transfer = get_object_or_404(StockTransfer, pk=pk)
    scoped_transfer(request, transfer, operation='receive')
    quantities = {line.pk: request.POST.get(f'qty_{line.pk}', '0') for line in transfer.lines.all()}
    try:
        receipt = receive_transfer(transfer=transfer, actor=request.user,
                                   receipt_reference=request.POST.get('receipt_reference', ''), quantities=quantities)
        messages.success(request, f'Receipt {receipt.reference} saved. Only confirmed quantities were added to destination stock.')
    except (ValidationError, IntegrityError) as exc:
        flash_exception(request, exc)
    return redirect('transfers:detail', pk=pk)
