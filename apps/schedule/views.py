"""Просмотр расписания и импорт файла с сайта БГИТУ."""
import os
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files import File
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.permissions import role_can, role_required
from apps.education.curriculum import plan_code_for_group, resolve_curriculum
from apps.education.models import Group, PlanSource

from .models import Bell, Lesson, ScheduleImport
from .services import (
    SEMESTER_WEEKS,
    detect_institute,
    parity_of_monday,
    resolve_lessons,
    run_import,
    semester_monday,
    semester_week_of,
    visible_lessons,
)

BGITU_SOURCE = 'https://bgitu.ru/studentu/raspisanie/ochnoe-obuchenie/'
DAY_SHORT = ['', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб']
DAY_FULL = ['', 'Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']

PROGRAM_SEMESTERS = 8  # семестров в программе бакалавриата


def current_program_semester(course, today=None):
    """Номер семестра программы: курс 2, осень → 3-й семестр."""
    if not course:
        return None
    today = today or date.today()
    autumn = today.month in (9, 10, 11, 12, 1)
    offset = 1 if autumn else 2
    return min(PROGRAM_SEMESTERS, (course - 1) * 2 + offset)


SUBGROUP_ALIASES = {'1': 'а', '2': 'б'}


def subgroup_code(value):
    """Подгруппа в одном виде: «1»/«2» из файла = «а»/«б» в интерфейсе."""
    value = (value or '').strip().lower()
    return SUBGROUP_ALIASES.get(value, value)


def division_subgroups(lessons):
    """Подгруппы группы, если в данных есть обе метки «а» и «б».

    Метки проставляет только парсер и только для групп, у которых в шапке
    файла есть подстолбцы «а»/«б». Поэтому наличие обеих меток — достаточный
    признак деления, даже если в конкретном слоте подгруппы учатся в разные
    недели.
    """
    present = sorted({
        subgroup_code(lesson.subgroup) for lesson in lessons if subgroup_code(lesson.subgroup)
    })
    return present if len(present) >= 2 else []


@login_required
def schedule_view(request):
    profile = getattr(request.user, 'profile', None)
    can_choose = role_can(request.user, 'can_manage_schedule') or role_can(request.user, 'can_view_all')
    groups = Group.objects.all()
    group = profile.group if profile else None
    if can_choose and request.GET.get('group'):
        group = groups.filter(code=request.GET['group']).first() or group
    if group is None and can_choose:
        group = groups.first()

    # Номер семестровой недели: ?week=N, зажатый в границы семестра.
    # ?week=odd|even — явная чётность (кнопки/скролл без пересчёта номера):
    # берём ближайшую неделю семестра нужной чётности относительно текущей.
    current_week = semester_week_of(date.today())
    raw_week = (request.GET.get('week') or '').strip().lower()
    explicit_parity = raw_week if raw_week in (Lesson.WEEK_ODD, Lesson.WEEK_EVEN) else ''
    # ?parity= — то же самое для ссылок, которые сохраняют номер недели.
    if not explicit_parity:
        wanted = (request.GET.get('parity') or '').strip().lower()
        explicit_parity = wanted if wanted in (Lesson.WEEK_ODD, Lesson.WEEK_EVEN) else ''
    if explicit_parity:
        base = max(1, min(SEMESTER_WEEKS, current_week))
        week = base if parity_of_monday(semester_monday(base)) == explicit_parity else base + 1
        week = max(1, min(SEMESTER_WEEKS, week))
    else:
        try:
            week = int(raw_week or current_week)
        except (TypeError, ValueError):
            week = current_week
        week = max(1, min(SEMESTER_WEEKS, week))
    direction = request.GET.get('dir')
    if direction not in ('next', 'prev'):
        direction = ''

    monday = semester_monday(week)
    sunday = monday + timedelta(days=6)
    # Чётность определяется по КАЛЕНДАРЮ выбранной недели: листание недель
    # само решает, показывать расписание нечётной или чётной недели.
    parity = parity_of_monday(monday)
    week_label = 'нечётная' if parity == 'odd' else 'чётная'
    is_current = week == current_week

    # Подгруппа: ?sub= → сохранённый выбор в профиле → «без подгруппы».
    lessons = []
    subgroups = []
    subgroups_by_day = {}
    # ?sub= — подгруппа; ?sub=odd|even сюда не попадает (это чётность недели).
    sub = subgroup_code(request.GET.get('sub'))
    if sub in (Lesson.WEEK_ODD, Lesson.WEEK_EVEN):
        sub = ''
    saved_sub = subgroup_code(profile.subgroup) if profile else ''
    has_parity = False
    has_subgroups = False
    if group:
        # Выборка с приоритетом: если несколько файлов дают занятие в одном
        # слоте (группа/день/пара/подгруппа), видно занятие самого свежего файла.
        all_lessons = visible_lessons(group)
        has_parity = any(item.week != Lesson.WEEK_ALL for item in all_lessons)
        # Пилюли выбора и метки подгрупп — только если в данных ЭТОЙ группы
        # есть обе метки «а»/«б» (парсер ставит их лишь для групп с
        # подстолбцами а/б в шапке файла).
        subgroups = division_subgroups(all_lessons)
        has_subgroups = bool(subgroups)
        # Если у группы нет деления (или выбранной подгруппы в ней нет),
        # сохранённый выбор профиля игнорируется — показываем всю группу.
        if sub not in subgroups:
            sub = saved_sub if saved_sub in subgroups else ''
        # В ячейке показываем оба недельных варианта пары, поэтому фильтр
        # по чётности здесь не применяется: он нужен только для шапки/дат.
        lessons = list(all_lessons)
        if sub:
            lessons = [item for item in lessons if subgroup_code(item.subgroup) in ('', sub)]
        if has_subgroups:
            for item in lessons:
                code = subgroup_code(item.subgroup)
                if code:
                    subgroups_by_day.setdefault(item.weekday, set()).add(code)
            subgroups_by_day = {day: sorted(values) for day, values in subgroups_by_day.items()}
    # Звонки по корпусам: время пары зависит от корпуса занятия (1-й/2-й).
    bells = {(bell.building, bell.pair): bell for bell in Bell.objects.all()}

    # Таблица: строки — пары, колонки — дни недели. Ячейка показывает ОБА
    # варианта пары: верхняя половина — 1-я неделя, нижняя — 2-я. Общая
    # (объединённая) ячейка — одна карточка без деления. Если у «а» и «б»
    # РАЗНЫЕ пары, половина недели делится ещё и пополам: слева «а», справа «б».
    by_cell = {}
    for lesson in lessons:
        by_cell.setdefault((lesson.weekday, lesson.pair), []).append(lesson)

    def row_lessons(week, items):
        """Карточки одной половины: общая — одна, иначе по подгруппам."""
        common = [item for item in items if not subgroup_code(item.subgroup)]
        if common:
            exact = next((item for item in common if item.week == week), None)
            return [exact or common[0]]
        by_subgroup = {}
        for item in items:
            code = subgroup_code(item.subgroup)
            current = by_subgroup.get(code)
            # Точная неделя важнее «каждой недели» для той же подгруппы.
            if current is None or (current.week == Lesson.WEEK_ALL and item.week != Lesson.WEEK_ALL):
                by_subgroup[code] = item
        return [by_subgroup[code] for code in sorted(by_subgroup)]

    def build_cell(items):
        if not items:
            return {'rows': [], 'split': False, 'has_weeks': False, 'week': Lesson.WEEK_ALL}
        specific = sorted({item.week for item in items if item.week != Lesson.WEEK_ALL})
        if not specific:
            rows = [{'week': Lesson.WEEK_ALL, 'lessons': row_lessons(Lesson.WEEK_ALL, items)}]
        elif len(specific) == 1:
            rows = [{'week': specific[0], 'lessons': row_lessons(specific[0], items)}]
        else:
            rows = [
                {'week': week, 'lessons': row_lessons(week, items)}
                for week in (Lesson.WEEK_ODD, Lesson.WEEK_EVEN)
            ]
        for half in rows:
            half['split'] = len(half['lessons']) > 1
            half['is_current'] = half['week'] == parity
        return {
            'rows': rows,
            'split': any(half['split'] for half in rows),
            'has_weeks': len(rows) > 1,
            'week': rows[0]['week'] if len(rows) == 1 else Lesson.WEEK_ALL,
        }

    # Число строк таблицы — из данных: последняя пара, на которой есть занятие
    # у любой группы в выбранную неделю, плюс пары выбранной группы из второй
    # недели (её ячейки показывают оба варианта). Приоритет источников тот же.
    week_pool = resolve_lessons(
        Lesson.objects.select_related('source').filter(week__in=[Lesson.WEEK_ALL, parity])
    )
    week_max = max((item.pair for item in week_pool), default=0)
    group_max = max((item.pair for item in lessons), default=0)
    max_pair = max(week_max, group_max)
    pairs = range(1, max_pair + 1) if max_pair else range(0)

    grid = []
    for pair in pairs:
        days = []
        for weekday in range(1, 7):
            cell = build_cell(by_cell.get((weekday, pair), []))
            for half in cell['rows']:
                for item in half['lessons']:
                    bell = bells.get((item.building or '2', pair)) or bells.get(('2', pair))
                    item.time_label = f'{bell.start}–{bell.end}' if bell else ''
            cell['is_today'] = monday + timedelta(days=weekday - 1) == date.today()
            days.append(cell)
        grid.append({'pair': pair, 'days': days})

    days_header = []
    for weekday in range(1, 7):
        day = monday + timedelta(days=weekday - 1)
        days_header.append({
            'short': DAY_SHORT[weekday],
            'full': DAY_FULL[weekday],
            'date': day,
            'is_today': day == date.today(),
            'subgroups': subgroups_by_day.get(weekday, []),
        })

    # Ссылки недель и подгрупп несут группу — переключение не сбрасывает выбор.
    group_qs = f'&group={group.code}' if can_choose and group else ''
    week_links = {
        'prev': f'?week={week - 1}{group_qs}&dir=prev' if week > 1 else '',
        'next': f'?week={week + 1}{group_qs}&dir=next' if week < SEMESTER_WEEKS else '',
    }
    # Явный выбор недели в выпадашке: ?parity=odd|even сохраняет группу и подгруппу.
    parity_query = f'{group_qs}&sub={sub}' if sub else group_qs
    parity_links = {}
    for value, monday_of in (
        (Lesson.WEEK_ODD, next((semester_monday(n) for n in range(1, SEMESTER_WEEKS + 1)
                                if parity_of_monday(semester_monday(n)) == Lesson.WEEK_ODD), None)),
        (Lesson.WEEK_EVEN, next((semester_monday(n) for n in range(1, SEMESTER_WEEKS + 1)
                                 if parity_of_monday(semester_monday(n)) == Lesson.WEEK_EVEN), None)),
    ):
        number = semester_week_of(monday_of) if monday_of else 1
        parity_links[value] = f'?week={number}{parity_query}'
    sub_links = {'all': f'?week={week}{group_qs}'}
    for item in subgroups:
        sub_links[item] = f'?week={week}{group_qs}&sub={item}'
    no_lessons = bool(group) and not lessons

    # Учебный план: все дисциплины программы и семестры, где они читаются.
    # Направление — из Group.program (09.03.02 → ist), иначе префикс группы.
    direction_code = plan_code_for_group(group) if group else ''
    curriculum = resolve_curriculum(direction_code) if direction_code else []
    program_semester = current_program_semester(group.course if group else None) if direction_code else None

    sources = list(ScheduleImport.objects.select_related('imported_by').order_by('-imported_at'))
    latest = sources[0] if sources else None
    plan_sources = list(PlanSource.objects.select_related('uploaded_by').order_by('-uploaded_at'))
    latest_plan = plan_sources[0] if plan_sources else None
    return render(request, 'schedule/schedule.html', {
        'group': group,
        'groups': groups,
        'can_choose_group': can_choose,
        'week': week,
        'week_label': week_label,
        'parity': parity,
        'has_parity': has_parity,
        'week_links': week_links,
        'parity_links': parity_links,
        'parity_odd': Lesson.WEEK_ODD,
        'parity_even': Lesson.WEEK_EVEN,
        'monday': monday,
        'sunday': sunday,
        'is_current': is_current,
        'direction': direction,
        'program_semesters': range(1, PROGRAM_SEMESTERS + 1),
        'program_semester': program_semester,
        'current_week': current_week,
        'days_header': days_header,
        'grid': grid,
        'pairs': pairs,
        'max_pair': max_pair,
        'curriculum': curriculum,
        'latest_import': latest,
        'sources': sources,
        'plan_sources': plan_sources,
        'latest_plan': latest_plan,
        'subgroups': subgroups,
        'has_subgroups': has_subgroups,
        'sub': sub,
        'sub_links': sub_links,
        'no_lessons': no_lessons,
        'can_import': role_can(request.user, 'can_manage_schedule') or role_can(request.user, 'can_view_all'),
    })


MAX_UPLOAD_SIZE = 15 * 1024 * 1024


def schedule_redirect(group_code=''):
    url = reverse('schedule:schedule')
    return f'{url}?group={group_code}' if group_code else url


@login_required
@role_required('can_manage_schedule')
def import_view(request):
    """Загрузка нескольких файлов расписания сразу.

    Каждый файл — отдельный источник занятий. Файлы разных институтов
    сохраняются рядом; повторная загрузка файла того же охвата заменяет
    занятия предыдущего (см. services.run_import).
    """
    if request.method == 'POST':
        uploads = request.FILES.getlist('file')
        if not uploads:
            messages.error(request, 'Выберите файлы расписания (.xls или .xlsx).')
            return redirect('schedule:import')

        group_code = request.POST.get('group', '')
        source_url = request.POST.get('source_url', BGITU_SOURCE).strip() or BGITU_SOURCE
        imported, errors, total_lessons = [], [], 0

        for upload in uploads:
            extension = os.path.splitext(upload.name)[1].lower()
            if extension not in ('.xls', '.xlsx'):
                errors.append(f'{upload.name}: поддерживаются только .xls и .xlsx.')
                continue
            if upload.size > MAX_UPLOAD_SIZE:
                errors.append(f'{upload.name}: файл больше 15 МБ.')
                continue
            record = ScheduleImport.objects.create(
                file=upload,
                original_name=upload.name[:255],
                institute=detect_institute(upload.name),
                size=upload.size,
                source_url=source_url,
                imported_by=request.user,
            )
            try:
                run_import(record, source_url=source_url)
            except Exception as exc:  # один битый файл не отменяет остальные
                record.note = f'ошибка импорта: {exc}'[:255]
                record.save(update_fields=['note'])
                errors.append(f'{upload.name}: не удалось разобрать файл — {exc}')
                continue
            imported.append(record)
            total_lessons += record.lessons_count

        if imported:
            names = ', '.join(item.institute or item.original_name for item in imported)
            messages.success(
                request,
                f'Загружено файлов: {len(imported)} · занятий: {total_lessons} ({names}).',
            )
        for error in errors:
            messages.error(request, error)
        return redirect(schedule_redirect(group_code))

    return render(request, 'schedule/import.html', {
        'imports': ScheduleImport.objects.select_related('imported_by')[:20],
        'source_url': BGITU_SOURCE,
    })


@login_required
@require_POST
@role_required('can_manage_schedule')
def delete_source(request, pk):
    """Удалить загруженный файл вместе со всеми его занятиями."""
    record = get_object_or_404(ScheduleImport, pk=pk)
    name = record.original_name
    with transaction.atomic():
        Lesson.objects.filter(source=record).delete()
        record.delete()
    messages.success(request, f'Файл «{name}» удалён вместе с занятиями.')
    return redirect(schedule_redirect(request.POST.get('group', '')))


@login_required
@require_POST
@role_required('can_manage_schedule')
def import_from_server_file(request):
    """Импорт приложенного в проект файла БГИТУ (для демо/первичной заливки)."""
    from django.conf import settings

    path = request.POST.get('path', '')
    allowed_root = (settings.BASE_DIR / 'fixtures' / 'schedule').resolve()
    full_path = (settings.BASE_DIR / path).resolve()
    # Только файлы расписания внутри fixtures/schedule — без выхода за пределы папки.
    if not path or os.path.isabs(path) or not full_path.is_relative_to(allowed_root):
        messages.error(request, 'Некорректный путь к файлу.')
        return redirect('schedule:import')
    if full_path.suffix.lower() not in ('.xls', '.xlsx'):
        messages.error(request, 'Поддерживаются только .xls и .xlsx.')
        return redirect('schedule:import')
    if not full_path.is_file():
        messages.error(request, 'Файл не найден.')
        return redirect('schedule:import')
    with full_path.open('rb') as handle:
        record = ScheduleImport(
            original_name=full_path.name,
            source_url=BGITU_SOURCE,
            imported_by=request.user,
        )
        record.file.save(full_path.name, File(handle), save=True)
    try:
        run_import(record, source_url=BGITU_SOURCE)
    except ValueError as exc:
        record.note = f'ошибка импорта: {exc}'[:255]
        record.save(update_fields=['note'])
        messages.error(request, f'Не удалось разобрать файл: {exc}')
        return redirect('schedule:import')
    messages.success(request, f'Импортировано занятий: {record.lessons_count}.')
    return redirect('schedule:schedule')
