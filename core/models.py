from django.conf import settings
from django.db import models


class Branch(models.Model):
    name = models.CharField(max_length=140)
    code = models.CharField(max_length=24, unique=True)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=35, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        verbose_name_plural = "Branches"

    def __str__(self):
        return f"{self.name} ({self.code})"


class StaffProfile(models.Model):
    class Role(models.TextChoices):
        MANAGER = "MANAGER", "Branch Manager"
        CASHIER = "CASHIER", "Cashier"
        WAREHOUSE = "WAREHOUSE", "Warehouse / Inventory"
        STAFF = "STAFF", "General Staff"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="store_profile",
    )
    role = models.CharField(max_length=16, choices=Role.choices)
    branch = models.ForeignKey(
        Branch,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="employees",
    )
    employee_id = models.CharField(
        max_length=35, blank=True, null=True, unique=True,
        help_text="Optional company-issued employee identifier.",
    )
    is_approved = models.BooleanField(
        default=False,
        help_text="An administrator must approve access before login.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("user__username",)

    def __str__(self):
        return f"{self.user.username} — {self.get_role_display()}"
