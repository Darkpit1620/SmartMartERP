"""Atomic, audited branch transfer operations.

No stock changes in draft. Dispatch moves stock OUT of origin; confirmed
receipts move physically received quantities INTO destination. Both actions
log inventory StockMovement entries. Never add stock at both ends at once.
"""
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from inventory.models import Product, StockMovement
from inventory.services import record_stock_movement
from .models import StockTransfer, StockTransferLine, TransferReceipt, TransferReceiptLine


def validate_quantity(value, product, *, allow_zero=False):
    if isinstance(value, bool):
        raise ValidationError('Quantity must be a valid number.')
    try:
        n = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError('Quantity must be a valid number.')
    if not n.is_finite() or n > Decimal('999999999.999') or (n < 0 if allow_zero else n < Decimal('0.001')):
        raise ValidationError('Quantity must be positive and within supported limits.')
    if n.as_tuple().exponent < -3:
        raise ValidationError('Use at most three decimal places.')
    if product.unit not in ('KG', 'LITRE') and n != n.to_integral_value():
        raise ValidationError('Packaged products must use whole-unit quantities.')
    return n


@transaction.atomic
def create_transfer(*, source, destination, actor, notes=''):
    if source.pk == destination.pk:
        raise ValidationError('Select two different branches.')
    if not source.active or not destination.active:
        raise ValidationError('Both branches must be active.')
    transfer = StockTransfer.objects.create(source_branch=source, destination_branch=destination,
                                            created_by=actor, notes=(notes or '').strip())
    transfer.reference = f'SMT-{timezone.localdate():%Y}-{transfer.pk:06d}'
    transfer.save(update_fields=['reference'])
    return transfer


@transaction.atomic
def add_transfer_line(*, transfer, product, quantity):
    locked = StockTransfer.objects.select_for_update().get(pk=transfer.pk)
    if locked.status != StockTransfer.Status.DRAFT:
        raise ValidationError('Only draft transfers can be edited.')
    if not product.is_active:
        raise ValidationError('Choose an active product.')
    qty = validate_quantity(quantity, product)
    if StockTransferLine.objects.filter(transfer=locked, product=product).exists():
        raise ValidationError('This product is already in the transfer. Remove it first to change the quantity.')
    return StockTransferLine.objects.create(transfer=locked, product=product, quantity=qty)


@transaction.atomic
def remove_transfer_line(*, transfer, line_id):
    locked = StockTransfer.objects.select_for_update().get(pk=transfer.pk)
    if locked.status != StockTransfer.Status.DRAFT:
        raise ValidationError('Only draft transfer lines can be removed.')
    deleted, _ = StockTransferLine.objects.filter(transfer=locked, pk=line_id).delete()
    if not deleted:
        raise ValidationError('Transfer line not found.')


@transaction.atomic
def dispatch_transfer(*, transfer, actor):
    locked = StockTransfer.objects.select_for_update().get(pk=transfer.pk)
    if locked.status != StockTransfer.Status.DRAFT:
        raise ValidationError('This transfer has already been dispatched or closed.')
    if not locked.source_branch.active or not locked.destination_branch.active:
        raise ValidationError('Both branches must be active.')
    lines = list(locked.lines.select_related('product').order_by('pk'))
    if not lines:
        raise ValidationError('Add at least one product before dispatching.')
    for line in lines:
        if not line.product.is_active:
            raise ValidationError(f'Product {line.product.sku} is inactive.')
        record_stock_movement(branch=locked.source_branch, product=line.product, actor=actor,
                              kind=StockMovement.Kind.TRANSFER_OUT, quantity=line.quantity,
                              reference=f'{locked.reference}/DISPATCH',
                              note=f'Dispatched to {locked.destination_branch.code}. Goods in transit.')
    locked.status = StockTransfer.Status.IN_TRANSIT
    locked.dispatched_at = timezone.now()
    locked.dispatched_by = actor
    locked.save(update_fields=['status', 'dispatched_at', 'dispatched_by'])
    return locked


@transaction.atomic
def receive_transfer(*, transfer, actor, receipt_reference, quantities):
    locked = StockTransfer.objects.select_for_update().get(pk=transfer.pk)
    if locked.status not in (StockTransfer.Status.IN_TRANSIT, StockTransfer.Status.PARTIAL):
        raise ValidationError('Only dispatched, not-fully-received transfers can be received.')
    reference = (receipt_reference or '').strip().upper()
    if len(reference) < 3 or len(reference) > 100:
        raise ValidationError('Enter a receipt reference of 3 to 100 characters.')
    if TransferReceipt.objects.filter(transfer=locked, reference=reference).exists():
        raise ValidationError('This receiving reference has already been recorded.')
    if not locked.destination_branch.active:
        raise ValidationError('The destination branch is inactive.')
    lines = list(locked.lines.select_related('product').select_for_update().order_by('pk'))
    pending = []
    for line in lines:
        value = quantities.get(line.pk, quantities.get(str(line.pk), '0'))
        qty = validate_quantity(value, line.product, allow_zero=True)
        if qty > line.remaining:
            raise ValidationError(f'You cannot receive more than the outstanding quantity of {line.product.sku}.')
        if qty > 0:
            pending.append((line, qty))
    if not pending:
        raise ValidationError('Enter at least one physically received quantity.')
    # If stock ledger writes fail, all receipts, item totals and balances roll back.
    receipt = TransferReceipt.objects.create(transfer=locked, reference=reference, received_by=actor)
    for line, qty in pending:
        record_stock_movement(branch=locked.destination_branch, product=line.product, actor=actor,
                              kind=StockMovement.Kind.TRANSFER_IN, quantity=qty,
                              reference=f'{locked.reference}/{reference}',
                              note=f'Received from {locked.source_branch.code}.')
        StockTransferLine.objects.filter(pk=line.pk).update(received_qty=line.received_qty + qty)
        TransferReceiptLine.objects.create(receipt=receipt, transfer_line=line, quantity=qty)
        line.received_qty += qty
    if all(line.remaining == 0 for line in lines):
        locked.status = StockTransfer.Status.RECEIVED
    else:
        locked.status = StockTransfer.Status.PARTIAL
    locked.save(update_fields=['status'])
    return receipt
