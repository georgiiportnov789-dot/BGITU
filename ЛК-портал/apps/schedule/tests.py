"""Тесты импорта и показа расписания."""
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files import File
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role
from apps.education.models import Group

from .models import Lesson, ScheduleImport
from .services import run_import

FIXTURE = settings.BASE_DIR / 'fixtures/schedule/bgitu-2026-27-1semestr-IVT-IST-PI-PRI.xls'


class ScheduleImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student_role = Role.objects.create(code='student', name='Студент', can_upload_works=True)
        cls.dean_role = Role.objects.create(code='dean', name='Деканат', can_manage_schedule=True)
        cls.student = User.objects.create_user('student', password='demo12345')
        cls.student.profile.role = cls.student_role
        cls.student.profile.save()
        cls.dean = User.objects.create_user('dean', password='demo12345')
        cls.dean.profile.role = cls.dean_role
        cls.dean.profile.save()

        with FIXTURE.open('rb') as handle:
            record = ScheduleImport(original_name=FIXTURE.name)
            record.file.save(FIXTURE.name, File(handle), save=True)
        run_import(record)
        cls.record = record

    def test_import_fills_lessons_and_groups(self):
        self.assertTrue(FIXTURE.exists(), 'нет файла расписания')
        self.assertGreater(Lesson.objects.count(), 200)
        self.assertGreaterEqual(Group.objects.count(), 10)
        self.assertTrue(Group.objects.filter(code='ИСТ-201').exists())
        self.assertEqual(self.record.lessons_count, Lesson.objects.count())

    def test_lessons_have_subject_and_room(self):
        lesson = Lesson.objects.filter(group__code='ИСТ-201').first()
        self.assertTrue(lesson.subject)
        self.assertTrue(lesson.teacher_name)
        self.assertTrue(lesson.room)
        self.assertIn(lesson.weekday, range(1, 7))
        self.assertIn(lesson.pair, range(1, 7))

    def test_student_schedule_shows_own_group(self):
        self.student.profile.group = Group.objects.get(code='ИСТ-201')
        self.student.profile.save()
        self.client.force_login(self.student)
        response = self.client.get(reverse('schedule:schedule'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ИСТ-201')
        self.assertContains(response, 'Базы данных')
        self.assertNotContains(response, 'id="groupSelect"')

    def test_staff_can_switch_group(self):
        self.client.force_login(self.dean)
        response = self.client.get(reverse('schedule:schedule'), {'group': 'ИСТ-101'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Группа ИСТ-101')
        self.assertContains(response, 'id="groupSelect"')

    def test_student_cannot_open_import(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('schedule:import')).status_code, 403)
