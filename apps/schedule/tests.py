"""Тесты импорта и показа расписания."""
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
import tempfile

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.education.models import Group

from .models import Lesson, ScheduleImport
from .services import detect_institute, run_import, visible_lessons

FIXTURE = settings.BASE_DIR / 'fixtures/schedule/bgitu-2026-27-1semestr-IVT-IST-PI-PRI.xls'
TEST_MEDIA = tempfile.mkdtemp(prefix='bgitu-schedule-media-')


def schedule_bytes(subject, group='ИСТ-201'):
    """Минимальный .xlsx в формате файла БГИТУ: шапка группы + одна пара."""
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    for row in (
        ['РАСПИСАНИЕ УЧЕБНЫХ ЗАНЯТИЙ'],
        ['', '1 корпус', '2 корпус', group],
        ['', '', '', ''],
        ['понедельник', '8.20-9.55', '8.50-10.25', f'{subject} №307 (Петров П.П.)'],
    ):
        sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


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

    def test_schedule_shows_table_and_dates(self):
        """Таблица с днями и диапазоном дат текущей недели семестра."""
        from .views import semester_monday, semester_week_of

        self.student.profile.group = Group.objects.get(code='ИСТ-201')
        self.student.profile.save()
        self.client.force_login(self.student)
        response = self.client.get(reverse('schedule:schedule'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Раздел в разработке')
        week = semester_week_of(date.today())
        monday = semester_monday(week)
        sunday = monday + timedelta(days=6)
        self.assertContains(response, f'<i aria-hidden="true">{week}</i>')
        self.assertContains(response, 'parity-badge parity-badge--')
        # Мусорные мета-подписи не возвращаем: неделя показана только бейджем.
        self.assertNotContains(response, 'неделя №')
        self.assertNotContains(response, 'parity-menu')
        self.assertNotContains(response, 'week-parity-note')
        self.assertNotContains(response, 'Источник — файл')
        self.assertNotContains(response, 'файл БГИТУ ·')
        self.assertContains(
            response,
            f'{monday.strftime("%d.%m.%Y")} — {sunday.strftime("%d.%m.%Y")}',
        )
        self.assertContains(response, 'Базы данных')
        self.assertContains(response, 'Учебный план · вся программа обучения')

    def test_pair_time_only_inside_lesson_cell(self):
        """В левой колонке — только номер пары; время пары — внизу карточки."""
        import re

        self.student.profile.group = Group.objects.get(code='ИСТ-201')
        self.student.profile.save()
        self.client.force_login(self.student)
        response = self.client.get(reverse('schedule:schedule'), {'week': '12'})
        html = response.content.decode()
        time_column = re.findall(
            r'<div class="sched-cell sched-cell--time[^"]*">(.*?)</div>', html, re.S,
        )
        self.assertTrue(time_column)
        for cell in time_column:
            self.assertNotIn(':', cell)
            self.assertNotIn('–', cell)
        self.assertRegex(html, r'class="sched-time mono">\d{1,2}:\d{2}–\d{1,2}:\d{2}<')
        # 2-я пара ИСТ-201 в понедельник — 2-й корпус, время по звонкам 2-го корпуса.
        self.assertIn('10:35–12:10', html)

    def test_red_cell_shows_second_building(self):
        """Красная ячейка файла = 2-й корпус, корпус виден в карточке."""
        self.client.force_login(self.dean)
        response = self.client.get(reverse('schedule:schedule'), {'group': 'ПИ-401', 'week': '12'})
        self.assertContains(response, 'Разработка мобильных бизнес-приложений')
        self.assertContains(response, 'sched-build--2')
        self.assertContains(response, '2 корп.')

    def test_week_arrows_and_limits(self):
        """Стрелки листают недели; на границах семестра — выключены."""
        self.client.force_login(self.dean)
        first = self.client.get(reverse('schedule:schedule'), {'group': 'ИСТ-201', 'week': '1'})
        self.assertContains(first, 'week=2')
        self.assertContains(first, 'dir=next')
        self.assertContains(first, 'is-disabled')  # стрелка «назад» неактивна
        last = self.client.get(reverse('schedule:schedule'), {'group': 'ИСТ-201', 'week': '18'})
        self.assertContains(last, 'is-disabled')  # стрелка «вперёд» неактивна
        self.assertNotContains(last, 'week=19')

    def test_week_switch_changes_dates(self):
        self.client.force_login(self.dean)
        w12 = self.client.get(reverse('schedule:schedule'), {'group': 'ИСТ-201', 'week': '12'})
        w13 = self.client.get(reverse('schedule:schedule'), {'group': 'ИСТ-201', 'week': '13', 'dir': 'next'})
        self.assertContains(w12, '16.11.2026 — 22.11.2026')
        self.assertContains(w13, '23.11.2026 — 29.11.2026')
        self.assertContains(w13, 'sched-in-next')

    def test_day_header_stacks_day_and_date(self):
        """Шапка дня: «Пн» и дата — две строки, а не склейка в одну."""
        self.client.force_login(self.dean)
        response = self.client.get(reverse('schedule:schedule'), {'group': 'ИСТ-201', 'week': '13'})
        html = response.content.decode()
        self.assertRegex(
            html,
            r'<div class="sched-cell sched-cell--head[^"]*">\s*'
            r'<span class="sched-day">Пн</span>\s*'
            r'<span class="sched-date mono">23\.11</span>',
        )
        self.assertRegex(
            html,
            r'<div class="sched-cell sched-cell--head[^"]*">\s*'
            r'<span class="sched-day">Сб</span>\s*'
            r'<span class="sched-date mono">28\.11</span>',
        )

    def test_today_column_has_soft_highlight(self):
        """Сегодня: is-today у шапки и у всех ячеек колонки (число строк — по данным)."""
        import re

        self.client.force_login(self.dean)
        response = self.client.get(reverse('schedule:schedule'), {'group': 'ИСТ-201'})
        html = response.content.decode()
        today = date.today()
        short = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][today.weekday()]
        self.assertRegex(
            html,
            rf'<div class="sched-cell sched-cell--head is-today">\s*'
            rf'<span class="sched-day">{short}</span>\s*'
            rf'<span class="sched-date mono">{today.strftime("%d.%m")}</span>',
        )
        self.assertEqual(html.count('sched-cell--head is-today'), 1)
        rows = len(response.context['grid'])
        self.assertGreater(rows, 0)
        self.assertEqual(len(re.findall(r'class="[^"]*sched-cell--body[^"]*is-today', html)), rows)

    def test_staff_can_switch_group(self):
        self.client.force_login(self.dean)
        response = self.client.get(reverse('schedule:schedule'), {'group': 'ИСТ-101'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ИСТ-101')
        self.assertContains(response, 'class="group-switch"')

    def test_student_cannot_open_import(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('schedule:import')).status_code, 403)

    def test_import_lives_in_modal_not_separate_panel(self):
        """Обновление расписания — кнопка в шапке и модальное окно, без отдельной панели."""
        self.client.force_login(self.dean)
        response = self.client.get(reverse('schedule:schedule'), {'group': 'ИСТ-201'})
        html = response.content.decode()
        self.assertContains(response, 'id="scheduleImportOpen"')
        self.assertContains(response, '<dialog class="dialog sched-import" id="scheduleImport"')
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'name="file"')
        # старой отдельной секции импорта больше нет
        self.assertNotIn('Импорт из файла БГИТУ', html)
        self.assertNotIn('import-form', html)

    def test_student_has_no_import_button(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('schedule:schedule'))
        self.assertNotContains(response, 'id="scheduleImportOpen"')
        self.assertNotContains(response, 'id="scheduleImport"')


class WeekParityTests(TestCase):
    """Чётность недели: без пометок в файле — одно расписание, без переключателя."""

    @classmethod
    def setUpTestData(cls):
        from apps.education.models import Group
        from .models import Lesson

        cls.group = Group.objects.create(code='ИСТ-201', course=2)
        cls.student_role = Role.objects.create(code='student', name='Студент', can_upload_works=True)
        cls.student = User.objects.create_user('pstudent', password='demo12345')
        cls.student.profile.role = cls.student_role
        cls.student.profile.group = cls.group
        cls.student.profile.save()
        Lesson.objects.create(group=cls.group, weekday=1, pair=1, week='all', subject='Философия')

    def test_parser_detects_week_marker(self):
        from .import_service import parse_cell

        self.assertEqual(parse_cell('Физика нечётная\n314 (Симохин С.П.)')['week'], 'odd')
        self.assertEqual(parse_cell('Математика чётн.')['week'], 'even')
        self.assertEqual(parse_cell('Базы данных\n482 (Козлова И.Р.)')['week'], 'all')
        # «над чертой» / «под чертой» — I и II неделя
        self.assertEqual(parse_cell('Физика (I неделя)')['week'], 'odd')
        self.assertEqual(parse_cell('Физика (II неделя)')['week'], 'even')

    def test_parser_splits_two_lessons_in_one_cell(self):
        """Две пары подряд в одной ячейке (ИСТ-301, ср, 2 пара) — обе сохраняются."""
        from .import_service import cell_entries

        text = 'Методы машинного обучения\n№228 (Казаков О.Д.)\n\nWeb-сервисы\n№205 (Иванов И.И.)'
        entries = cell_entries(text)
        self.assertEqual([item['subject'] for item in entries], ['Методы машинного обучения', 'Web-сервисы'])

    def test_parser_reads_subgroup_letter_from_prefix(self):
        from .import_service import cell_entries

        entries = cell_entries('а Физика\n№307 (Симохин С.П.)\n\nб Информатика\n№228 (Юркова О.Н.)')
        self.assertEqual([item['subgroup'] for item in entries], ['а', 'б'])
        self.assertEqual([item['subject'] for item in entries], ['Физика', 'Информатика'])

    def test_imported_groups_have_subgroups(self):
        """В файле есть группы с подгруппами «а»/«б» — они сохранены как подгруппы."""
        from .services import parse_schedule

        lessons, _ = parse_schedule(str(FIXTURE))
        codes = {item['subgroup'] for item in lessons if item['subgroup']}
        self.assertTrue({'а', 'б'} & codes, f'ожидались подгруппы а/б, есть {codes}')

    def test_parity_follows_selected_week(self):
        """Оба недельных варианта видны в таблице, неделя меняет только бейдж/даты."""
        from .models import Lesson

        Lesson.objects.create(group=self.group, weekday=2, pair=1, week='odd', subject='Только нечёт')
        Lesson.objects.create(group=self.group, weekday=2, pair=2, week='even', subject='Только чёт')
        self.client.force_login(self.student)
        # неделя 13 семестра: 23–29.11.2026 — 13-я, нечётная
        odd = self.client.get(reverse('schedule:schedule'), {'week': '13'})
        self.assertContains(odd, '<b>Только нечёт</b>')
        self.assertContains(odd, '<b>Только чёт</b>')
        self.assertContains(odd, '1-я неделя')
        # неделя 12: 16–22.11.2026 — 12-я, чётная
        even = self.client.get(reverse('schedule:schedule'), {'week': '12'})
        self.assertContains(even, '<b>Только чёт</b>')
        self.assertContains(even, '<b>Только нечёт</b>')
        self.assertContains(even, '2-я неделя')
        # предмет «каждую неделю» виден в таблице в обеих
        self.assertContains(odd, '<b>Философия</b>')
        self.assertContains(even, '<b>Философия</b>')

    def test_same_slot_odd_even_shows_two_halves(self):
        """Один слот: верхняя половина — 1-я неделя, нижняя — 2-я, со своими деталями."""
        from .models import Bell, Lesson

        Bell.objects.create(building='1', pair=6, start='15:45', end='17:20')
        Bell.objects.create(building='2', pair=6, start='16:15', end='17:50')
        Lesson.objects.create(
            group=self.group, weekday=3, pair=6, week='odd', subject='Слот-нечёт',
            room='101', teacher_name='Петров П.П.', building='1',
        )
        Lesson.objects.create(
            group=self.group, weekday=3, pair=6, week='even', subject='Слот-чёт',
            room='202', teacher_name='Иванов И.И.', building='2',
        )
        self.client.force_login(self.student)
        odd = self.client.get(reverse('schedule:schedule'), {'week': '13'})
        html = odd.content.decode()
        self.assertContains(odd, 'sched-cell--weeks')
        self.assertGreater(html.index('Слот-нечёт'), 0)
        self.assertLess(html.index('Слот-нечёт'), html.index('Слот-чёт'))
        self.assertIn('<span class="sched-half__label mono">1-я неделя</span>', html)
        self.assertIn('<span class="sched-half__label mono">2-я неделя</span>', html)
        # У каждой половины — своя аудитория, преподаватель и время по корпусу.
        self.assertIn('ауд. 101', html)
        self.assertIn('Петров П.П.', html)
        self.assertIn('15:45–17:20', html)
        self.assertIn('ауд. 202', html)
        self.assertIn('Иванов И.И.', html)
        self.assertIn('16:15–17:50', html)
        even = self.client.get(reverse('schedule:schedule'), {'week': '12'})
        self.assertContains(even, '<b>Слот-чёт</b>')
        self.assertContains(even, '<b>Слот-нечёт</b>')

    def test_subgroup_filter(self):
        """?sub=б показывает занятия второй подгруппы."""
        from .models import Lesson

        Lesson.objects.create(group=self.group, weekday=6, pair=5, week='all', subject='Первая-подгр', subgroup='1')
        Lesson.objects.create(group=self.group, weekday=6, pair=5, week='all', subject='Вторая-подгр', subgroup='2')
        self.client.force_login(self.student)
        response = self.client.get(reverse('schedule:schedule'), {'week': '12', 'sub': 'б'})
        self.assertContains(response, '<b>Вторая-подгр</b>')
        self.assertNotContains(response, '<b>Первая-подгр</b>')
        self.assertContains(response, 'sub-pill is-active')

    def test_curriculum_block_lists_program(self):
        """Блок учебного плана: все дисциплины программы по семестрам."""
        self.client.force_login(self.student)
        response = self.client.get(reverse('schedule:schedule'))
        self.assertContains(response, 'Учебный план · вся программа обучения')
        self.assertContains(response, 'Математический анализ')
        self.assertContains(response, 'Иностранный язык')
        # многолетняя дисциплина — отрезок по семестрам
        self.assertContains(response, 'Иностранный язык: 1–4 семестры')
        self.assertContains(response, '>3</b><em>сем.</em>')

    def test_curriculum_marks_current_semester(self):
        from datetime import date

        from .views import current_program_semester

        expected = current_program_semester(2, date.today())  # ИСТ-201 — 2 курс
        self.client.force_login(self.student)
        response = self.client.get(reverse('schedule:schedule'))
        self.assertContains(response, f'is-now" style="--w: {expected}"')


class ServerImportPathTests(TestCase):
    """Импорт по пути: только файлы расписания из fixtures/schedule."""

    @classmethod
    def setUpTestData(cls):
        cls.dean_role = Role.objects.create(code='dean', name='Деканат', can_manage_schedule=True)
        cls.dean = User.objects.create_user('pdean', password='demo12345')
        cls.dean.profile.role = cls.dean_role
        cls.dean.profile.save()

    def test_rejects_path_outside_schedule_dir(self):
        self.client.force_login(self.dean)
        for bad in ('../../config/settings/base.py', '/etc/passwd', 'manage.py', ''):
            response = self.client.post(reverse('schedule:import_server'), {'path': bad}, follow=True)
            self.assertContains(response, 'Некорректный путь к файлу.', msg_prefix=bad)


class SubgroupSplitCellTests(TestCase):
    """Режим «все»: разные пары «а»/«б» — две карточки в половинках ячейки."""

    @classmethod
    def setUpTestData(cls):
        from apps.education.models import Group
        from .models import Lesson

        cls.group = Group.objects.create(code='ИСТ-201', course=2)
        cls.role = Role.objects.create(code='student', name='Студент', can_upload_works=True)
        cls.student = User.objects.create_user('substudent', password='demo12345')
        cls.student.profile.role = cls.role
        cls.student.profile.group = cls.group
        cls.student.profile.save()
        Lesson.objects.create(group=cls.group, weekday=6, pair=5, week='all', subject='Подгруппа-один', subgroup='1')
        Lesson.objects.create(group=cls.group, weekday=6, pair=5, week='all', subject='Подгруппа-два', subgroup='2')
        # Общая (объединённая) пара: подгруппы нет, карточка одна.
        Lesson.objects.create(group=cls.group, weekday=5, pair=4, week='all', subject='Общая-пара')
        Lesson.objects.create(
            group=cls.group, weekday=4, pair=3, week='all', subject='Второй-корпус', building='2', room='314',
        )

    def test_conflicting_pair_shows_both_halves(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('schedule:schedule'), {'week': '12'})
        self.assertContains(response, '<b>Подгруппа-один</b>')
        self.assertContains(response, '<b>Подгруппа-два</b>')
        self.assertContains(response, 'sched-cell--split')

    def test_common_pair_is_single_card_without_subgroup(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('schedule:schedule'), {'week': '12'})
        html = response.content.decode()
        self.assertIn('<b>Общая-пара</b>', html)
        start = html.index('<b>Общая-пара</b>')
        card = html[html.rindex('sched-lesson', 0, start):start]
        self.assertNotIn('sched-sub', card)

    def test_user_subgroup_wins(self):
        profile = self.student.profile
        profile.subgroup = 'б'
        profile.save()
        self.client.force_login(self.student)
        response = self.client.get(reverse('schedule:schedule'), {'week': '12'})
        self.assertContains(response, '<b>Подгруппа-два</b>')
        self.assertNotContains(response, '<b>Подгруппа-один</b>')
        self.assertNotContains(response, 'sched-cell--split')


class SubgroupVisibilityTests(TestCase):
    """Выбор подгрупп и метки — только у групп с реальным делением.

    Деление определяется по данным выбранной группы: парсер ставит метки
    «а»/«б» только тогда, когда в шапке файла под именем группы есть
    подстолбцы «а» и «б». Одиночная метка делением не считается.
    """

    @classmethod
    def setUpTestData(cls):
        cls.student_role = Role.objects.create(code='student', name='Студент', can_upload_works=True)
        cls.dean_role = Role.objects.create(code='dean', name='Деканат', can_view_all=True)
        cls.division = Group.objects.create(code='ИСТ-501', course=2)
        cls.plain = Group.objects.create(code='ПИ-501', course=4)
        cls.lone = Group.objects.create(code='ПРИ-501', course=1)
        cls.parity = Group.objects.create(code='ИВТ-501', course=1)

        cls.student = User.objects.create_user('visstudent', password='demo12345')
        cls.student.profile.role = cls.student_role
        cls.student.profile.group = cls.division
        cls.student.profile.save()
        cls.dean = User.objects.create_user('visdean', password='demo12345')
        cls.dean.profile.role = cls.dean_role
        cls.dean.profile.save()

        # Группа с делением: две подгруппы в одном слоте + общая пара.
        Lesson.objects.create(group=cls.division, weekday=1, pair=1, week='all', subject='Деление-а', subgroup='1')
        Lesson.objects.create(group=cls.division, weekday=1, pair=1, week='all', subject='Деление-б', subgroup='2')
        Lesson.objects.create(group=cls.division, weekday=2, pair=2, week='all', subject='Общая-с-делением')

        # Группа без деления: обычные пары, подгрупп нет вообще.
        Lesson.objects.create(group=cls.plain, weekday=1, pair=1, week='all', subject='Пара-раз')
        Lesson.objects.create(group=cls.plain, weekday=2, pair=2, week='all', subject='Пара-два')

        # Группа с одиночной пометкой подгруппы: второй половины в слоте нет.
        Lesson.objects.create(group=cls.lone, weekday=1, pair=1, week='all', subject='Одиночная-метка', subgroup='1')
        Lesson.objects.create(group=cls.lone, weekday=2, pair=2, week='all', subject='Обычная-пара')

        # Один и тот же день и пара, но разные недели: одновременно не стоят.
        Lesson.objects.create(group=cls.parity, weekday=3, pair=3, week='odd', subject='Нечёт-подгруппа', subgroup='1')
        Lesson.objects.create(group=cls.parity, weekday=3, pair=3, week='even', subject='Чёт-подгруппа', subgroup='2')

    def _login_as_student(self, group):
        self.student.profile.group = group
        self.student.profile.save()
        self.client.force_login(self.student)

    def test_division_group_shows_pills_and_filters(self):
        """Есть деление — пилюли и метки видны, ?sub= фильтрует занятия."""
        self._login_as_student(self.division)
        page = self.client.get(reverse('schedule:schedule'), {'week': '12'})
        self.assertEqual(page.context['subgroups'], ['а', 'б'])
        self.assertTrue(page.context['has_subgroups'])
        self.assertContains(page, 'class="sub-line"')
        self.assertContains(page, 'class="sub-pill')
        self.assertContains(page, 'sub-pill is-active')  # активна «все»
        self.assertContains(page, 'class="sched-sub mono"')

        second = self.client.get(reverse('schedule:schedule'), {'week': '12', 'sub': 'б'})
        self.assertContains(second, '<b>Деление-б</b>')
        self.assertNotContains(second, '<b>Деление-а</b>')
        self.assertContains(second, '<b>Общая-с-делением</b>')

        first = self.client.get(reverse('schedule:schedule'), {'week': '12', 'sub': 'а'})
        self.assertContains(first, '<b>Деление-а</b>')
        self.assertNotContains(first, '<b>Деление-б</b>')

    def test_group_without_division_has_no_subgroup_ui(self):
        """Нет деления — ни пилюль, ни меток, ни слова «подгруппа», все пары видны."""
        self._login_as_student(self.plain)
        page = self.client.get(reverse('schedule:schedule'), {'week': '12'})
        self.assertEqual(page.context['subgroups'], [])
        self.assertFalse(page.context['has_subgroups'])
        html = page.content.decode()
        self.assertNotIn('подгрупп', html.lower())
        self.assertNotIn('sub-line', html)
        self.assertNotIn('sub-pill', html)
        self.assertNotIn('sched-sub', html)
        self.assertContains(page, '<b>Пара-раз</b>')
        self.assertContains(page, '<b>Пара-два</b>')

    def test_lone_subgroup_mark_is_not_division(self):
        """Одна пометка подгруппы без второй половины — не повод для пилюль."""
        self._login_as_student(self.lone)
        page = self.client.get(reverse('schedule:schedule'), {'week': '12'})
        self.assertEqual(page.context['subgroups'], [])
        html = page.content.decode()
        self.assertNotIn('подгрупп', html.lower())
        self.assertNotIn('sched-sub', html)
        self.assertContains(page, '<b>Одиночная-метка</b>')
        self.assertContains(page, '<b>Обычная-пара</b>')

    def test_subgroups_on_different_weeks_still_division(self):
        """Обе метки подгрупп в данных — деление есть; недели показаны половинами."""
        self._login_as_student(self.parity)
        page = self.client.get(reverse('schedule:schedule'), {'week': '13'})
        self.assertEqual(page.context['subgroups'], ['а', 'б'])
        self.assertContains(page, 'sub-pill')
        self.assertContains(page, 'sched-cell--weeks')
        self.assertContains(page, '<b>Нечёт-подгруппа</b>')
        self.assertContains(page, '<b>Чёт-подгруппа</b>')

    def test_saved_subgroup_ignored_for_group_without_division(self):
        """Сохранённая в профиле подгруппа не фильтрует группу без деления."""
        profile = self.student.profile
        profile.subgroup = 'б'
        profile.save()
        self._login_as_student(self.plain)
        page = self.client.get(reverse('schedule:schedule'), {'week': '12'})
        self.assertEqual(page.context['sub'], '')
        self.assertNotContains(page, 'sub-pill')
        self.assertContains(page, '<b>Пара-раз</b>')
        self.assertContains(page, '<b>Пара-два</b>')
        profile.refresh_from_db()
        self.assertEqual(profile.subgroup, 'б')  # профиль не тронут

    def test_switching_group_drops_foreign_subgroup(self):
        """Переключение с группы с делением на группу без него снимает фильтр."""
        self.dean.profile.subgroup = 'б'
        self.dean.profile.save()
        self.client.force_login(self.dean)
        page = self.client.get(reverse('schedule:schedule'), {'group': self.plain.code, 'week': '12'})
        self.assertEqual(page.context['group'], self.plain)
        self.assertEqual(page.context['sub'], '')
        self.assertFalse(page.context['has_subgroups'])
        self.assertNotContains(page, 'sub-pill')
        self.assertNotContains(page, 'sched-sub')
        self.assertContains(page, '<b>Пара-раз</b>')
        self.assertContains(page, '<b>Пара-два</b>')


class ParityByCalendarTests(TestCase):
    """Листание недель само определяет чётность: календарь решает, какое расписание показать."""

    @classmethod
    def setUpTestData(cls):
        cls.group = Group.objects.create(code='ИСТ-201', course=2)
        role = Role.objects.create(code='student', name='Студент', can_upload_works=True)
        cls.student = User.objects.create_user('paritystudent', password='demo12345')
        cls.student.profile.role = role
        cls.student.profile.group = cls.group
        cls.student.profile.save()
        Lesson.objects.create(group=cls.group, weekday=1, pair=1, week='odd', subject='Нечёт-предмет')
        Lesson.objects.create(group=cls.group, weekday=1, pair=2, week='even', subject='Чёт-предмет')

    def test_parity_flips_with_week_number(self):
        """Соседние недели — противоположная чётность; оба варианта пары на месте."""
        from .views import parity_of_monday, semester_monday

        self.client.force_login(self.student)
        seen = {}
        for week in (12, 13):
            response = self.client.get(reverse('schedule:schedule'), {'week': str(week)})
            parity = parity_of_monday(semester_monday(week))
            seen[week] = parity
            label = 'нечётная' if parity == 'odd' else 'чётная'
            self.assertContains(response, f'parity-badge parity-badge--{parity}')
            self.assertContains(response, f'<b>{label}</b>')
            self.assertContains(response, '<b>Нечёт-предмет</b>')
            self.assertContains(response, '<b>Чёт-предмет</b>')
        self.assertNotEqual(seen[12], seen[13], 'соседние недели должны быть разной чётности')

    def test_week_page_shows_no_lessons_state(self):
        """Неделя без пар для группы — явное сообщение, а не пустая таблица."""
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse('schedule:schedule'), {'week': '3'}), 'sched-table')
        # в этой группе пары только по понедельнику — убираем их и смотрим пустой слот
        Lesson.objects.filter(group=self.group).delete()
        response = self.client.get(reverse('schedule:schedule'), {'week': '3'})
        self.assertContains(response, 'занятий нет')

    def test_week_links_keep_group(self):
        dean_role = Role.objects.create(code='dean2', name='Деканат', can_manage_schedule=True)
        dean = User.objects.create_user('pardean', password='demo12345')
        dean.profile.role = dean_role
        dean.profile.save()
        self.client.force_login(dean)
        response = self.client.get(reverse('schedule:schedule'), {'week': '5', 'group': 'ИСТ-201'})
        self.assertContains(response, 'week=6&amp;group=ИСТ-201&amp;dir=next')
        self.assertContains(response, 'week=4&amp;group=ИСТ-201&amp;dir=prev')


