"""Импорт расписания БГИТУ из .xls/.xlsx."""
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from apps.schedule.models import ScheduleImport
from apps.schedule.services import run_import


class Command(BaseCommand):
    help = 'Импортирует файл расписания БГИТУ (.xls/.xlsx) в базу.'

    def add_arguments(self, parser):
        parser.add_argument('path', help='Путь к файлу расписания')
        parser.add_argument('--url', default='', help='URL источника')

    def handle(self, *args, **options):
        path = Path(options['path'])
        if not path.exists():
            raise CommandError(f'Файл не найден: {path}')
        record = ScheduleImport(original_name=path.name, source_url=options['url'])
        with path.open('rb') as handle:
            record.file.save(path.name, File(handle), save=True)
        run_import(record, source_url=options['url'])
        self.stdout.write(self.style.SUCCESS(
            f'Импортировано занятий: {record.lessons_count}, групп: {record.groups_count}.'
        ))
