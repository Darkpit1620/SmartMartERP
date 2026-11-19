"""Central stock-change API. Never directly edit BranchStock.quantity in application views."""
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from .models import BranchStock, StockMovement


@transaction.atomic
def record_stock_movement(*, branch, product, actor, kind, quantity, reference, note=""):
    if kind not in StockMovement.Kind.values:
        raise ValidationError("Invalid stock movement type.")
    if isinstance(quantity, bool):
        raise ValidationError("Enter a valid positive quantity.")
    try:
        quantity = Decimal(str(quantity))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("Enter a valid positive quantity.")
    if not quantity.is_finite() or quantity < Decimal("0.001") or quantity > Decimal("999999999.999"):
        raise ValidationError("Enter a valid positive quantity.")
    if quantity.as_tuple().exponent < -3:
        raise ValidationError("Use at most three decimal places.")
    if product.unit not in ("KG", "LITRE") and quantity != quantity.to_integral_value():
        raise ValidationError("Packaged items must be received in whole units.")
    reference = (reference or "").strip()
    if not reference:
        raise ValidationError("A reference is required for the stock audit trail.")
    if not actor or not actor.is_authenticated:
        raise ValidationError("A signed-in employee must record the movement.")

    stock, _ = BranchStock.objects.get_or_create(branch=branch, product=product, defaults={"quantity": 0})
    qs = BranchStock.objects.filter(pk=stock.pk)
    if kind in (StockMovement.Kind.CORRECTION_OUT, StockMovement.Kind.TRANSFER_OUT):
        updated = qs.filter(quantity__gte=quantity).update(quantity=F("quantity") - quantity)
        if not updated:
            raise ValidationError("Not enough stock in this branch to remove that quantity.")
    else:
        qs.update(quantity=F("quantity") + quantity)

    stock.refresh_from_db()
    movement = StockMovement.objects.create(
        branch=branch, product=product, kind=kind, quantity=quantity,
        balance_after=stock.quantity, reference=reference, note=(note or "").strip(),
        recorded_by=actor,
    )
    return movement
