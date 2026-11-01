"""Тесты учебного процесса: курсы, работы, оценки, посещаемость."""
import tempfile
from datetime import date

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role

from .models import Assignment, Attendance, Course, Enrollment, Grade, Group, Submission


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='bgitu-test-media-'))
class EducationFlowTests(TestCase):
    def setUp(self):
        self.student_role = Role.objects.create(code='student', name='Студент', can_upload_works=True)
        self.teacher_role = Role.objects.create(code='teacher', name='Преподаватель', can_create_courses=True, can_grade=True)
        self.group = Group.objects.create(code='ИСТ-201', course=2)
        self.student = self.make_user('student', self.student_role, self.group)
        self.student2 = self.make_user('student2', self.student_role, self.group)
        self.teacher = self.make_user('teacher', self.teacher_role)
        self.course = Course.objects.create(
            title='Базы данных', code='БД-201', group=self.group, teacher=self.teacher, semester=3,
        )
        for student in (self.student, self.student2):
            Enrollment.objects.create(course=self.course, student=student)

    def make_user(self, username, role, group=None):
        user = User.objects.create_user(username=username, password='demo12345')
        profile = user.profile
        profile.role = role
        profile.group = group
        profile.save()
        return user

    def test_teacher_creates_course_and_students_enroll(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('education:course_create'), {
            'title': 'Веб-разработка', 'code': 'WEB-201', 'group': self.group.id,
            'semester': '4', 'description': 'Практикум',
        })
        course = Course.objects.get(code='WEB-201')
        self.assertRedirects(response, reverse('education:course_detail', args=[course.id]))
        self.assertEqual(course.enrollments.count(), 2)
        self.assertEqual(course.teacher, self.teacher)

    def test_student_uploads_work_and_teacher_reviews(self):
        assignment = Assignment.objects.create(
            course=self.course, title='Лабораторная 1', created_by=self.teacher,
        )
        self.client.force_login(self.student)
        response = self.client.post(
            reverse('education:submit_work', args=[assignment.id]),
            {'file': SimpleUploadedFile('work.txt', b'lab result', content_type='text/plain'), 'comment': 'Готово'},
        )
        self.assertRedirects(response, reverse('education:course_detail', args=[self.course.id]))
        submission = Submission.objects.get(assignment=assignment, student=self.student)
        self.assertEqual(submission.status, Submission.STATUS_SUBMITTED)
        self.assertTrue(submission.file.name.endswith('.txt'))

        self.client.force_login(self.teacher)
        self.client.post(
            reverse('education:review_submission', args=[submission.id]),
            {'status': 'reviewed', 'grade': '5', 'teacher_comment': 'Отлично'},
        )
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.STATUS_REVIEWED)
        self.assertEqual(submission.grade, '5')
        self.assertEqual(submission.reviewed_by, self.teacher)

    def test_student_cannot_upload_to_foreign_course(self):
        foreign_group = Group.objects.create(code='ПИ-201', course=2)
        foreign_course = Course.objects.create(title='Чужой', code='X-1', group=foreign_group, teacher=self.teacher)
        assignment = Assignment.objects.create(course=foreign_course, title='Чужая лаба', created_by=self.teacher)
        self.client.force_login(self.student)
        response = self.client.post(
            reverse('education:submit_work', args=[assignment.id]),
            {'file': SimpleUploadedFile('work.txt', b'x')},
        )
        self.assertRedirects(response, reverse('education:courses'))
        self.assertFalse(Submission.objects.filter(assignment=assignment, student=self.student).exists())

    def test_grade_and_attendance_by_teacher(self):
        self.client.force_login(self.teacher)
        self.client.post(
            reverse('education:set_grade', args=[self.course.id]),
            {'student': self.student.id, 'kind': 'exam', 'value': '5', 'date': date.today().isoformat()},
        )
        grade = Grade.objects.get(course=self.course, student=self.student, kind='exam')
        self.assertEqual(grade.value, '5')

        response = self.client.post(
            reverse('education:attendance', args=[self.course.id]),
            {'date': date.today().isoformat(), f'status_{self.student.id}': 'absent',
             f'status_{self.student2.id}': 'present'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Attendance.objects.filter(course=self.course, date=date.today()).count(), 2)
        self.assertEqual(
            Attendance.objects.get(course=self.course, student=self.student, date=date.today()).status,
            Attendance.STATUS_ABSENT,
        )

    def test_student_cannot_grade_or_mark_attendance(self):
        self.client.force_login(self.student)
        self.assertEqual(
            self.client.post(reverse('education:set_grade', args=[self.course.id]), {'student': self.student.id, 'kind': 'exam', 'value': '5'}).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse('education:attendance', args=[self.course.id])).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse('education:journal', args=[self.course.id])).status_code,
            403,
        )

    def test_foreign_teacher_cannot_open_journal(self):
        other = self.make_user('teacher2', self.teacher_role)
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('education:journal', args=[self.course.id])).status_code, 403)
