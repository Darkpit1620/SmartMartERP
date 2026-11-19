from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import IntegrityError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from core.models import Branch
from inventory.models import Product
from pos.models import Sale
from pos.services import line_for, quantity_from_text
from .forms import (CustomerForm, PurchaseLineForm, PurchaseOrderForm,
                    SupplierForm, WholesaleLineForm, WholesaleOrderForm)
from .models import (PurchaseOrder, PurchaseOrderLine, Supplier, WholesaleCustomer,
                     WholesaleOrder, WholesaleOrderLine)
from .permissions import ensure_branch, trade_branch
from .services import (fulfill_wholesale_order, prepare_wholesale_order,
                       receive_delivery, submit_purchase_order)


def flash_error(request, error):
    if isinstance(error, ValidationError):
        for m in error.messages[:5]:
            messages.error(request, m)
    else:
        messages.error(request, str(error))


def find_product(raw):
    code = (raw or '').strip()
    if not code or len(code) > 64:
        raise ValidationError('Enter a valid product SKU or barcode.')
    product = Product.objects.filter(is_active=True).filter(
        Q(sku__iexact=code) | Q(barcode__iexact=code)
    ).first()
    if not product:
        raise ValidationError('Product not found. Use a SKU or barcode from your catalogue.')
    return product


def product_search(request, wholesale=False):
    term = request.GET.get('q', '').strip()[:60]
    if len(term) < 2:
        return [], term
    qs = Product.objects.filter(is_active=True)
    if wholesale:
        qs = qs.filter(wholesale_price__gt=0)
    return list(qs.filter(Q(sku__icontains=term) | Q(name__icontains=term) | Q(barcode__icontains=term))[:20]), term


def scoped_order(request, model, pk, *, operation='view'):
    branch = trade_branch(request, operation=operation)
    order = get_object_or_404(model, pk=pk)
    ensure_branch(order, branch)
    return order


@login_required
@require_GET
def home(request):
    branch = trade_branch(request, operation='view')
    branch_list = Branch.objects.filter(active=True).order_by('name') if request.user.is_superuser else []
    purchase_orders = PurchaseOrder.objects.filter(branch=branch).select_related('supplier')[:8] if branch else []
    wholesale_orders = WholesaleOrder.objects.filter(branch=branch).select_related('customer')[:8] if branch else []
    return render(request, 'trading/home.html', {
        'branch': branch, 'branches': branch_list,
        'purchase_orders': purchase_orders, 'wholesale_orders': wholesale_orders,
        'can_purchase': request.user.is_superuser or request.user.store_profile.role == 'MANAGER',
    })


@login_required
@require_http_methods(['GET', 'POST'])
def supplier_new(request):
    trade_branch(request, operation='purchasing')
    form = SupplierForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            supplier = form.save()
        except IntegrityError:
            form.add_error('name', 'This supplier already exists.')
        else:
            messages.success(request, f'Supplier {supplier.name} created.')
            return redirect('trading:home')
    return render(request, 'trading/form.html', {'form': form, 'heading': 'Register supplier',
                                                'subheading': 'Add a genuine supplier contact for purchasing.'})


@login_required
@require_http_methods(['GET', 'POST'])
def customer_new(request):
    trade_branch(request, operation='wholesale')
    form = CustomerForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        customer = form.save()
        messages.success(request, f'Wholesale customer {customer} created.')
        return redirect('trading:home')
    return render(request, 'trading/form.html', {'form': form, 'heading': 'Register wholesale customer',
                                                'subheading': 'Customer contact information for bulk orders.'})


@login_required
@require_http_methods(['GET', 'POST'])
def purchase_new(request):
    branch = trade_branch(request, operation='purchasing')
    if branch is None:
        messages.error(request, 'Create an active branch first.')
        return redirect('trading:home')
    form = PurchaseOrderForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        po = form.save(commit=False)
        po.branch = branch
        po.created_by = request.user
        po.save()
        messages.success(request, f'{po.reference} created. Add products before ordering.')
        return redirect('trading:purchase_detail', pk=po.pk)
    return render(request, 'trading/form.html', {'form': form, 'heading': 'New supplier purchase order',
                                                'subheading': f'Supplier order for {branch.name}.'})