class WeekParityQueryTests(TestCase):
    """?week=odd|even — прямой выбор чётности без пересчёта номера недели."""

    @classmethod
    def setUpTestData(cls):
        cls.group = Group.objects.create(code='ИСТ-201', course=2)
        role = Role.objects.create(code='student', name='Студент', can_upload_works=True)
        cls.student = User.objects.create_user('oddstudent', password='demo12345')
        cls.student.profile.role = role
        cls.student.profile.group = cls.group
        cls.student.profile.save()
        Lesson.objects.create(group=cls.group, weekday=4, pair=3, week=Lesson.WEEK_ODD, subject='Только-нечёт')
        Lesson.objects.create(group=cls.group, weekday=4, pair=3, week=Lesson.WEEK_EVEN, subject='Только-чёт')
        Lesson.objects.create(group=cls.group, weekday=5, pair=1, week=Lesson.WEEK_ALL, subject='Каждую-неделю')

    def test_week_query_param_selects_parity(self):
        """?week=odd и ?week=even меняют неделю, но ячейка показывает оба варианта."""
        self.client.force_login(self.student)
        odd = self.client.get(reverse('schedule:schedule'), {'week': 'odd'})
        even = self.client.get(reverse('schedule:schedule'), {'week': 'even'})
        for response in (odd, even):
            self.assertContains(response, '<b>Только-нечёт</b>')
            self.assertContains(response, '<b>Только-чёт</b>')
        # «каждую неделю» — в обеих
        self.assertContains(odd, '<b>Каждую-неделю</b>')
        self.assertContains(even, '<b>Каждую-неделю</b>')
        self.assertContains(odd, 'data-parity="odd"')
        self.assertContains(even, 'data-parity="even"')

    def test_explicit_parity_matches_calendar_week(self):
        """Выбранный ?week=odd попадает на неделю с нечётной календарной чётностью."""
        from .views import parity_of_monday, semester_monday, semester_week_of

        self.client.force_login(self.student)
        for parity in ('odd', 'even'):
            self.client.force_login(self.student)
            response = self.client.get(reverse('schedule:schedule'), {'week': parity})
            self.assertEqual(response.status_code, 200)
            number = response.context['week']
            self.assertEqual(parity_of_monday(semester_monday(number)), parity)
            self.assertEqual(semester_week_of(response.context['monday']), number)

    def test_parity_links_switch_without_reloading_number(self):
        """Выпадашка недель: ссылки data-parity-odd/even есть и ведут на нужную чётность."""
        self.client.force_login(self.student)
        response = self.client.get(reverse('schedule:schedule'), {'week': 'odd'})
        links = response.context['parity_links']
        self.assertTrue(links['odd'] and links['even'])
        self.assertContains(response, f'data-parity-odd="{links["odd"]}"')
        self.assertContains(response, f'data-parity-even="{links["even"]}"')
        # ссылка «чётная» — ?week=N той недели семестра, у которой чётный номер
        query = links['even'].split('?', 1)[1]
        self.assertEqual(query.split('&')[0], 'week=2')
        target = self.client.get(reverse('schedule:schedule') + links['even'])
        self.assertEqual(target.status_code, 200)
        self.assertEqual(target.context['parity'], 'even')
        self.assertContains(target, 'data-parity="even"')
        self.assertContains(target, '<b>Только-чёт</b>')

    def test_subgroup_param_not_confused_with_parity(self):
        """?sub=odd не считается подгруппой — фильтр подгруппы остаётся пустым."""
        self.client.force_login(self.student)
        response = self.client.get(reverse('schedule:schedule'), {'week': 'even', 'sub': 'odd'})
        self.assertEqual(response.context['sub'], '')
        self.assertContains(response, '<b>Только-чёт</b>')


