"""Просмотр расписания и импорт файла с сайта БГИТУ."""
import os
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files import File
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.permissions import role_can, role_required
from apps.education.models import Group

from .import_service import WEEKDAYS
from .models import Bell, Lesson, ScheduleImport
from .services import run_import

BGITU_SOURCE = 'https://bgitu.ru/studentu/raspisanie/ochnoe-obuchenie/'
DAY_SHORT = ['', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб']


def current_parity():
    return 'odd' if date.today().isocalendar()[1] % 2 else 'even'


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

    week = request.GET.get('week')
    if week not in ('odd', 'even'):
        week = current_parity()
    week_label = 'нечётная' if week == 'odd' else 'чётная'

    lessons = []
    if group:
        lessons = list(
            Lesson.objects.filter(group=group, week__in=['all', week])
            .select_related('source')
            .order_by('weekday', 'pair', 'subgroup')
        )
    bells = {b.pair: b for b in Bell.objects.filter(building='2')}

    days = []
    today = date.today()
    for weekday in range(1, 7):
        day_lessons = [lesson for lesson in lessons if lesson.weekday == weekday]
        days.append({
            'n': weekday,
            'name': DAY_SHORT[weekday],
            'full': list(WEEKDAYS.keys())[weekday - 1],
            'is_today': today.weekday() + 1 == weekday and week == current_parity(),
            'lessons': [
                {
                    'lesson': lesson,
                    'time': (bells.get(lesson.pair).start if bells.get(lesson.pair) else ''),
                }
                for lesson in day_lessons
            ],
        })
    latest = ScheduleImport.objects.order_by('-imported_at').first()
    return render(request, 'schedule/schedule.html', {
        'group': group,
        'groups': groups,
        'can_choose_group': can_choose,
        'week': week,
        'week_label': week_label,
        'week_number': today.isocalendar()[1],
        'days': days,
        'bells': [bells[p] for p in sorted(bells)],
        'latest_import': latest,
    })


@login_required
@role_required('can_manage_schedule')
def import_view(request):
    if request.method == 'POST':
        upload = request.FILES.get('file')
        if upload is None:
            messages.error(request, 'Выберите файл расписания (.xls или .xlsx).')
            return redirect('schedule:import')
        ext = os.path.splitext(upload.name)[1].lower()
        if ext not in ('.xls', '.xlsx'):
            messages.error(request, 'Поддерживаются только .xls и .xlsx.')
            return redirect('schedule:import')
        if upload.size > 15 * 1024 * 1024:
            messages.error(request, 'Файл больше 15 МБ.')
            return redirect('schedule:import')
        record = ScheduleImport.objects.create(
            file=upload,
            original_name=upload.name,
            source_url=request.POST.get('source_url', BGITU_SOURCE).strip() or BGITU_SOURCE,
            imported_by=request.user,
        )
        try:
            run_import(record, source_url=record.source_url)
        except ValueError as exc:
            record.note = f'ошибка импорта: {exc}'[:255]
            record.save(update_fields=['note'])
            messages.error(request, f'Не удалось разобрать файл: {exc}')
            return redirect('schedule:import')
        messages.success(
            request,
            f'Импортировано занятий: {record.lessons_count}, групп: {record.groups_count}.',
        )
        return redirect('schedule:schedule')

    return render(request, 'schedule/import.html', {
        'imports': ScheduleImport.objects.select_related('imported_by')[:20],
        'source_url': BGITU_SOURCE,
    })


@login_required
@require_POST
@role_required('can_manage_schedule')
def import_from_server_file(request):
    """Импорт приложенного в проект файла БГИТУ (для демо/первичной заливки)."""
    path = request.POST.get('path', '')
    if os.path.isabs(path) or '..' in path:
        messages.error(request, 'Некорректный путь к файлу.')
        return redirect('schedule:import')
    from django.conf import settings

    full_path = settings.BASE_DIR / path
    if not full_path.exists():
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
