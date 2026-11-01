"""Демо-данные портала: роли, пользователи, курсы, работы, оценки."""
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Profile, Role, RoleRequest
from apps.education.models import Assignment, Attendance, Course, Enrollment, Grade, Group, Submission
from apps.schedule.models import ScheduleImport
from apps.schedule.services import run_import

DEMO_PASSWORD = 'demo12345'
SCHEDULE_FILE = 'fixtures/schedule/bgitu-2026-27-1semestr-IVT-IST-PI-PRI.xls'
SCHEDULE_URL = 'https://bgitu.ru/studentu/raspisanie/ochnoe-obuchenie/2026-27/1-semestr/v8/'

ROLES = [
    ('student', 'Студент', 'Кабинет, расписание, оценки, курсы и загрузка работ.', {}),
    ('monitor', 'Староста группы', 'То же, что студент; видит свою группу.', {}),
    ('teacher', 'Преподаватель', 'Создаёт курсы и задания, ведёт журнал, посещаемость и проверяет работы.',
     {'can_create_courses': True, 'can_grade': True, 'can_upload_works': False}),
    ('dean', 'Деканат / учебный офис', 'Назначает группы и роли студентов, управляет расписанием.',
     {'can_manage_users': True, 'can_approve_roles': True, 'can_manage_schedule': True, 'can_grade': True, 'can_upload_works': False}),
    ('editor', 'Редактор сайта', 'Готовит контент; доступ к расписанию и курсам не нужен.',
     {'can_upload_works': False}),
    ('rector', 'Ректор / руководство', 'Видит сводные данные по всем группам.',
     {'can_view_all': True, 'can_upload_works': False}),
    ('admin', 'Администратор', 'Управляет пользователями, ролями, расписанием и курсами.',
     {'can_manage_users': True, 'can_manage_roles': True, 'can_approve_roles': True, 'can_manage_schedule': True,
      'can_create_courses': True, 'can_grade': True, 'can_view_all': True, 'can_upload_works': False}),
    ('developer', 'Разработчик', 'Полный доступ ко всем разделам и данным, включая выдачу роли разработчика.',
     {'can_manage_users': True, 'can_manage_roles': True, 'can_approve_roles': True, 'can_manage_schedule': True,
      'can_create_courses': True, 'can_grade': True, 'can_view_all': True, 'is_developer': True}),
]