class WeekMarkerParserTests(TestCase):
    """Разбор обозначений чётности недели из файла БГИТУ."""

    def test_numerator_denominator_words(self):
        from .import_service import cell_entries

        odd = cell_entries('Физика\n№307 (Петров П.П.)\nчислитель')
        even = cell_entries('Информатика\n№228 (Юркова О.В.)\nзнаменатель')
        self.assertEqual([item['week'] for item in odd], ['odd'])
        self.assertEqual([item['week'] for item in even], ['even'])
        # слова-метки не попадают в название дисциплины
        self.assertEqual(odd[0]['subject'], 'Физика')
        self.assertEqual(even[0]['subject'], 'Информатика')

    def test_odd_even_short_form(self):
        from .import_service import parse_cell

        self.assertEqual(parse_cell('Физика\nнечёт')['week'], 'odd')
        self.assertEqual(parse_cell('Физика (чёт)')['week'], 'even')
        # «отчётности» — не метка чётности
        self.assertEqual(parse_cell('Получение отчётности №214')['week'], 'all')
        self.assertEqual(parse_cell('Физика\nнечётная неделя')['week'], 'odd')

    def test_upper_lower_week(self):
        from .import_service import parse_cell

        self.assertEqual(parse_cell('Физика\nверхняя неделя')['week'], 'odd')
        self.assertEqual(parse_cell('Физика\nнижняя неделя')['week'], 'even')
        self.assertEqual(parse_cell('Физика\nВерхняя неделя')['subject'], 'Физика')

    def test_roman_week_marks(self):
        from .import_service import detect_week

        self.assertEqual(detect_week('Физика (I неделя)'), 'odd')
        self.assertEqual(detect_week('Физика (II полугодие)'), 'even')
        # маркер в скобках снимается — ФИО в скобках за ним остаётся преподавателем
        from .import_service import parse_cell

        item = parse_cell('Физика (I неделя) №307 (Петров П.П.)')
        self.assertEqual((item['week'], item['teacher_name'], item['room']), ('odd', 'Петров П.П.', '307'))

    def test_slash_fraction_week_numbers(self):
        from .import_service import parse_cell

        # «7/11 неделя» — суммарные номера недель, чётность сходится → odd
        self.assertEqual(parse_cell('Физика\n7/11 неделя')['week'], 'odd')
        self.assertEqual(parse_cell('Физика\n6/10 неделя')['week'], 'even')
        # «7/14 неделя» — разная чётность чисел: метка неоднозначна → all
        self.assertEqual(parse_cell('Физика\n7/14 неделя')['week'], 'all')

    def test_fraction_cell_gives_two_parities(self):
        """Ячейка «числитель / знаменатель» разбивается на нечётное и чётное занятие."""
        from .import_service import cell_week_parity, parse_cell, split_fraction_entries

        text = 'Физика №307 (Петров П.П.) / Информатика №228 (Юркова О.В.)'
        self.assertEqual(cell_week_parity(text), 'pair')
        # так делает parse_schedule: каждая часть дроби → отдельное занятие
        parts = split_fraction_entries(text)
        self.assertEqual(len(parts), 2)
        entries = [parse_cell(part) for part in parts]
        self.assertEqual([(item['subject'], item['week']) for item in entries],
                         [('Физика', 'odd'), ('Информатика', 'even')])
        self.assertEqual(entries[0]['teacher_name'], 'Петров П.П.')
        self.assertEqual(entries[1]['teacher_name'], 'Юркова О.В.')

    def test_file_vertical_halves_are_weeks(self):
        """Верхняя половина ячейки пары — 1-я неделя, нижняя — 2-я (не подгруппы)."""
        from .import_service import parse_schedule

        lessons, _ = parse_schedule(str(FIXTURE))
        self.assertTrue(any(item['week'] == 'odd' for item in lessons))
        self.assertTrue(any(item['week'] == 'even' for item in lessons))
        # Вторник, 2-я пара ИСТ-201: сверху «Физика», снизу «ОЗОЖ».
        slot = [
            item for item in lessons
            if item['group'] == 'ИСТ-201' and item['weekday'] == 2 and item['pair'] == 2
        ]
        self.assertEqual(
            {(item['subject'], item['week']) for item in slot},
            {('Физика', 'odd'), ('Основы здорового образа жизни', 'even')},
        )
        self.assertTrue(all(item['subgroup'] == '' for item in slot))
        # Никаких номеров занятий вместо подгрупп.
        self.assertFalse(any(item['subgroup'] in ('1', '2') for item in lessons))

    def test_parse_schedule_keeps_cell_parity(self):
        """parse_schedule переносит признак недели из разбора ячейки в занятие."""
        from unittest import mock

        from . import import_service

        rows = [
            ['РАСПИСАНИЕ УЧЕБНЫХ ЗАНЯТИЙ'],
            ['', '1 корпус', '2 корпус', 'ИСТ-201'],
            ['', '', '', ''],
            ['понедельник', '8.20-9.55', '8.50-10.25', 'Физика №307 (Петров П.П.)\nнечётная неделя'],
            ['', '10.05-11.40', '10.35-12.10', 'Информатика №228 (Юркова О.В.)\nчётная неделя'],
        ]
        merged = [(1, 2, 3, 4)]
        with mock.patch.object(import_service, 'read_sheet', return_value=(rows, merged, {})):
            lessons, _bells = import_service.parse_schedule('dummy.xls')
        self.assertEqual(
            [(item['pair'], item['week'], item['subject']) for item in lessons],
            [(1, 'odd', 'Физика'), (2, 'even', 'Информатика')],
        )



