from decimal import Decimal
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from core.models import Branch
from inventory.models import BranchStock, Product
from .models import Sale
from .permissions import may_verify_payments, pos_branch, visible_sales
from .services import build_cart, complete_sale, line_for, quantity_from_text


def _cart(request, branch):
    if not branch:
        return {}
    if request.session.get('pos_cart_branch') != branch.pk:
        request.session['pos_cart'] = {}
        request.session['pos_cart_branch'] = branch.pk
        request.session['pos_checkout_token'] = uuid4().hex
        request.session.modified = True
    if 'pos_checkout_token' not in request.session:
        request.session['pos_checkout_token'] = uuid4().hex
    return dict(request.session.get('pos_cart', {}))


def _save_cart(request, cart):
    request.session['pos_cart'] = cart
    request.session.modified = True


def _mode(request):
    value = request.session.get('pos_sale_mode', Sale.SaleType.RETAIL)
    return value if value in Sale.SaleType.values else Sale.SaleType.RETAIL


def _error_messages(request, error):
    if isinstance(error, ValidationError):
        for text in error.messages[:6]:
            messages.error(request, text)
    else:
        messages.error(request, str(error))


@login_required
@require_GET
def index(request):
    branch = pos_branch(request)
    branches = Branch.objects.filter(active=True).order_by('name') if request.user.is_superuser else []
    if branch is None:
        return render(request, 'pos/index.html', {
            'branch': None, 'branches': branches, 'rows': [], 'cart_rows': [],
            'query': '', 'cart_errors': [], 'subtotal': 0, 'included_tax': 0,
            'mode': _mode(request), 'page': None,
        })
    cart = _cart(request, branch)
    mode = _mode(request)
    cart_rows, subtotal, included_tax, cart_errors = build_cart(cart, mode, branch)
    search = request.GET.get('q', '').strip()[:120]
    products = Product.objects.filter(is_active=True).select_related('category')
    if search:
        products = products.filter(Q(sku__icontains=search) | Q(barcode__iexact=search)
                                   | Q(name__icontains=search))
    else:
        # Don't load thousands of catalogue items on an idle POS screen.
        products = products.order_by('name', 'pk')
    page = Paginator(products, 18).get_page(request.GET.get('page'))
    quantities = dict(BranchStock.objects.filter(
        branch=branch, product_id__in=[p.pk for p in page]
    ).values_list('product_id', 'quantity'))
    rows = [{'product': p, 'available': quantities.get(p.pk, Decimal('0.000')),
             'saleable': (p.retail_price > 0 and quantities.get(p.pk, Decimal('0.000')) > 0)} for p in page]
    return render(request, 'pos/index.html', {
        'branch': branch, 'branches': branches, 'rows': rows, 'cart_rows': cart_rows,
        'subtotal': subtotal, 'included_tax': included_tax,
        'cart_errors': cart_errors, 'mode': mode, 'query': search, 'page': page,
        'cart_count': len(cart), 'token': request.session['pos_checkout_token'],
        'currency': 'KES',
    })


@login_required
@require_POST
def set_mode(request):
    branch = pos_branch(request)
    if not branch:
        raise Http404('Set up a branch first.')
    _cart(request, branch)
    mode = request.POST.get('sale_type', '')
    if mode not in Sale.SaleType.values:
        messages.error(request, 'Select retail or wholesale pricing.')
    else:
        request.session['pos_sale_mode'] = mode
        messages.info(request, 'Pricing switched to ' + mode.lower() + '.')
    return redirect('pos:index')


@login_required
@require_POST
def add_item(request):
    branch = pos_branch(request)
    if not branch:
        raise Http404('Set up a branch first.')
    cart = _cart(request, branch)
    raw_id = request.POST.get('product_id', '')
    if not raw_id.isascii() or not raw_id.isdigit():
        messages.error(request, 'Choose a valid product.')
        return redirect('pos:index')
    product = get_object_or_404(Product, pk=int(raw_id), is_active=True)
    try:
        quantity = quantity_from_text(request.POST.get('quantity', '1'), product)
        current = Decimal(cart.get(str(product.pk), '0'))
        new_qty = quantity_from_text(current + quantity, product)
        if product.retail_price <= 0:
            raise ValidationError('This product has no verified retail price.')
        available = BranchStock.objects.filter(branch=branch, product=product).values_list('quantity', flat=True).first() or 0
        if new_qty > available:
            raise ValidationError(f'Only {available} available at this branch.')
        if len(cart) >= 120 and str(product.pk) not in cart:
            raise ValidationError('Maximum 120 different products per checkout.')
        cart[str(product.pk)] = str(new_qty)
        _save_cart(request, cart)
        messages.success(request, f'{product.name} added to the cart.')
    except (ValidationError, ArithmeticError) as error:
        _error_messages(request, error)
    return redirect('pos:index')


