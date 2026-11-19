from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from core.models import Branch, StaffProfile


PASSWORD = 'H5!fR9mK2zT7qV3'


class EmployeeActivationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser('sm10b_owner', 'owner10b@example.test', PASSWORD)
        cls.manager = User.objects.create_user('sm10b_manager', password=PASSWORD)
        cls.branch = Branch.objects.create(name='Stage10B East', code='10B-EAST', active=True)
        cls.other = Branch.objects.create(name='Stage10B West', code='10B-WEST', active=True)
        cls.manager_profile = StaffProfile.objects.create(user=cls.manager, role='MANAGER', branch=cls.branch, is_approved=True)

    def employee_data(self, **kwargs):
        data = {
            'username': 'sm10b_cashier',
            'first_name': 'Example', 'last_name': 'Cashier',
            'email': 'cashier10b@example.test',
            'role': 'CASHIER', 'branch': str(self.branch.pk),
            'password1': PASSWORD, 'password2': PASSWORD,
        }
        data.update(kwargs)
        return data

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(reverse('staff_activation:home'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url)

    def test_manager_and_cashier_forbidden(self):
        self.client.force_login(self.manager)
        for name in ('home', 'create_employee', 'create_branch'):
            self.assertEqual(self.client.get(reverse('staff_activation:' + name)).status_code, 403)
        self.assertEqual(self.client.post(reverse('staff_activation:review_employee', args=[self.manager_profile.pk]), {'action': 'suspend'}).status_code, 403)
        self.manager_profile.refresh_from_db()
        self.assertTrue(self.manager_profile.is_approved)

    def test_admin_creates_pending_employee_then_approves(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('staff_activation:create_employee'), self.employee_data())
        self.assertRedirects(response, reverse('staff_activation:home'))
        user = get_user_model().objects.get(username='sm10b_cashier')
        profile = user.store_profile
        self.assertEqual(profile.branch_id, self.branch.pk)
        self.assertEqual(profile.role, 'CASHIER')
        self.assertFalse(profile.is_approved)
        self.assertTrue(profile.employee_id.startswith('SME-'))
        self.assertTrue(user.check_password(PASSWORD))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

        self.client.logout()
        response = self.client.post(reverse('core:login'), {'username': user.username, 'password': PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

        self.client.force_login(self.admin)
        response = self.client.post(reverse('staff_activation:review_employee', args=[profile.pk]), {'action': 'approve'})
        self.assertRedirects(response, reverse('staff_activation:home'))
        profile.refresh_from_db()
        self.assertTrue(profile.is_approved)
        self.client.logout()
        response = self.client.post(reverse('core:login'), {'username': user.username, 'password': PASSWORD})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('core:dashboard'))
        self.assertEqual(self.client.get(reverse('core:cashier_portal')).status_code, 200)
        self.assertEqual(self.client.get(reverse('core:warehouse_portal')).status_code, 403)

    def test_admin_suspend_revokes_access(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('staff_activation:review_employee', args=[self.manager_profile.pk]), {'action': 'suspend'})
        self.assertRedirects(response, reverse('staff_activation:home'))
        self.manager_profile.refresh_from_db()
        self.assertFalse(self.manager_profile.is_approved)
        self.client.logout()
        response = self.client.post(reverse('core:login'), {'username': 'sm10b_manager', 'password': PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_mismatched_password_does_not_create_user(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('staff_activation:create_employee'), self.employee_data(password2='Different678!'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username='sm10b_cashier').exists())
        self.assertContains(response, 'passwords do not match', status_code=200)

    def test_duplicate_username_and_email_rejected(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('staff_activation:create_employee'), self.employee_data(username='sm10b_manager'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username='sm10b_cashier').exists())
        existing = get_user_model().objects.create_user('sm10b_existing', email='cashier10b@example.test', password=PASSWORD)
        response = self.client.post(reverse('staff_activation:create_employee'), self.employee_data())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username='sm10b_cashier').exists())

    def test_inactive_branch_does_not_allow_approval(self):
        self.manager_profile.is_approved = False
        self.manager_profile.save(update_fields=['is_approved'])
        self.branch.active = False
        self.branch.save(update_fields=['active'])
        self.client.force_login(self.admin)
        response = self.client.post(reverse('staff_activation:review_employee', args=[self.manager_profile.pk]), {'action': 'approve'})
        self.assertEqual(response.status_code, 302)
        self.manager_profile.refresh_from_db()
        self.assertFalse(self.manager_profile.is_approved)

    def test_branch_creation_and_directory_filter(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('staff_activation:create_branch'), {
            'name': 'Stage10B South', 'code': '10b-south', 'address': 'Training location', 'phone': '', 'active': 'on'
        })
        self.assertRedirects(response, reverse('staff_activation:home'))
        self.assertTrue(Branch.objects.filter(code='10B-SOUTH', active=True).exists())
        response = self.client.get(reverse('staff_activation:home'), {'branch': self.other.pk})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'sm10b_manager')

    def test_csrf_protects_approval(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        response = csrf_client.post(reverse('staff_activation:review_employee', args=[self.manager_profile.pk]), {'action': 'suspend'})
        self.assertEqual(response.status_code, 403)
        self.manager_profile.refresh_from_db()
        self.assertTrue(self.manager_profile.is_approved)

    def test_no_get_mutations(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('staff_activation:review_employee', args=[self.manager_profile.pk])).status_code, 405)
        self.manager_profile.refresh_from_db()
        self.assertTrue(self.manager_profile.is_approved)
