from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ('pos', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(name='ReturnRequest', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('status', models.CharField(choices=[('REQUESTED', 'Awaiting manager review'), ('APPROVED', 'Return approved'), ('REJECTED', 'Rejected')], default='REQUESTED', max_length=12)),
            ('reason', models.TextField(max_length=500)),
            ('amount', models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
            ('reviewed_at', models.DateTimeField(blank=True, null=True)),
            ('review_note', models.CharField(blank=True, max_length=300)),
            ('restocked', models.BooleanField(default=False)),
            ('refund_status', models.CharField(choices=[('PENDING','Refund not yet recorded as paid'),('RECORDED','Refund manually recorded as paid')], default='PENDING', max_length=12)),
            ('refund_method', models.CharField(blank=True, choices=[('CASH','Cash'),('MPESA','M-Pesa (manual reference)'),('CARD','Card (manual reference)'),('BANK','Bank transfer (manual reference)')], max_length=10)),
            ('refund_reference', models.CharField(blank=True, max_length=120)),
            ('refunded_at', models.DateTimeField(blank=True, null=True)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('sale', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='return_requests', to='pos.sale')),
            ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='return_requests_created', to=settings.AUTH_USER_MODEL)),
            ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='returns_reviewed', to=settings.AUTH_USER_MODEL)),
            ('refunded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='refunds_recorded', to=settings.AUTH_USER_MODEL)),
        ], options={'ordering': ('-created_at', '-pk')}),
        migrations.CreateModel(name='ReturnLine', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('quantity', models.DecimalField(decimal_places=3, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.001'))])),
            ('amount', models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
            ('request', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='lines', to='returns_ops.returnrequest')),
            ('sale_item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='return_lines', to='pos.saleitem')),
        ]),
        migrations.AddConstraint(model_name='returnline', constraint=models.UniqueConstraint(fields=('request', 'sale_item'), name='returns_one_line_per_request')),
        migrations.AddIndex(model_name='returnrequest', index=models.Index(fields=['status', 'created_at'], name='returns_ops_status_44ab9f_idx')),
    ]
