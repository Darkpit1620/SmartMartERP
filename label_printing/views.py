"""Read-only label selection and printing for approved stock staff."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from core.models import StaffProfile
from inventory.models import Product
from .services import make_labels, sku_input


def _allowed(request):
    user = request.user
    if user.is_superuser and user.is_active:
        return
    try:
        profile = user.store_profile
    except StaffProfile.DoesNotExist:
        raise PermissionDenied('Only approved stock staff can print labels.')
    if (not user.is_active or not profile.is_approved or
        profile.role not in (StaffProfile.Role.MANAGER, StaffProfile.Role.WAREHOUSE) or
        not profile.branch_id or not profile.branch.active):
        raise PermissionDenied('Only approved managers and warehouse employees may print labels.')


@login_required
@require_GET
def home(request):
    _allowed(request)
    query = request.GET.get('q', '').strip()[:80]
    products = Product.objects.filter(is_active=True).select_related('category').order_by('name', 'sku')
    if query:
        products = products.filter(Q(name__icontains=query) | Q(sku__icontains=query) | Q(barcode__icontains=query))
    page = Paginator(products, 25).get_page(request.GET.get('page'))
    return render(request, 'label_printing/home.html', {'page': page, 'query': query, 'copies_options': range(1, 9)})


@login_required
@require_POST
def preview(request):
    _allowed(request)
    raw_skus = request.POST.get('skus', '')
    checked = request.POST.getlist('selected_skus')
    copies = request.POST.get('copies', '1')
    mode = request.POST.get('mode', 'shelf')
    try:
        requested = sku_input(raw_skus, checked)
        labels, skipped = make_labels(requested, copies, mode)
        if not labels:
            raise ValidationError('No priced, active products could be printed.')
    except ValidationError as exc:
        return render(request, 'label_printing/error.html', {'errors': exc.messages}, status=400)
    return render(request, 'label_printing/print.html', {
        'labels': labels, 'skipped': skipped, 'mode': mode,
        'count': len(labels), 'unique_count': len(requested),
    })
