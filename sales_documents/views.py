"""Branch-scoped, read-only printable documents plus separately authorized details edits."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from core.models import Branch, StaffProfile
from pos.permissions import visible_sales
from .forms import BranchBrandForm, CustomerDetailsForm
from .models import BranchPrintBrand, CustomerDetailsEdit, SaleCustomerDetails, invoice_number


def _sale(request, pk):
    return get_object_or_404(visible_sales(request).select_related('branch', 'cashier'), pk=pk)


def _print_context(sale):
    brand = BranchPrintBrand.objects.filter(branch=sale.branch).first()
    details = SaleCustomerDetails.objects.filter(sale=sale).first()
    return {
        'sale': sale,
        'items': sale.items.all(),
        'brand': brand,
        'customer': details,
        'invoice_number': invoice_number(sale),
    }


@login_required
@require_GET
def home(request):
    page = Paginator(visible_sales(request).select_related('branch', 'cashier'), 25).get_page(request.GET.get('page'))
    return render(request, 'sales_documents/home.html', {'page': page})


@login_required
@require_GET
def thermal_receipt(request, pk):
    return render(request, 'sales_documents/thermal.html', _print_context(_sale(request, pk)))


@login_required
@require_GET
def commercial_invoice(request, pk):
    return render(request, 'sales_documents/invoice.html', _print_context(_sale(request, pk)))


@login_required
@require_http_methods(['GET', 'POST'])
def customer_details(request, pk):
    sale = _sale(request, pk)
    previous = SaleCustomerDetails.objects.filter(sale=sale).first()
    form = CustomerDetailsForm(request.POST or None, instance=previous)
    if request.method == 'POST' and form.is_valid():
        if form.has_changed():
            with transaction.atomic():
                # Serialize modifications to the parent sale, avoiding concurrent edit races.
                from pos.models import Sale
                Sale.objects.select_for_update().get(pk=sale.pk)
                details, _ = SaleCustomerDetails.objects.get_or_create(sale=sale)
                updated = CustomerDetailsForm(request.POST, instance=details)
                if not updated.is_valid():
                    form = updated
                elif updated.has_changed():
                    record = updated.save(commit=False)
                    record.updated_by = request.user
                    record.save()
                    CustomerDetailsEdit.objects.create(
                        details=record, actor=request.user,
                        changed_fields=', '.join(updated.changed_data),
                    )
                    messages.success(request, 'Customer details saved for this sale.')
                    return redirect('sales_documents:commercial_invoice', pk=sale.pk)
                else:
                    return redirect('sales_documents:commercial_invoice', pk=sale.pk)
        else:
            return redirect('sales_documents:commercial_invoice', pk=sale.pk)
    return render(request, 'sales_documents/customer.html', {
        'sale': sale, 'form': form, 'invoice_number': invoice_number(sale),
        'edits': previous.edit_history.select_related('actor')[:10] if previous else [],
    })


def _brand_branch(request):
    if request.user.is_superuser:
        options = Branch.objects.filter(active=True).order_by('name')
        raw = (request.POST if request.method == 'POST' else request.GET).get('branch', '')
        if raw:
            if not raw.isascii() or not raw.isdigit():
                raise Http404('Invalid branch')
            return get_object_or_404(options, pk=int(raw)), options
        return options.first(), options
    try:
        profile = request.user.store_profile
    except StaffProfile.DoesNotExist:
        raise PermissionDenied('An approved branch manager account is required.')
    if (not profile.is_approved or profile.role != StaffProfile.Role.MANAGER or
            not profile.branch_id or not profile.branch.active):
        raise PermissionDenied('Only an approved branch manager may edit receipt branding.')
    return profile.branch, None


@login_required
@require_http_methods(['GET', 'POST'])
def brand_settings(request):
    branch, branches = _brand_branch(request)
    if branch is None:
        return render(request, 'sales_documents/branding.html', {'branch': None, 'branches': branches})
    profile = BranchPrintBrand.objects.filter(branch=branch).first()
    initial = {'trade_name': branch.name, 'address': branch.address, 'phone': branch.phone} if profile is None else None
    form = BranchBrandForm(request.POST or None, instance=profile, initial=initial)
    if request.method == 'POST' and form.is_valid():
        profile = form.save(commit=False)
        profile.branch = branch
        profile.updated_by = request.user
        profile.save()
        messages.success(request, 'Branch receipt branding saved.')
        return redirect(reverse('sales_documents:brand_settings') + '?branch=' + str(branch.pk))
    return render(request, 'sales_documents/branding.html', {
        'branch': branch, 'branches': branches, 'form': form,
    })