@login_required
@require_GET
def purchase_detail(request, pk):
    po = scoped_order(request, PurchaseOrder, pk)
    manager = request.user.is_superuser or request.user.store_profile.role == 'MANAGER'
    lines = list(po.lines.select_related('product'))
    matched, search_term = product_search(request)
    receipts = po.receipts.prefetch_related('lines__purchase_line__product').select_related('recorded_by')
    return render(request, 'trading/purchase_detail.html', {
        'po': po, 'lines': lines, 'receipts': receipts, 'manager': manager,
        'line_form': PurchaseLineForm(initial={'product_code': request.GET.get('sku', '')[:64]}),
        'matched_products': matched, 'search_term': search_term,
        'total': sum((x.line_total for x in lines), Decimal('0.00')),
    })


@login_required
@require_POST
def purchase_add_line(request, pk):
    po = scoped_order(request, PurchaseOrder, pk, operation='purchasing')
    if po.status != PurchaseOrder.Status.DRAFT:
        raise PermissionDenied('Purchase-order lines can only be edited in draft.')
    form = PurchaseLineForm(request.POST)
    if form.is_valid():
        try:
            product = find_product(form.cleaned_data['product_code'])
            qty = quantity_from_text(form.cleaned_data['quantity'], product)
            if PurchaseOrderLine.objects.filter(order=po, product=product).exists():
                raise ValidationError('Product already in the order. Remove it before adding a different quantity.')
            PurchaseOrderLine.objects.create(
                order=po, product=product, quantity=qty, unit_cost=form.cleaned_data['unit_cost'])
            messages.success(request, 'Product added to purchase order.')
        except (ValidationError, IntegrityError) as exc:
            flash_error(request, exc)
    else:
        flash_error(request, 'Check product, quantity and supplier cost. ' + '; '.join(form.errors.get_json_data().keys()))
    return redirect('trading:purchase_detail', pk=po.pk)


@login_required
@require_POST
def purchase_remove_line(request, pk, line_id):
    po = scoped_order(request, PurchaseOrder, pk, operation='purchasing')
    if po.status != PurchaseOrder.Status.DRAFT:
        raise PermissionDenied('Only draft lines may be removed.')
    line = get_object_or_404(PurchaseOrderLine, pk=line_id, order=po)
    line.delete()
    return redirect('trading:purchase_detail', pk=po.pk)


@login_required
@require_POST
def purchase_place(request, pk):
    po = scoped_order(request, PurchaseOrder, pk, operation='purchasing')
    try:
        submit_purchase_order(po)
        messages.success(request, f'{po.reference} placed. Record actual deliveries to increase stock.')
    except ValidationError as exc:
        flash_error(request, exc)
    return redirect('trading:purchase_detail', pk=po.pk)


@login_required
@require_POST
def purchase_receive(request, pk):
    po = scoped_order(request, PurchaseOrder, pk, operation='receive')
    lines = list(po.lines.all())
    received = {line.pk: request.POST.get(f'qty_{line.pk}', '0') for line in lines}
    try:
        receipt = receive_delivery(order=po, actor=request.user,
                                   delivery_note=request.POST.get('delivery_note', ''), quantities=received)
        messages.success(request, f'Goods receipt #{receipt.pk} saved. Branch stock updated.')
    except (ValidationError, IntegrityError) as exc:
        flash_error(request, exc)
    return redirect('trading:purchase_detail', pk=po.pk)