class Command(BaseCommand):
    help = 'Создаёт демо-роли, пользователей, курсы и импортирует расписание БГИТУ.'

    def add_arguments(self, parser):
        parser.add_argument('--skip-schedule', action='store_true', help='Не импортировать расписание, если занятия уже есть')
        parser.add_argument('--force-schedule', action='store_true', help='Переимпортировать расписание принудительно')

    def handle(self, *args, **options):
        roles = self.make_roles()
        users = self.make_users(roles)
        self.make_schedule(users['developer'], options)
        groups = self.assign_groups(users)
        self.make_courses(users, groups)
        self.make_requests(users)
        self.stdout.write(self.style.SUCCESS('Демо-данные готовы.'))
        self.stdout.write('Вход: student / teacher / dean / admin / developer, пароль ' + DEMO_PASSWORD)

    def make_roles(self):
        roles = {}
        for code, name, description, flags in ROLES:
            defaults = {
                'name': name,
                'description': description,
                'can_upload_works': True,
                'is_system': code != 'developer',
            }
            defaults.update(flags)
            role, _ = Role.objects.update_or_create(code=code, defaults=defaults)
            roles[code] = role
        return roles

    def make_user(self, username, first, last, email, role, group=None, record='', superuser=False):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={'first_name': first, 'last_name': last, 'email': email},
        )
        user.first_name = first
        user.last_name = last
        user.email = email
        user.is_staff = bool(superuser)
        user.is_superuser = bool(superuser)
        user.set_password(DEMO_PASSWORD)
        user.save()
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role = role
        profile.group = group
        profile.record_book = record
        profile.save()
        return user

    def make_users(self, roles):
        users = {
            'developer': self.make_user('developer', 'Илья', 'Кузнецов', 'i.kuznetsov@bgitu.ru', roles['developer'], superuser=True),
            'admin': self.make_user('admin', 'Марина', 'Орлова', 'm.orlova@bgitu.ru', roles['admin'], superuser=True),
            'dean': self.make_user('dean', 'Ольга', 'Белова', 'o.belova@bgitu.ru', roles['dean']),
            'teacher': self.make_user('teacher', 'Андрей', 'Иванов', 'a.ivanov@bgitu.ru', roles['teacher']),
            'teacher2': self.make_user('teacher2', 'Ирина', 'Козлова', 'i.kozlova@bgitu.ru', roles['teacher']),
            'teacher3': self.make_user('teacher3', 'Михаил', 'Моргунов', 'm.morgunov@bgitu.ru', roles['teacher']),
            'teacher4': self.make_user('teacher4', 'Ирина', 'Рудакова', 'i.rudakova@bgitu.ru', roles['teacher']),
            'student': self.make_user('student', 'Георгий', 'Портнов', 'g.portnov@bgitu.ru', roles['student']),
            'monitor': self.make_user('monitor', 'Анна', 'Смирнова', 'a.smirnova@bgitu.ru', roles['monitor']),
        }
        extra = [
            ('student1', 'Илья', 'Петров'),
            ('student2', 'Мария', 'Соколова'),
            ('student3', 'Артём', 'Кузнецов'),
            ('student4', 'Дарья', 'Егорова'),
            ('student5', 'Павел', 'Новиков'),
            ('student6', 'Ольга', 'Фёдорова'),
            ('student7', 'Никита', 'Лазарев'),
            ('student8', 'Полина', 'Мельникова'),
        ]
        for username, first, last in extra:
            users[username] = self.make_user(
                username, first, last, f'{username}@bgitu.ru', roles['student']
            )
        return users

    def make_schedule(self, user, options):
        fixture = settings.BASE_DIR / SCHEDULE_FILE
        from apps.schedule.models import Lesson

        if not fixture.exists():
            self.stdout.write(self.style.WARNING('Файл расписания не найден: ' + SCHEDULE_FILE))
            return
        if Lesson.objects.exists() and not options['force_schedule']:
            if not options['skip_schedule']:
                self.stdout.write('Расписание уже импортировано — пропускаю.')
            return
        with fixture.open('rb') as handle:
            record = ScheduleImport(
                original_name=Path(SCHEDULE_FILE).name,
                source_url=SCHEDULE_URL,
                imported_by=user,
            )
            record.file.save(Path(SCHEDULE_FILE).name, File(handle), save=True)
        run_import(record, source_url=SCHEDULE_URL)
        self.stdout.write(f'Расписание: {record.lessons_count} занятий, {record.groups_count} групп.')

    def assign_groups(self, users):
        ist201, _ = Group.objects.get_or_create(code='ИСТ-201', defaults={'course': 2, 'program': '09.03.02'})
        ist101, _ = Group.objects.get_or_create(code='ИСТ-101', defaults={'course': 1, 'program': '09.03.02'})
        members = ['student', 'monitor', 'student1', 'student2', 'student3', 'student4', 'student5']
        for index, key in enumerate(members):
            profile = users[key].profile
            profile.group = ist201
            profile.record_book = f'ИСТ-201/{24 + index:02d}'
            profile.save()
        for key in ('student6', 'student7', 'student8'):
            profile = users[key].profile
            profile.group = ist101
            profile.record_book = f'ИСТ-101/{12 + int(key[-1]):02d}'
            profile.save()
        return {'ИСТ-201': ist201, 'ИСТ-101': ist101}

    def make_courses(self, users, groups):
        group = groups['ИСТ-201']
        students = list(Profile.objects.filter(group=group).values_list('user_id', flat=True))
        courses = [
            ('Базы данных', 'БД-201', users['teacher2'], 3,
             'Проектирование реляционных баз, нормализация, SQL и транзакции. Лабораторные — в аудитории 482.'),
            ('Программирование на Python', 'ПРОГ-201', users['teacher3'], 3,
             'Функции, модули, работа с файлами и ООП. Курс идёт параллельно с лабораторными в 227.'),
            ('Философия', 'ФИЛ-201', users['teacher4'], 3,
             'Курс с зачётом: семинары, эссе и итоговая работа.'),
        ]
        made = {}
        for title, code, teacher, semester, description in courses:
            course, _ = Course.objects.get_or_create(
                code=code, group=group,
                defaults={'title': title, 'teacher': teacher, 'semester': semester, 'description': description},
            )
            course.title = title
            course.teacher = teacher
            course.description = description
            course.save()
            Enrollment.objects.filter(course=course).delete()
            Enrollment.objects.bulk_create([Enrollment(course=course, student_id=sid) for sid in students])
            made[code] = course

        db = made['БД-201']
        assignment, _ = Assignment.objects.get_or_create(
            course=db, title='Лабораторная №3. Нормализация схемы',
            defaults={
                'description': 'Привести схему из методички к 3НФ, показать декомпозицию и описать ограничения.',
                'due_date': date.today() + timedelta(days=6),
                'created_by': users['teacher2'],
            },
        )
        coursework, _ = Assignment.objects.get_or_create(
            course=db, title='Курсовая работа: проект базы данных',
            defaults={
                'description': 'ER-модель, DDL, запросы и отчёт. Тема согласуется с преподавателем до конца месяца.',
                'due_date': date.today() + timedelta(days=35),
                'created_by': users['teacher2'],
            },
        )
        py = made['ПРОГ-201']
        Assignment.objects.get_or_create(
            course=py, title='Лабораторная №2. Функции и модули',
            defaults={
                'description': 'Разбить программу на модули, покрыть функции тестами и приложить отчёт.',
                'due_date': date.today() + timedelta(days=9),
                'created_by': users['teacher3'],
            },
        )

        # Демо-работа студента: проверенная лабораторная.
        submission, created = Submission.objects.get_or_create(
            assignment=assignment, student=users['student'],
            defaults={'comment': 'Вариант 4, схема в приложении.', 'status': Submission.STATUS_REVIEWED,
                      'grade': '5', 'teacher_comment': 'Нормализация верная, замечание к именованию таблиц.',
                      'reviewed_at': timezone.now(), 'reviewed_by': users['teacher2']},
        )
        if not submission.file:
            submission.file.save('lab3-portnov.txt', ContentFile('Лабораторная №3. Вариант 4.\nНормализация схемы до 3НФ.\n'.encode('utf-8')), save=True)
        monitor_submission, monitor_created = Submission.objects.get_or_create(
            assignment=assignment, student=users['monitor'],
            defaults={'comment': 'Прикладываю схему и скрипт создания таблиц.', 'status': Submission.STATUS_SUBMITTED},
        )
        if not monitor_submission.file:
            monitor_submission.file.save(
                'lab3-smirnova.txt',
                ContentFile('Лабораторная №3. Вариант 2.\nER-модель и SQL-скрипт.\n'.encode('utf-8')),
                save=True,
            )

        # Оценки: у студента средний 4,5 (5 и 4 + зачёт).
        grades = [
            (db, users['student'], Grade.KIND_EXAM, '5'),
            (py, users['student'], Grade.KIND_EXAM, '4'),
            (made['ФИЛ-201'], users['student'], Grade.KIND_CREDIT, 'зачтено'),
            (db, users['monitor'], Grade.KIND_EXAM, '4'),
            (db, users['student1'], Grade.KIND_EXAM, '3'),
            (py, users['monitor'], Grade.KIND_EXAM, '5'),
        ]
        for course, student, kind, value in grades:
            Grade.objects.update_or_create(
                course=course, student=student, kind=kind,
                defaults={'value': value, 'date': date.today() - timedelta(days=12),
                          'created_by': course.teacher},
            )

        # Посещаемость за три занятия.
        for days_ago in (21, 14, 7):
            lesson_date = date.today() - timedelta(days=days_ago)
            for index, student_id in enumerate(students):
                Attendance.objects.update_or_create(
                    course=db, student_id=student_id, date=lesson_date,
                    defaults={
                        'status': Attendance.STATUS_ABSENT if (days_ago == 14 and index == 2) else Attendance.STATUS_PRESENT,
                        'marked_by': users['teacher2'],
                    },
                )

    def make_requests(self, users):
        RoleRequest.objects.get_or_create(
            user=users['student5'], role=Role.objects.get(code='monitor'), status=RoleRequest.STATUS_PENDING,
            defaults={'comment': 'Готов вести старостат группы ИСТ-201 со следующего месяца.'},
        )
