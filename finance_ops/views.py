"""Read-only sales reporting and audited operating-expense review."""
import csv
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from core.models import Branch
from pos.models import Sale
from .forms import ExpenseForm
from .models import Expense
from .permissions import finance_scope
from .services import review_expense

MONEY = DecimalField(max_digits=16, decimal_places=2)
ZERO = Decimal('0.00')
CONFIRMED = (Sale.PaymentStatus.CASH_RECEIVED, Sale.PaymentStatus.VERIFIED)


def amount_sum(qs, field):
    return qs.aggregate(total=Coalesce(Sum(field), Value(ZERO), output_field=MONEY))['total']


def permitted_filter(request):
    """Return validated branch/date parameters. All access checks precede queries."""
    fixed = finance_scope(request.user)
    today = timezone.localdate()
    default_start = today.replace(day=1)
    raw_start = request.GET.get('start', default_start.isoformat())
    raw_end = request.GET.get('end', today.isoformat())
    try:
        start, end = date.fromisoformat(raw_start), date.fromisoformat(raw_end)
    except (ValueError, TypeError):
        raise Http404('Dates must be valid YYYY-MM-DD values.')
    if start > end or (end - start).days > 366 or end > today:
        raise Http404('Choose a valid reporting period of at most 367 days, ending today or earlier.')

    if fixed is not None:
        branch = fixed  # A manager cannot override their assigned branch using a query string.
    else:
        selected = request.GET.get('branch', '')
        if selected:
            if not selected.isascii() or not selected.isdecimal():
                raise Http404('Unknown branch.')
            branch = get_object_or_404(Branch, pk=int(selected))
        else:
            branch = None  # Superuser sees all branches.
    return branch, start, end


def records(branch, start, end):
    sales = Sale.objects.filter(created_at__date__gte=start, created_at__date__lte=end)
    expenses = Expense.objects.filter(incurred_on__gte=start, incurred_on__lte=end)
    if branch is not None:
        sales = sales.filter(branch=branch)
        expenses = expenses.filter(branch=branch)
    return sales, expenses


def totals(sales, expenses):
    return {
        'recorded_sales': amount_sum(sales, 'subtotal'),
        'confirmed_receipts': amount_sum(sales.filter(payment_status__in=CONFIRMED), 'subtotal'),
        'unverified_receipts': amount_sum(sales.filter(payment_status=Sale.PaymentStatus.UNVERIFIED), 'subtotal'),
        'retail_sales': amount_sum(sales.filter(sale_type=Sale.SaleType.RETAIL), 'subtotal'),
        'wholesale_sales': amount_sum(sales.filter(sale_type=Sale.SaleType.WHOLESALE), 'subtotal'),
        'approved_expenses': amount_sum(expenses.filter(status=Expense.Status.APPROVED), 'amount'),
        'pending_expenses': amount_sum(expenses.filter(status=Expense.Status.PENDING), 'amount'),
        'sale_count': sales.count(),
        'pending_expense_count': expenses.filter(status=Expense.Status.PENDING).count(),
    }


@login_required
@require_GET
def overview(request):
    branch, start, end = permitted_filter(request)
    sales, expenses_qs = records(branch, start, end)
    summary = totals(sales, expenses_qs)

    sale_per_branch = {
        row['branch_id']: row for row in sales.values('branch_id').annotate(
            recorded=Coalesce(Sum('subtotal'), Value(ZERO), output_field=MONEY),
            confirmed=Coalesce(Sum('subtotal', filter=Q(payment_status__in=CONFIRMED)),
                               Value(ZERO), output_field=MONEY),
            transactions=Count('pk'),
        )
    }
    expense_per_branch = {
        row['branch_id']: row for row in expenses_qs.filter(status=Expense.Status.APPROVED)
        .values('branch_id').annotate(amount=Coalesce(Sum('amount'), Value(ZERO), output_field=MONEY))
    }
    active_branches = Branch.objects.filter(pk=branch.pk) if branch is not None else Branch.objects.all()
    branch_rows = []
    for b in active_branches.order_by('name'):
        sr = sale_per_branch.get(b.pk, {})
        er = expense_per_branch.get(b.pk, {})
        branch_rows.append({
            'branch': b,
            'recorded': sr.get('recorded', ZERO),
            'confirmed': sr.get('confirmed', ZERO),
            'expenses': er.get('amount', ZERO),
            'transactions': sr.get('transactions', 0),
        })

    beginning = max(start, end - timedelta(days=13))
    day_totals = {
        row['day']: row['amount']
        for row in sales.filter(created_at__date__gte=beginning)
        .annotate(day=TruncDate('created_at'))
        .values('day').annotate(amount=Sum('subtotal'))
    }
    largest = max(day_totals.values(), default=ZERO)
    daily = []
    for offset in range((end - beginning).days + 1):
        day = beginning + timedelta(days=offset)
        value = day_totals.get(day, ZERO)
        width = round((value / largest) * 100) if largest else 0
        daily.append({'day': day, 'amount': value, 'width': width})

    return render(request, 'finance_ops/overview.html', {
        'summary': summary, 'branch_rows': branch_rows, 'daily': daily,
        'sales': sales.select_related('branch', 'cashier').order_by('-created_at', '-pk')[:20],
        'branch_filter': branch, 'branches': Branch.objects.order_by('name') if request.user.is_superuser else (),
        'start': start, 'end': end, 'is_head_office': request.user.is_superuser,
    })


