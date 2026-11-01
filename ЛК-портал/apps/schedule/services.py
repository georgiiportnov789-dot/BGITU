"""Сохранение импортированного расписания в БД."""
from django.db import transaction

from apps.education.models import Group

from .import_service import parse_schedule
from .models import Bell, Lesson, ScheduleImport


def group_course(code):
    digits = ''.join(ch for ch in code if ch.isdigit())
    return int(digits[0]) if digits else 1


def run_import(record: ScheduleImport, source_url=''):
    """Разобрать файл записи и заменить занятия. Возвращает record."""
    path = record.file.path
    lessons, bells = parse_schedule(path)
    codes = sorted({item['group'] for item in lessons})

    with transaction.atomic():
        Lesson.objects.all().delete()
        groups = {}
        for code in codes:
            groups[code], _ = Group.objects.get_or_create(
                code=code,
                defaults={'course': group_course(code), 'program': '09.03.02 «Информационные системы и технологии»'},
            )
        Lesson.objects.bulk_create([
            Lesson(
                group=groups[item['group']],
                weekday=item['weekday'],
                pair=item['pair'],
                week=item['week'],
                subject=item['subject'][:180],
                kind=item['kind'][:40],
                teacher_name=item['teacher_name'][:120],
                room=item['room'][:40],
                subgroup=item['subgroup'][:8],
                source=record,
            )
            for item in lessons
        ])
        for (building, pair), (start, end) in bells.items():
            Bell.objects.update_or_create(
                building=building, pair=pair, defaults={'start': start, 'end': end}
            )
        record.lessons_count = len(lessons)
        record.groups_count = len(codes)
        record.note = 'импорт занятий из файла БГИТУ'
        if source_url:
            record.source_url = source_url
        record.save(update_fields=['lessons_count', 'groups_count', 'note', 'source_url'])
    return record
