"""Transactional purchase receiving and wholesale fulfillment.

Stock receipts use the Stage 3 audited inventory service. Wholesale checkouts
reuse Stage 4 POS atomic stock decrement and official receipt generation.
"""
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from inventory.models import Product
from inventory.services import record_stock_movement
from inventory.models import StockMovement
from pos.models import Sale
from pos.services import complete_sale, line_for, money, quantity_from_text
from .models import (GoodsReceipt, GoodsReceiptLine, PurchaseOrder,
                     PurchaseOrderLine, WholesaleOrder, WholesaleOrderLine)


def checked_qty(raw, product):
    return quantity_from_text(raw, product)


@transaction.atomic
def submit_purchase_order(order):
    order = PurchaseOrder.objects.select_for_update().get(pk=order.pk)
    if order.status != PurchaseOrder.Status.DRAFT:
        raise ValidationError('Only draft purchase orders can be placed.')
    if not order.lines.exists():
        raise ValidationError('Add at least one product before placing the purchase order.')
    PurchaseOrder.objects.filter(pk=order.pk, status=PurchaseOrder.Status.DRAFT).update(
        status=PurchaseOrder.Status.ORDERED, ordered_at=timezone.now())
    order.refresh_from_db()
    return order


@transaction.atomic
def receive_delivery(*, order, actor, delivery_note, quantities):
    """Receive a subset of PO lines once; duplicate delivery references are rejected.

    quantities: {PurchaseOrderLine.pk: decimal/text qty}; zero/empty skips a line.
    All validation and stock mutations happen inside the same transaction.
    """
    order = PurchaseOrder.objects.select_for_update().get(pk=order.pk)
    if order.status not in (PurchaseOrder.Status.ORDERED, PurchaseOrder.Status.PARTIAL):
        raise ValidationError('This purchase order is not open for deliveries.')
    delivery_note = (delivery_note or '').strip()
    if not (3 <= len(delivery_note) <= 100):
        raise ValidationError('Enter a delivery note reference (3–100 characters).')
    if GoodsReceipt.objects.filter(order=order, delivery_note=delivery_note).exists():
        raise ValidationError('This delivery reference has already been received for the purchase order.')

    lines = list(order.lines.select_for_update().select_related('product'))
    accepted = []
    for line in lines:
        raw = quantities.get(line.pk, '0')
        if not str(raw).strip() or str(raw).strip() == '0':
            continue
        qty = checked_qty(raw, line.product)
        if qty > line.remaining:
            raise ValidationError(f'{line.product.sku}: only {line.remaining} remain on this order.')
        accepted.append((line, qty))
    if not accepted:
        raise ValidationError('Enter a positive received quantity for at least one product.')

    receipt = GoodsReceipt.objects.create(order=order, delivery_note=delivery_note, recorded_by=actor)
    for line, qty in accepted:
        moved = record_stock_movement(
            branch=order.branch, product=line.product, actor=actor,
            kind=StockMovement.Kind.RECEIPT, quantity=qty,
            reference=f'{order.reference} / GRN-{receipt.pk}',
            note=f'Supplier {order.supplier.name}; delivery note {delivery_note}; PO line {line.pk}',
        )
        PurchaseOrderLine.objects.filter(pk=line.pk).update(received_qty=F('received_qty') + qty)
        GoodsReceiptLine.objects.create(receipt=receipt, purchase_line=line, quantity=qty, stock_movement=moved)

    order.status = (PurchaseOrder.Status.RECEIVED if not PurchaseOrderLine.objects.filter(
        order=order, received_qty__lt=F('quantity')).exists() else PurchaseOrder.Status.PARTIAL)
    order.save(update_fields=['status'])
    return receipt


@transaction.atomic
def prepare_wholesale_order(order):
    order = WholesaleOrder.objects.select_for_update().get(pk=order.pk)
    if order.status != WholesaleOrder.Status.DRAFT:
        raise ValidationError('Only draft orders can be prepared.')
    if not order.lines.exists():
        raise ValidationError('Add at least one product first.')
    order.status = WholesaleOrder.Status.READY
    order.save(update_fields=['status'])
    return order


@transaction.atomic
def fulfill_wholesale_order(*, order, actor, method, tendered='', reference=''):
    """Complete the wholesale order in the existing POS ledger, exactly once."""
    order = WholesaleOrder.objects.select_for_update().get(pk=order.pk)
    if order.status == WholesaleOrder.Status.FULFILLED and order.sale_id:
        return order
    if order.status != WholesaleOrder.Status.READY:
        raise ValidationError('The order must be ready before checkout.')
    if not order.customer.is_active or not order.branch.active:
        raise ValidationError('Customer or branch is inactive.')
    lines = list(order.lines.select_related('product'))
    if not lines:
        raise ValidationError('No products in this order.')
    if len(lines) > 120:
        raise ValidationError('A wholesale checkout supports up to 120 different products.')
    cart = {str(line.product_id): str(line.quantity) for line in lines}
    sale = complete_sale(
        branch=order.branch, cashier=actor, cart=cart, mode=Sale.SaleType.WHOLESALE,
        method=method, tendered=tendered, reference=reference,
        token=order.checkout_token,
    )
    order.sale = sale
    order.status = WholesaleOrder.Status.FULFILLED
    order.fulfilled_at = timezone.now()
    order.save(update_fields=['sale', 'status', 'fulfilled_at'])
    return order
