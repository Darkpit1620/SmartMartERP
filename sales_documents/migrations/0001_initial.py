from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0001_initial'),
        ('pos', '0001_initial'),
    ]
    operations = [
        migrations.CreateModel(
            name='BranchPrintBrand',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('trade_name', models.CharField(max_length=140)),
                ('business_number', models.CharField(blank=True, max_length=65)),
                ('address', models.CharField(blank=True, max_length=255)),
                ('phone', models.CharField(blank=True, max_length=45)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('footer', models.CharField(blank=True, max_length=200)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('branch', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,
                                                related_name='print_brand', to='core.branch')),
                ('updated_by', models.ForeignKey(blank=True, null=True,
                                                on_delete=django.db.models.deletion.PROTECT,
                                                related_name='updated_receipt_brands', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='SaleCustomerDetails',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer_name', models.CharField(blank=True, max_length=140)),
                ('customer_phone', models.CharField(blank=True, max_length=45)),
                ('customer_email', models.EmailField(blank=True, max_length=254)),
                ('customer_address', models.CharField(blank=True, max_length=255)),
                ('customer_reference', models.CharField(blank=True, max_length=70)),
                ('note', models.CharField(blank=True, max_length=240)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('sale', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,
                                              related_name='invoice_customer', to='pos.sale')),
                ('updated_by', models.ForeignKey(blank=True, null=True,
                                                on_delete=django.db.models.deletion.PROTECT,
                                                related_name='edited_invoice_customers', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='CustomerDetailsEdit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('changed_fields', models.CharField(max_length=200)),
                ('changed_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                            to=settings.AUTH_USER_MODEL)),
                ('details', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                              related_name='edit_history', to='sales_documents.salecustomerdetails')),
            ],
            options={'ordering': ('-changed_at', '-pk')},
        ),
    ]
