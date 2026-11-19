from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from core.models import Branch, StaffProfile
from inventory.models import BranchStock, Category, Product
from .models import Sale
from .services import complete_sale, quantity_from_text


class POSTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(name='City Centre', code='CITY', active=True)
        cls.other_branch = Branch.objects.create(name='Airport', code='AIR', active=True)
        cls.category = Category.objects.create(name='Test groceries')
        cls.product = Product.objects.create(
            category=cls.category, name='Rice 1kg', sku='RICE-TEST-001',
            unit=Product.Unit.EACH, retail_price=Decimal('120.00'),
            wholesale_price=Decimal('100.00'), wholesale_min_qty=5,
            tax_rate=Decimal('0'), cost_price=Decimal('80.00'),
        )
        cls.weighted = Product.objects.create(
            category=cls.category, name='Loose bananas', sku='BANANA-TEST',
            unit=Product.Unit.KG, retail_price=Decimal('100'),
            wholesale_price=Decimal('85'), wholesale_min_qty=2,
            tax_rate=Decimal('0'), cost_price=Decimal('60'),
        )
        cls.no_price = Product.objects.create(
            category=cls.category, name='Pending item', sku='PENDING-TEST',
            unit=Product.Unit.EACH, retail_price=Decimal('0'),
            wholesale_price=Decimal('0'), cost_price=Decimal('0'),
        )
        BranchStock.objects.create(branch=cls.branch, product=cls.product, quantity=Decimal('12.000'))
        BranchStock.objects.create(branch=cls.other_branch, product=cls.product, quantity=Decimal('3.000'))
        BranchStock.objects.create(branch=cls.branch, product=cls.weighted, quantity=Decimal('10.000'))
        BranchStock.objects.create(branch=cls.branch, product=cls.no_price, quantity=Decimal('10.000'))
        User = get_user_model()
        cls.cashier = User.objects.create_user(username='sales_a', password='secure-example-pass')
        cls.manager = User.objects.create_user(username='manager_a', password='secure-example-pass')
        cls.other_cashier = User.objects.create_user(username='sales_b', password='secure-example-pass')
        cls.warehouse = User.objects.create_user(username='whse', password='secure-example-pass')
        cls.unapproved = User.objects.create_user(username='pending', password='secure-example-pass')
        cls.admin = User.objects.create_superuser(username='root_admin', email='root@test.example', password='secure-example-pass')
        for account, role, branch, approved in [
            (cls.cashier, 'CASHIER', cls.branch, True),
            (cls.manager, 'MANAGER', cls.branch, True),
            (cls.other_cashier, 'CASHIER', cls.other_branch, True),
            (cls.warehouse, 'WAREHOUSE', cls.branch, True),
            (cls.unapproved, 'CASHIER', cls.branch, False),
        ]:
            StaffProfile.objects.create(user=account, role=role, branch=branch, is_approved=approved)

    def login_and_cart(self, user=None, product=None, qty='2'):
        self.client.force_login(user or self.cashier)
        self.client.get(reverse('pos:index'))
        product = product or self.product
        response = self.client.post(reverse('pos:add_item'), {'product_id': product.pk, 'quantity': qty})
        self.assertEqual(response.status_code, 302)
        return self.client.session['pos_checkout_token']

    def test_retail_cash_checkout_reduces_stock_once_and_prints_receipt(self):
        token = self.login_and_cart()
        data = {'checkout_token': token, 'payment_method': 'CASH', 'cash_tendered': '300.00'}
        response = self.client.post(reverse('pos:checkout'), data)
        self.assertEqual(response.status_code, 302)
        sale = Sale.objects.get()
        self.assertEqual(sale.subtotal, Decimal('240.00'))
        self.assertEqual(sale.change_due, Decimal('60.00'))
        self.assertEqual(sale.items.count(), 1)
        self.assertEqual(sale.items.first().unit_price, Decimal('120.00'))
        self.assertEqual(sale.payment_status, Sale.PaymentStatus.CASH_RECEIVED)
        self.assertIn('SM-', sale.receipt_number)
        stock = BranchStock.objects.get(branch=self.branch, product=self.product)
        self.assertEqual(stock.quantity, Decimal('10.000'))
        receipt = self.client.get(reverse('pos:receipt', args=[sale.pk]))
        self.assertContains(receipt, 'Rice 1kg')
        # Repeated network request returns original sale without charging stock again.
        repeated = self.client.post(reverse('pos:checkout'), data)
        self.assertEqual(repeated.status_code, 302)
        self.assertEqual(Sale.objects.count(), 1)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, Decimal('10.000'))

    def test_checkout_fails_when_cash_is_insufficient(self):
        token = self.login_and_cart()
        response = self.client.post(reverse('pos:checkout'), {
            'checkout_token': token, 'payment_method': 'CASH', 'cash_tendered': '20.00',
        })
        self.assertRedirects(response, reverse('pos:index'))
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(BranchStock.objects.get(branch=self.branch, product=self.product).quantity, Decimal('12.000'))

    def test_checkout_rechecks_stock_and_rolls_back(self):
        token = self.login_and_cart(qty='2')
        BranchStock.objects.filter(branch=self.branch, product=self.product).update(quantity=Decimal('1.000'))
        response = self.client.post(reverse('pos:checkout'), {
            'checkout_token': token, 'payment_method': 'CASH', 'cash_tendered': '1000.00',
        })
        self.assertRedirects(response, reverse('pos:index'))
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(BranchStock.objects.get(branch=self.branch, product=self.product).quantity, Decimal('1.000'))

    def test_wholesale_minimum_applies_and_bulk_price_used(self):
        token = self.login_and_cart(qty='4')
        self.client.post(reverse('pos:set_mode'), {'sale_type': 'WHOLESALE'})
        failed = self.client.post(reverse('pos:checkout'), {
            'checkout_token': token, 'payment_method': 'CASH', 'cash_tendered': '2000',
        })
        self.assertEqual(failed.status_code, 302)
        self.assertEqual(Sale.objects.count(), 0)
        self.client.post(reverse('pos:update_item'), {'product_id': self.product.pk, 'quantity': '5'})
        done = self.client.post(reverse('pos:checkout'), {
            'checkout_token': token, 'payment_method': 'CASH', 'cash_tendered': '500',
        })
        self.assertEqual(done.status_code, 302)
        self.assertEqual(Sale.objects.get().subtotal, Decimal('500.00'))

    def test_pending_price_cannot_be_sold(self):
        self.login_and_cart(product=self.no_price, qty='1')
        self.assertEqual(self.client.session['pos_cart'], {})

    def test_fractional_weight_and_whole_item_validation(self):
        self.assertEqual(quantity_from_text('1.250', self.weighted), Decimal('1.250'))
        for invalid in ('-1', 'NaN', 'Infinity', '1.0001', '0'):
            with self.assertRaises(ValidationError):
                quantity_from_text(invalid, self.weighted)
        with self.assertRaises(ValidationError):
            quantity_from_text('1.5', self.product)

    def test_mpesa_manual_reference_pending_and_manager_confirmation(self):
        token = self.login_and_cart()
        self.client.post(reverse('pos:checkout'), {
            'checkout_token': token, 'payment_method': 'MPESA', 'payment_reference': 'SAMPLE-TRX-1234',
        })
        sale = Sale.objects.get()
        self.assertEqual(sale.payment_status, Sale.PaymentStatus.UNVERIFIED)
        self.client.post(reverse('pos:verify_payment', args=[sale.pk]), {'confirmed': 'yes'})
        sale.refresh_from_db()
        self.assertEqual(sale.payment_status, Sale.PaymentStatus.UNVERIFIED)
        self.client.force_login(self.manager)
        response = self.client.post(reverse('pos:verify_payment', args=[sale.pk]), {'confirmed': 'yes'})
        self.assertEqual(response.status_code, 302)
        sale.refresh_from_db()
        self.assertEqual(sale.payment_status, Sale.PaymentStatus.VERIFIED)
        self.assertEqual(sale.verified_by, self.manager)

    def test_cashier_sees_only_their_receipts_manager_sees_branch(self):
        self.login_and_cart()
        token = self.client.session['pos_checkout_token']
        self.client.post(reverse('pos:checkout'), {
            'checkout_token': token, 'payment_method': 'CASH', 'cash_tendered': '250',
        })
        sale = Sale.objects.get()
        self.client.force_login(self.other_cashier)
        self.assertEqual(self.client.get(reverse('pos:receipt', args=[sale.pk])).status_code, 404)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse('pos:receipt', args=[sale.pk])).status_code, 200)

    def test_warehouse_and_unapproved_cannot_open_pos(self):
        for account in (self.warehouse, self.unapproved):
            self.client.force_login(account)
            self.assertEqual(self.client.get(reverse('pos:index')).status_code, 403)

    def test_csrf_required_for_checkout(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.cashier)
        response = client.post(reverse('pos:checkout'), {'payment_method': 'CASH'})
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_select_training_branch(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('pos:index') + '?branch=' + str(self.other_branch.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session['pos_branch_id'], self.other_branch.pk)
