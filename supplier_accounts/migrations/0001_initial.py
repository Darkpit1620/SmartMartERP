from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('trading', '0001_initial'),
    ]
    operations = [
        migrations.CreateModel(
            name='SupplierInvoice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('invoice_number', models.CharField(max_length=80)),
                ('invoice_date', models.DateField()),
                ('due_date', models.DateField()),
                ('amount', models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('note', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('purchase_order', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='supplier_invoices', to='trading.purchaseorder')),
                ('recorded_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='supplier_invoices_entered', to=settings.AUTH_USER_MODEL)),
                ('supplier', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='account_invoices', to='trading.supplier')),
            ],
            options={'ordering': ('-created_at', '-pk')},
        ),
        migrations.CreateModel(
            name='SupplierPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('method', models.CharField(choices=[('CASH', 'Cash'), ('BANK', 'Bank transfer'), ('MPESA', 'M-Pesa'), ('CARD', 'Card'), ('OTHER', 'Other')], max_length=12)),
                ('reference', models.CharField(max_length=100)),
                ('paid_on', models.DateField()),
                ('note', models.CharField(blank=True, max_length=255)),
                ('recorded_at', models.DateTimeField(auto_now_add=True)),
                ('invoice', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payments', to='supplier_accounts.supplierinvoice')),
                ('recorded_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='supplier_payments_entered', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('-recorded_at', '-pk')},
        ),
        migrations.AddConstraint(model_name='supplierinvoice', constraint=models.UniqueConstraint(fields=('supplier', 'invoice_number'), name='supplier_accounts_supplier_invoice_unique')),
        migrations.AddConstraint(model_name='supplierpayment', constraint=models.UniqueConstraint(fields=('invoice', 'reference'), name='supplier_accounts_invoice_payment_ref_unique')),
    ]