@login_required
@require_POST
def update_item(request):
    branch = pos_branch(request)
    if not branch:
        raise Http404('Set up a branch first.')
    cart = _cart(request, branch)
    raw_id = request.POST.get('product_id', '')
    if not raw_id.isascii() or not raw_id.isdigit():
        raise Http404('Invalid product')
    key = str(int(raw_id))
    if key not in cart:
        messages.error(request, 'That product is not in your cart.')
        return redirect('pos:index')
    action = request.POST.get('action', 'update')
    if action == 'remove':
        cart.pop(key, None)
    else:
        product = get_object_or_404(Product, pk=int(raw_id))
        try:
            quantity = quantity_from_text(request.POST.get('quantity'), product)
            available = BranchStock.objects.filter(branch=branch, product=product).values_list('quantity', flat=True).first() or 0
            if quantity > available:
                raise ValidationError(f'Only {available} available at this branch.')
            cart[key] = str(quantity)
        except ValidationError as error:
            _error_messages(request, error)
            return redirect('pos:index')
    _save_cart(request, cart)
    return redirect('pos:index')


@login_required
@require_POST
def checkout(request):
    branch = pos_branch(request)
    if not branch:
        raise Http404('Set up a branch first.')
    cart = _cart(request, branch)
    token = request.POST.get('checkout_token', '')
    # After network retries, return the original receipt without creating a second sale.
    previous = Sale.objects.filter(checkout_token=token).first() if token else None
    if previous:
        if previous.cashier_id == request.user.pk and previous.branch_id == branch.pk:
            return redirect('pos:receipt', pk=previous.pk)
        raise Http404('Checkout token not found')
    if not token or token != request.session.get('pos_checkout_token'):
        messages.error(request, 'Checkout expired. Refresh and try again.')
        return redirect('pos:index')
    try:
        sale = complete_sale(
            branch=branch, cashier=request.user, cart=cart, mode=_mode(request),
            method=request.POST.get('payment_method'), token=token,
            tendered=request.POST.get('cash_tendered', ''),
            reference=request.POST.get('payment_reference', ''),
        )
    except ValidationError as error:
        _error_messages(request, error)
        return redirect('pos:index')
    request.session['pos_cart'] = {}
    request.session['pos_checkout_token'] = uuid4().hex
    request.session.modified = True
    messages.success(request, f'Sale completed: {sale.receipt_number}.')
    return redirect('pos:receipt', pk=sale.pk)


@login_required
@require_GET
def receipt(request, pk):
    allowed = visible_sales(request)
    sale = get_object_or_404(allowed.select_related('branch', 'cashier'), pk=pk)
    return render(request, 'pos/receipt.html', {
        'sale': sale, 'items': sale.items.all(),
        'can_verify': may_verify_payments(request, sale),
    })


@login_required
@require_GET
def sales(request):
    allowed = visible_sales(request).select_related('branch', 'cashier')
    page = Paginator(allowed, 30).get_page(request.GET.get('page'))
    return render(request, 'pos/sales.html', {'page': page})


@login_required
@require_POST
def verify_payment(request, pk):
    allowed = visible_sales(request)
    # A branch manager can verify any sale from their branch, including another cashier's sale.
    sale = get_object_or_404(allowed, pk=pk)
    if not may_verify_payments(request, sale):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('Only the branch manager or administrator can verify payments.')
    if sale.payment_method == Sale.PaymentMethod.CASH or sale.payment_status != Sale.PaymentStatus.UNVERIFIED:
        messages.error(request, 'Only unverified external payment references can be verified.')
    elif request.POST.get('confirmed') != 'yes':
        messages.error(request, 'Check the payment with the provider before verifying.')
    else:
        from django.db import transaction
        with transaction.atomic():
            updated = Sale.objects.filter(pk=sale.pk, payment_status=Sale.PaymentStatus.UNVERIFIED).update(
                payment_status=Sale.PaymentStatus.VERIFIED,
                verified_by=request.user, verified_at=timezone.now(),
            )
        if updated:
            messages.success(request, 'Payment marked verified by authorized staff.')
    return redirect('pos:receipt', pk=sale.pk)
