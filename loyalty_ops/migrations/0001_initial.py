# Stage 13H: new standalone loyalty tables only. No modifications to existing POS tables.
import django.core.validators
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
            name='LoyaltyMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('member_code', models.CharField(max_length=22, unique=True)),
                ('full_name', models.CharField(max_length=140)),
                ('phone', models.CharField(blank=True, max_length=35)),
                ('consent_recorded', models.BooleanField(default=False, help_text='Customer has agreed to enrollment and purchase history linkage.')),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='loyalty_members', to='core.branch')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='loyalty_members_created', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('-created_at', '-pk'), 'indexes': [models.Index(fields=['branch', 'member_code'], name='loyalty_ops_branch_code_idx')]},
        ),
        migrations.CreateModel(
            name='LoyaltyReward',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=120)),
                ('details', models.CharField(blank=True, max_length=250)),
                ('points_cost', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='loyalty_rewards', to='core.branch')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='loyalty_rewards_created', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('title', 'pk')},
        ),
        migrations.CreateModel(
            name='LoyaltyPurchase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('points_awarded', models.PositiveIntegerField()),
                ('linked_at', models.DateTimeField(auto_now_add=True)),
                ('linked_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='loyalty_sales_linked', to=settings.AUTH_USER_MODEL)),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='loyalty_purchases', to='loyalty_ops.loyaltymember')),
                ('sale', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='loyalty_purchase', to='pos.sale')),
            ],
            options={'ordering': ('-linked_at', '-pk')},
        ),
        migrations.CreateModel(
            name='LoyaltyRedemption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('points_spent', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ('state', models.CharField(choices=[('RESERVED', 'Points reserved, awaiting handover'), ('FULFILLED', 'Reward handed to customer'), ('CANCELLED', 'Cancelled, points released')], default='RESERVED', max_length=12)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('review_reference', models.CharField(blank=True, max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='loyalty_redemptions', to='loyalty_ops.loyaltymember')),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='loyalty_redemptions_requested', to=settings.AUTH_USER_MODEL)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='loyalty_redemptions_reviewed', to=settings.AUTH_USER_MODEL)),
                ('reward', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='loyalty_redemptions', to='loyalty_ops.loyaltyreward')),
            ],
            options={'ordering': ('-created_at', '-pk'), 'indexes': [models.Index(fields=['member', 'state'], name='loyalty_ops_member_state_idx')]},
        ),
    ]
