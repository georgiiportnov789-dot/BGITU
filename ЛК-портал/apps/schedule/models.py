"""Расписание: звонки, занятия, импорт файла с сайта БГИТУ."""
from django.conf import settings
from django.db import models


class Bell(models.Model):
    building = models.CharField('корпус', max_length=8, default='2')
    pair = models.PositiveSmallIntegerField('пара')
    start = models.CharField('начало', max_length=8)
    end = models.CharField('конец', max_length=8)

    class Meta:
        verbose_name = 'звонок'
        verbose_name_plural = 'звонки'
        ordering = ['building', 'pair']
        constraints = [models.UniqueConstraint(fields=['building', 'pair'], name='uniq_bell')]

    def __str__(self):
        return f'{self.building} корпус · {self.pair} пара {self.start}–{self.end}'


class ScheduleImport(models.Model):
    file = models.FileField('файл', upload_to='schedule/%Y/%m/')
    original_name = models.CharField('имя файла', max_length=255)
    source_url = models.URLField('источник', blank=True)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='schedule_imports'
    )
    imported_at = models.DateTimeField('импортирован', auto_now_add=True)
    lessons_count = models.PositiveIntegerField('занятий', default=0)
    groups_count = models.PositiveSmallIntegerField('групп', default=0)
    note = models.CharField('примечание', max_length=255, blank=True)

    class Meta:
        verbose_name = 'импорт расписания'
        verbose_name_plural = 'импорты расписания'
        ordering = ['-imported_at']

    def __str__(self):
        return f'{self.original_name} · {self.imported_at:%d.%m.%Y}'


class Lesson(models.Model):
    WEEK_ALL = 'all'
    WEEK_ODD = 'odd'
    WEEK_EVEN = 'even'
    WEEK_CHOICES = [
        (WEEK_ALL, 'каждую неделю'),
        (WEEK_ODD, 'нечётная'),
        (WEEK_EVEN, 'чётная'),
    ]

    group = models.ForeignKey('education.Group', on_delete=models.CASCADE, related_name='lessons')
    weekday = models.PositiveSmallIntegerField('день недели')  # 1 — понедельник
    pair = models.PositiveSmallIntegerField('пара')
    week = models.CharField('неделя', max_length=8, choices=WEEK_CHOICES, default=WEEK_ALL)
    subject = models.CharField('дисциплина', max_length=180)
    kind = models.CharField('вид занятия', max_length=40, blank=True)
    teacher_name = models.CharField('преподаватель', max_length=120, blank=True)
    room = models.CharField('аудитория', max_length=40, blank=True)
    subgroup = models.CharField('подгруппа', max_length=8, blank=True)
    source = models.ForeignKey(ScheduleImport, on_delete=models.SET_NULL, null=True, blank=True, related_name='lessons')

    class Meta:
        verbose_name = 'занятие'
        verbose_name_plural = 'занятия'
        ordering = ['weekday', 'pair', 'subgroup']
        indexes = [models.Index(fields=['group', 'weekday', 'week'])]

    def __str__(self):
        return f'{self.group} · {self.subject}'

    @property
    def weekday_name(self):
        return ['', 'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота'][self.weekday]
