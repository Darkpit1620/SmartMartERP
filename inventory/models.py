from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

from core.models import Branch


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    class Unit(models.TextChoices):
        EACH = "EACH", "Piece / Each"
        KG = "KG", "Kilogram"
        LITRE = "LITRE", "Litre"
        PACK = "PACK", "Pack"
        CARTON = "CARTON", "Carton"
        BAG = "BAG", "Bag / Sack"

    category = models.ForeignKey(Category, related_name="products", on_delete=models.PROTECT)
    name = models.CharField(max_length=170)
    sku = models.CharField(max_length=48, unique=True, help_text="Unique internal stock code")
    barcode = models.CharField(
        max_length=64, unique=True, null=True, blank=True,
        help_text="Scan the product barcode or type its exact digits. Leave empty if unavailable.",
    )
    unit = models.CharField(max_length=10, choices=Unit.choices, default=Unit.EACH)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    retail_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    wholesale_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    wholesale_min_qty = models.PositiveIntegerField(default=6, validators=[MinValueValidator(1)])
    reorder_level = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("5.000"), validators=[MinValueValidator(Decimal("0.000"))])
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "sku")
        indexes = [models.Index(fields=["name"]), models.Index(fields=["category", "is_active"])]

    def save(self, *args, **kwargs):
        self.sku = (self.sku or "").strip().upper()
        self.barcode = (self.barcode or "").strip() or None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.sku})"


class BranchStock(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="stock_records")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="branch_stock")
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"), validators=[MinValueValidator(Decimal("0.000"))])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("branch__name", "product__name")
        constraints = [models.UniqueConstraint(fields=["branch", "product"], name="inventory_one_stock_per_branch_product")]
        verbose_name_plural = "Branch stock balances"

    def __str__(self):
        return f"{self.branch.code}: {self.product.sku} = {self.quantity}"


class StockMovement(models.Model):
    class Kind(models.TextChoices):
        RECEIPT = "RECEIPT", "Stock received"
        CORRECTION_IN = "CORRECTION_IN", "Positive stock correction"
        CORRECTION_OUT = "CORRECTION_OUT", "Negative stock correction"
        TRANSFER_OUT = "TRANSFER_OUT", "Dispatched branch transfer"
        TRANSFER_IN = "TRANSFER_IN", "Received branch transfer"

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="stock_movements")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock_movements")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))])
    balance_after = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal("0.000"))])
    reference = models.CharField(max_length=120, help_text="Delivery note, stock count or adjustment reference")
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_stock_movements")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [models.Index(fields=["branch", "created_at"])]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.product.sku} × {self.quantity}"
