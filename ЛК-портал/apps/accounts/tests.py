"""Тесты ролей, заявок и управления пользователями."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.education.models import Group

from .models import Profile, Role, RoleRequest


class RoleFlowTests(TestCase):
    def setUp(self):
        self.student_role = Role.objects.create(code='student', name='Студент', can_upload_works=True)
        self.teacher_role = Role.objects.create(code='teacher', name='Преподаватель', can_create_courses=True, can_grade=True)
        self.dean_role = Role.objects.create(code='dean', name='Деканат', can_manage_users=True, can_approve_roles=True)
        self.admin_role = Role.objects.create(
            code='admin', name='Администратор', can_manage_users=True, can_manage_roles=True, can_approve_roles=True
        )
        self.dev_role = Role.objects.create(code='developer', name='Разработчик', can_manage_roles=True, is_developer=True)
        self.group = Group.objects.create(code='ИСТ-201', course=2)

        self.student = self.make_user('student', self.student_role, self.group)
        self.teacher = self.make_user('teacher', self.teacher_role)
        self.dean = self.make_user('dean', self.dean_role)
        self.admin = self.make_user('admin', self.admin_role)
        self.developer = self.make_user('developer', self.dev_role)

    def make_user(self, username, role, group=None):
        user = User.objects.create_user(username=username, password='demo12345', first_name='Тест', last_name=username)
        profile = user.profile
        profile.role = role
        profile.group = group
        profile.save()
        return user

    def test_student_requests_role_and_dean_approves(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse('accounts:role_request_create', args=[self.teacher_role.id]),
            {'comment': 'Веду практику'},
        )
        self.assertRedirects(response, reverse('accounts:roles'))
        request_obj = RoleRequest.objects.get(user=self.student, role=self.teacher_role)
        self.assertEqual(request_obj.status, RoleRequest.STATUS_PENDING)

        self.client.force_login(self.dean)
        response = self.client.post(
            reverse('accounts:role_request_review', args=[request_obj.id, 'approve']),
            {'review_comment': 'Согласовано'},
        )
        self.assertRedirects(response, reverse('accounts:role_requests'))
        request_obj.refresh_from_db()
        self.student.profile.refresh_from_db()
        self.assertEqual(request_obj.status, RoleRequest.STATUS_APPROVED)
        self.assertEqual(self.student.profile.role, self.teacher_role)

    def test_developer_role_requires_developer_approval(self):
        RoleRequest.objects.create(user=self.student, role=self.dev_role)
        request_obj = RoleRequest.objects.get(user=self.student, role=self.dev_role)

        self.client.force_login(self.dean)
        self.client.post(reverse('accounts:role_request_review', args=[request_obj.id, 'approve']))
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, RoleRequest.STATUS_PENDING)

        self.client.force_login(self.developer)
        self.client.post(reverse('accounts:role_request_review', args=[request_obj.id, 'approve']))
        request_obj.refresh_from_db()
        self.student.profile.refresh_from_db()
        self.assertEqual(request_obj.status, RoleRequest.STATUS_APPROVED)
        self.assertEqual(self.student.profile.role, self.dev_role)

    def test_role_creation_permission_and_developer_flag(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse('accounts:role_create')).status_code, 403)

        self.client.force_login(self.admin)
        response = self.client.post(reverse('accounts:role_create'), {
            'name': 'Методист', 'code': 'methodist', 'description': 'Планы',
            'can_create_courses': 'on', 'can_grade': 'on',
        })
        self.assertRedirects(response, reverse('accounts:roles'))
        self.assertTrue(Role.objects.filter(code='methodist').exists())

        response = self.client.post(reverse('accounts:role_create'), {
            'name': 'Полный', 'code': 'fullaccess', 'is_developer': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Role.objects.filter(code='fullaccess').exists())

    def test_only_developer_can_assign_developer_role(self):
        group = Group.objects.create(code='ИСТ-101', course=1)
        self.client.force_login(self.dean)
        response = self.client.post(
            reverse('accounts:student_update', args=[self.student.id]),
            {'role': self.dev_role.id, 'group': group.id, 'record_book': 'ИСТ-101/01'},
        )
        self.assertRedirects(response, reverse('accounts:students'))
        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.profile.role, self.student_role)

        self.client.force_login(self.developer)
        self.client.post(
            reverse('accounts:student_update', args=[self.student.id]),
            {'role': self.student_role.id, 'group': group.id, 'record_book': 'ИСТ-101/01'},
        )
        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.profile.group, group)

    def test_student_cannot_open_management_pages(self):
        self.client.force_login(self.student)
        for name in ('accounts:students', 'accounts:role_create', 'accounts:role_requests'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403 if name != 'accounts:role_requests' else 200)


class RegistrationTests(TestCase):
    def setUp(self):
        self.role = Role.objects.create(code='student', name='Студент', is_system=True, can_upload_works=True)
        self.group = Group.objects.create(code='ИСТ-201', course=2)
        self.payload = {
            'last_name': 'Портнов',
            'first_name': 'Георгий',
            'username': 'newstudent',
            'email': 'newstudent@example.ru',
            'group': str(self.group.id),
            'password1': 'Bgu2026!study',
            'password2': 'Bgu2026!study',
        }

    def test_register_creates_profile_and_logs_in(self):
        response = self.client.post(reverse('accounts:register'), self.payload)
        self.assertRedirects(response, reverse('portal:dashboard'))
        user = User.objects.get(username='newstudent')
        self.assertEqual(user.profile.role, self.role)
        self.assertEqual(user.profile.group, self.group)
        self.assertEqual(self.client.session['_auth_user_id'], str(user.pk))
        self.assertContains(self.client.get(reverse('portal:dashboard')), 'ИСТ-201')

    def test_register_rejects_duplicate_username(self):
        User.objects.create_user('newstudent', email='other@example.ru', password='Bgu2026!study')
        response = self.client.post(reverse('accounts:register'), self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'уже занят')
        self.assertEqual(User.objects.filter(username='newstudent').count(), 1)

    def test_register_rejects_password_mismatch(self):
        self.payload['password2'] = 'Other2026!study'
        response = self.client.post(reverse('accounts:register'), self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'не совпадают')
        self.assertFalse(User.objects.filter(username='newstudent').exists())
