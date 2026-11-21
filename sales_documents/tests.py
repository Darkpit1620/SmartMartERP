from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from core.models import Branch, StaffProfile
from inventory.models import Category, Product, BranchStock
from pos.models import Sale, SaleItem
from .models import BranchPrintBrand, SaleCustomerDetails, CustomerDetailsEdit, invoice_number


class SalesDocumentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(name='Documents North', code='DO-N', active=True)
        cls.other_branch = Branch.objects.create(name='Documents South', code='DO-S', active=True)
        category = Category.objects.create(name='Documents Test Grocery')
        cls.product = Product.objects.create(category=category, name='Flour pack', sku='DOC-FLOUR',
            unit=Product.Unit.EACH, retail_price=Decimal('100.00'),
            wholesale_price=Decimal('90.00'), cost_price=Decimal('65.00'), tax_rate=0)
        BranchStock.objects.create(branch=cls.branch, product=cls.product, quantity=Decimal('5.000'))
        User = get_user_model()
        cls.admin = User.objects.create_superuser('doc_admin', 'doc_admin@example.test', 'test-password-223')
        cls.cashier = User.objects.create_user('doc_cashier', password='test-password-223')
        cls.other_cashier = User.objects.create_user('doc_other_cashier', password='test-password-223')
        cls.manager = User.objects.create_user('doc_manager', password='test-password-223')
        cls.other_manager = User.objects.create_user('doc_other_manager', password='test-password-223')
        cls.warehouse = User.objects.create_user('doc_warehouse', password='test-password-223')
        cls.pending = User.objects.create_user('doc_pending', password='test-password-223')
        for user, branch, role, approved in [
            (cls.cashier, cls.branch, StaffProfile.Role.CASHIER, True),
            (cls.other_cashier, cls.other_branch, StaffProfile.Role.CASHIER, True),
            (cls.manager, cls.branch, StaffProfile.Role.MANAGER, True),
            (cls.other_manager, cls.other_branch, StaffProfile.Role.MANAGER, True),
            (cls.warehouse, cls.branch, StaffProfile.Role.WAREHOUSE, True),
            (cls.pending, cls.branch, StaffProfile.Role.CASHIER, False),
        ]:
            StaffProfile.objects.create(user=user, branch=branch, role=role, is_approved=approved)
        cls.sale = Sale.objects.create(
            branch=cls.branch, cashier=cls.cashier, sale_type=Sale.SaleType.RETAIL,
            payment_method=Sale.PaymentMethod.CASH, payment_status=Sale.PaymentStatus.CASH_RECEIVED,
            subtotal=Decimal('200.00'), included_tax=Decimal('0.00'),
            tendered_amount=Decimal('250.00'), change_due=Decimal('50.00'),
            checkout_token='doc-sales-token-a', receipt_number='SM-DOC-0001',
        )
        cls.item = SaleItem.objects.create(sale=cls.sale, product=cls.product, sku='DOC-FLOUR',
            description='Flour pack', unit='EACH', quantity=Decimal('2.000'),
            unit_price=Decimal('100.00'), tax_rate=0, line_total=Decimal('200.00'), included_tax=0)
        cls.other_sale = Sale.objects.create(
            branch=cls.other_branch, cashier=cls.other_cashier, sale_type=Sale.SaleType.RETAIL,
            payment_method=Sale.PaymentMethod.MPESA, payment_status=Sale.PaymentStatus.UNVERIFIED,
            payment_reference='DEMO-MPESA-REF', subtotal=Decimal('100.00'),
            checkout_token='doc-sales-token-b', receipt_number='SM-DOC-0002',
        )
        SaleItem.objects.create(sale=cls.other_sale, product=cls.product, sku='DOC-FLOUR',
            description='Flour pack', unit='EACH', quantity=1, unit_price=100,
            tax_rate=0, line_total=100, included_tax=0)

    def test_invoice_number_deterministic_unique(self):
        self.assertEqual(invoice_number(self.sale), 'SMI-%010d' % self.sale.pk)
        self.assertNotEqual(invoice_number(self.sale), invoice_number(self.other_sale))

    def test_anonymous_redirects(self):
        for name, args in [('sales_documents:home', []), ('sales_documents:thermal_receipt', [self.sale.pk]),
                           ('sales_documents:commercial_invoice', [self.sale.pk]),
                           ('sales_documents:customer_details', [self.sale.pk]),
                           ('sales_documents:brand_settings', [])]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 302)

    def test_cashier_prints_only_own_receipt_and_invoice(self):
        self.client.force_login(self.cashier)
        for name in ('sales_documents:thermal_receipt', 'sales_documents:commercial_invoice'):
            own = self.client.get(reverse(name, args=[self.sale.pk]))
            self.assertContains(own, 'Flour pack')
            self.assertContains(own, self.sale.receipt_number)
            self.assertEqual(self.client.get(reverse(name, args=[self.other_sale.pk])).status_code, 404)

    def test_manager_scoped_to_branch(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse('sales_documents:commercial_invoice', args=[self.sale.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('sales_documents:commercial_invoice', args=[self.other_sale.pk])).status_code, 404)
        home = self.client.get(reverse('sales_documents:home'))
        self.assertContains(home, self.sale.receipt_number)
        self.assertNotContains(home, self.other_sale.receipt_number)

    def test_admin_can_print_across_branches(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('sales_documents:commercial_invoice', args=[self.other_sale.pk])).status_code, 200)

    def test_unapproved_and_warehouse_denied(self):
        for user in (self.pending, self.warehouse):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('sales_documents:home')).status_code, 403)
            self.assertEqual(self.client.get(reverse('sales_documents:thermal_receipt', args=[self.sale.pk])).status_code, 403)
            self.assertEqual(self.client.get(reverse('sales_documents:brand_settings')).status_code, 403)

    def test_read_only_printing_preserves_sales_and_stock(self):
        self.client.force_login(self.admin)
        before_sales = Sale.objects.count()
        before_quantity = BranchStock.objects.get(branch=self.branch, product=self.product).quantity
        self.client.get(reverse('sales_documents:thermal_receipt', args=[self.sale.pk]))
        self.client.get(reverse('sales_documents:commercial_invoice', args=[self.sale.pk]))
        self.assertEqual(Sale.objects.count(), before_sales)
        self.assertEqual(BranchStock.objects.get(branch=self.branch, product=self.product).quantity, before_quantity)
        self.assertFalse(SaleCustomerDetails.objects.exists())

    def test_unverified_payment_warning_printed(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('sales_documents:commercial_invoice', args=[self.other_sale.pk]))
        self.assertContains(response, 'EXTERNAL PAYMENT REFERENCE NOT VERIFIED')
        self.assertContains(response, 'not a certified KRA eTIMS fiscal invoice')

    def test_customer_edit_persisted_and_audited(self):
        self.client.force_login(self.cashier)
        url = reverse('sales_documents:customer_details', args=[self.sale.pk])
        response = self.client.post(url, {'customer_name': 'Retail Buyer', 'customer_phone': '0712345678',
                                          'customer_email': 'buyer@example.test', 'customer_reference': 'BUY-001'})
        self.assertRedirects(response, reverse('sales_documents:commercial_invoice', args=[self.sale.pk]))
        details = SaleCustomerDetails.objects.get(sale=self.sale)
        self.assertEqual(details.customer_name, 'Retail Buyer')
        self.assertEqual(details.updated_by, self.cashier)
        self.assertEqual(CustomerDetailsEdit.objects.filter(details=details).count(), 1)
        self.assertContains(self.client.get(reverse('sales_documents:commercial_invoice', args=[self.sale.pk])), 'Retail Buyer')
        self.client.post(url, {'customer_name': 'Retail Buyer', 'customer_phone': '0712345678',
                               'customer_email': 'buyer@example.test', 'customer_reference': 'BUY-001'})
        self.assertEqual(CustomerDetailsEdit.objects.filter(details=details).count(), 1)

    def test_customer_requires_name_if_phone_provided(self):
        self.client.force_login(self.cashier)
        response = self.client.post(reverse('sales_documents:customer_details', args=[self.sale.pk]),
                                    {'customer_name': '', 'customer_phone': '0700000000'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter a customer name')
        self.assertFalse(SaleCustomerDetails.objects.exists())

    def test_customer_details_cannot_be_changed_cross_branch(self):
        self.client.force_login(self.cashier)
        response = self.client.post(reverse('sales_documents:customer_details', args=[self.other_sale.pk]),
                                    {'customer_name': 'Unauthorized'})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(SaleCustomerDetails.objects.exists())

    def test_customer_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.cashier)
        response = client.post(reverse('sales_documents:customer_details', args=[self.sale.pk]),
                               {'customer_name': 'Without CSRF'})
        self.assertEqual(response.status_code, 403)

    def test_brand_manager_can_edit_assigned_branch(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse('sales_documents:brand_settings'),
                                    {'branch': str(self.other_branch.pk), 'trade_name': 'North Supermarket',
                                     'footer': 'Visit us again'})
        self.assertEqual(response.status_code, 302)
        brand = BranchPrintBrand.objects.get(branch=self.branch)
        self.assertEqual(brand.trade_name, 'North Supermarket')
        self.assertFalse(BranchPrintBrand.objects.filter(branch=self.other_branch).exists())
        self.assertContains(self.client.get(reverse('sales_documents:thermal_receipt', args=[self.sale.pk])), 'North Supermarket')

    def test_admin_brand_scoped_to_selected_branch(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('sales_documents:brand_settings'),
            {'branch': str(self.other_branch.pk), 'trade_name': 'South Supermarket'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(BranchPrintBrand.objects.get(branch=self.other_branch).trade_name, 'South Supermarket')
        self.assertFalse(BranchPrintBrand.objects.filter(branch=self.branch).exists())

    def test_brand_manager_from_other_branch_cannot_edit_north(self):
        self.client.force_login(self.other_manager)
        self.client.post(reverse('sales_documents:brand_settings'),
            {'branch': str(self.branch.pk), 'trade_name': 'South Authorized'})
        self.assertFalse(BranchPrintBrand.objects.filter(branch=self.branch).exists())
        self.assertEqual(BranchPrintBrand.objects.get(branch=self.other_branch).trade_name, 'South Authorized')

    def test_print_escapes_untrusted_names(self):
        self.client.force_login(self.cashier)
        self.client.post(reverse('sales_documents:customer_details', args=[self.sale.pk]),
                         {'customer_name': '<script>alert(1)</script>'})
        response = self.client.get(reverse('sales_documents:commercial_invoice', args=[self.sale.pk]))
        self.assertNotContains(response, '<script>alert(1)</script>', html=False)
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;', html=False)
