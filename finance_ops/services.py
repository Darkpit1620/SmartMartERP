"""Approval workflow. Never mutate POS sales, receipts or inventory here."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Expense


@transaction.atomic
def review_expense(*, pk, actor, approve, note=''):
    if not actor.is_authenticated or not actor.is_active or not actor.is_superuser:
        raise PermissionDenied('Only head-office administrators may approve expenses.')
    expense = Expense.objects.select_for_update().get(pk=pk)
    if expense.status != Expense.Status.PENDING:
        raise ValidationError('This expense has already been reviewed.')
    expense.status = Expense.Status.APPROVED if approve else Expense.Status.REJECTED
    expense.reviewed_by = actor
    expense.reviewed_at = timezone.now()
    expense.review_note = (note or '').strip()[:350]
    expense.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_note'])
    return expense
