# Stage 13B: cashier shift and cash-drawer history.
from decimal import Decimal
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q
import django.core.validators


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0001_initial'),
    ]
    operations = [
        migrations.CreateModel(
            name='CashierShift',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('OPEN', 'Open'), ('CLOSED', 'Awaiting review'), ('REVIEWED', 'Reviewed')], default='OPEN', max_length=10)),
                ('opening_cash', models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))])),
                ('opened_at', models.DateTimeField(auto_now_add=True)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('closing_cash', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('cash_sales', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('paid_in_total', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('paid_out_total', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('expected_cash', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('variance', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('closing_note', models.CharField(blank=True, max_length=300)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('review_note', models.CharField(blank=True, max_length=300)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cashier_shifts', to='core.branch')),
                ('cashier', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cashier_shifts', to=settings.AUTH_USER_MODEL)),
                ('closed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='closed_cashier_shifts', to=settings.AUTH_USER_MODEL)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reviewed_cashier_shifts', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('-opened_at', '-pk')},
        ),
        migrations.CreateModel(
            name='CashDrawerEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('IN', 'Cash added to drawer'), ('OUT', 'Cash taken from drawer')], max_length=3)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('reference', models.CharField(max_length=100)),
                ('note', models.CharField(max_length=300)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('recorded_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cash_drawer_entries', to=settings.AUTH_USER_MODEL)),
                ('shift', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='entries', to='shift_ops.cashiershift')),
            ],
            options={'ordering': ('created_at', 'pk')},
        ),
        migrations.AddConstraint(model_name='cashiershift', constraint=models.UniqueConstraint(condition=Q(status='OPEN'), fields=('cashier',), name='shiftops_one_open_per_cashier')),
        migrations.AddIndex(model_name='cashiershift', index=models.Index(fields=['branch', 'opened_at'], name='shiftops_branch_open_idx')),
        migrations.AddConstraint(model_name='cashdrawerentry', constraint=models.UniqueConstraint(fields=('shift', 'reference'), name='shiftops_unique_entry_reference')),
    ]