class ScheduleCellRulesTests(TestCase):
    """Правила чтения ячеек файла БГИТУ: недели, корпус, подгруппы."""

    @classmethod
    def setUpTestData(cls):
        from .import_service import parse_schedule

        cls.lessons, _bells = parse_schedule(str(FIXTURE))

    def slot(self, group, weekday, pair):
        return [
            item for item in self.lessons
            if item['group'] == group and item['weekday'] == weekday and item['pair'] == pair
        ]

    def test_building_from_font_colour(self):
        """Красный шрифт = 2-й корпус, чёрный = 1-й (проверка на реальном файле)."""
        monday_first = self.slot('ПИ-401', 1, 1)
        self.assertEqual(len(monday_first), 1)
        self.assertEqual(monday_first[0]['building'], '1')  # «Бизнес-аналитика» чёрным
        monday_second = self.slot('ПИ-401', 1, 2)
        self.assertEqual(len(monday_second), 1)
        self.assertEqual(monday_second[0]['subject'], 'Разработка мобильных бизнес-приложений')
        self.assertEqual(monday_second[0]['building'], '2')  # красным
        self.assertEqual(sum(1 for item in self.lessons if item['building'] == '2'), 59)

    def test_subgroups_only_where_header_has_ab(self):
        """Подстолбцы «а»/«б» есть только у ПРИ-101, ПРИ-201, ПРИ-301."""
        divided = {
            item['group'] for item in self.lessons if item['subgroup']
        }
        self.assertEqual(divided, {'ПРИ-101', 'ПРИ-201', 'ПРИ-301'})
        self.assertTrue(all(item['subgroup'] == '' for item in self.lessons if item['group'] == 'ПРИ-401'))

    def test_common_merged_cell_is_one_lesson_without_subgroup(self):
        """Объединённая на обе подколонки ячейка — одна пара всей группы."""
        slot = self.slot('ПРИ-201', 1, 2)
        self.assertEqual(
            {(item['subject'], item['week'], item['subgroup']) for item in slot},
            {('Философия', 'odd', ''), ('Математика', 'even', '')},
        )

    def test_split_subgroup_cells_have_their_own_lessons(self):
        """Разделённые подколонки «а»/«б» — у каждой подгруппы своя пара."""
        slot = self.slot('ПРИ-101', 1, 3)
        self.assertEqual(
            {(item['subgroup'], item['subject']) for item in slot},
            {('а', 'Frontend-разработка'), ('б', 'Физика')},
        )
        self.assertTrue(all(item['week'] == 'all' for item in slot))

    def test_week_numbers_match_halves(self):
        """week=1 — верхняя половина, week=2 — нижняя; property week_number."""
        from .models import Lesson

        self.assertEqual(Lesson(week='odd').week_number, 1)
        self.assertEqual(Lesson(week='even').week_number, 2)
        self.assertEqual(Lesson(week='all').week_number, 0)
        self.assertEqual(Lesson(week='odd').week_label, '1-я неделя')


