"""Branch-scoped, read-only ledger and deliberate POST-only recording actions."""
import csv
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods
from core.models import Branch
from .forms import InvoiceForm, PaymentForm
from .models import SupplierInvoice, SupplierPayment
from .permissions import ensure_invoice_branch, permitted_branch
from .services import record_invoice, record_payment


def branch_invoices(branch):
    if branch is None:
        return SupplierInvoice.objects.none()
    return SupplierInvoice.objects.filter(purchase_order__branch=branch).select_related('supplier', 'purchase_order', 'recorded_by')


def csv_safe(raw):
    text = str(raw if raw is not None else '')
    if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
        return "'" + text
    return text


def money_txt(value):
    return f'{value:.2f}'


@login_required
@require_GET
def home(request):
    branch = permitted_branch(request)
    branches = Branch.objects.filter(active=True) if request.user.is_superuser else []
    qs = branch_invoices(branch)
    search = request.GET.get('q', '').strip()[:80]
    if search:
        from django.db.models import Q
        qs = qs.filter(Q(invoice_number__icontains=search) | Q(supplier__name__icontains=search))
    invoices = list(qs[:200])
    for item in invoices:
        item.ledger_paid = item.paid_amount
        item.ledger_balance = max(item.amount - item.ledger_paid, Decimal('0.00'))
    all_items = branch_invoices(branch)
    invoiced = all_items.aggregate(v=Sum('amount'))['v'] or Decimal('0.00')
    paid = SupplierPayment.objects.filter(invoice__purchase_order__branch=branch).aggregate(v=Sum('amount'))['v'] if branch else None
    paid = paid or Decimal('0.00')
    return render(request, 'supplier_accounts/home.html', {
        'branch': branch, 'branches': branches, 'invoices': invoices, 'search': search,
        'invoiced': invoiced, 'paid': paid, 'outstanding': invoiced - paid,
        'invoice_count': all_items.count(), 'list_truncated': qs.count() > 200,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def invoice_new(request):
    branch = permitted_branch(request)
    if branch is None:
        messages.error(request, 'Create an active branch first.')
        return redirect('supplier_accounts:home')
    form = InvoiceForm(request.POST or None, branch=branch)
    if request.method == 'GET' and request.GET.get('purchase_order'):
        form.fields['purchase_order'].initial = request.GET.get('purchase_order')
    if request.method == 'POST' and form.is_valid():
        try:
            invoice = record_invoice(actor=request.user, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f'Supplier invoice {invoice.invoice_number} recorded. No external payment was sent.')
            return redirect(f'/supplier-accounts/invoices/{invoice.pk}/?branch={branch.pk}')
    return render(request, 'supplier_accounts/form.html', {
        'form': form, 'branch': branch, 'heading': 'Record supplier invoice',
        'instructions': 'Use the supplier’s genuine invoice document. The total must fit within the purchase order value.',
    })


@login_required
@require_GET
def invoice_detail(request, pk):
    branch = permitted_branch(request)
    invoice = get_object_or_404(SupplierInvoice.objects.select_related('purchase_order__branch', 'supplier'), pk=pk)
    ensure_invoice_branch(invoice, branch)
    return render(request, 'supplier_accounts/detail.html', {
        'invoice': invoice, 'branch': branch,
        'payments': invoice.payments.select_related('recorded_by').all(),
    })


@login_required
@require_http_methods(['GET', 'POST'])
def payment_new(request, pk):
    branch = permitted_branch(request)
    invoice = get_object_or_404(SupplierInvoice.objects.select_related('purchase_order__branch', 'supplier'), pk=pk)
    ensure_invoice_branch(invoice, branch)
    form = PaymentForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            payment = record_payment(invoice=invoice, actor=request.user, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f'Payment record {payment.reference} saved. This did NOT send money.')
            return redirect(f'/supplier-accounts/invoices/{invoice.pk}/?branch={branch.pk}')
    return render(request, 'supplier_accounts/form.html', {
        'form': form, 'branch': branch, 'invoice': invoice,
        'heading': f'Record payment: {invoice.invoice_number}',
        'instructions': 'Only record a payment after confirming it was actually made outside SmartMart. There is no automatic bank or M-Pesa transfer.',
    })


@login_required
@require_GET
def export_csv(request):
    branch = permitted_branch(request)
    qs = branch_invoices(branch).order_by('supplier__name', 'invoice_number')
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="smartmart_supplier_balances.csv"'
    writer = csv.writer(response)
    writer.writerow(['SmartMart ERP supplier accounts (KES)', 'Manual entries; not bank reconciliation'])
    writer.writerow(['Branch', csv_safe(branch.name if branch else 'No branch')])
    writer.writerow(['Supplier', 'Invoice', 'Purchase order', 'Invoice date', 'Due date', 'Invoice total KES', 'Recorded payments KES', 'Outstanding KES', 'Status'])
    for inv in qs:
        paid = inv.paid_amount
        writer.writerow([csv_safe(inv.supplier.name), csv_safe(inv.invoice_number), csv_safe(inv.purchase_order.reference),
                         str(inv.invoice_date), str(inv.due_date), money_txt(inv.amount),
                         money_txt(paid), money_txt(max(inv.amount-paid, Decimal('0.00'))), inv.state])
    return response