@login_required
@require_http_methods(['GET', 'POST'])
def wholesale_new(request):
    branch = trade_branch(request, operation='wholesale')
    if branch is None:
        messages.error(request, 'Create an active branch first.')
        return redirect('trading:home')
    form = WholesaleOrderForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        order = form.save(commit=False)
        order.branch = branch
        order.created_by = request.user
        order.save()
        messages.success(request, f'{order.reference} created. Add bulk products.')
        return redirect('trading:wholesale_detail', pk=order.pk)
    return render(request, 'trading/form.html', {'form': form, 'heading': 'New wholesale customer order',
                                                'subheading': f'Bulk sale for {branch.name}.'})


@login_required
@require_GET
def wholesale_detail(request, pk):
    order = scoped_order(request, WholesaleOrder, pk, operation='wholesale')
    lines = list(order.lines.select_related('product'))
    matched, search_term = product_search(request, wholesale=True)
    # Quote is indicative: Stage 4 POS recalculates from current prices at fulfillment.
    return render(request, 'trading/wholesale_detail.html', {
        'order': order, 'lines': lines,
        'line_form': WholesaleLineForm(initial={'product_code': request.GET.get('sku', '')[:64]}),
        'matched_products': matched, 'search_term': search_term,
        'quote_total': sum((x.quoted_total for x in lines), Decimal('0.00')),
        'payment_methods': Sale.PaymentMethod.choices,
    })


@login_required
@require_POST
def wholesale_add_line(request, pk):
    order = scoped_order(request, WholesaleOrder, pk, operation='wholesale')
    if order.status != WholesaleOrder.Status.DRAFT:
        raise PermissionDenied('Only draft wholesale orders can be edited.')
    form = WholesaleLineForm(request.POST)
    if form.is_valid():
        try:
            product = find_product(form.cleaned_data['product_code'])
            pricing = line_for(product, form.cleaned_data['quantity'], Sale.SaleType.WHOLESALE)
            if WholesaleOrderLine.objects.filter(order=order, product=product).exists():
                raise ValidationError('Product already on the order; remove it first to change quantity.')
            WholesaleOrderLine.objects.create(order=order, product=product,
                                             quantity=pricing['quantity'], quoted_unit_price=pricing['price'])
            messages.success(request, 'Bulk product added.')
        except (ValidationError, IntegrityError) as exc:
            flash_error(request, exc)
    else:
        flash_error(request, 'Check product and wholesale minimum quantity.')
    return redirect('trading:wholesale_detail', pk=order.pk)


@login_required
@require_POST
def wholesale_remove_line(request, pk, line_id):
    order = scoped_order(request, WholesaleOrder, pk, operation='wholesale')
    if order.status != WholesaleOrder.Status.DRAFT:
        raise PermissionDenied('Only draft lines can be removed.')
    get_object_or_404(WholesaleOrderLine, pk=line_id, order=order).delete()
    return redirect('trading:wholesale_detail', pk=order.pk)


@login_required
@require_POST
def wholesale_prepare(request, pk):
    order = scoped_order(request, WholesaleOrder, pk, operation='wholesale')
    try:
        prepare_wholesale_order(order)
        messages.success(request, 'Order prepared. Confirm stock and payment before checkout.')
    except ValidationError as exc:
        flash_error(request, exc)
    return redirect('trading:wholesale_detail', pk=order.pk)


@login_required
@require_POST
def wholesale_fulfill(request, pk):
    order = scoped_order(request, WholesaleOrder, pk, operation='wholesale')
    try:
        order = fulfill_wholesale_order(
            order=order, actor=request.user,
            method=request.POST.get('payment_method', ''),
            tendered=request.POST.get('cash_tendered', ''),
            reference=request.POST.get('payment_reference', ''),
        )
    except (ValidationError, IntegrityError) as exc:
        flash_error(request, exc)
        return redirect('trading:wholesale_detail', pk=order.pk)
    messages.success(request, f'{order.reference} completed in POS. Receipt: {order.sale.receipt_number}')
    return redirect('pos:receipt', pk=order.sale_id)