class MergedCellAcrossPairsTests(TestCase):
    """Объединённая ячейка через границу пар не должна дублировать занятие в соседней паре."""

    def test_merged_cell_not_duplicated(self):
        """Ячейка (7,9) в файле БГИТУ: 1-я пара подгруппы «б» не появляется во 2-й."""
        import xlrd
        from .import_service import parse_schedule

        book = xlrd.open_workbook(str(FIXTURE), formatting_info=True)
        sheet = book.sheet_by_index(0)
        # ищем объединение по вертикали, пересекающее границу пары, и группу за ним
        merged = [m for m in sheet.merged_cells if m[1] - m[0] > 1]
        self.assertTrue(merged, 'в файле нет объединённых ячеек — проверка неприменима')
        lessons, _ = parse_schedule(str(FIXTURE))
        # ни одна ячейка не содержит два занятия с одинаковыми предметом и подгруппой
        seen = {}
        for item in lessons:
            key = (item['group'], item['weekday'], item['pair'], item['subject'], item['subgroup'])
            seen[key] = seen.get(key, 0) + 1
        duplicates = {k: v for k, v in seen.items() if v > 1}
        # одинаковые предмет+подгруппа допустимы только при разных аудиториях (реальные разные занятия)
        self.assertTrue(all(v <= 2 for v in duplicates.values()), duplicates)


