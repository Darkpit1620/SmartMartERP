from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse
from core.models import Branch, StaffProfile
from inventory.models import Category, Product, BranchStock, StockMovement
from .models import StockTransfer, StockTransferLine, TransferReceipt
from .services import create_transfer, add_transfer_line, dispatch_transfer, receive_transfer


class TransferTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.main = Branch.objects.create(name='Transfer Main', code='TRMAIN')
        cls.west = Branch.objects.create(name='Transfer West', code='TRWEST')
        cls.other = Branch.objects.create(name='Transfer Other', code='TROTHER')
        category = Category.objects.create(name='Transfer Test Goods')
        cls.rice = Product.objects.create(category=category, name='Transfer Rice', sku='TX-RICE-1', unit='EACH',
                                         cost_price=50, retail_price=100, wholesale_price=85)
        cls.beans = Product.objects.create(category=category, name='Transfer Beans kg', sku='TX-BEAN-1', unit='KG',
                                          cost_price=50, retail_price=100, wholesale_price=85)
        BranchStock.objects.create(branch=cls.main, product=cls.rice, quantity=Decimal('30.000'))
        BranchStock.objects.create(branch=cls.main, product=cls.beans, quantity=Decimal('9.500'))
        BranchStock.objects.create(branch=cls.west, product=cls.rice, quantity=Decimal('4.000'))
        User = get_user_model()
        cls.admin = User.objects.create_superuser('transfer_admin', 'tadmin@example.test', 'test-pass-123')
        cls.manager = User.objects.create_user('transfer_manager', password='test-pass-123')
        cls.sender = User.objects.create_user('transfer_sender', password='test-pass-123')
        cls.receiver = User.objects.create_user('transfer_receiver', password='test-pass-123')
        cls.stranger = User.objects.create_user('transfer_stranger', password='test-pass-123')
        cls.cashier = User.objects.create_user('transfer_cashier', password='test-pass-123')
        cls.pending = User.objects.create_user('transfer_pending', password='test-pass-123')
        for user, role, branch, approved in [
            (cls.manager, 'MANAGER', cls.main, True),
            (cls.sender, 'WAREHOUSE', cls.main, True),
            (cls.receiver, 'WAREHOUSE', cls.west, True),
            (cls.stranger, 'MANAGER', cls.other, True),
            (cls.cashier, 'CASHIER', cls.main, True),
            (cls.pending, 'MANAGER', cls.main, False),
        ]:
            StaffProfile.objects.create(user=user, role=role, branch=branch, is_approved=approved)

    def make_transfer(self, qty='10', product=None):
        transfer = create_transfer(source=self.main, destination=self.west, actor=self.manager)
        line = add_transfer_line(transfer=transfer, product=product or self.rice, quantity=qty)
        return transfer, line

    def stock(self, branch, product=None):
        return BranchStock.objects.get(branch=branch, product=product or self.rice).quantity

    def test_no_stock_change_until_dispatch(self):
        transfer, line = self.make_transfer()
        self.assertEqual(transfer.status, 'DRAFT')
        self.assertEqual(self.stock(self.main), Decimal('30.000'))
        self.assertEqual(self.stock(self.west), Decimal('4.000'))
        self.assertEqual(StockMovement.objects.count(), 0)
        self.assertTrue(transfer.reference.startswith('SMT-'))

    def test_dispatch_then_partial_then_full_receiving_with_audit(self):
        transfer, line = self.make_transfer()
        dispatch_transfer(transfer=transfer, actor=self.sender)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, 'IN_TRANSIT')
        self.assertEqual(self.stock(self.main), Decimal('20.000'))
        self.assertEqual(self.stock(self.west), Decimal('4.000'))
        self.assertEqual(StockMovement.objects.filter(kind='TRANSFER_OUT').count(), 1)
        receipt = receive_transfer(transfer=transfer, actor=self.receiver,
                                   receipt_reference='grn-001', quantities={line.pk: '4'})
        transfer.refresh_from_db()
        self.assertEqual(receipt.reference, 'GRN-001')
        self.assertEqual(transfer.status, 'PARTIAL')
        self.assertEqual(self.stock(self.west), Decimal('8.000'))
        self.assertEqual(StockTransferLine.objects.get(pk=line.pk).remaining, Decimal('6.000'))
        receive_transfer(transfer=transfer, actor=self.receiver, receipt_reference='GRN-002', quantities={str(line.pk): '6'})
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, 'RECEIVED')
        self.assertEqual(self.stock(self.main), Decimal('20.000'))
        self.assertEqual(self.stock(self.west), Decimal('14.000'))
        self.assertEqual(StockMovement.objects.filter(kind='TRANSFER_IN').count(), 2)
        self.assertEqual(TransferReceipt.objects.count(), 2)

    def test_duplicate_dispatch_and_duplicate_receipt_deduct_only_once(self):
        transfer, line = self.make_transfer()
        dispatch_transfer(transfer=transfer, actor=self.sender)
        with self.assertRaises(ValidationError):
            dispatch_transfer(transfer=transfer, actor=self.sender)
        self.assertEqual(self.stock(self.main), Decimal('20.000'))
        receive_transfer(transfer=transfer, actor=self.receiver, receipt_reference='GRN-001', quantities={line.pk: '4'})
        with self.assertRaises(ValidationError):
            receive_transfer(transfer=transfer, actor=self.receiver, receipt_reference='GRN-001', quantities={line.pk: '2'})
        self.assertEqual(self.stock(self.west), Decimal('8.000'))

    def test_insufficient_stock_rolls_back_all_dispatch_lines(self):
        transfer, line = self.make_transfer('10')
        add_transfer_line(transfer=transfer, product=self.beans, quantity='11')
        with self.assertRaises(ValidationError):
            dispatch_transfer(transfer=transfer, actor=self.sender)
        self.assertEqual(self.stock(self.main), Decimal('30.000'))
        self.assertEqual(self.stock(self.main, self.beans), Decimal('9.500'))
        self.assertFalse(StockMovement.objects.exists())
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, 'DRAFT')

    def test_invalid_receipts_and_pack_fractions_are_blocked(self):
        transfer, line = self.make_transfer()
        dispatch_transfer(transfer=transfer, actor=self.sender)
        for invalid in ('11', '1.5', '-1', 'NaN', 'Infinity', '0.0001'):
            with self.assertRaises(ValidationError):
                receive_transfer(transfer=transfer, actor=self.receiver,
                                 receipt_reference='GRN-INVALID', quantities={line.pk: invalid})
        self.assertEqual(self.stock(self.west), Decimal('4.000'))
        self.assertFalse(TransferReceipt.objects.exists())

    def test_invalid_origin_and_duplicated_product(self):
        with self.assertRaises(ValidationError):
            create_transfer(source=self.main, destination=self.main, actor=self.manager)
        transfer, line = self.make_transfer()
        with self.assertRaises(ValidationError):
            add_transfer_line(transfer=transfer, product=self.rice, quantity='1')
        with self.assertRaises(ValidationError):
            add_transfer_line(transfer=transfer, product=self.rice, quantity='0.5')

    def test_branch_access_and_permissions(self):
        transfer, line = self.make_transfer()
        for account in (self.cashier, self.pending):
            self.client.force_login(account)
            self.assertEqual(self.client.get(reverse('transfers:list')).status_code, 403)
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(reverse('transfers:detail', args=[transfer.pk])).status_code, 404)
        self.client.force_login(self.receiver)
        self.assertEqual(self.client.get(reverse('transfers:new')).status_code, 403)
        self.assertEqual(self.client.post(reverse('transfers:dispatch', args=[transfer.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('transfers:detail', args=[transfer.pk])).status_code, 200)
        self.client.force_login(self.sender)
        self.assertEqual(self.client.post(reverse('transfers:receive', args=[transfer.pk]), {'receipt_reference':'GRN-001'}).status_code, 404)
        self.assertEqual(self.client.get(reverse('transfers:new')).status_code, 403)

    def test_end_to_end_forms_and_destination_receiving(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse('transfers:new'), {'destination_branch': self.west.pk, 'notes': 'Shelves need restock'})
        self.assertEqual(response.status_code, 302)
        transfer = StockTransfer.objects.get()
        self.assertEqual(transfer.source_branch, self.main)
        self.client.post(reverse('transfers:add', args=[transfer.pk]), {'product_code': self.rice.sku, 'quantity':'6'})
        line = transfer.lines.get()
        self.client.force_login(self.sender)
        resp = self.client.post(reverse('transfers:dispatch', args=[transfer.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.stock(self.main), Decimal('24.000'))
        self.client.force_login(self.receiver)
        resp = self.client.post(reverse('transfers:receive', args=[transfer.pk]), {'receipt_reference':'GRN-103', f'qty_{line.pk}':'6'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.stock(self.west), Decimal('10.000'))

    def test_csrf_required_to_receive(self):
        transfer, line = self.make_transfer()
        dispatch_transfer(transfer=transfer, actor=self.sender)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.receiver)
        response = client.post(reverse('transfers:receive', args=[transfer.pk]), {'receipt_reference': 'GRN-554', f'qty_{line.pk}':'1'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.stock(self.west), Decimal('4.000'))

    def test_weighted_products_allow_three_decimal_places(self):
        transfer, line = self.make_transfer('1.250', product=self.beans)
        dispatch_transfer(transfer=transfer, actor=self.sender)
        receive_transfer(transfer=transfer, actor=self.receiver, receipt_reference='GRN-WEIGHT', quantities={line.pk:'1.250'})
        self.assertEqual(self.stock(self.west, self.beans), Decimal('1.250'))
