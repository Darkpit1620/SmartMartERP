"""Add approved demo staff ONLY to the POS-TRAINING branch while DEBUG is enabled.

Prints random passwords once. Never changes existing accounts or real branches.
"""
from secrets import token_urlsafe
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Branch, StaffProfile


DEMO_ROLES = (
    ('demo10b_manager', 'MANAGER'),
    ('demo10b_cashier', 'CASHIER'),
    ('demo10b_warehouse', 'WAREHOUSE'),
    ('demo10b_staff', 'STAFF'),
)


class Command(BaseCommand):
    help = 'Create four distinct, approved local TRAINING-ONLY employees in POS-TRAINING.'

    def handle(self, *args, **kwargs):
        if not settings.DEBUG:
            raise CommandError('Demo employee creation is forbidden when DEBUG=False.')
        try:
            branch = Branch.objects.get(code='POS-TRAINING', active=True)
        except Branch.DoesNotExist:
            raise CommandError('Training branch not found. Run: python manage.py setup_pos_demo')
        User = get_user_model()
        with transaction.atomic():
            for username, role in DEMO_ROLES:
                if User.objects.filter(username=username).exists():
                    self.stdout.write(f'{username}: already exists; password and access unchanged')
                    continue
                password = token_urlsafe(20)
                user = User.objects.create_user(
                    username=username, password=password,
                    email=f'{username}@example.invalid',
                    first_name='Training', last_name=role.title(),
                    is_staff=False, is_superuser=False,
                )
                p = StaffProfile.objects.create(user=user, branch=branch, role=role, is_approved=True)
                p.employee_id = f'SME-{p.pk:07d}' if not StaffProfile.objects.filter(employee_id=f'SME-{p.pk:07d}').exists() else None
                if p.employee_id:
                    p.save(update_fields=['employee_id'])
                self.stdout.write(f'USERNAME: {username}  PASSWORD (show once): {password}')
        self.stdout.write(self.style.SUCCESS('Training employees created. Do not use these accounts with real customer data.'))
        self.stdout.write('Keep the passwords private; existing demo passwords are never reset by rerunning this command.')