class NavTooltipMarkupTests(TestCase):
    """Подсказки разделов у свёрнутого рельса кабинета."""

    @classmethod
    def setUpTestData(cls):
        from apps.schedule.models import Lesson

        cls.group = Group.objects.create(code='ИСТ-201', course=2)
        role = Role.objects.create(code='student', name='Студент', can_upload_works=True)
        cls.student = User.objects.create_user('tipstudent', password='demo12345')
        cls.student.profile.role = role
        cls.student.profile.group = cls.group
        cls.student.profile.save()
        Lesson.objects.create(group=cls.group, weekday=1, pair=1, week='all', subject='Математика')

    def test_reel_items_have_tooltip_labels(self):
        """Каждый пункт рельса несёт data-tip с названием раздела + в body есть пузырёк."""
        self.client.force_login(self.student)
        response = self.client.get(reverse('schedule:schedule'))
        html = response.content.decode()
        self.assertContains(response, 'id="navTip"')
        self.assertContains(response, 'role="tooltip"')
        for label in ('Обзор', 'Расписание', 'Стипендия', 'Курсы', 'Оценки', 'Роли', 'Профиль'):
            self.assertIn(f'data-tip="{label}"', html, label)

    def test_tooltip_has_no_native_title_attribute(self):
        """Своя подсказка: у пунктов нет title, иначе браузер покажет вторую."""
        self.client.force_login(self.student)
        response = self.client.get(reverse('schedule:schedule'))
        html = response.content.decode()
        start = html.index('class="cab-nav"')
        end = html.index('</aside>', start)
        reel = html[start:end]
        self.assertNotIn('title="', reel)