@login_required
@require_GET
def expenses(request):
    branch = finance_scope(request.user)
    qs = Expense.objects.select_related('branch', 'recorded_by', 'reviewed_by')
    if branch is not None:
        qs = qs.filter(branch=branch)
    status = request.GET.get('status', 'ALL')
    if status not in ('ALL', *Expense.Status.values):
        raise Http404('Invalid status')
    if status != 'ALL':
        qs = qs.filter(status=status)
    return render(request, 'finance_ops/expenses.html', {
        'expenses': qs[:150], 'status': status,
        'is_head_office': request.user.is_superuser,
    })


@login_required
def new_expense(request):
    fixed = finance_scope(request.user)
    form = ExpenseForm(request.POST or None, fixed_branch=fixed)
    if request.method == 'POST' and form.is_valid():
        expense = form.save(commit=False)
        if fixed is not None:
            expense.branch = fixed
        expense.recorded_by = request.user
        expense.status = Expense.Status.PENDING
        expense.full_clean()
        expense.save()
        messages.success(request, 'Expense recorded and sent for head-office approval.')
        return redirect('finance_ops:expenses')
    return render(request, 'finance_ops/new_expense.html', {'form': form})


@login_required
@require_POST
def review(request, pk):
    finance_scope(request.user)
    if not request.user.is_superuser:
        raise PermissionDenied('Only head-office administrators may approve expenses.')
    action = request.POST.get('action')
    if action not in ('approve', 'reject'):
        raise Http404('Invalid review action.')
    get_object_or_404(Expense, pk=pk)
    try:
        review_expense(pk=pk, actor=request.user, approve=(action == 'approve'),
                       note=request.POST.get('note', ''))
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        messages.success(request, 'Expense reviewed and audit details saved.')
    return redirect('finance_ops:expenses')


def safe_csv(value):
    """Prevent formula evaluation in spreadsheet programs when opening CSV files."""
    text = str(value if value is not None else '')
    return "'" + text if text.startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else text


@login_required
@require_GET
def export_report(request):
    branch, start, end = permitted_filter(request)
    sales, expenses_qs = records(branch, start, end)
    if sales.count() + expenses_qs.count() > 10000:
        return HttpResponse('Too many transactions. Choose a shorter date range.', status=400,
                            content_type='text/plain')
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="smartmart-finance-{start}-{end}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Type', 'Date', 'Branch', 'Reference', 'Category/Payment',
                     'Status', 'Recorded Sales (KES)', 'Expense Amount (KES)'])
    for sale in sales.select_related('branch').order_by('created_at', 'pk'):
        writer.writerow(['SALE', timezone.localtime(sale.created_at).date().isoformat(),
                         safe_csv(sale.branch.code), safe_csv(sale.receipt_number or sale.pk),
                         sale.get_payment_method_display(), sale.get_payment_status_display(),
                         sale.subtotal, ''])
    for expense in expenses_qs.select_related('branch').order_by('incurred_on', 'pk'):
        writer.writerow(['EXPENSE', expense.incurred_on.isoformat(), safe_csv(expense.branch.code),
                         safe_csv(expense.reference or f'EXP-{expense.pk}'),
                         expense.get_category_display(), expense.get_status_display(),
                         '', expense.amount])
    return response
