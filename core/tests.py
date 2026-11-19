from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from .models import Branch, StaffProfile


class SmartMartPortalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(name="Central Store", code="CENTRAL")
        User = get_user_model()
        cls.admin = User.objects.create_superuser("owner", "owner@example.test", "TestPassword123!")
        cls.cashier = User.objects.create_user("cashier", password="TestPassword123!")
        cls.cashier_profile = StaffProfile.objects.create(
            user=cls.cashier, branch=cls.branch, role=StaffProfile.Role.CASHIER,
            is_approved=True,
        )
        cls.pending = User.objects.create_user("pending", password="TestPassword123!")
        StaffProfile.objects.create(
            user=cls.pending, branch=cls.branch, role=StaffProfile.Role.WAREHOUSE,
            is_approved=False,
        )

    def test_homepage_is_public(self):
        self.assertEqual(self.client.get(reverse("core:home")).status_code, 200)

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_approved_cashier_goes_to_cashier_portal(self):
        self.client.force_login(self.cashier)
        response = self.client.get(reverse("core:dashboard"))
        self.assertRedirects(response, reverse("core:cashier_portal"))

    def test_cashier_cannot_open_warehouse(self):
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse("core:warehouse_portal")).status_code, 403)

    def test_admin_can_open_admin_portal(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("core:admin_portal")).status_code, 200)

    def test_admin_cannot_be_impersonated_by_cashier(self):
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse("core:admin_portal")).status_code, 403)

    def test_pending_account_cannot_log_in(self):
        response = self.client.post(reverse("core:login"), {
            "username": "pending", "password": "TestPassword123!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_valid_cashier_can_log_in(self):
        response = self.client.post(reverse("core:login"), {
            "username": "cashier", "password": "TestPassword123!",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:dashboard"))
