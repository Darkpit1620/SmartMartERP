"""Finance security and data-integrity tests; run with manage.py test finance_ops."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Branch, StaffProfile
from pos.models import Sale
from .models import Expense
from .services import review_expense


class FinanceStageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.branch_a = Branch.objects.create(name='North Shop', code='NTH')
        cls.branch_b = Branch.objects.create(name='East Shop', code='EST')
        cls.admin = User.objects.create_superuser(username='finance_root', email='finance@example.com', password='test-password-123')
        cls.manager_a = User.objects.create_user(username='finance_mgr_a', password='test-password-123')
        cls.manager_b = User.objects.create_user(username='finance_mgr_b', password='test-password-123')
        cls.cashier = User.objects.create_user(username='finance_cashier', password='test-password-123')
        cls.pending_mgr = User.objects.create_user(username='finance_pending', password='test-password-123')
        for user, role, branch, approved in (
            (cls.manager_a, 'MANAGER', cls.branch_a, True),
            (cls.manager_b, 'MANAGER', cls.branch_b, True),
            (cls.cashier, 'CASHIER', cls.branch_a, True),
            (cls.pending_mgr, 'MANAGER', cls.branch_a, False),
        ):
            StaffProfile.objects.create(user=user, role=role, branch=branch, is_approved=approved)
        cls.sale_cash = Sale.objects.create(
            branch=cls.branch_a, cashier=cls.cashier,
            sale_type=Sale.SaleType.RETAIL, payment_method=Sale.PaymentMethod.CASH,
            payment_status=Sale.PaymentStatus.CASH_RECEIVED, subtotal=Decimal('140.00'),
            checkout_token='finance-test-cash-1',
        )
        cls.sale_unverified = Sale.objects.create(
            branch=cls.branch_a, cashier=cls.cashier,
            sale_type=Sale.SaleType.WHOLESALE, payment_method=Sale.PaymentMethod.MPESA,
            payment_status=Sale.PaymentStatus.UNVERIFIED, subtotal=Decimal('310.00'),
            checkout_token='finance-test-mpesa-2',
        )
        cls.sale_other = Sale.objects.create(
            branch=cls.branch_b, cashier=cls.cashier,
            sale_type=Sale.SaleType.RETAIL, payment_method=Sale.PaymentMethod.CASH,
            payment_status=Sale.PaymentStatus.CASH_RECEIVED, subtotal=Decimal('700.00'),
            checkout_token='finance-test-other-3',
        )
        cls.approved_expense = Expense.objects.create(
            branch=cls.branch_a, category=Expense.Category.UTILITIES,
            amount=Decimal('25.00'), description='Electricity test',
            recorded_by=cls.manager_a, status=Expense.Status.APPROVED,
        )
        cls.pending_expense = Expense.objects.create(
            branch=cls.branch_a, category=Expense.Category.TRANSPORT,
            amount=Decimal('60.00'), description='Delivery test', recorded_by=cls.manager_a,
        )
        cls.other_expense = Expense.objects.create(
            branch=cls.branch_b, category=Expense.Category.RENT,
            amount=Decimal('100.00'), description='East rent test',
            recorded_by=cls.manager_b, status=Expense.Status.APPROVED,
        )

    def test_manager_sees_only_branch_totals(self):
        self.client.force_login(self.manager_a)
        response = self.client.get(reverse('finance_ops:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['summary']['recorded_sales'], Decimal('450.00'))
        self.assertEqual(response.context['summary']['confirmed_receipts'], Decimal('140.00'))
        self.assertEqual(response.context['summary']['unverified_receipts'], Decimal('310.00'))
        self.assertEqual(response.context['summary']['approved_expenses'], Decimal('25.00'))
        self.assertEqual(response.context['summary']['pending_expenses'], Decimal('60.00'))
        self.assertEqual(len(response.context['branch_rows']), 1)
        self.assertEqual(response.context['branch_rows'][0]['branch'], self.branch_a)
        self.assertNotContains(response, 'East Shop')

    def test_manager_cannot_switch_branch_by_query_or_export(self):
        self.client.force_login(self.manager_a)
        response = self.client.get(reverse('finance_ops:overview'), {'branch': self.branch_b.pk})
        self.assertEqual(response.context['summary']['recorded_sales'], Decimal('450.00'))
        csv_resp = self.client.get(reverse('finance_ops:export_report'), {'branch': self.branch_b.pk})
        self.assertEqual(csv_resp.status_code, 200)
        self.assertIn('NTH', csv_resp.content.decode())
        self.assertNotIn('EST', csv_resp.content.decode())

    def test_admin_can_filter_all_branches(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('finance_ops:overview'))
        self.assertEqual(response.context['summary']['recorded_sales'], Decimal('1150.00'))
        selected = self.client.get(reverse('finance_ops:overview'), {'branch': self.branch_b.pk})
        self.assertEqual(selected.context['summary']['recorded_sales'], Decimal('700.00'))
        self.assertEqual(selected.context['summary']['approved_expenses'], Decimal('100.00'))

    def test_cashiers_and_pending_managers_cannot_see_finance(self):
        for user in (self.cashier, self.pending_mgr):
            self.client.force_login(user)
            for route in ('overview', 'expenses', 'new_expense', 'export_report'):
                response = self.client.get(reverse(f'finance_ops:{route}'))
                self.assertEqual(response.status_code, 403, (user.username, route))
        self.client.logout()
        response = self.client.get(reverse('finance_ops:overview'))
        self.assertEqual(response.status_code, 302)

    def test_manager_records_pending_expense_to_own_branch(self):
        self.client.force_login(self.manager_a)
        response = self.client.post(reverse('finance_ops:new_expense'), {
            'branch': str(self.branch_b.pk),  # Forged POST field cannot override manager scope.
            'category': 'OFFICE', 'amount': '18.50',
            'incurred_on': timezone.localdate().isoformat(),
            'description': 'Office materials', 'reference': 'OFC-2',
        })
        self.assertRedirects(response, reverse('finance_ops:expenses'))
        expense = Expense.objects.get(reference='OFC-2')
        self.assertEqual(expense.branch, self.branch_a)
        self.assertEqual(expense.status, Expense.Status.PENDING)
        self.assertEqual(expense.recorded_by, self.manager_a)
        result = self.client.get(reverse('finance_ops:overview'))
        self.assertEqual(result.context['summary']['approved_expenses'], Decimal('25.00'))

    def test_manager_cannot_approve_expenses(self):
        self.client.force_login(self.manager_a)
        response = self.client.post(reverse('finance_ops:review', args=[self.pending_expense.pk]), {'action': 'approve'})
        self.assertEqual(response.status_code, 403)
        self.pending_expense.refresh_from_db()
        self.assertEqual(self.pending_expense.status, Expense.Status.PENDING)

    def test_admin_approval_changes_totals_and_cannot_repeat(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('finance_ops:review', args=[self.pending_expense.pk]), {'action': 'approve'})
        self.assertRedirects(response, reverse('finance_ops:expenses'))
        self.pending_expense.refresh_from_db()
        self.assertEqual(self.pending_expense.status, Expense.Status.APPROVED)
        self.assertEqual(self.pending_expense.reviewed_by, self.admin)
        result = self.client.get(reverse('finance_ops:overview'), {'branch': self.branch_a.pk})
        self.assertEqual(result.context['summary']['approved_expenses'], Decimal('85.00'))
        self.client.post(reverse('finance_ops:review', args=[self.pending_expense.pk]), {'action': 'reject'})
        self.pending_expense.refresh_from_db()
        self.assertEqual(self.pending_expense.status, Expense.Status.APPROVED)

    def test_review_is_post_only_and_bad_action_rejected(self):
        self.client.force_login(self.admin)
        target = reverse('finance_ops:review', args=[self.pending_expense.pk])
        self.assertEqual(self.client.get(target).status_code, 405)
        self.assertEqual(self.client.post(target, {'action': 'delete'}).status_code, 404)

    def test_invalid_dates_do_not_leak_sales(self):
        self.client.force_login(self.manager_a)
        for filters in ({'start': '2020-01-01', 'end': '2030-01-01'},
                        {'start': 'invalid', 'end': '2026-11-01'},
                        {'start': '2030-01-01', 'end': '2026-01-01'}):
            self.assertEqual(self.client.get(reverse('finance_ops:overview'), filters).status_code, 404)

    def test_csv_has_expected_header(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('finance_ops:export_report'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        body = response.content.decode('utf-8')
        self.assertIn('Recorded Sales (KES)', body)
        self.assertIn('EXPENSE', body)

    def test_rejects_invalid_expense_amount(self):
        self.client.force_login(self.manager_a)
        before = Expense.objects.count()
        self.client.post(reverse('finance_ops:new_expense'), {
            'category': 'RENT', 'amount': '-12.00', 'incurred_on': timezone.localdate().isoformat(),
            'description': 'Bad value',
        })
        self.assertEqual(Expense.objects.count(), before)
