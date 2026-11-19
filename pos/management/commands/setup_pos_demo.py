"""Opt-in, clearly labelled training branch, training stock and example prices.

Never seed training quantities into a real branch. Safe to run twice.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Branch
from inventory.models import BranchStock, Category, Product, StockMovement
from inventory.services import record_stock_movement

TRAINING_PRODUCTS = [
    ('Maize Flour 2 kg', 'EACH', '155.00', '140.00', 6),
    ('Rice 5 kg', 'EACH', '760.00', '700.00', 4),
    ('Cooking Oil 1 L', 'EACH', '320.00', '295.00', 6),
    ('Sugar 2 kg', 'EACH', '290.00', '260.00', 6),
    ('Milk 500 ml', 'EACH', '65.00', '60.00', 12),
    ('Laundry Detergent 1 kg', 'EACH', '210.00', '195.00', 6),
    ('Bath Soap 200 g', 'EACH', '85.00', '75.00', 8),
    ('Bananas by kilogram', 'KG', '120.00', '105.00', 5),
]


class Command(BaseCommand):
    help = 'Create an explicitly labelled TRAINING-ONLY branch and 8 sample checkout products.'

    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(is_superuser=True, is_active=True).first()
        if not actor:
            raise CommandError('Create an administrator first with python manage.py createsuperuser.')
        with transaction.atomic():
            branch, _ = Branch.objects.get_or_create(
                code='POS-TRAINING',
                defaults={
                    'name': 'POS TRAINING BRANCH — NOT REAL INVENTORY',
                    'address': 'Training data only; do not record real customer sales here',
                    'active': True,
                },
            )
            category, _ = Category.objects.get_or_create(name='POS Training Products (Sample Data)')
            for index, (name, unit, retail, wholesale, minimum) in enumerate(TRAINING_PRODUCTS, 1):
                product, _ = Product.objects.get_or_create(
                    sku=f'DEMO-POS-{index:03d}',
                    defaults={
                        'category': category, 'name': f'TRAINING ONLY — {name}',
                        'unit': unit, 'retail_price': Decimal(retail),
                        'wholesale_price': Decimal(wholesale), 'cost_price': Decimal('0.00'),
                        'wholesale_min_qty': minimum, 'tax_rate': Decimal('0.00'),
                    },
                )
                if not BranchStock.objects.filter(branch=branch, product=product).exists():
                    record_stock_movement(
                        branch=branch, product=product, actor=actor,
                        kind=StockMovement.Kind.RECEIPT, quantity=Decimal('30.000'),
                        reference='POS-TRAINING-SETUP', note='TRAINING STOCK — NOT REAL INVENTORY',
                    )
        self.stdout.write(self.style.SUCCESS('Demo branch ready: POS-TRAINING (not actual inventory).'))
        self.stdout.write('Log in as superuser, open POS, and select POS TRAINING BRANCH.')
        self.stdout.write('Search for DEMO-POS-001, add quantity 2, and test cash checkout.')
        self.stdout.write('Re-running this command will not reset your training stock or demo prices.')