class NoTitleTruncationTests(TestCase):
    """Названия предметов не обрезаются: ни clamp, ни фиксированные строки."""

    def test_css_has_no_line_clamp_or_fixed_rows(self):
        from pathlib import Path

        css = (Path(settings.BASE_DIR) / 'static/css/cabinet.css').read_text(encoding='utf-8')
        start = css.index('.sched-table {')
        block = css[start:css.index('.sched-empty')]
        # строки таблицы — по содержимому, а не жёсткие 88px
        self.assertIn('grid-auto-rows: minmax(', block)
        self.assertNotIn('grid-template-rows: 34px repeat', block)
        # у названия нет обрезки многоточием/клампом
        title_block = css[css.index('.sched-lesson b {'):css.index('.sched-kind {')]
        self.assertNotIn('-webkit-line-clamp', title_block)
        self.assertNotIn('text-overflow: ellipsis', title_block)


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class MultiFileImportTests(TestCase):
    """Несколько файлов расписания: хранение, замена, удаление, приоритет."""

    @classmethod
    def setUpTestData(cls):
        cls.dean_role = Role.objects.create(code='mdean', name='Деканат', can_manage_schedule=True)
        cls.student_role = Role.objects.create(code='mstudent', name='Студент', can_upload_works=True)
        cls.dean = User.objects.create_user('mdean', password='demo12345')
        cls.dean.profile.role = cls.dean_role
        cls.dean.profile.save()
        cls.student = User.objects.create_user('mstudent', password='demo12345')
        cls.student.profile.role = cls.student_role
        cls.student.profile.save()

    def upload(self, *files):
        payload = [
            SimpleUploadedFile(
                name, content,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            for name, content in files
        ]
        self.client.force_login(self.dean)
        return self.client.post(
            reverse('schedule:import'), {'file': payload, 'group': 'ИСТ-201'}, follow=True,
        )

    def test_detect_institute_from_filename(self):
        self.assertEqual(
            detect_institute('bgitu-2026-27-1semestr-IVT-IST-PI-PRI.xls'),
            'ИВТ · ИСТ · ПИ · ПРИ',
        )
        self.assertEqual(detect_institute('ist-raspisanie.xlsx'), 'ИСТ')

    def test_multiple_files_are_all_stored_and_parsed(self):
        self.upload(
            ('ist-2026.xlsx', schedule_bytes('Физика', 'ИСТ-201')),
            ('ivt-2026.xlsx', schedule_bytes('Информатика', 'ИВТ-101')),
        )
        self.assertEqual(ScheduleImport.objects.count(), 2)
        ist = ScheduleImport.objects.get(institute='ИСТ')
        ivt = ScheduleImport.objects.get(institute='ИВТ')
        self.assertEqual((ist.lessons_count, ist.groups_count), (1, 1))
        self.assertEqual((ivt.lessons_count, ivt.groups_count), (1, 1))
        self.assertTrue(ist.lessons.filter(subject='Физика', group__code='ИСТ-201').exists())
        self.assertTrue(ivt.lessons.filter(subject='Информатика', group__code='ИВТ-101').exists())
        self.assertEqual(ist.uploaded_by, self.dean)
        self.assertGreater(ist.size, 0)

    def test_reupload_same_institute_replaces_lessons(self):
        self.upload(('ist-old.xlsx', schedule_bytes('Старая физика')))
        old = ScheduleImport.objects.get()
        self.upload(('ist-new.xlsx', schedule_bytes('Новая информатика')))
        self.assertEqual(ScheduleImport.objects.filter(institute='ИСТ').count(), 1)
        source = ScheduleImport.objects.get(institute='ИСТ')
        self.assertNotEqual(source.pk, old.pk)
        self.assertEqual(source.lessons_count, 1)
        self.assertEqual(Lesson.objects.filter(group__code='ИСТ-201').count(), 1)
        self.assertFalse(Lesson.objects.filter(subject='Старая физика').exists())
        self.assertTrue(Lesson.objects.filter(subject='Новая информатика', source=source).exists())

    def test_reupload_keeps_other_institutes(self):
        self.upload(
            ('ist-2026.xlsx', schedule_bytes('Физика', 'ИСТ-201')),
            ('ivt-2026.xlsx', schedule_bytes('Информатика', 'ИВТ-101')),
        )
        ivt = ScheduleImport.objects.get(institute='ИВТ')
        self.upload(('ist-2027.xlsx', schedule_bytes('Новая физика', 'ИСТ-201')))
        self.assertEqual(ScheduleImport.objects.count(), 2)
        self.assertEqual(ScheduleImport.objects.get(institute='ИВТ').pk, ivt.pk)
        self.assertTrue(Lesson.objects.filter(source=ivt, subject='Информатика').exists())
        self.assertTrue(Lesson.objects.filter(subject='Новая физика').exists())
        self.assertFalse(Lesson.objects.filter(subject='Физика').exists())

    def test_delete_source_removes_only_its_lessons(self):
        self.upload(
            ('ist-2026.xlsx', schedule_bytes('Физика', 'ИСТ-201')),
            ('ivt-2026.xlsx', schedule_bytes('Информатика', 'ИВТ-101')),
        )
        ivt = ScheduleImport.objects.get(institute='ИВТ')
        response = self.client.post(
            reverse('schedule:source_delete', args=[ivt.pk]), {'group': 'ИСТ-201'}, follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ScheduleImport.objects.filter(pk=ivt.pk).exists())
        self.assertFalse(Lesson.objects.filter(group__code='ИВТ-101').exists())
        self.assertTrue(Lesson.objects.filter(group__code='ИСТ-201').exists())
        self.assertEqual(ScheduleImport.objects.count(), 1)

    def test_student_cannot_delete_source(self):
        self.upload(('ist-2026.xlsx', schedule_bytes('Физика', 'ИСТ-201')))
        source = ScheduleImport.objects.get()
        self.client.force_login(self.student)
        response = self.client.post(reverse('schedule:source_delete', args=[source.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(ScheduleImport.objects.filter(pk=source.pk).exists())

    def test_newest_file_wins_conflict_but_old_stays_in_db(self):
        self.upload(('ivt-old.xlsx', schedule_bytes('Старая физика', 'ИСТ-201')))
        old = ScheduleImport.objects.get()
        self.upload(('ist-new.xlsx', schedule_bytes('Новая информатика', 'ИСТ-201')))
        # разные институты → обе записи живут, в БД два занятия одного слота
        self.assertEqual(ScheduleImport.objects.count(), 2)
        self.assertEqual(Lesson.objects.filter(group__code='ИСТ-201').count(), 2)
        ScheduleImport.objects.filter(pk=old.pk).update(imported_at=timezone.now() - timedelta(days=1))

        group = Group.objects.get(code='ИСТ-201')
        visible = visible_lessons(group)
        self.assertEqual([item.subject for item in visible], ['Новая информатика'])

        self.client.force_login(self.dean)
        response = self.client.get(reverse('schedule:schedule'), {'group': 'ИСТ-201', 'week': '12'})
        self.assertContains(response, '<b>Новая информатика</b>')
        self.assertNotContains(response, '<b>Старая физика</b>')
        # старое занятие не удалено — просто перекрыто свежим файлом
        self.assertTrue(Lesson.objects.filter(source=old, subject='Старая физика').exists())

        # правило симметрично: если свежее окажется старый файл, видно его
        ScheduleImport.objects.filter(pk=old.pk).update(imported_at=timezone.now() + timedelta(minutes=1))
        visible = visible_lessons(group)
        self.assertEqual([item.subject for item in visible], ['Старая физика'])
        response = self.client.get(reverse('schedule:schedule'), {'group': 'ИСТ-201', 'week': '12'})
        self.assertContains(response, '<b>Старая физика</b>')
        self.assertNotContains(response, '<b>Новая информатика</b>')

        # Удалили самый свежий файл — в слоте снова видно занятие второго.
        self.client.post(reverse('schedule:source_delete', args=[old.pk]), follow=True)
        response = self.client.get(reverse('schedule:schedule'), {'group': 'ИСТ-201', 'week': '12'})
        self.assertContains(response, '<b>Новая информатика</b>')
        self.assertNotContains(response, '<b>Старая физика</b>')

    def test_conflict_is_per_subgroup(self):
        """Конфликт только внутри одной подгруппы; «1» и «а» — одна подгруппа."""
        group = Group.objects.create(code='ПИ-201', course=2)
        old = ScheduleImport.objects.create(original_name='old.xlsx', institute='ИВТ')
        new = ScheduleImport.objects.create(original_name='new.xlsx', institute='ИСТ')
        Lesson.objects.create(group=group, weekday=2, pair=1, week='all', subject='Старая-а', subgroup='1', source=old)
        Lesson.objects.create(group=group, weekday=2, pair=1, week='all', subject='Старая-б', subgroup='2', source=old)
        Lesson.objects.create(group=group, weekday=2, pair=1, week='all', subject='Новая-а', subgroup='а', source=new)
        self.assertEqual(
            sorted(item.subject for item in visible_lessons(group)),
            ['Новая-а', 'Старая-б'],
        )

    def test_modal_has_multiple_upload_and_sources_list(self):
        self.upload(('ist-2026.xlsx', schedule_bytes('Физика', 'ИСТ-201')))
        self.client.force_login(self.dean)
        response = self.client.get(reverse('schedule:schedule'), {'group': 'ИСТ-201'})
        html = response.content.decode()
        self.assertIn('multiple', html)
        self.assertIn('name="file"', html)
        self.assertIn('data-import-delete', html)
        self.assertIn('ist-2026.xlsx', html)
        self.assertIn(reverse('schedule:source_delete', args=[ScheduleImport.objects.get().pk]), html)

    def test_bad_file_does_not_cancel_good_one(self):
        bad = SimpleUploadedFile('notes.txt', b'not a schedule', content_type='text/plain')
        good = SimpleUploadedFile('ist-2026.xlsx', schedule_bytes('Физика'), content_type='application/octet-stream')
        self.client.force_login(self.dean)
        response = self.client.post(
            reverse('schedule:import'), {'file': [bad, good]}, follow=True,
        )
        self.assertContains(response, 'notes.txt')
        self.assertEqual(ScheduleImport.objects.count(), 1)
        self.assertTrue(Lesson.objects.filter(subject='Физика').exists())


class ScheduleRowCountTests(TestCase):
    """Строки таблицы — только пары, которые есть хотя бы у одной группы.

    Пустая пара (например 6-я) не занимает строку и не создаёт ячеек; число
    строк считается по всей выборке семестра/недели, без фильтра по группе.
    """

    @classmethod
    def setUpTestData(cls):
        role = Role.objects.create(code='rowstudent', name='Студент', can_upload_works=True)
        cls.group = Group.objects.create(code='ИСТ-401', course=4)
        cls.other = Group.objects.create(code='ИВТ-401', course=4)
        cls.student = User.objects.create_user('rowstudent', password='demo12345')
        cls.student.profile.role = role
        cls.student.profile.group = cls.group
        cls.student.profile.save()
        # своя группа — пары 1 и 2, соседняя — 5: строка 5 должна остаться
        Lesson.objects.create(group=cls.group, weekday=1, pair=1, week='all', subject='Математика')
        Lesson.objects.create(group=cls.group, weekday=2, pair=2, week='all', subject='Физика')
        Lesson.objects.create(group=cls.other, weekday=3, pair=5, week='all', subject='Химия')

    @staticmethod
    def pair_rows(html):
        import re

        return [int(n) for n in re.findall(
            r'<div class="sched-cell sched-cell--time[^"]*">\s*<b>(\d+)</b>', html,
        )]

    def test_empty_pairs_have_no_rows(self):
        """Пары 1..5: 6-й нет ни у кого, поэтому строки «6» и её ячеек нет."""
        self.client.force_login(self.student)
        response = self.client.get(reverse('schedule:schedule'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertEqual(self.pair_rows(html), [1, 2, 3, 4, 5])
        self.assertEqual(len(response.context['grid']), 5)
        self.assertEqual(response.context['max_pair'], 5)
        # сетка получает фактическое число строк-пар, а не константу 6
        self.assertIn('style="--pairs: 5"', html)
        self.assertNotIn('<b>6</b>', html)

    def test_row_returns_when_any_group_has_the_pair(self):
        """Пара 6 есть у соседней группы — строка 6 появляется («ни у кого» = все группы)."""
        Lesson.objects.create(group=self.other, weekday=4, pair=6, week='all', subject='Информатика')
        self.client.force_login(self.student)
        response = self.client.get(reverse('schedule:schedule'))
        html = response.content.decode()
        self.assertEqual(self.pair_rows(html), [1, 2, 3, 4, 5, 6])
        self.assertIn('style="--pairs: 6"', html)
        self.assertIn('<b>6</b>', html)

    def test_pair_of_other_week_does_not_add_row(self):
        """Пара 6 только в нечётной неделе не создаёт строку в чётной."""
        Lesson.objects.create(group=self.other, weekday=4, pair=6, week='odd', subject='Информатика')
        self.client.force_login(self.student)
        response = self.client.get(reverse('schedule:schedule'), {'week': '12'})  # чётная
        html = response.content.decode()
        self.assertEqual(self.pair_rows(html), [1, 2, 3, 4, 5])
        self.assertNotIn('<b>6</b>', html)

    def test_no_data_renders_empty_state_without_table(self):
        """Нет занятий вообще — пустое состояние, таблица не падает и не рисуется."""
        empty = Group.objects.create(code='ИСТ-499', course=4)
        self.student.profile.group = empty
        self.student.profile.save()
        self.client.force_login(self.student)
        response = self.client.get(reverse('schedule:schedule'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('занятий нет', html)
        self.assertNotIn('class="sched-table"', html)
