from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from core.models import Branch, StaffProfile
from .models import Attendance, LeaveRequest
from .services import create_leave


class WorkforceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.a = Branch.objects.create(name='HR Test East', code='HR-TEST-EAST')
        cls.b = Branch.objects.create(name='HR Test West', code='HR-TEST-WEST')
        cls.admin = User.objects.create_superuser('hr_super', 'hr_super@example.test', 'test-pass-54321')
        cls.manager = User.objects.create_user('hr_manager_east', password='test-pass-54321')
        cls.worker = User.objects.create_user('hr_worker_east', password='test-pass-54321')
        cls.other = User.objects.create_user('hr_worker_west', password='test-pass-54321')
        cls.pending = User.objects.create_user('hr_pending', password='test-pass-54321')
        cls.foreign_manager = User.objects.create_user('hr_manager_west', password='test-pass-54321')
        cls.manager_p = StaffProfile.objects.create(user=cls.manager, branch=cls.a, role='MANAGER', is_approved=True)
        cls.worker_p = StaffProfile.objects.create(user=cls.worker, branch=cls.a, role='CASHIER', is_approved=True)
        cls.other_p = StaffProfile.objects.create(user=cls.other, branch=cls.b, role='STAFF', is_approved=True)
        cls.pending_p = StaffProfile.objects.create(user=cls.pending, branch=cls.a, role='STAFF', is_approved=False)
        cls.foreign_manager_p = StaffProfile.objects.create(user=cls.foreign_manager, branch=cls.b, role='MANAGER', is_approved=True)

    def test_authentication_and_approval_are_required(self):
        self.assertEqual(self.client.get(reverse('workforce:home')).status_code, 302)
        self.client.force_login(self.pending)
        self.assertEqual(self.client.get(reverse('workforce:home')).status_code, 403)
        self.assertEqual(self.client.post(reverse('workforce:attendance_action', args=['in'])).status_code, 403)
        self.client.force_login(self.worker)
        self.assertEqual(self.client.get(reverse('workforce:home')).status_code, 200)
        self.assertEqual(self.client.get(reverse('workforce:team')).status_code, 403)
        self.assertEqual(self.client.get(reverse('workforce:team_leaves')).status_code, 403)

    def test_check_in_and_out_only_once_per_day(self):
        self.client.force_login(self.worker)
        url = reverse('workforce:attendance_action', args=['in'])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(Attendance.objects.filter(profile=self.worker_p).count(), 1)
        self.client.post(reverse('workforce:attendance_action', args=['out']))
        a = Attendance.objects.get(profile=self.worker_p)
        self.assertIsNotNone(a.checked_out_at)
        self.client.post(reverse('workforce:attendance_action', args=['out']))
        a.refresh_from_db()
        self.assertIsNotNone(a.checked_out_at)

    def test_cannot_check_out_before_in(self):
        self.client.force_login(self.worker)
        self.client.post(reverse('workforce:attendance_action', args=['out']))
        self.assertEqual(Attendance.objects.filter(profile=self.worker_p).count(), 0)

    def test_leave_validation_and_overlap(self):
        today = timezone.localdate() + timedelta(days=2)
        with self.assertRaises(ValidationError):
            create_leave(self.worker_p, leave_type='ANNUAL', starts_on=today + timedelta(days=1), ends_on=today)
        self.client.force_login(self.worker)
        response = self.client.post(reverse('workforce:request_leave'), {
            'leave_type': 'ANNUAL', 'starts_on': str(today),
            'ends_on': str(today + timedelta(days=3)), 'reason': 'Planned time off',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LeaveRequest.objects.count(), 1)
        response = self.client.post(reverse('workforce:request_leave'), {
            'leave_type': 'SICK', 'starts_on': str(today + timedelta(days=1)),
            'ends_on': str(today + timedelta(days=2)), 'reason': 'Overlap',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LeaveRequest.objects.count(), 1)

    def test_manager_approves_worker_but_cannot_approve_own_leave(self):
        start = timezone.localdate() + timedelta(days=4)
        leave = create_leave(self.worker_p, leave_type='ANNUAL', starts_on=start, ends_on=start + timedelta(days=1))
        self.client.force_login(self.manager)
        response = self.client.post(reverse('workforce:review_leave', args=[leave.pk]), {'action': 'approve'})
        self.assertEqual(response.status_code, 302)
        leave.refresh_from_db()
        self.assertEqual(leave.status, 'APPROVED')
        self.assertEqual(leave.reviewed_by, self.manager)
        response = self.client.post(reverse('workforce:review_leave', args=[leave.pk]), {'action': 'approve'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LeaveRequest.objects.get(pk=leave.pk).status, 'APPROVED')
        own = create_leave(self.manager_p, leave_type='ANNUAL', starts_on=start, ends_on=start)
        response = self.client.post(reverse('workforce:review_leave', args=[own.pk]), {'action': 'approve'})
        self.assertEqual(response.status_code, 403)
        self.client.force_login(self.admin)
        response = self.client.post(reverse('workforce:review_leave', args=[own.pk]), {'action': 'approve'})
        self.assertEqual(response.status_code, 302)
        own.refresh_from_db()
        self.assertEqual(own.status, 'APPROVED')

    def test_branch_isolation_for_team_and_review(self):
        today = timezone.localdate() + timedelta(days=3)
        leave = create_leave(self.other_p, leave_type='UNPAID', starts_on=today, ends_on=today)
        self.client.force_login(self.manager)
        page = self.client.get(reverse('workforce:team'))
        self.assertContains(page, 'hr_worker_east')
        self.assertNotContains(page, 'hr_worker_west')
        self.assertEqual(self.client.post(reverse('workforce:review_leave', args=[leave.pk]), {'action': 'approve'}).status_code, 404)
        leave.refresh_from_db()
        self.assertEqual(leave.status, 'PENDING')
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('workforce:team')), 'hr_worker_west')

    def test_rejection_requires_reason_and_cancel_only_own_pending(self):
        start = timezone.localdate() + timedelta(days=5)
        leave = create_leave(self.worker_p, leave_type='ANNUAL', starts_on=start, ends_on=start)
        self.client.force_login(self.manager)
        self.client.post(reverse('workforce:review_leave', args=[leave.pk]), {'action': 'reject', 'note': ''})
        leave.refresh_from_db()
        self.assertEqual(leave.status, 'PENDING')
        self.client.post(reverse('workforce:review_leave', args=[leave.pk]), {'action': 'reject', 'note': 'Coverage unavailable'})
        leave.refresh_from_db()
        self.assertEqual(leave.status, 'REJECTED')
        self.client.force_login(self.worker)
        self.client.post(reverse('workforce:cancel_leave', args=[leave.pk]))
        self.assertEqual(LeaveRequest.objects.get(pk=leave.pk).status, 'REJECTED')
        pending = create_leave(self.worker_p, leave_type='UNPAID', starts_on=start + timedelta(days=2), ends_on=start + timedelta(days=2))
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse('workforce:cancel_leave', args=[pending.pk])).status_code, 404)
        self.client.force_login(self.worker)
        self.client.post(reverse('workforce:cancel_leave', args=[pending.pk]))
        self.assertEqual(LeaveRequest.objects.get(pk=pending.pk).status, 'CANCELLED')

    def test_csrf_blocks_attendance_mutation(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.worker)
        response = client.post(reverse('workforce:attendance_action', args=['in']))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Attendance.objects.exists())
